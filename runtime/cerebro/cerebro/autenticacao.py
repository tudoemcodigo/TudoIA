"""Autenticação de /mcp e /indexar: JWT do Keycloak (client_credentials) validado localmente.

Fail-closed: sem configuração, sem chaves (JWKS inacessível) ou token inválido, nada é liberado. /saude é público
(health check, sem dados). Papéis: `tudoia-admin`, `tudoia-operador`, `tudoia-leitor`, lidos de `realm_access.roles`
ou do claim `groups` (mesma regra de `painel/tudoia_painel/autenticacao.py`).

Por que joserfc e não `authlib.jose`: o módulo `authlib.jose` está deprecado na authlib 1.9 e emite aviso a cada
importação; a própria mensagem indica o joserfc, que é a dependência dele.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import functools
import hmac
import json
import logging
import time
from collections.abc import Awaitable, Callable, Iterator
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

import httpx
from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwk import RSAKey
from joserfc.jwt import JWTClaimsRegistry

log = logging.getLogger("cerebro.auth")

PAPEL_ADMIN = "tudoia-admin"
PAPEL_OPERADOR = "tudoia-operador"
PAPEL_LEITOR = "tudoia-leitor"
PAPEIS = (PAPEL_ADMIN, PAPEL_OPERADOR, PAPEL_LEITOR)
PAPEIS_ESCRITA = (PAPEL_ADMIN, PAPEL_OPERADOR)

ENV_TOKEN_ESTATICO = "CEREBRO_TOKEN_ESTATICO"
TAMANHO_MIN_TOKEN_ESTATICO = 32  # abaixo disso o segredo é recusado (o caminho fica desligado)

ALGORITMOS = ["RS256"]  # Keycloak assina com RS256. Sem "none" e sem HS* (confusão de chave).
TAMANHO_MAX_TOKEN = 8192
TTL_CHAVES = 300  # segundos com as chaves em cache antes de reconsultar o JWKS
INTERVALO_MIN_RECARGA = 30  # kid desconhecido só dispara nova busca a cada 30 s (limita abuso)
BACKOFF_FALHA = 10  # após falha do JWKS, não tenta de novo por 10 s (não martela o Keycloak)
TIMEOUT_JWKS = 5.0
LIMITE_JWKS = 64 * 1024  # bytes; um JWKS do Keycloak tem poucos KB
LEEWAY_RELOGIO = 30  # segundos de tolerância para exp/nbf

# Papéis do token da requisição atual. Definido pelo GuardaMcp; ausente = sem autenticação (negado).
_papeis_atuais: ContextVar[frozenset[str] | None] = ContextVar("papeis_atuais", default=None)


class ErroAuth(Exception):
    def __init__(self, status: int, codigo: str, mensagem: str) -> None:
        super().__init__(mensagem)
        self.status = status
        self.codigo = codigo
        self.mensagem = mensagem


@dataclass(frozen=True)
class ConfigOidc:
    issuers: tuple[str, ...]  # `iss` aceitos, exatamente como o Keycloak os publica (um por host de acesso)
    jwks_url: str  # onde buscar as chaves (pode ser outro host, ex.: host.docker.internal)
    client_id: str  # azp e aud esperados: o cliente de serviço

    def __post_init__(self) -> None:
        # Um `str` aqui seria iterado caractere a caractere na lista de claims: normaliza para tupla.
        if isinstance(self.issuers, str):
            object.__setattr__(self, "issuers", (self.issuers,))

    @classmethod
    def do_ambiente(cls, valores: dict[str, str]) -> ConfigOidc | None:
        """None quando faltar qualquer campo ou a URL não for http(s): o servidor então nega /mcp e /indexar."""
        # Um realm pode ser alcançado por mais de um host (localhost no host, host.docker.internal nos containers).
        # O Keycloak põe no `iss` o host usado na requisição do token, então aceitamos todos os informados.
        issuers = tuple(i.strip().rstrip("/") for i in (valores.get("CEREBRO_OIDC_ISSUER") or "").split(",") if i.strip())
        jwks = (valores.get("CEREBRO_OIDC_JWKS_URL") or "").strip()
        cliente = (valores.get("CEREBRO_OIDC_CLIENT_ID") or "").strip()
        if not issuers or not all(i.startswith(("http://", "https://")) for i in issuers):
            return None
        if not (jwks.startswith(("http://", "https://")) and cliente):
            return None
        return cls(issuers=issuers, jwks_url=jwks, client_id=cliente)


def papeis_do_token(claims: dict[str, Any]) -> list[str]:
    """Papéis do Cérebro presentes no token. Aceita grupo com caminho (/tudoia-admin) e papel de realm."""
    grupos = claims.get("groups") or []
    realm = (claims.get("realm_access") or {}).get("roles") or []
    candidatos = {str(x).strip().lstrip("/") for x in [*grupos, *realm] if isinstance(x, str)}
    return [p for p in PAPEIS if p in candidatos]


def extrair_bearer(cabecalhos: list[tuple[bytes, bytes]]) -> str:
    """Token do cabeçalho Authorization. Mais de um cabeçalho, esquema diferente de Bearer ou vazio = 401."""
    valores = [v for k, v in cabecalhos if k.lower() == b"authorization"]
    if not valores:
        raise ErroAuth(401, "token_ausente", "envie Authorization: Bearer <token>")
    if len(valores) > 1:
        raise ErroAuth(401, "token_invalido", "cabeçalho Authorization repetido")
    try:
        texto = valores[0].decode("ascii")
    except UnicodeDecodeError:
        raise ErroAuth(401, "token_invalido", "cabeçalho Authorization inválido") from None
    esquema, _, token = texto.partition(" ")
    if esquema.lower() != "bearer" or not token or len(token) > TAMANHO_MAX_TOKEN:
        raise ErroAuth(401, "token_invalido", "envie Authorization: Bearer <token>")
    return token


def _cabecalho_jwt(token: str) -> dict[str, Any]:
    """Lê o cabeçalho sem verificar nada (só para escolher a chave). A verificação é feita por `jwt.decode`."""
    try:
        bruto = token.split(".")[0]
        bruto += "=" * (-len(bruto) % 4)
        cabecalho = json.loads(base64.urlsafe_b64decode(bruto))
    except (ValueError, json.JSONDecodeError):
        raise ErroAuth(401, "token_invalido", "token mal formado") from None
    if not isinstance(cabecalho, dict):
        raise ErroAuth(401, "token_invalido", "token mal formado")
    return cabecalho


class Verificador:
    """Valida JWT contra as chaves públicas do issuer. Cache com recarga limitada; falha do JWKS = 503."""

    def __init__(
        self,
        config: ConfigOidc,
        buscar_jwks: Callable[[], Awaitable[dict[str, Any]]] | None = None,
        relogio: Callable[[], float] = time.monotonic,
        agora: Callable[[], float] = time.time,
    ) -> None:
        self._config = config
        self._buscar = buscar_jwks or self._buscar_http
        self._relogio = relogio
        self._agora = agora
        self._chaves: dict[str, RSAKey] | None = None
        self._buscada_em = 0.0
        self._falha_ate = 0.0
        self._trava = asyncio.Lock()
        self._registro = JWTClaimsRegistry(
            leeway=LEEWAY_RELOGIO,
            iss={"essential": True, "values": list(config.issuers)},
            exp={"essential": True},
            azp={"essential": True, "value": config.client_id},
            aud={"essential": True, "value": config.client_id},
        )

    async def _buscar_http(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=TIMEOUT_JWKS, follow_redirects=False) as cliente:
            async with cliente.stream("GET", self._config.jwks_url) as resp:
                if resp.status_code != 200:
                    raise ValueError(f"JWKS HTTP {resp.status_code}")
                corpo = bytearray()
                async for pedaco in resp.aiter_bytes():
                    corpo += pedaco
                    if len(corpo) > LIMITE_JWKS:
                        raise ValueError("JWKS acima do limite")
        return json.loads(bytes(corpo))

    def _montar_chaves(self, dados: dict[str, Any]) -> dict[str, RSAKey]:
        chaves: dict[str, RSAKey] = {}
        for item in dados.get("keys", []):
            if not isinstance(item, dict) or item.get("kty") != "RSA" or item.get("use", "sig") != "sig":
                continue
            kid = item.get("kid")
            if isinstance(kid, str) and kid:
                chaves[kid] = RSAKey.import_key(item)
        if not chaves:
            raise ValueError("JWKS sem chaves RSA de assinatura")
        return chaves

    async def _recarregar(self) -> None:
        agora = self._relogio()
        if agora < self._falha_ate:
            raise ErroAuth(503, "chaves_indisponiveis", "chaves de verificação indisponíveis")
        try:
            self._chaves = self._montar_chaves(await self._buscar())
            self._buscada_em = self._relogio()
        except Exception as exc:  # qualquer falha (rede, JSON, tamanho, formato) fecha a porta
            self._falha_ate = self._relogio() + BACKOFF_FALHA
            log.warning("JWKS indisponível (%s)", exc.__class__.__name__)
            raise ErroAuth(503, "chaves_indisponiveis", "chaves de verificação indisponíveis") from None

    async def _chave(self, kid: str) -> RSAKey:
        async with self._trava:
            agora = self._relogio()
            expirou = self._chaves is None or agora - self._buscada_em > TTL_CHAVES
            desconhecida = self._chaves is not None and kid not in self._chaves and (
                agora - self._buscada_em > INTERVALO_MIN_RECARGA
            )
            if expirou or desconhecida:
                await self._recarregar()
        chave = (self._chaves or {}).get(kid)
        if chave is None:
            raise ErroAuth(401, "token_invalido", "chave de assinatura desconhecida")
        return chave

    async def validar(self, token: str) -> dict[str, Any]:
        """Claims do token. Lança ErroAuth (401 para token ruim, 503 quando as chaves não podem ser obtidas)."""
        if len(token) > TAMANHO_MAX_TOKEN:
            raise ErroAuth(401, "token_invalido", "token grande demais")
        cabecalho = _cabecalho_jwt(token)
        if cabecalho.get("alg") not in ALGORITMOS:
            raise ErroAuth(401, "token_invalido", "algoritmo de assinatura não aceito")
        kid = cabecalho.get("kid")
        if not isinstance(kid, str) or not kid:
            raise ErroAuth(401, "token_invalido", "token sem kid")
        chave = await self._chave(kid)
        try:
            tok = jwt.decode(token, chave, algorithms=ALGORITMOS)
            self._registro.validate(tok.claims)
        except JoseError:
            raise ErroAuth(401, "token_invalido", "token recusado") from None
        except (ValueError, TypeError, KeyError):
            raise ErroAuth(401, "token_invalido", "token recusado") from None
        return dict(tok.claims)


def token_estatico_do_ambiente(valores: dict[str, str]) -> str | None:
    """Segredo do token sem expiração (papel de operador). None quando ausente ou curto: o caminho fica desligado."""
    segredo = (valores.get(ENV_TOKEN_ESTATICO) or "").strip()
    return segredo if len(segredo) >= TAMANHO_MIN_TOKEN_ESTATICO else None


async def autenticar(
    verificador: Verificador | None, cabecalhos: list[tuple[bytes, bytes]], estatico: str | None = None
) -> list[str]:
    """Papéis do token (lista não vazia) ou ErroAuth. Sem verificador configurado, nega (fail-closed).

    Token estático: comparado em tempo constante, antes do JWT. Se não bater, cai na validação JWT normal.
    """
    token = extrair_bearer(cabecalhos)
    if estatico is not None and hmac.compare_digest(token.encode("utf-8"), estatico.encode("utf-8")):
        return [PAPEL_OPERADOR]
    if verificador is None:
        raise ErroAuth(503, "auth_nao_configurada", "autenticação não configurada: defina CEREBRO_OIDC_*")
    claims = await verificador.validar(token)
    papeis = papeis_do_token(claims)
    if not papeis:
        raise ErroAuth(403, "papel_insuficiente", f"sua conta não tem nenhum papel do Cérebro ({', '.join(PAPEIS)})")
    return papeis


@contextlib.contextmanager
def autorizado(papeis: list[str] | tuple[str, ...] | frozenset[str]) -> Iterator[None]:
    """Define os papéis da requisição (uso do GuardaMcp e dos testes)."""
    marca = _papeis_atuais.set(frozenset(papeis))
    try:
        yield
    finally:
        _papeis_atuais.reset(marca)


def exigir(*aceitos: str) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """Decorador de ferramenta MCP: sem papel aceito (ou sem contexto de autenticação) devolve erro, sem executar."""

    def decorador(funcao: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @functools.wraps(funcao)
        async def envolvida(*args: Any, **kwargs: Any) -> Any:
            papeis = _papeis_atuais.get()
            if papeis is None or not (papeis & set(aceitos)):
                motivo = "sem_autenticacao" if papeis is None else "papel_insuficiente"
                log.warning("ferramenta negada ferramenta=%s motivo=%s", funcao.__name__, motivo)
                return {"erro": f"esta ferramenta exige um destes papéis: {', '.join(aceitos)}"}
            return await funcao(*args, **kwargs)

        return envolvida

    return decorador


class GuardaMcp:
    """Middleware ASGI. /saude passa livre; /indexar exige papel de escrita; o resto exige qualquer papel."""

    def __init__(self, app: Any, verificador: Verificador | None, estatico: str | None = None) -> None:
        self.app = app
        self.verificador = verificador
        self.estatico = estatico

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] == "lifespan" or (scope["type"] == "http" and scope.get("path") == "/saude"):
            return await self.app(scope, receive, send)
        if scope["type"] != "http":
            return  # websocket etc.: o Cérebro não expõe nenhum; recusa calada
        escrita = scope.get("path") == "/indexar"
        try:
            papeis = await autenticar(self.verificador, scope.get("headers") or [], self.estatico)
            if escrita and not set(papeis) & set(PAPEIS_ESCRITA):
                raise ErroAuth(403, "papel_insuficiente", f"esta rota exige {PAPEL_OPERADOR} ou {PAPEL_ADMIN}")
        except ErroAuth as erro:
            # só o código do motivo; token e cabeçalhos nunca entram no log. %r neutraliza quebra de linha no path.
            log.warning("auth negada rota=%r status=%d motivo=%s", scope.get("path"), erro.status, erro.codigo)
            return await _responder_erro(send, erro)
        with autorizado(papeis):
            return await self.app(scope, receive, send)


async def _responder_erro(send: Any, erro: ErroAuth) -> None:
    corpo = json.dumps({"erro": erro.mensagem, "codigo": erro.codigo}, ensure_ascii=False).encode("utf-8")
    cabecalhos = [(b"content-type", b"application/json"), (b"content-length", str(len(corpo)).encode()),
                  (b"cache-control", b"no-store")]
    if erro.status == 401:
        cabecalhos.append((b"www-authenticate", b'Bearer error="invalid_token"'))
    await send({"type": "http.response.start", "status": erro.status, "headers": cabecalhos})
    await send({"type": "http.response.body", "body": corpo})

"""Autenticação do painel: OpenID Connect (Authorization Code + PKCE S256) contra qualquer IdP OIDC.

O painel só fala OIDC com um issuer. Quem decide o provedor de identidade (Keycloak local, Keycloak com
brokering para Microsoft Entra ID, Google, etc.) é o realm desse issuer. Para trocar de IdP, troque o issuer
e o client; o código do painel não muda.

Papéis (vindos do claim `groups` ou de `realm_access.roles`):
- tudoia-admin: tudo, inclusive segredos, provedores e importação de skills (execução de código).
- tudoia-operador: lê e altera o que não é administrativo.
- tudoia-leitor: só leitura.

Fail-closed: sem configuração OIDC, toda rota /api responde 503 e nada é liberado.
"""
import asyncio
import base64
import json
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlencode

import httpx
from authlib.integrations.base_client.errors import OAuthError
from joserfc import jwt as jose_jwt
from joserfc.jwk import KeySet
from authlib.integrations.starlette_client import OAuth
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.datastructures import Headers
from starlette.middleware.sessions import SessionMiddleware

from .auditoria import Auditoria
from .contexto import porta_do_painel
from .envfile import gravar_valor, ler_env
from .erros import corpo_erro
from .seguranca import checar

PAPEL_ADMIN = "tudoia-admin"
PAPEL_OPERADOR = "tudoia-operador"
PAPEL_LEITOR = "tudoia-leitor"
PAPEIS = (PAPEL_ADMIN, PAPEL_OPERADOR, PAPEL_LEITOR)

# Rotas que só o papel admin acessa, em qualquer método.
PREFIXOS_SO_ADMIN = (
    "/api/segredos",
    "/api/provedores",
    "/api/governanca/skills/importar",   # executa `npx` com repositório externo
    "/api/governanca/mcp",
    "/api/modelos/local/baixar",
)
# Rotas que qualquer papel lê, mas só o admin altera. Governança grava regras e skills que todo agente de IA executa
# como instrução, e o sync grava tokens de MCP em claro nas pastas das instâncias: é poder de admin.
PREFIXOS_ESCRITA_SO_ADMIN = (
    "/api/governanca",
)
METODOS_SEGUROS = {"GET", "HEAD", "OPTIONS"}
IDADE_MAXIMA_SESSAO = 8 * 3600
# A conta é reconfirmada no Keycloak no máximo a cada 30 s por sessão (desativação e troca de papel valem logo).
TTL_REVALIDACAO_S = 30
_AUTO = object()  # sentinela: ler a configuração do .env (padrão de criar_app)
CHAVES = {
    "issuer": "TUDOIA_OIDC_ISSUER",
    "client_id": "TUDOIA_OIDC_CLIENT_ID",
    "client_secret": "TUDOIA_OIDC_CLIENT_SECRET",
    "scope": "TUDOIA_OIDC_SCOPE",
    "cookie_seguro": "TUDOIA_COOKIE_SEGURO",
    "segredo_sessao": "TUDOIA_SESSAO_SEGREDO",
    "bearer_clientes": "TUDOIA_API_BEARER_CLIENTES",
}
# Algoritmo aceito para token de API. Fixo: nunca aceitar "none" nem algoritmo escolhido pelo token.
ALGORITMOS_JWT = ["RS256"]
TTL_JWKS_S = 600
# kid desconhecido (rotação de chaves no Keycloak) só dispara nova busca a cada 30 s: um token forjado não martela o IdP.
INTERVALO_MIN_RECARGA_JWKS_S = 30


@dataclass(frozen=True)
class ConfigAuth:
    issuer: str
    client_id: str
    client_secret: str
    segredo_sessao: str
    scope: str = "openid email profile"
    cookie_seguro: bool = False
    # azp (cliente de serviço) autorizado a chamar /api com Bearer. Vazio = Bearer desligado.
    bearer_clientes: frozenset[str] = frozenset()

    @classmethod
    def do_ambiente(cls, valores: dict[str, str]) -> "ConfigAuth | None":
        """None quando faltar issuer, client ou segredo (o painel recusa as rotas /api)."""
        issuer = (valores.get(CHAVES["issuer"]) or "").strip()
        client_id = (valores.get(CHAVES["client_id"]) or "").strip()
        client_secret = (valores.get(CHAVES["client_secret"]) or "").strip()
        segredo = (valores.get(CHAVES["segredo_sessao"]) or "").strip()
        if not (issuer.startswith("https://") or issuer.startswith("http://")) or not client_id or not client_secret:
            return None
        if len(segredo) < 32:
            return None
        bearer = frozenset(c.strip() for c in (valores.get(CHAVES["bearer_clientes"]) or "").split(",") if c.strip())
        return cls(
            issuer=issuer.rstrip("/"),
            client_id=client_id,
            client_secret=client_secret,
            segredo_sessao=segredo,
            scope=(valores.get(CHAVES["scope"]) or "openid email profile").strip(),
            cookie_seguro=(valores.get(CHAVES["cookie_seguro"]) or "0").strip().lower() in ("1", "true", "sim"),
            bearer_clientes=bearer,
        )


def carregar_config_auth(raiz: Path, dir_backup: Path) -> ConfigAuth | None:
    """Lê o .env da raiz (variáveis do ambiente têm precedência). Gera o segredo de sessão na primeira vez."""
    env_path = raiz / ".env"
    valores = {**(ler_env(env_path) if env_path.exists() else {}), **{k: v for k, v in os.environ.items() if k.startswith("TUDOIA_")}}
    if not valores.get(CHAVES["issuer"]):
        return None
    if not (valores.get(CHAVES["segredo_sessao"]) or "").strip():
        # Só persiste quando a configuração OIDC existe: sem IdP não há o que proteger com esta chave.
        novo = secrets.token_urlsafe(48)
        gravar_valor(env_path, CHAVES["segredo_sessao"], novo, dir_backup)
        valores[CHAVES["segredo_sessao"]] = novo
    return ConfigAuth.do_ambiente(valores)


def retorno_seguro(valor: str | None) -> str:
    r"""Só volta para dentro do painel. Bloqueia open redirect (https://site, //site, /\site)."""
    if not valor or not valor.startswith("/app") or valor.startswith("//") or "\\" in valor:
        return "/app/"
    return valor


def _usuario(claims: dict) -> dict:
    """Dados da conta exibidos no painel. Nada de token aqui: só identificação."""
    return {"sub": claims.get("sub"), "email": claims.get("email"),
            "login": claims.get("preferred_username"),
            "nome": claims.get("name") or claims.get("preferred_username")}


def papeis_do_token(claims: dict) -> list[str]:
    """Papéis do painel presentes nos claims. Aceita grupo com caminho (/tudoia-admin) e papel de realm."""
    grupos = claims.get("groups") or []
    realm = (claims.get("realm_access") or {}).get("roles") or []
    candidatos = {str(x).strip().lstrip("/") for x in [*grupos, *realm]}
    return [p for p in PAPEIS if p in candidatos]


def decidir(metodo: str, caminho: str, papeis: list[str] | None) -> tuple[int, str, str] | None:
    """Regra de autorização do /api. None = permitido; senão (status, código, mensagem). Função pura."""
    if not (caminho == "/api" or caminho.startswith("/api/")):
        return None
    if caminho == "/api/sessao":
        return None
    if not papeis:
        return 401, "nao_autenticado", "faça login em /auth/login"
    if any(caminho.startswith(p) for p in PREFIXOS_SO_ADMIN) and PAPEL_ADMIN not in papeis:
        return 403, "papel_insuficiente", f"esta ação exige o papel {PAPEL_ADMIN}"
    if (metodo not in METODOS_SEGUROS and PAPEL_ADMIN not in papeis
            and any(caminho == p or caminho.startswith(p + "/") for p in PREFIXOS_ESCRITA_SO_ADMIN)):
        return 403, "papel_insuficiente", f"alterar a governança exige o papel {PAPEL_ADMIN}"
    if metodo not in METODOS_SEGUROS and not ({PAPEL_ADMIN, PAPEL_OPERADOR} & set(papeis)):
        return 403, "papel_insuficiente", f"alterar exige {PAPEL_OPERADOR} ou {PAPEL_ADMIN}"
    return None


async def consultar_userinfo(issuer: str, access_token: str) -> dict | None:
    """Claims atuais da conta no Keycloak. None = token recusado (conta desativada ou sessão revogada).
    Erro de rede ou resposta inesperada levanta exceção: quem chama nega o acesso (fail-closed)."""
    if not access_token:
        return None
    async with httpx.AsyncClient(timeout=5.0, follow_redirects=False) as cliente:
        r = await cliente.get(f"{issuer}/protocol/openid-connect/userinfo",
                              headers={"authorization": f"Bearer {access_token}"})
    if r.status_code in (401, 403):
        return None
    r.raise_for_status()
    return r.json()


class CacheJwks:
    """Chaves públicas do realm, em memória. Renova a cada TTL_JWKS_S e, com `kid` desconhecido, no máximo a cada
    INTERVALO_MIN_RECARGA_JWKS_S (rotação de chaves). Uma busca por vez. Erro de rede levanta exceção (quem chama nega)."""

    def __init__(self, issuer: str, buscar=None):
        self.url = f"{issuer}/protocol/openid-connect/certs"
        self._buscar = buscar or self._baixar
        self._chaves = None
        self._ate = 0.0
        self._buscada_em = 0.0
        self._trava = asyncio.Lock()

    async def _baixar(self):
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=False) as cliente:
            r = await cliente.get(self.url)
            r.raise_for_status()
            return KeySet.import_key_set(r.json())

    def _conhece(self, kid: str | None) -> bool:
        return kid is None or any(k.kid == kid for k in self._chaves.keys)

    async def obter(self, kid: str | None = None):
        async with self._trava:
            agora = time.time()
            vencida = self._chaves is None or agora >= self._ate
            desconhecida = (self._chaves is not None and not self._conhece(kid)
                            and agora - self._buscada_em >= INTERVALO_MIN_RECARGA_JWKS_S)
            if vencida or desconhecida:
                self._chaves = await self._buscar()
                self._buscada_em = agora
                self._ate = agora + TTL_JWKS_S
            return self._chaves


def kid_do_token(token: str) -> str | None:
    """`kid` do cabeçalho, sem verificar nada: serve só para escolher/renovar a chave. A verificação é do decode."""
    try:
        bruto = token.split(".")[0]
        cabecalho = json.loads(base64.urlsafe_b64decode(bruto + "=" * (-len(bruto) % 4)))
        kid = cabecalho.get("kid") if isinstance(cabecalho, dict) else None
        return kid if isinstance(kid, str) else None
    except ValueError:
        return None


def _tem_audiencia(claims: dict, audiencia: str) -> bool:
    aud = claims.get("aud")
    return aud == audiencia or (isinstance(aud, list) and audiencia in aud)


def validar_token_bearer(token: str, issuer: str, clientes: frozenset[str], chaves: KeySet,
                         audiencia: str | None = None) -> dict | None:
    """Claims do token ou None. Confere assinatura RS256, emissor, validade, o cliente (azp) autorizado e, quando
    informada, a audiência (o token precisa ter sido emitido para este painel, não para outro serviço do realm).
    Função pura: as chaves chegam prontas (o cache de JWKS fica fora)."""
    try:
        decodificado = jose_jwt.decode(token, chaves, algorithms=ALGORITMOS_JWT)
        registro = jose_jwt.JWTClaimsRegistry(iss={"essential": True, "value": issuer}, exp={"essential": True})
        registro.validate(decodificado.claims)
    except Exception:  # noqa: BLE001 — qualquer falha de verificação é token recusado
        return None
    claims = dict(decodificado.claims)
    if claims.get("azp") not in clientes:
        return None
    if audiencia is not None and not _tem_audiencia(claims, audiencia):
        return None
    return claims


class GuardaAutorizacao:
    """Middleware ASGI: confirma a sessão no Keycloak (a cada TTL_REVALIDACAO_S) e aplica `decidir` a cada /api.
    Aceita também `Authorization: Bearer` de cliente de serviço autorizado (TUDOIA_API_BEARER_CLIENTES).
    Precisa rodar DENTRO do SessionMiddleware."""

    def __init__(self, app, config: ConfigAuth | None, revalidador=None, jwks: CacheJwks | None = None):
        self.app = app
        self.config = config
        self.revalidador = revalidador or (lambda token: consultar_userinfo(config.issuer, token))
        self.jwks = jwks or (CacheJwks(config.issuer) if config is not None else None)

    async def _autorizar_bearer(self, scope, receive, send, caminho):
        if not self.config.bearer_clientes:
            return await _json(send, 401, corpo_erro("bearer_desativado", "tokens de API não estão habilitados neste painel"))
        esquema, _, token = Headers(scope=scope).get("authorization", "").partition(" ")
        token = token.strip()
        if esquema.lower() != "bearer" or not token:
            return await _json(send, 401, corpo_erro("token_invalido", "use o cabeçalho Authorization: Bearer <token>"))
        try:
            chaves = await self.jwks.obter(kid_do_token(token))
        except Exception:  # noqa: BLE001 — sem as chaves não há como verificar: nega (fail-closed)
            return await _json(send, 503, corpo_erro("identidade_indisponivel",
                                                     "não foi possível obter as chaves do Keycloak; tente de novo"))
        claims = validar_token_bearer(token, self.config.issuer, self.config.bearer_clientes, chaves,
                                      audiencia=self.config.client_id)
        if claims is None:
            return await _json(send, 401, corpo_erro("token_invalido",
                                                     "token recusado: assinatura, emissor, validade ou cliente"))
        papeis = papeis_do_token(claims)
        if not papeis:
            return await _json(send, 403, corpo_erro("papel_insuficiente", "o token não tem papel do painel"))
        recusa = decidir(scope["method"], caminho, papeis)
        if recusa:
            status, codigo, mensagem = recusa
            return await _json(send, status, corpo_erro(codigo, mensagem))
        scope["tudoia_bearer"] = {"claims": claims, "papeis": papeis}
        return await self.app(scope, receive, send)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        caminho = scope.get("path", "")
        if not (caminho == "/api" or caminho.startswith("/api/")):
            return await self.app(scope, receive, send)
        if self.config is None:
            if caminho == "/api/sessao":
                return await self.app(scope, receive, send)  # /api/sessao diz ao SPA se há IdP configurado
            corpo = corpo_erro("auth_nao_configurada",
                               "autenticação não configurada: defina TUDOIA_OIDC_* no .env (veja docs/componentes/keycloak.md)")
            return await _json(send, 503, corpo)
        if Headers(scope=scope).get("authorization") is not None:
            return await self._autorizar_bearer(scope, receive, send, caminho)
        if caminho == "/api/sessao":
            return await self.app(scope, receive, send)
        sessao = scope.get("session") or {}
        papeis = _papeis_validos(sessao)
        # Idade fora de [0, TTL] (inclusive `verificado_em` no futuro, que um cookie forjado usaria para nunca
        # revalidar) força a confirmação no Keycloak, que não aceita access_token forjado.
        if papeis and not 0 <= time.time() - _numero(sessao.get("verificado_em")) <= TTL_REVALIDACAO_S:
            try:
                claims = await self.revalidador(sessao.get("access_token") or "")
            except Exception:  # noqa: BLE001 — sem confirmação do Keycloak não há acesso
                return await _json(send, 503, corpo_erro("identidade_indisponivel",
                                                         "não foi possível confirmar a sessão no Keycloak; tente de novo"))
            papeis_novos = papeis_do_token(claims) if claims else []
            if not papeis_novos:
                # Conta desativada, sessão revogada ou sem papel do painel: a sessão deixa de valer.
                sessao.clear()
                papeis = None
            else:
                sessao["papeis"] = papeis_novos
                sessao["verificado_em"] = time.time()
                sessao["usuario"] = _usuario(claims)
                papeis = papeis_novos
        recusa = decidir(scope["method"], caminho, papeis)
        if recusa:
            status, codigo, mensagem = recusa
            return await _json(send, status, corpo_erro(codigo, mensagem))
        return await self.app(scope, receive, send)


def _numero(valor) -> float:
    return float(valor) if isinstance(valor, (int, float)) and not isinstance(valor, bool) else 0.0


def _papeis_validos(sessao: dict) -> list[str] | None:
    expira = sessao.get("expira_em")
    if not isinstance(expira, (int, float)):
        return None
    restante = expira - time.time()
    if restante < 0 or restante > IDADE_MAXIMA_SESSAO:  # além da idade máxima: o painel nunca emitiu esse cookie
        return None
    papeis = sessao.get("papeis")
    return list(papeis) if isinstance(papeis, list) and papeis else None


async def _json(send, status: int, corpo: dict) -> None:
    dados = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
    cabecalhos = [(b"content-type", b"application/json"), (b"content-length", str(len(dados)).encode()),
                  (b"cache-control", b"no-store")]
    await send({"type": "http.response.start", "status": status, "headers": cabecalhos})
    await send({"type": "http.response.body", "body": dados})


def registrar_autenticacao(app: FastAPI, config: ConfigAuth | None, arquivo_auditoria: Path | None = None) -> None:
    """Liga sessão, guarda, auditoria e rotas /auth/* e /api/sessao. Chame ANTES de add_middleware(GuardaApi)."""
    app.add_middleware(GuardaAutorizacao, config=config)
    app.add_middleware(Auditoria, arquivo=arquivo_auditoria)  # por fora da guarda: vê quem pediu e o status final
    app.add_middleware(
        SessionMiddleware,
        secret_key=config.segredo_sessao if config else secrets.token_urlsafe(32),
        session_cookie="tudoia_sessao",
        max_age=IDADE_MAXIMA_SESSAO,
        same_site="lax",
        https_only=bool(config and config.cookie_seguro),
    )
    oauth = OAuth()
    if config is not None:
        oauth.register(
            name="tudoia",
            client_id=config.client_id,
            client_secret=config.client_secret,
            server_metadata_url=f"{config.issuer}/.well-known/openid-configuration",
            client_kwargs={"scope": config.scope, "code_challenge_method": "S256"},
        )

    def _base(request: Request) -> str:
        # O Host já foi validado pela GuardaApi (127.0.0.1 ou localhost na porta do painel).
        return str(request.base_url).rstrip("/")

    def _sem_config() -> JSONResponse:
        return JSONResponse(corpo_erro("auth_nao_configurada", "autenticação não configurada no .env"), status_code=503)

    @app.get("/auth/login")
    async def login(request: Request, retorno: str = "/app/"):
        if config is None:
            return _sem_config()
        request.session["retorno"] = retorno_seguro(retorno)
        return await oauth.tudoia.authorize_redirect(request, f"{_base(request)}/auth/callback")

    @app.get("/auth/callback")
    async def callback(request: Request):
        if config is None:
            return _sem_config()
        if _papeis_validos(request.session):
            destino = request.session.get("retorno") or "/app/"
            return RedirectResponse(destino, status_code=303)
        try:
            token = await oauth.tudoia.authorize_access_token(request)
        except OAuthError:
            aceita = request.headers.get("accept", "")
            if "text/html" in aceita:
                destino = request.session.get("retorno") or "/app/"
                return RedirectResponse(f"/auth/login?retorno={quote(destino, safe='/')}", status_code=303)
            # Não devolvemos a descrição do erro: ela pode ecoar parâmetros do IdP.
            return JSONResponse(corpo_erro("login_recusado", "o login foi recusado ou expirou; tente de novo"),
                                status_code=401)
        claims = token.get("userinfo") or {}
        papeis = papeis_do_token(claims)
        if not papeis:
            return JSONResponse(corpo_erro("sem_papel",
                                           f"sua conta não tem nenhum papel do painel ({', '.join(PAPEIS)})"),
                                status_code=403)
        destino = request.session.get("retorno") or "/app/"
        request.session.clear()
        request.session.update({
            "usuario": _usuario(claims),
            "entrou_em": time.time(),
            "papeis": papeis,
            "expira_em": time.time() + IDADE_MAXIMA_SESSAO,
            "verificado_em": time.time(),
            "access_token": token.get("access_token"),
            "id_token": token.get("id_token"),
        })
        return RedirectResponse(destino, status_code=303)

    @app.post("/auth/logout")
    async def logout(request: Request):
        porta = porta_do_painel()
        recusa = checar("POST", Headers(scope=request.scope), True, porta)
        if recusa:
            status, codigo, mensagem = recusa
            return JSONResponse(corpo_erro(codigo, mensagem), status_code=status)
        id_token = request.session.get("id_token")
        request.session.clear()
        pos_saida = f"{_base(request)}/app/"
        url_idp = None
        if config is not None:
            meta = await oauth.tudoia.load_server_metadata()
            fim = meta.get("end_session_endpoint")
            if fim:
                parametros = {"post_logout_redirect_uri": pos_saida, "client_id": config.client_id}
                if id_token:
                    parametros["id_token_hint"] = id_token
                url_idp = f"{fim}?{urlencode(parametros)}"
        return JSONResponse({"ok": True, "url": url_idp or pos_saida})

    @app.get("/api/sessao")
    def sessao(request: Request):
        papeis = _papeis_validos(request.session)
        if config is None:
            return {"configurado": False, "autenticado": False, "usuario": None, "papeis": []}
        bearer = request.scope.get("tudoia_bearer")
        if bearer:
            # Token de cliente de serviço: não há sessão de navegador. Mostra a identidade do token.
            papeis_token = bearer["papeis"]
            return {
                "configurado": True,
                "autenticado": True,
                "via": "bearer",
                "usuario": _usuario(bearer["claims"]),
                "papeis": papeis_token,
                "pode_alterar": bool({PAPEL_ADMIN, PAPEL_OPERADOR} & set(papeis_token)),
                "admin": PAPEL_ADMIN in papeis_token,
                "conta_url": f"{config.issuer}/account/",
            }
        if not papeis:
            return {"configurado": True, "autenticado": False, "usuario": None, "papeis": []}
        return {
            "configurado": True,
            "autenticado": True,
            "usuario": request.session.get("usuario"),
            "papeis": papeis,
            "pode_alterar": bool({PAPEL_ADMIN, PAPEL_OPERADOR} & set(papeis)),
            "admin": PAPEL_ADMIN in papeis,
            "entrou_em": request.session.get("entrou_em"),
            "expira_em": request.session.get("expira_em"),
            "verificado_em": request.session.get("verificado_em"),
            # A conta (senha, e-mail, 2FA) é gerida pelo próprio Keycloak; o painel só aponta para lá.
            "conta_url": f"{config.issuer}/account/",
        }

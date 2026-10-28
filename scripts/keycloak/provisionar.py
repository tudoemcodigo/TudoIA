"""Provisiona o realm do painel TudoIA no Keycloak, de forma idempotente.

Fonte da verdade: infra/keycloak/realm-tudoia.json (realm, papéis, grupos, escopo, cliente)
e infra/keycloak/idps/*.json (identity providers; *.example.json NÃO são aplicados).

Uso (na raiz do repositório):
    .venv\\Scripts\\python.exe -m scripts.keycloak.provisionar
    .venv\\Scripts\\python.exe -m scripts.keycloak.provisionar --verificar
    .venv\\Scripts\\python.exe -m scripts.keycloak.provisionar --rotacionar-secret
    .venv\\Scripts\\python.exe -m scripts.keycloak.provisionar --admin-inicial pessoa@dominio.com

Configuração (ambiente tem prioridade sobre D:\\TudoIA\\.env):
    TUDOIA_KEYCLOAK_URL             padrão http://localhost:8180
    TUDOIA_KEYCLOAK_REALM           padrão tudoia
    TUDOIA_PAINEL_PORTA             padrão 3100 (portas dos redirect URIs)
    TUDOIA_KEYCLOAK_ADMIN           admin do realm master (pede no terminal se ausente)
    TUDOIA_KEYCLOAK_ADMIN_PASSWORD  senha do admin (pede no terminal se ausente)
    TUDOIA_IDP_*                    variáveis referenciadas pelos IdPs aplicados

Grava no .env: TUDOIA_OIDC_ISSUER, TUDOIA_OIDC_CLIENT_ID, TUDOIA_OIDC_CLIENT_SECRET (painel) e
TUDOIA_MCP_CLIENT_ID, TUDOIA_MCP_CLIENT_SECRET (cliente de serviço do Cérebro, client_credentials).

Códigos de saída: 0 ok (ou sem alterações), 1 desvio/validação, 2 conexão/autenticação.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import secrets
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "painel"))
from tudoia_painel.envfile import gravar_valor, ler_env  # noqa: E402

GRUPO_CONTA_SERVICO = "tudoia-operador"  # papel que o token do Cérebro carrega (escrita liberada)
# Campos do template que não são atributos do cliente no Keycloak (tratados em rotinas próprias).
_SO_DO_PLANO = ("defaultClientScopes", "optionalClientScopes", "protocolMappers", "grupoConta")

TEMPLATE_PADRAO = RAIZ / "infra" / "keycloak" / "realm-tudoia.json"
IDPS_PADRAO = RAIZ / "infra" / "keycloak" / "idps"
ENV_PADRAO = RAIZ / ".env"
BACKUP_ENV = RAIZ / "dados" / "backups" / "env"

URL_PADRAO = "http://localhost:8180"
REALM_PADRAO = "tudoia"
PORTA_PADRAO = "3100"
TIMEOUT = httpx.Timeout(10.0, connect=5.0)

_PLACEHOLDER = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
_AUSENTE = object()


class ErroValidacao(Exception):
    """Template/IdP inválido, variável ausente ou erro da API (código de saída 1)."""


class ErroConexao(Exception):
    """Keycloak inacessível ou credencial recusada (código de saída 2)."""


# --------------------------------------------------------------------------- templates


@dataclass(frozen=True)
class Idp:
    alias: str
    representacao: dict[str, Any]
    mappers: list[dict[str, Any]]


@dataclass(frozen=True)
class Plano:
    realm: dict[str, Any]
    roles: list[dict[str, Any]]
    grupos: list[dict[str, Any]]
    escopo: dict[str, Any]
    cliente: dict[str, Any]
    cliente_servico: dict[str, Any]
    cliente_capturas: dict[str, Any] | None = None
    idps: list[Idp] = field(default_factory=list)


@dataclass
class Relatorio:
    registros: list[str] = field(default_factory=list)
    senha_temporaria: str | None = None
    email_admin_inicial: str | None = None


def carregar_template(caminho: Path) -> dict[str, Any]:
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise ErroValidacao(f"template ilegível ou JSON inválido: {caminho}") from None
    validar_template(dados)
    return dados


def _sem_segredos(obj: Any, caminho: str = "") -> None:
    if isinstance(obj, dict):
        for chave, valor in obj.items():
            if "secret" in chave.lower():
                raise ErroValidacao(
                    f"template não pode conter segredos (chave '{caminho}{chave}'); "
                    "o segredo do cliente é gerado pelo provisionamento"
                )
            _sem_segredos(valor, f"{caminho}{chave}.")
    elif isinstance(obj, list):
        for item in obj:
            _sem_segredos(item, caminho)


def validar_template(t: Any) -> None:
    if not isinstance(t, dict):
        raise ErroValidacao("template deve ser um objeto JSON")
    for secao in ("realm", "roles", "grupos", "escopo", "cliente", "clienteServico"):
        if secao not in t:
            raise ErroValidacao(f"template sem a seção '{secao}'")
    _sem_segredos(t)

    nomes_papeis = {p["name"] for p in t["roles"]}
    for grupo in t["grupos"]:
        faltam = set(grupo.get("roles", [])) - nomes_papeis
        if faltam:
            raise ErroValidacao(
                f"grupo '{grupo['name']}' referencia papel inexistente: {', '.join(sorted(faltam))}"
            )

    cliente = t["cliente"]
    exigidos = {
        "publicClient": False,
        "standardFlowEnabled": True,
        "directAccessGrantsEnabled": False,
        "implicitFlowEnabled": False,
        "serviceAccountsEnabled": False,
    }
    for chave, valor in exigidos.items():
        if cliente.get(chave) is not valor:
            raise ErroValidacao(
                f"cliente '{cliente.get('clientId')}': {chave} deve ser {str(valor).lower()}"
            )
    if cliente.get("attributes", {}).get("pkce.code.challenge.method") != "S256":
        raise ErroValidacao("cliente sem PKCE obrigatório (pkce.code.challenge.method = S256)")
    if not cliente.get("redirectUris"):
        raise ErroValidacao("cliente sem redirectUris")

    grupos = {g["name"] for g in t["grupos"]}
    servicos = [("clienteServico", t["clienteServico"])]
    if "clienteServicoCapturas" in t:
        servicos.append(("clienteServicoCapturas", t["clienteServicoCapturas"]))
    for secao, servico in servicos:
        exigidos_servico = {"publicClient": False, "standardFlowEnabled": False, "directAccessGrantsEnabled": False,
                            "implicitFlowEnabled": False, "serviceAccountsEnabled": True}
        for chave, valor in exigidos_servico.items():
            if servico.get(chave) is not valor:
                raise ErroValidacao(f"{secao} '{servico.get('clientId')}': {chave} deve ser {str(valor).lower()}")
        if not str(servico.get("attributes", {}).get("access.token.lifespan", "")).isdigit():
            raise ErroValidacao(f"{secao} sem access.token.lifespan (segundos)")
        grupo = servico.get("grupoConta", GRUPO_CONTA_SERVICO)
        if grupo not in grupos:
            raise ErroValidacao(f"{secao}: grupo '{grupo}' ausente do template")


def substituir(obj: Any, variaveis: dict[str, str]) -> Any:
    """Troca ${NOME} em strings. Falha (sem alterar nada) se alguma variável estiver ausente."""
    faltando: set[str] = set()

    def troca_texto(texto: str) -> str:
        def sub(m: re.Match[str]) -> str:
            valor = variaveis.get(m.group(1), "")
            if not valor:
                faltando.add(m.group(1))
                return m.group(0)
            return valor

        return _PLACEHOLDER.sub(sub, texto)

    def percorre(v: Any) -> Any:
        if isinstance(v, str):
            return troca_texto(v)
        if isinstance(v, dict):
            return {k: percorre(x) for k, x in v.items()}
        if isinstance(v, list):
            return [percorre(x) for x in v]
        return v

    resultado = percorre(obj)
    if faltando:
        raise ErroValidacao(f"variável(is) ausente(s): {', '.join(sorted(faltando))}")
    return resultado


def carregar_idps(diretorio: Path, variaveis: dict[str, str]) -> list[Idp]:
    if not diretorio.is_dir():
        return []
    idps: list[Idp] = []
    for arquivo in sorted(diretorio.glob("*.json")):
        if arquivo.name.endswith(".example.json"):
            continue
        try:
            bruto = json.loads(arquivo.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raise ErroValidacao(f"{arquivo.name}: JSON ilegível") from None
        if (
            not isinstance(bruto, dict)
            or not bruto.get("alias")
            or not bruto.get("providerId")
            or not isinstance(bruto.get("config"), dict)
        ):
            raise ErroValidacao(f"{arquivo.name}: exige alias, providerId e config")
        if not re.fullmatch(r"[a-z0-9-]+", bruto["alias"]):
            raise ErroValidacao(f"{arquivo.name}: alias deve ser [a-z0-9-]+")
        mappers = bruto.pop("mappers", [])
        for m in mappers:
            if not isinstance(m, dict) or not m.get("name") or not m.get("identityProviderMapper"):
                raise ErroValidacao(f"{arquivo.name}: mapper sem name ou identityProviderMapper")
        try:
            representacao = substituir(bruto, variaveis)
            mappers = substituir(mappers, variaveis)
        except ErroValidacao as exc:
            raise ErroValidacao(f"{arquivo.name}: {exc}") from None
        idps.append(Idp(alias=representacao["alias"], representacao=representacao, mappers=mappers))

    aliases = [i.alias for i in idps]
    if len(aliases) != len(set(aliases)):
        raise ErroValidacao("alias de IdP duplicado")
    return idps


def validar_config(config: dict[str, str]) -> None:
    if not re.fullmatch(r"https?://[^\s]+", config["TUDOIA_KEYCLOAK_URL"]):
        raise ErroValidacao("TUDOIA_KEYCLOAK_URL deve começar com http:// ou https://")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", config["TUDOIA_KEYCLOAK_REALM"]):
        raise ErroValidacao("TUDOIA_KEYCLOAK_REALM inválido (use letras, números, - e _)")
    porta = config["TUDOIA_PAINEL_PORTA"]
    if not (porta.isdigit() and 1 <= int(porta) <= 65535):
        raise ErroValidacao("TUDOIA_PAINEL_PORTA deve ser um número de 1 a 65535")


def montar_config(arquivo_env: Path, ambiente: dict[str, str]) -> dict[str, str]:
    """Junta .env e ambiente (ambiente vence) e aplica padrões. Não imprime nada."""
    valores = {k: v for k, v in ler_env(arquivo_env).items() if k.startswith("TUDOIA_")}
    valores.update({k: v for k, v in ambiente.items() if k.startswith("TUDOIA_")})
    config = dict(valores)
    config["TUDOIA_KEYCLOAK_URL"] = (valores.get("TUDOIA_KEYCLOAK_URL") or URL_PADRAO).rstrip("/")
    config["TUDOIA_KEYCLOAK_REALM"] = valores.get("TUDOIA_KEYCLOAK_REALM") or REALM_PADRAO
    config["TUDOIA_PAINEL_PORTA"] = valores.get("TUDOIA_PAINEL_PORTA") or PORTA_PADRAO
    return config


def montar_plano(template: dict[str, Any], config: dict[str, str], idps_dir: Path) -> Plano:
    """Valida tudo e resolve placeholders antes de qualquer chamada de rede."""
    validar_config(config)
    try:
        resolvido = substituir(template, config)
    except ErroValidacao as exc:
        raise ErroValidacao(f"template: {exc}") from None
    return Plano(
        realm={**resolvido["realm"], "realm": config["TUDOIA_KEYCLOAK_REALM"]},
        roles=resolvido["roles"],
        grupos=resolvido["grupos"],
        escopo=resolvido["escopo"],
        cliente=resolvido["cliente"],
        cliente_servico=resolvido["clienteServico"],
        cliente_capturas=resolvido.get("clienteServicoCapturas"),
        idps=carregar_idps(idps_dir, config),
    )


# --------------------------------------------------------------------------- HTTP


def diferencas(desejado: Any, atual: Any, caminho: str = "") -> list[str]:
    """Campos do desejado que diferem do atual (o atual pode ter campos extras)."""
    if isinstance(desejado, dict):
        if not isinstance(atual, dict):
            return [caminho or "(raiz)"]
        saida: list[str] = []
        for chave, valor in desejado.items():
            saida += diferencas(valor, atual.get(chave, _AUSENTE), f"{caminho}.{chave}" if caminho else chave)
        return saida
    if isinstance(desejado, list) and all(isinstance(x, str) for x in desejado):
        if not isinstance(atual, list) or sorted(desejado) != sorted(atual):
            return [caminho]
        return []
    return [] if desejado == atual else [caminho]


def obter_token(url: str, usuario: str, senha: str, cliente: httpx.Client) -> str:
    """Password grant no client admin-cli do realm master (built-in do Keycloak)."""
    try:
        resp = cliente.post(
            f"{url}/realms/master/protocol/openid-connect/token",
            data={"grant_type": "password", "client_id": "admin-cli", "username": usuario, "password": senha},
            timeout=TIMEOUT,
        )
    except httpx.HTTPError:
        raise ErroConexao(f"não foi possível conectar em {url}") from None
    if resp.status_code in (400, 401):
        raise ErroConexao("credenciais de administrador recusadas (conta do realm master)")
    if resp.status_code != 200:
        raise ErroConexao(f"autenticação falhou (HTTP {resp.status_code})")
    try:
        return resp.json()["access_token"]
    except (ValueError, KeyError):
        raise ErroConexao("resposta de token inesperada do Keycloak") from None


class Keycloak:
    """Cliente mínimo da Admin REST API com timeout em toda chamada."""

    def __init__(self, base: str, token: str, cliente: httpx.Client) -> None:
        self._base = base
        self._http = cliente
        self._cabecalhos = {"Authorization": f"Bearer {token}"}

    def chamar(self, metodo: str, caminho: str, corpo: Any = None, aceitos=(200, 201, 204), ausente_ok=False):
        try:
            resp = self._http.request(
                metodo, self._base + caminho, json=corpo, headers=self._cabecalhos, timeout=TIMEOUT
            )
        except httpx.HTTPError:
            raise ErroConexao(f"falha de rede em {metodo} {caminho}") from None
        if ausente_ok and resp.status_code == 404:
            return None
        if resp.status_code in (401, 403):
            raise ErroConexao("administrador sem permissão para esta operação")
        if resp.status_code not in aceitos:
            raise ErroValidacao(f"Keycloak respondeu HTTP {resp.status_code} em {metodo} {caminho}")
        return resp

    def obter(self, caminho: str, ausente_ok: bool = False) -> Any:
        resp = self.chamar("GET", caminho, aceitos=(200,), ausente_ok=ausente_ok)
        return None if resp is None else resp.json()

    def criar(self, caminho: str, corpo: dict[str, Any]) -> str:
        resp = self.chamar("POST", caminho, corpo=corpo, aceitos=(201,))
        return resp.headers.get("Location", "").rsplit("/", 1)[-1]


# --------------------------------------------------------------------------- sincronização


class Sincronizador:
    """Compara o plano com o realm vivo e, se `aplicar`, corrige. Sem `aplicar` nunca escreve."""

    def __init__(self, kc: Keycloak, plano: Plano, realm: str, aplicar: bool, rotacionar: bool) -> None:
        self.kc = kc
        self.plano = plano
        self.realm = realm
        self.base = f"/admin/realms/{quote(realm, safe='')}"
        self.aplicar = aplicar
        self.rotacionar = rotacionar
        self.registros: list[str] = []
        self.segredos: dict[str, str] = {}  # clientId -> segredo (só quando aplicado)

    def _registra(self, mensagem: str) -> None:
        self.registros.append(mensagem)

    def executar(self, admin_inicial: str | None) -> str | None:
        """Devolve a senha temporária do admin inicial, se criado."""
        realm_vivo = self.kc.obter(self.base, ausente_ok=True)
        if realm_vivo is None:
            self._registra(f"realm '{self.realm}' ausente")
            if not self.aplicar:
                return None
            self.kc.criar("/admin/realms", self.plano.realm)
        else:
            desvios = diferencas(self.plano.realm, realm_vivo)
            if desvios:
                self._registra(f"realm '{self.realm}': {', '.join(desvios)}")
                if self.aplicar:
                    self.kc.chamar("PUT", self.base, corpo=self.plano.realm)

        papeis = self._papeis()
        self._grupos(papeis)
        self._escopo()
        self._cliente(self.plano.cliente)
        self._cliente(self.plano.cliente_servico)
        if self.plano.cliente_capturas is not None:
            self._cliente(self.plano.cliente_capturas)
        self._idps()
        if admin_inicial is None or not self.aplicar:
            return None
        return self._admin_inicial(admin_inicial)

    def _papeis(self) -> dict[str, dict[str, Any]]:
        atuais = {p["name"]: p for p in self.kc.obter(f"{self.base}/roles")}
        for papel in self.plano.roles:
            vivo = atuais.get(papel["name"])
            if vivo is None:
                self._registra(f"papel '{papel['name']}' ausente")
                if self.aplicar:
                    self.kc.criar(f"{self.base}/roles", papel)
            elif diferencas(papel, vivo):
                self._registra(f"papel '{papel['name']}': descrição divergente")
                if self.aplicar:
                    self.kc.chamar("PUT", f"{self.base}/roles/{quote(papel['name'], safe='')}", corpo={**vivo, **papel})
        return {p["name"]: p for p in self.kc.obter(f"{self.base}/roles")}

    def _grupos(self, papeis: dict[str, dict[str, Any]]) -> None:
        atuais = {g["name"]: g for g in self.kc.obter(f"{self.base}/groups")}
        for grupo in self.plano.grupos:
            nome = grupo["name"]
            vivo = atuais.get(nome)
            if vivo is None:
                self._registra(f"grupo '{nome}' ausente")
                if not self.aplicar:
                    continue
                gid = self.kc.criar(f"{self.base}/groups", {"name": nome})
                mapeados: list[dict[str, Any]] = []
            else:
                gid = vivo["id"]
                mapeados = self.kc.obter(f"{self.base}/groups/{gid}/role-mappings/realm")
            self._mapeamentos(nome, gid, mapeados, grupo.get("roles", []), papeis)

    def _mapeamentos(self, nome, gid, mapeados, desejados, papeis) -> None:
        vivos = {r["name"]: r for r in mapeados}
        faltam = [n for n in desejados if n not in vivos]
        sobram = [r for n, r in vivos.items() if n not in desejados]
        if faltam:
            self._registra(f"grupo '{nome}' sem papel(is): {', '.join(faltam)}")
            if self.aplicar:
                reps = [papeis[n] for n in faltam if n in papeis]
                self.kc.chamar("POST", f"{self.base}/groups/{gid}/role-mappings/realm", corpo=reps)
        if sobram:
            self._registra(f"grupo '{nome}' com papel(is) não previstos: {', '.join(r['name'] for r in sobram)}")
            if self.aplicar:
                self.kc.chamar("DELETE", f"{self.base}/groups/{gid}/role-mappings/realm", corpo=sobram)

    def _escopo(self) -> None:
        escopo = self.plano.escopo
        nome = escopo["name"]
        lista = self.kc.obter(f"{self.base}/client-scopes")
        vivo = next((e for e in lista if e["name"] == nome), None)
        if vivo is None:
            self._registra(f"client scope '{nome}' ausente")
            if not self.aplicar:
                return
            corpo = {k: v for k, v in escopo.items() if k != "protocolMappers"}
            sid = self.kc.criar(f"{self.base}/client-scopes", corpo)
            vivo = self.kc.obter(f"{self.base}/client-scopes/{sid}")
        else:
            vivo = self.kc.obter(f"{self.base}/client-scopes/{vivo['id']}")
            campos = {k: escopo[k] for k in ("description", "protocol", "attributes") if k in escopo}
            if diferencas(campos, vivo):
                self._registra(f"client scope '{nome}': {', '.join(diferencas(campos, vivo))}")
                if self.aplicar:
                    self.kc.chamar("PUT", f"{self.base}/client-scopes/{vivo['id']}", corpo={**vivo, **campos})

        sid = vivo["id"]
        mappers_vivos = {m["name"]: m for m in (vivo.get("protocolMappers") or [])}
        for mapper in escopo.get("protocolMappers", []):
            existente = mappers_vivos.get(mapper["name"])
            caminho = f"{self.base}/client-scopes/{sid}/protocol-mappers/models"
            if existente is None:
                self._registra(f"mapper '{mapper['name']}' ausente no escopo '{nome}'")
                if self.aplicar:
                    self.kc.criar(caminho, mapper)
            elif diferencas(mapper, existente):
                self._registra(f"mapper '{mapper['name']}' divergente")
                if self.aplicar:
                    self.kc.chamar("PUT", f"{caminho}/{existente['id']}", corpo={**existente, **mapper})

    def _cliente(self, cli: dict[str, Any]) -> None:
        cid = cli["clientId"]
        lista = self.kc.obter(f"{self.base}/clients?clientId={quote(cid, safe='')}")
        vivo = next((c for c in lista if c["clientId"] == cid), None)
        campos = {k: v for k, v in cli.items() if k not in _SO_DO_PLANO}
        criado = False
        if vivo is None:
            self._registra(f"cliente '{cid}' ausente")
            if not self.aplicar:
                return
            uid = self.kc.criar(f"{self.base}/clients", {k: v for k, v in cli.items() if k not in _SO_DO_PLANO})
            criado = True
        else:
            uid = vivo["id"]
            desvios = diferencas(campos, vivo)
            if desvios:
                self._registra(f"cliente '{cid}': {', '.join(desvios)}")
                if self.aplicar:
                    corpo = {**vivo, **campos, "attributes": {**(vivo.get("attributes") or {}), **campos["attributes"]}}
                    self.kc.chamar("PUT", f"{self.base}/clients/{uid}", corpo=corpo)

        self._escopos_padrao(uid, cli)
        self._mapeadores_cliente(uid, cid, cli.get("protocolMappers", []))
        if cli.get("serviceAccountsEnabled"):
            self._conta_servico(uid, cid, cli.get("grupoConta", GRUPO_CONTA_SERVICO))
        self._segredo(cid, uid, criado)

    def _escopos_padrao(self, uid: str, cli: dict[str, Any]) -> None:
        vivos = {e["name"] for e in self.kc.obter(f"{self.base}/clients/{uid}/default-client-scopes")}
        ausentes = [n for n in cli["defaultClientScopes"] if n not in vivos]
        if not ausentes:
            return
        self._registra(f"cliente sem escopo(s) padrão: {', '.join(ausentes)}")
        if self.aplicar:
            ids = {e["name"]: e["id"] for e in self.kc.obter(f"{self.base}/client-scopes")}
            for nome in ausentes:
                self.kc.chamar("PUT", f"{self.base}/clients/{uid}/default-client-scopes/{ids[nome]}")

    def _mapeadores_cliente(self, uid: str, cid: str, desejados: list[dict[str, Any]]) -> None:
        if not desejados:
            return
        caminho = f"{self.base}/clients/{uid}/protocol-mappers/models"
        vivos = {m["name"]: m for m in self.kc.obter(caminho)}
        for mapper in desejados:
            existente = vivos.get(mapper["name"])
            if existente is None:
                self._registra(f"mapper '{mapper['name']}' ausente no cliente '{cid}'")
                if self.aplicar:
                    self.kc.criar(caminho, mapper)
            elif diferencas(mapper, existente):
                self._registra(f"mapper '{mapper['name']}' divergente no cliente '{cid}'")
                if self.aplicar:
                    self.kc.chamar("PUT", f"{caminho}/{existente['id']}", corpo={**existente, **mapper})

    def _conta_servico(self, uid: str, cid: str, grupo: str) -> None:
        usuario = self.kc.obter(f"{self.base}/clients/{uid}/service-account-user")["id"]
        gid = next((g["id"] for g in self.kc.obter(f"{self.base}/groups") if g["name"] == grupo), None)
        if gid is None:  # só ocorre sem --aplicar, antes da criação do grupo
            self._registra(f"conta de serviço de '{cid}' sem o grupo '{grupo}' (grupo ausente)")
            return
        if grupo in {g["name"] for g in self.kc.obter(f"{self.base}/users/{usuario}/groups")}:
            return
        self._registra(f"conta de serviço de '{cid}' fora do grupo '{grupo}'")
        if self.aplicar:
            self.kc.chamar("PUT", f"{self.base}/users/{usuario}/groups/{gid}")

    def _segredo(self, cid: str, uid: str, criado: bool) -> None:
        if not self.aplicar:
            if self.rotacionar and not criado:
                self._registra(f"segredo do cliente '{cid}' seria rotacionado (--rotacionar-secret)")
            return
        valor = self.kc.obter(f"{self.base}/clients/{uid}/client-secret").get("value")
        if not valor or (self.rotacionar and not criado):
            valor = self.kc.chamar("POST", f"{self.base}/clients/{uid}/client-secret", aceitos=(200,)).json()["value"]
            self._registra(f"segredo do cliente '{cid}' gerado/rotacionado")
        self.segredos[cid] = valor

    def _idps(self) -> None:
        base_idp = f"{self.base}/identity-provider/instances"
        for idp in self.plano.idps:
            alias = quote(idp.alias, safe="")
            rep = idp.representacao
            vivo = self.kc.obter(f"{base_idp}/{alias}", ausente_ok=True)
            # O Keycloak devolve clientSecret mascarado: o segredo não entra na comparação.
            cmp_rep = {**rep, "config": {k: v for k, v in rep["config"].items() if k != "clientSecret"}}
            if vivo is None:
                self._registra(f"identity provider '{idp.alias}' ausente")
                if self.aplicar:
                    self.kc.criar(base_idp, rep)
                mapa: dict[str, dict[str, Any]] = {}
            else:
                desvios = diferencas(cmp_rep, vivo)
                if self.rotacionar and "clientSecret" in rep["config"]:
                    desvios.append("config.clientSecret (--rotacionar-secret)")
                if desvios:
                    self._registra(f"identity provider '{idp.alias}': {', '.join(desvios)}")
                    if self.aplicar:
                        corpo = {**vivo, **rep, "config": {**vivo["config"], **rep["config"]}}
                        self.kc.chamar("PUT", f"{base_idp}/{alias}", corpo=corpo)
                mapa = {m["name"]: m for m in self.kc.obter(f"{base_idp}/{alias}/mappers")}
            for mapper in idp.mappers:
                corpo = {
                    "name": mapper["name"],
                    "identityProviderAlias": idp.alias,
                    "identityProviderMapper": mapper["identityProviderMapper"],
                    "config": mapper.get("config", {}),
                }
                existente = mapa.get(mapper["name"])
                caminho = f"{base_idp}/{alias}/mappers"
                if existente is None:
                    self._registra(f"mapper '{mapper['name']}' ausente no IdP '{idp.alias}'")
                    if self.aplicar:
                        self.kc.criar(caminho, corpo)
                elif diferencas(corpo, existente):
                    self._registra(f"mapper '{mapper['name']}' divergente no IdP '{idp.alias}'")
                    if self.aplicar:
                        self.kc.chamar("PUT", f"{caminho}/{existente['id']}", corpo={**existente, **corpo})

    def _admin_inicial(self, email: str) -> str | None:
        email = email.strip().lower()
        if len(email) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            raise ErroValidacao("--admin-inicial: e-mail inválido")
        por_usuario = self.kc.obter(f"{self.base}/users?username={quote(email, safe='')}&exact=true")
        por_email = self.kc.obter(f"{self.base}/users?email={quote(email, safe='')}&exact=true")
        if por_usuario or por_email:
            self._registra(f"usuário '{email}' já existe: senha e grupos não foram alterados")
            return None
        self._registra(f"usuário administrador inicial '{email}' criado")
        senha = secrets.token_urlsafe(18)
        uid = self.kc.criar(
            f"{self.base}/users",
            {
                "username": email,
                "email": email,
                "enabled": True,
                "emailVerified": True,
                "requiredActions": ["UPDATE_PASSWORD"],
            },
        )
        self.kc.chamar(
            "PUT",
            f"{self.base}/users/{uid}/reset-password",
            corpo={"type": "password", "value": senha, "temporary": True},
        )
        grupo = next((g for g in self.kc.obter(f"{self.base}/groups") if g["name"] == "tudoia-admin"), None)
        if grupo is None:
            raise ErroValidacao("grupo 'tudoia-admin' não encontrado após a sincronização")
        self.kc.chamar("PUT", f"{self.base}/users/{uid}/groups/{grupo['id']}")
        return senha


def _gravar_env(env_path: Path, pares: list[tuple[str, str]], registros: list[str]) -> None:
    atuais = ler_env(env_path)
    for chave, valor in pares:
        if atuais.get(chave) != valor:
            gravar_valor(env_path, chave, valor, BACKUP_ENV)
            registros.append(f"{chave} gravado em .env")


def provisionar(
    config: dict[str, str],
    admin_usuario: str,
    admin_senha: str,
    *,
    verificar: bool = False,
    rotacionar_secret: bool = False,
    admin_inicial: str | None = None,
    template_path: Path = TEMPLATE_PADRAO,
    idps_dir: Path = IDPS_PADRAO,
    env_path: Path = ENV_PADRAO,
    cliente_http: httpx.Client | None = None,
) -> Relatorio:
    """Aplica (ou, com `verificar`, só compara) o template no Keycloak.

    Com `verificar=True` nenhuma escrita é feita: registros = desvios encontrados.
    """
    plano = montar_plano(carregar_template(template_path), config, idps_dir)
    realm = config["TUDOIA_KEYCLOAK_REALM"]
    url = config["TUDOIA_KEYCLOAK_URL"]

    proprio = cliente_http is None
    http = cliente_http or httpx.Client(timeout=TIMEOUT)
    try:
        token = obter_token(url, admin_usuario, admin_senha, http)
        kc = Keycloak(url, token, http)
        sync = Sincronizador(kc, plano, realm, aplicar=not verificar, rotacionar=rotacionar_secret)
        senha = sync.executar(None if verificar else admin_inicial)
    finally:
        if proprio:
            http.close()

    rel = Relatorio(registros=sync.registros)
    if senha is not None:
        rel.senha_temporaria = senha
        rel.email_admin_inicial = admin_inicial.strip().lower() if admin_inicial else None
    painel_id = plano.cliente["clientId"]
    mcp_id = plano.cliente_servico["clientId"]
    capturas_id = plano.cliente_capturas["clientId"] if plano.cliente_capturas is not None else None
    necessarios = [painel_id, mcp_id, *([capturas_id] if capturas_id else [])]
    if not verificar and all(cid in sync.segredos for cid in necessarios):
        pares = [
            ("TUDOIA_OIDC_ISSUER", f"{url}/realms/{realm}"),
            ("TUDOIA_OIDC_CLIENT_ID", painel_id),
            ("TUDOIA_OIDC_CLIENT_SECRET", sync.segredos[painel_id]),
            ("TUDOIA_MCP_CLIENT_ID", mcp_id),
            ("TUDOIA_MCP_CLIENT_SECRET", sync.segredos[mcp_id]),
        ]
        if capturas_id:
            pares += [
                ("TUDOIA_CAPTURAS_CLIENT_ID", capturas_id),
                ("TUDOIA_CAPTURAS_CLIENT_SECRET", sync.segredos[capturas_id]),
            ]
        _gravar_env(env_path, pares, rel.registros)
    return rel


def _credenciais(config: dict[str, str]) -> tuple[str, str]:
    usuario = config.get("TUDOIA_KEYCLOAK_ADMIN") or ""
    senha = config.get("TUDOIA_KEYCLOAK_ADMIN_PASSWORD") or ""
    if usuario and senha:
        return usuario, senha
    if not sys.stdin.isatty():
        raise ErroConexao("defina TUDOIA_KEYCLOAK_ADMIN e TUDOIA_KEYCLOAK_ADMIN_PASSWORD")
    usuario = usuario or input("Usuário admin do realm master: ").strip()
    senha = senha or getpass.getpass("Senha do admin: ")
    if not usuario or not senha:
        raise ErroConexao("usuário e senha do admin são obrigatórios")
    return usuario, senha


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Provisiona o realm tudoia no Keycloak (idempotente).")
    parser.add_argument("--verificar", action="store_true", help="somente leitura; sai com 1 se houver desvio")
    parser.add_argument("--rotacionar-secret", action="store_true", help="gera novo segredo dos clientes tudoia-painel e tudoia-mcp")
    parser.add_argument("--admin-inicial", metavar="EMAIL", help="cria o primeiro administrador do painel")
    args = parser.parse_args(argv)

    try:
        config = montar_config(ENV_PADRAO, dict(os.environ))
        usuario, senha = _credenciais(config)
        rel = provisionar(
            config,
            usuario,
            senha,
            verificar=args.verificar,
            rotacionar_secret=args.rotacionar_secret,
            admin_inicial=args.admin_inicial,
        )
    except ErroValidacao as exc:
        print(f"Erro de validação: {exc}", file=sys.stderr)
        return 1
    except ErroConexao as exc:
        print(f"Erro de conexão ou autenticação: {exc}", file=sys.stderr)
        return 2

    if args.verificar:
        if rel.registros:
            print("Desvios encontrados entre o template e o Keycloak:")
            for registro in rel.registros:
                print(f"  - {registro}")
            return 1
        print("Sem desvios: realm igual ao template.")
        return 0

    if not rel.registros:
        print("igual: nenhuma alteração necessária.")
    for registro in rel.registros:
        print(f"alterado: {registro}")
    if rel.senha_temporaria:
        print(f"Senha temporária de {rel.email_admin_inicial} (exibida uma única vez; troca obrigatória no 1º login):")
        print(rel.senha_temporaria)
    return 0


if __name__ == "__main__":
    sys.exit(main())

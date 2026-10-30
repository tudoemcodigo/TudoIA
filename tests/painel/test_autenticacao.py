"""Autenticação e autorização do painel: regra pura, configuração fail-closed e a aplicação HTTP real.

O fluxo de login contra um IdP real é coberto em tests/keycloak (teste de integração, opt-in).
Aqui testamos as decisões de segurança: quem entra, quem altera, quem é admin, e o que recusa.
"""
import base64
import json
import time

import pytest
from fastapi.testclient import TestClient
from itsdangerous import TimestampSigner

from tudoia_painel.app import criar_app
from tudoia_painel.autenticacao import (
    PAPEL_ADMIN,
    PAPEL_LEITOR,
    PAPEL_OPERADOR,
    ConfigAuth,
    decidir,
    papeis_do_token,
    retorno_seguro,
)

SEGREDO = "s" * 48
CONFIG = ConfigAuth(issuer="https://idp.teste/realms/tudoia", client_id="tudoia-painel",
                    client_secret="segredo-de-teste", segredo_sessao=SEGREDO)
BASE = "http://127.0.0.1:3100"


def cookie(papeis, expira_em=None):
    dados = {"papeis": papeis, "expira_em": expira_em if expira_em is not None else time.time() + 600,
             "verificado_em": time.time(), "usuario": {"email": "x@teste"}}
    return TimestampSigner(SEGREDO).sign(base64.b64encode(json.dumps(dados).encode("utf-8"))).decode()


# ---------------------------------------------------------------- regra de autorização (pura)

@pytest.mark.parametrize("metodo, caminho, papeis, esperado", [
    # sem sessão: tudo em /api exige login, inclusive leitura
    ("GET", "/api/servicos", None, 401),
    ("GET", "/api/servicos", [], 401),
    # leitor: lê, não altera
    ("GET", "/api/servicos", [PAPEL_LEITOR], None),
    ("POST", "/api/servicos/litellm/acao", [PAPEL_LEITOR], 403),
    # operador: altera o que não é administrativo
    ("POST", "/api/servicos/litellm/acao", [PAPEL_OPERADOR], None),
    ("POST", "/api/segredos", [PAPEL_OPERADOR], 403),
    ("POST", "/api/provedores", [PAPEL_OPERADOR], 403),
    ("POST", "/api/governanca/skills/importar", [PAPEL_OPERADOR], 403),
    ("GET", "/api/segredos", [PAPEL_OPERADOR], 403),
    # governança: todos leem; só admin altera (o sync grava tokens nas pastas das instâncias)
    ("GET", "/api/governanca", [PAPEL_LEITOR], None),
    ("GET", "/api/governanca/instancias", [PAPEL_OPERADOR], None),
    ("POST", "/api/governanca/instancias", [PAPEL_OPERADOR], 403),
    ("PUT", "/api/governanca/instancias/x", [PAPEL_OPERADOR], 403),
    ("POST", "/api/governanca/sincronizar", [PAPEL_OPERADOR], 403),
    ("PUT", "/api/governanca/skills/x/conteudo", [PAPEL_OPERADOR], 403),
    ("POST", "/api/governanca/regras", [PAPEL_OPERADOR], 403),
    ("POST", "/api/governanca/sincronizar", [PAPEL_ADMIN], None),
    # admin: tudo
    ("GET", "/api/segredos", [PAPEL_ADMIN], None),
    ("POST", "/api/provedores", [PAPEL_ADMIN], None),
    ("POST", "/api/governanca/skills/importar", [PAPEL_ADMIN], None),
    # sessão é sempre consultável; fora de /api não há regra
    ("GET", "/api/sessao", None, None),
    ("GET", "/app/", None, None),
    ("GET", "/auth/login", None, None),
    # prefixo parecido não vira exceção: /api/segredos-x continua exigindo admin
    ("POST", "/api/segredos-x", [PAPEL_OPERADOR], 403),
])
def test_decidir(metodo, caminho, papeis, esperado):
    resultado = decidir(metodo, caminho, papeis)
    assert (resultado[0] if resultado else None) == esperado


def test_papel_desconhecido_nao_concede_acesso():
    # Papel fora da lista não é reconhecido: sem papel válido, a sessão não vale nada.
    assert papeis_do_token({"groups": ["/outro-sistema-admin"]}) == []
    assert papeis_do_token({"realm_access": {"roles": ["offline_access", "uma-role-qualquer"]}}) == []


def test_papeis_aceitam_grupo_com_barra_e_papel_de_realm():
    assert papeis_do_token({"groups": ["/tudoia-admin"]}) == [PAPEL_ADMIN]
    assert papeis_do_token({"realm_access": {"roles": [PAPEL_LEITOR, PAPEL_OPERADOR]}}) == [PAPEL_OPERADOR, PAPEL_LEITOR]


@pytest.mark.parametrize("valor, esperado", [
    ("/app/", "/app/"),
    ("/app/?aba=modelos", "/app/?aba=modelos"),
    ("https://evil.example/", "/app/"),
    ("//evil.example/x", "/app/"),
    ("/\\evil.example", "/app/"),
    ("/api/segredos", "/app/"),
    (None, "/app/"),
    ("", "/app/"),
])
def test_retorno_seguro_bloqueia_open_redirect(valor, esperado):
    assert retorno_seguro(valor) == esperado


# ---------------------------------------------------------------- configuração fail-closed

def test_sem_issuer_ou_sem_segredo_nao_ha_configuracao():
    base = {"TUDOIA_OIDC_ISSUER": "https://idp/realms/x", "TUDOIA_OIDC_CLIENT_ID": "c",
            "TUDOIA_OIDC_CLIENT_SECRET": "s", "TUDOIA_SESSAO_SEGREDO": SEGREDO}
    assert ConfigAuth.do_ambiente(base) is not None
    assert ConfigAuth.do_ambiente({**base, "TUDOIA_OIDC_ISSUER": ""}) is None
    assert ConfigAuth.do_ambiente({**base, "TUDOIA_OIDC_ISSUER": "ftp://idp"}) is None
    assert ConfigAuth.do_ambiente({**base, "TUDOIA_OIDC_CLIENT_SECRET": ""}) is None
    # segredo de sessão curto demais: recusa, em vez de assinar cookies com chave fraca
    assert ConfigAuth.do_ambiente({**base, "TUDOIA_SESSAO_SEGREDO": "curto"}) is None


def test_issuer_com_barra_final_e_cookie_seguro_por_flag():
    base = {"TUDOIA_OIDC_ISSUER": "https://idp/realms/x/", "TUDOIA_OIDC_CLIENT_ID": "c",
            "TUDOIA_OIDC_CLIENT_SECRET": "s", "TUDOIA_SESSAO_SEGREDO": SEGREDO}
    cfg = ConfigAuth.do_ambiente(base)
    assert cfg.issuer == "https://idp/realms/x" and cfg.cookie_seguro is False
    assert ConfigAuth.do_ambiente({**base, "TUDOIA_COOKIE_SEGURO": "1"}).cookie_seguro is True


# ---------------------------------------------------------------- aplicação HTTP real

@pytest.fixture
def app_auth(tmp_path):
    raiz = tmp_path / "raiz"
    raiz.mkdir()
    return criar_app(raiz, servicos=_ServicoFalso(), home=tmp_path / "home", autenticacao=CONFIG)


class _ServicoFalso:
    def listar(self):
        return []

    def acao(self, nome, acao):
        pass

    def acao_todos(self, acao):
        pass


def test_sem_configuracao_todo_api_responde_503(tmp_path):
    raiz = tmp_path / "raiz"
    raiz.mkdir()
    with TestClient(criar_app(raiz, servicos=_ServicoFalso(), home=tmp_path, autenticacao=None), base_url=BASE) as c:
        c.cookies.set("tudoia_sessao", cookie([PAPEL_ADMIN]))  # mesmo com sessão válida: não há IdP configurado
        r = c.get("/api/servicos")
        assert r.status_code == 503
        assert r.json()["erro"]["codigo"] == "auth_nao_configurada"
        assert c.get("/api/sessao").json()["configurado"] is False


def test_sem_login_api_recusa_e_app_publico(app_auth):
    with TestClient(app_auth, base_url=BASE) as c:
        r = c.get("/api/servicos")
        assert r.status_code == 401
        assert r.json()["erro"]["codigo"] == "nao_autenticado"
        # a casca do SPA e o estático são públicos (não têm segredo); os dados não
        assert c.get("/app/").status_code == 200
        sessao = c.get("/api/sessao").json()
        assert sessao["autenticado"] is False and sessao["papeis"] == []


def test_cookie_falsificado_nao_vale(app_auth):
    with TestClient(app_auth, base_url=BASE) as c:
        assinado = cookie([PAPEL_ADMIN])
        c.cookies.set("tudoia_sessao", assinado[:-4] + "AAAA")  # assinatura adulterada
        assert c.get("/api/servicos").status_code == 401


def test_cookie_assinado_com_outra_chave_nao_vale(app_auth):
    forjado = TimestampSigner("outra-chave-qualquer-que-o-atacante-tem-1234567890").sign(
        base64.b64encode(json.dumps({"papeis": [PAPEL_ADMIN], "expira_em": time.time() + 600}).encode())).decode()
    with TestClient(app_auth, base_url=BASE) as c:
        c.cookies.set("tudoia_sessao", forjado)
        assert c.get("/api/servicos").status_code == 401


def test_sessao_expirada_nao_vale(app_auth):
    with TestClient(app_auth, base_url=BASE) as c:
        c.cookies.set("tudoia_sessao", cookie([PAPEL_ADMIN], expira_em=time.time() - 1))
        assert c.get("/api/servicos").status_code == 401


def test_leitor_le_mas_nao_altera(app_auth):
    with TestClient(app_auth, base_url=BASE) as c:
        c.cookies.set("tudoia_sessao", cookie([PAPEL_LEITOR]))
        assert c.get("/api/servicos").status_code == 200
        r = c.post("/api/servicos/litellm/acao", json={"acao": "start"})
        assert r.status_code == 403
        assert r.json()["erro"]["codigo"] == "papel_insuficiente"


def test_operador_altera_mas_nao_e_admin(app_auth):
    with TestClient(app_auth, base_url=BASE) as c:
        c.cookies.set("tudoia_sessao", cookie([PAPEL_OPERADOR]))
        assert c.get("/api/segredos").status_code == 403
        assert c.post("/api/provedores", json={}).status_code == 403


def test_sessao_devolve_papeis_e_flags(app_auth):
    with TestClient(app_auth, base_url=BASE) as c:
        c.cookies.set("tudoia_sessao", cookie([PAPEL_OPERADOR]))
        r = c.get("/api/sessao").json()
        assert r["autenticado"] is True
        assert r["papeis"] == [PAPEL_OPERADOR]
        assert r["pode_alterar"] is True and r["admin"] is False


def test_logout_recusa_origem_de_outro_site(app_auth):
    """Logout é POST e passa pela mesma guarda de origem: outro site não consegue derrubar a sessão."""
    with TestClient(app_auth, base_url=BASE) as c:
        c.cookies.set("tudoia_sessao", cookie([PAPEL_ADMIN]))
        r = c.post("/auth/logout", json={}, headers={"origin": "http://evil.example"})
        assert r.status_code == 403


# ---------------------------------------------------------------- confirmação da sessão no Keycloak


def cookie_antigo(papeis):
    """Sessão cuja última confirmação no Keycloak passou do TTL: o guarda precisa consultar de novo."""
    dados = {"papeis": papeis, "expira_em": time.time() + 600, "verificado_em": time.time() - 3600,
             "access_token": "token-de-teste", "usuario": {"email": "x@teste"}}
    return TimestampSigner(SEGREDO).sign(base64.b64encode(json.dumps(dados).encode("utf-8"))).decode()


def _userinfo_falso(monkeypatch, resposta):
    chamadas = []

    async def falso(issuer, access_token):
        chamadas.append(access_token)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta

    monkeypatch.setattr("tudoia_painel.autenticacao.consultar_userinfo", falso)
    return chamadas


def test_conta_desativada_derruba_a_sessao_antes_do_tempo(app_auth, monkeypatch):
    """Antes: a sessão valia até 8 h mesmo com a conta removida. Agora o Keycloak é consultado e recusa."""
    chamadas = _userinfo_falso(monkeypatch, None)
    with TestClient(app_auth, base_url=BASE) as c:
        c.cookies.set("tudoia_sessao", cookie_antigo([PAPEL_ADMIN]))
        r = c.get("/api/servicos")
        assert r.status_code == 401
    assert chamadas == ["token-de-teste"]


def test_troca_de_papel_vale_na_hora(app_auth, monkeypatch):
    _userinfo_falso(monkeypatch, {"sub": "1", "groups": ["/tudoia-operador"]})
    with TestClient(app_auth, base_url=BASE) as c:
        c.cookies.set("tudoia_sessao", cookie_antigo([PAPEL_LEITOR]))  # era leitor no login
        assert c.post("/api/servicos/litellm/acao", json={"acao": "start"}).status_code != 403


def test_sem_papel_do_painel_no_keycloak_derruba_a_sessao(app_auth, monkeypatch):
    _userinfo_falso(monkeypatch, {"sub": "1", "groups": []})
    with TestClient(app_auth, base_url=BASE) as c:
        c.cookies.set("tudoia_sessao", cookie_antigo([PAPEL_ADMIN]))
        assert c.get("/api/servicos").status_code == 401


def test_keycloak_indisponivel_nega_acesso_fail_closed(app_auth, monkeypatch):
    _userinfo_falso(monkeypatch, ConnectionError("keycloak fora"))
    with TestClient(app_auth, base_url=BASE) as c:
        c.cookies.set("tudoia_sessao", cookie_antigo([PAPEL_ADMIN]))
        r = c.get("/api/servicos")
        assert r.status_code == 503
        assert r.json()["erro"]["codigo"] == "identidade_indisponivel"


def test_dentro_do_ttl_nao_consulta_o_keycloak(app_auth, monkeypatch):
    chamadas = _userinfo_falso(monkeypatch, None)
    with TestClient(app_auth, base_url=BASE) as c:
        c.cookies.set("tudoia_sessao", cookie([PAPEL_ADMIN]))  # verificado agora
        assert c.get("/api/servicos").status_code == 200
    assert chamadas == []


def test_sessao_sem_marca_de_verificacao_e_consultada(app_auth, monkeypatch):
    """Cookie de versão antiga (sem verificado_em) não pode passar sem confirmação."""
    chamadas = _userinfo_falso(monkeypatch, None)
    dados = {"papeis": [PAPEL_ADMIN], "expira_em": time.time() + 600}
    antigo = TimestampSigner(SEGREDO).sign(base64.b64encode(json.dumps(dados).encode("utf-8"))).decode()
    with TestClient(app_auth, base_url=BASE) as c:
        c.cookies.set("tudoia_sessao", antigo)
        assert c.get("/api/servicos").status_code == 401
    assert len(chamadas) == 1


def _cookie_cru(dados):
    return TimestampSigner(SEGREDO).sign(base64.b64encode(json.dumps(dados).encode("utf-8"))).decode()


def test_verificado_em_no_futuro_nao_escapa_da_confirmacao(app_auth, monkeypatch):
    """Quem tiver o segredo de sessão forja o cookie, mas não um access_token que o Keycloak aceite."""
    chamadas = _userinfo_falso(monkeypatch, None)
    forjado = _cookie_cru({"papeis": [PAPEL_ADMIN], "expira_em": time.time() + 600,
                           "verificado_em": time.time() + 10**9, "access_token": "forjado"})
    with TestClient(app_auth, base_url=BASE) as c:
        c.cookies.set("tudoia_sessao", forjado)
        assert c.get("/api/servicos").status_code == 401
    assert chamadas == ["forjado"]


@pytest.mark.parametrize("verificado_em", ["agora", None, True, [1]])
def test_verificado_em_invalido_nao_derruba_o_painel(app_auth, monkeypatch, verificado_em):
    chamadas = _userinfo_falso(monkeypatch, None)
    with TestClient(app_auth, base_url=BASE) as c:
        c.cookies.set("tudoia_sessao", _cookie_cru({"papeis": [PAPEL_ADMIN], "expira_em": time.time() + 600,
                                                     "verificado_em": verificado_em}))
        assert c.get("/api/servicos").status_code == 401
    assert len(chamadas) == 1


def test_expira_em_alem_da_idade_maxima_nao_vale(app_auth):
    with TestClient(app_auth, base_url=BASE) as c:
        c.cookies.set("tudoia_sessao", cookie([PAPEL_ADMIN], expira_em=time.time() + 10 * 365 * 86400))
        assert c.get("/api/servicos").status_code == 401


def test_operador_nao_cria_instancia_nem_sincroniza(app_auth):
    """Operador apontava uma instância para pasta dele e o sync gravava os tokens de MCP ali."""
    with TestClient(app_auth, base_url=BASE) as c:
        c.cookies.set("tudoia_sessao", cookie([PAPEL_OPERADOR]))
        r = c.post("/api/governanca/instancias", json={"id": "minha", "cliente": "claude", "caminho": "C:/Temp/x"})
        assert r.status_code == 403 and r.json()["erro"]["codigo"] == "papel_insuficiente"
        assert c.post("/api/governanca/sincronizar", json={}).status_code == 403


def test_callback_com_sessao_ativa_redireciona_direto(app_auth):
    """Usuário que dá F5 no callback ou volta pelo histórico com sessão ativa não recebe erro."""
    with TestClient(app_auth, base_url=BASE, follow_redirects=False) as c:
        c.cookies.set("tudoia_sessao", cookie([PAPEL_ADMIN]))
        r = c.get("/auth/callback?code=expirado&state=xyz")
        assert r.status_code == 303
        assert r.headers["location"] == "/app/"


def test_callback_recusado_para_navegador_redireciona_login(app_auth, monkeypatch):
    """Navegador com code expirado ou mismatching_state é redirecionado para novo login limpo."""
    from authlib.integrations.base_client.errors import OAuthError

    async def _falha_oauth(*args, **kwargs):
        raise OAuthError("mismatching_state")

    monkeypatch.setattr("authlib.integrations.starlette_client.StarletteOAuth2App.authorize_access_token", _falha_oauth)
    with TestClient(app_auth, base_url=BASE, follow_redirects=False) as c:
        r = c.get("/auth/callback?code=expirado&state=xyz", headers={"accept": "text/html,application/xhtml+xml"})
        assert r.status_code == 303
        assert r.headers["location"].startswith("/auth/login?retorno=")


def test_callback_recusado_para_api_devolve_401(app_auth, monkeypatch):
    """Cliente de API ou chamada sem HTML recebe o erro JSON 401."""
    from authlib.integrations.base_client.errors import OAuthError

    async def _falha_oauth(*args, **kwargs):
        raise OAuthError("mismatching_state")

    monkeypatch.setattr("authlib.integrations.starlette_client.StarletteOAuth2App.authorize_access_token", _falha_oauth)
    with TestClient(app_auth, base_url=BASE, follow_redirects=False) as c:
        r = c.get("/auth/callback?code=expirado&state=xyz", headers={"accept": "application/json"})
        assert r.status_code == 401
        assert r.json()["erro"]["codigo"] == "login_recusado"


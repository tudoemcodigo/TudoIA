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



# ---------------------------------------------------------------- login sem laço, com várias abas e sessão antiga
# O estado do OAuth ficava no cookie de sessão: abas abertas quando a sessão vencia iam ao login juntas, uma
# sobrescrevia o cookie da outra e, com o SSO do Keycloak, giravam até ERR_TOO_MANY_REDIRECTS.

from urllib.parse import parse_qs, quote, urlparse  # noqa: E402

from starlette.responses import RedirectResponse  # noqa: E402

from tudoia_painel.autenticacao import (  # noqa: E402
    MAX_TENTATIVAS_LOGIN,
    PREFIXO_COOKIE_LOGIN,
    MemoriaComValidade,
    _integracao_no_servidor,
)

HTML = {"accept": "text/html,application/xhtml+xml"}


@pytest.fixture
def idp_falso(monkeypatch):
    """Troca a ida ao Keycloak: o redirect guarda o estado como o authlib faria; o token sai de `respostas`."""
    respostas = {"token": None}

    async def _redirect(self, request, redirect_uri=None, **kwargs):
        await self.framework.set_state_data(request.session, kwargs["state"], {"redirect_uri": redirect_uri})
        return RedirectResponse(f"https://idp.teste/auth?state={kwargs['state']}", status_code=302)

    async def _token(self, request, **kwargs):
        from authlib.integrations.base_client.errors import OAuthError
        state = request.query_params.get("state")
        if not await self.framework.get_state_data(request.session, state):
            raise OAuthError("mismatching_state")
        await self.framework.clear_state_data(request.session, state)
        return respostas["token"] or {"userinfo": {"sub": "u1", "email": "x@teste", "groups": ["/tudoia-admin"]},
                                      "access_token": "a" * 1200, "id_token": "i" * 900}

    monkeypatch.setattr("authlib.integrations.starlette_client.StarletteOAuth2App.authorize_redirect", _redirect)
    monkeypatch.setattr("authlib.integrations.starlette_client.StarletteOAuth2App.authorize_access_token", _token)
    return respostas


def _iniciar_login_por(c, alvo):
    r = c.get(alvo)
    assert r.status_code == 302, r.text
    return parse_qs(urlparse(r.headers["location"]).query)["state"][0], r


def _iniciar_login(c, retorno="/app/"):
    return _iniciar_login_por(c, f"/auth/login?retorno={quote(retorno, safe='/')}")


def test_login_nao_grava_o_cookie_de_sessao_e_amarra_o_state_ao_navegador(app_auth, idp_falso):
    with TestClient(app_auth, base_url=BASE, follow_redirects=False) as c:
        state, r = _iniciar_login(c)
    assert state.startswith("1")
    cookies = r.headers.get_list("set-cookie")
    assert not any(k.startswith("tudoia_sessao=") for k in cookies)
    (do_login,) = [k for k in cookies if k.startswith(f"{PREFIXO_COOKIE_LOGIN}{state}=")]
    assert "Path=/auth/callback" in do_login and "HttpOnly" in do_login and "SameSite=lax" in do_login


def test_varias_abas_logando_juntas_todas_entram(app_auth, idp_falso):
    """A reprodução real: 3 a 5 abas recarregadas juntas com o SSO do Keycloak vivo."""
    with TestClient(app_auth, base_url=BASE, follow_redirects=False) as c:
        estados = [_iniciar_login(c, f"/app/#aba{i}")[0] for i in range(5)]
        for i, state in enumerate(estados):
            r = c.get("/auth/callback", params={"state": state, "code": "x"}, headers=HTML)
            assert r.status_code == 303 and r.headers["location"] == f"/app/#aba{i}", (i, r.text)
        assert c.get("/api/sessao").json()["autenticado"] is True


def test_callback_com_state_de_outro_navegador_e_recusado(app_auth, idp_falso):
    """Sem o cookie do login, um state válido não basta (CSRF de login): nova tentativa limpa, não entra."""
    with TestClient(app_auth, base_url=BASE, follow_redirects=False) as atacante:
        state, _ = _iniciar_login(atacante)
    with TestClient(app_auth, base_url=BASE, follow_redirects=False) as vitima:
        r = vitima.get("/auth/callback", params={"state": state, "code": "x"}, headers=HTML)
        assert r.status_code == 303 and "tentativa=2" in r.headers["location"]
        assert vitima.get("/api/sessao").json()["autenticado"] is False


def test_segunda_falha_mostra_pagina_e_nao_redireciona(app_auth, idp_falso):
    with TestClient(app_auth, base_url=BASE, follow_redirects=False) as c:
        primeira = c.get("/auth/callback", params={"state": "x" * 30, "code": "x"}, headers=HTML)
        assert primeira.status_code == 303
        alvo = primeira.headers["location"]
        assert alvo.startswith("/auth/login?") and "tentativa=2" in alvo
        state, _ = _iniciar_login_por(c, alvo)
        assert state.startswith(str(MAX_TENTATIVAS_LOGIN))
        c.cookies.delete(f"{PREFIXO_COOKIE_LOGIN}{state}", path="/auth/callback")  # o cookie não chegou de novo
        segunda = c.get("/auth/callback", params={"state": state, "code": "x"}, headers=HTML)
        assert segunda.status_code == 400 and "location" not in segunda.headers
        assert "Entrar de novo" in segunda.text


@pytest.mark.parametrize("tentativa, esperado", [(0, "1"), (-5, "1"), (99, str(MAX_TENTATIVAS_LOGIN))])
def test_tentativa_do_login_fica_na_faixa(app_auth, idp_falso, tentativa, esperado):
    with TestClient(app_auth, base_url=BASE, follow_redirects=False) as c:
        state, _ = _iniciar_login_por(c, f"/auth/login?tentativa={tentativa}")
    assert state[0] == esperado


def test_sessao_vencida_e_grande_nao_atrapalha_o_novo_login(app_auth, idp_falso):
    antiga = _cookie_cru({"papeis": [PAPEL_ADMIN], "expira_em": time.time() - 60, "verificado_em": 0,
                          "access_token": "a" * 1800, "id_token": "i" * 1400})
    with TestClient(app_auth, base_url=BASE, follow_redirects=False) as c:
        c.cookies.set("tudoia_sessao", antiga)
        state, _ = _iniciar_login(c, "/app/#modelos")
        r = c.get("/auth/callback", params={"state": state, "code": "x"}, headers=HTML)
        assert r.status_code == 303 and r.headers["location"] == "/app/#modelos"
        assert c.get("/api/sessao").json()["autenticado"] is True


def test_login_com_sessao_valida_volta_direto_sem_ir_ao_keycloak(app_auth, idp_falso):
    with TestClient(app_auth, base_url=BASE, follow_redirects=False) as c:
        c.cookies.set("tudoia_sessao", cookie([PAPEL_ADMIN]))
        r = c.get("/auth/login?retorno=/app/%23custos")
        assert r.status_code == 303 and r.headers["location"] == "/app/#custos"
        r = c.get("/auth/login?retorno=https://site.mau/")
        assert r.headers["location"] == "/app/"


def test_callback_atrasado_de_outra_aba_com_sessao_ja_valida_entra(app_auth, idp_falso):
    with TestClient(app_auth, base_url=BASE, follow_redirects=False) as c:
        primeiro, _ = _iniciar_login(c, "/app/#a")
        segundo, _ = _iniciar_login(c, "/app/#b")
        assert c.get("/auth/callback", params={"state": segundo, "code": "x"}, headers=HTML).status_code == 303
        r = c.get("/auth/callback", params={"state": primeiro, "code": "velho"}, headers=HTML)
        assert r.status_code == 303 and r.headers["location"] == "/app/#a"


def _metadados_falsos(monkeypatch):
    async def _meta(self):
        return {"end_session_endpoint": "https://idp.teste/logout"}

    monkeypatch.setattr("authlib.integrations.starlette_client.StarletteOAuth2App.load_server_metadata", _meta)


def test_id_token_fica_no_servidor_e_o_logout_o_envia_ao_keycloak(app_auth, idp_falso, monkeypatch):
    """Com os dois tokens reais no cookie ele passava de 4 KB (o navegador descartava). O id_token agora fica no
    servidor e o logout continua mandando o id_token_hint, sem a tela de confirmação do Keycloak."""
    _metadados_falsos(monkeypatch)
    idp_falso["token"] = {"userinfo": {"sub": "u1", "groups": ["/tudoia-admin"]},
                          "access_token": "a" * 2200, "id_token": "id-token-de-teste" + "i" * 1800}
    with TestClient(app_auth, base_url=BASE, follow_redirects=False) as c:
        state, _ = _iniciar_login(c)
        r = c.get("/auth/callback", params={"state": state, "code": "x"}, headers=HTML)
        assert r.status_code == 303 and len(r.cookies["tudoia_sessao"]) < 4096
        sessao = json.loads(base64.b64decode(r.cookies["tudoia_sessao"].split(".")[0]))
        assert "id_token" not in sessao and sessao["access_token"] and sessao["sid"]
        saida = c.post("/auth/logout", json={}, headers={"origin": BASE}).json()["url"]
        assert "id_token_hint=id-token-de-teste" in saida
        # o id_token sai da memória junto com a sessão: um segundo logout não o reaproveita
        c.cookies.set("tudoia_sessao", r.cookies["tudoia_sessao"])
        assert "id_token_hint" not in c.post("/auth/logout", json={}, headers={"origin": BASE}).json()["url"]


def test_logout_com_sid_estranho_nao_quebra(app_auth, monkeypatch):
    _metadados_falsos(monkeypatch)
    with TestClient(app_auth, base_url=BASE) as c:
        c.cookies.set("tudoia_sessao", _cookie_cru({"sid": ["x"], "papeis": [PAPEL_ADMIN], "expira_em": time.time() + 60}))
        r = c.post("/auth/logout", json={}, headers={"origin": BASE})
        assert r.status_code == 200 and "id_token_hint" not in r.json()["url"]


def test_logins_pendentes_vencem_e_tem_teto():
    pend = MemoriaComValidade(ttl_s=60, maximo=3)
    for i in range(5):
        pend.guardar(f"s{i}", {"i": i})
        time.sleep(0.001)
    assert pend.ler("s0") is None and pend.ler("s1") is None and pend.ler("s4") == {"i": 4}
    vencido = MemoriaComValidade(ttl_s=-1)
    vencido.guardar("s", {"i": 1})
    assert vencido.ler("s") is None and vencido.ler(None) is None


def test_integracao_guarda_o_estado_no_servidor_sem_tocar_na_sessao():
    import asyncio
    pend = MemoriaComValidade()
    integ = _integracao_no_servidor(pend).framework_integration_cls("tudoia")
    sessao = {}
    asyncio.run(integ.set_state_data(sessao, "s1", {"nonce": "n"}))
    assert sessao == {} and asyncio.run(integ.get_state_data(sessao, "s1")) == {"nonce": "n"}
    asyncio.run(integ.clear_state_data(sessao, "s1"))
    assert asyncio.run(integ.get_state_data(sessao, "s1")) is None

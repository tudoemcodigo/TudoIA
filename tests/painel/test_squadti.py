"""Rotas /api/squadti: o painel só repassa pedidos validados à API local da Squad. Seam: HTTP do painel e uma API falsa real
(servidor HTTP em thread), nada de métodos privados."""
import base64
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient
from itsdangerous import TimestampSigner

from tudoia_painel.app import criar_app
from tudoia_painel.autenticacao import PAPEL_LEITOR, PAPEL_OPERADOR, ConfigAuth
from tudoia_painel.rotas import squadti

SEGREDO = "t" * 48
CONFIG_AUTH = ConfigAuth(issuer="https://idp.teste/realms/tudoia", client_id="tudoia-painel",
                         client_secret="segredo-de-teste", segredo_sessao=SEGREDO)
BASE = "http://127.0.0.1:3100"
TOKEN = "a1" * 20


def cookie(papeis):
    dados = {"papeis": papeis, "expira_em": time.time() + 3600, "verificado_em": time.time(), "usuario": {"email": "t@local"}}
    return TimestampSigner(SEGREDO).sign(base64.b64encode(json.dumps(dados).encode())).decode()


class ApiFalsa:
    """Imita a API da Squad por httpx.MockTransport: registra o que recebe e devolve a resposta combinada."""

    def __init__(self):
        self.pedidos = []
        self.resposta = (200, {"ok": True})
        self.url = "http://127.0.0.1:8790"

    def __call__(self, request: httpx.Request) -> httpx.Response:
        corpo = json.loads(request.content) if request.content else None
        self.pedidos.append({"metodo": request.method, "caminho": request.url.raw_path.decode(),
                             "auth": request.headers.get("authorization"), "corpo": corpo})
        status, dados = self.resposta
        return httpx.Response(status, json=dados)


@pytest.fixture
def api_falsa(monkeypatch):
    a = ApiFalsa()
    monkeypatch.setattr(squadti, "TRANSPORTE", httpx.MockTransport(a))
    return a


def montar(tmp_path, env_extra, papel):
    raiz, home = tmp_path / "raiz", tmp_path / "home"
    raiz.mkdir()
    home.mkdir()
    (raiz / ".env").write_text("\n".join(env_extra) + "\n", encoding="utf-8")
    c = TestClient(criar_app(raiz, object(), home, autenticacao=CONFIG_AUTH), base_url=BASE)
    c.cookies.set("tudoia_sessao", cookie([papel]))
    return c


@pytest.fixture
def operador(tmp_path, api_falsa):
    with montar(tmp_path, [f"TUDOIA_SQUADTI_TOKEN={TOKEN}"], PAPEL_OPERADOR) as c:
        yield c


@pytest.fixture
def leitor(tmp_path, api_falsa):
    with montar(tmp_path, [f"TUDOIA_SQUADTI_TOKEN={TOKEN}"], PAPEL_LEITOR) as c:
        yield c


# ---------------------------------------------------------------- repasse
def test_listar_repassa_com_o_token_do_env(operador, api_falsa):
    api_falsa.resposta = (200, {"tarefas": []})
    r = operador.get("/api/squadti/tarefas")
    assert r.status_code == 200 and r.json() == {"tarefas": []}
    assert api_falsa.pedidos == [{"metodo": "GET", "caminho": "/api/tarefas", "auth": f"Bearer {TOKEN}", "corpo": None}]


def test_iniciar_local_estrito_nao_pede_consentimento(operador, api_falsa):
    api_falsa.resposta = (202, {"tarefa": "T1"})
    r = operador.post("/api/squadti/tarefas", json={"tarefa": "T1", "briefing": "x"})
    assert r.status_code == 202
    assert api_falsa.pedidos[0]["corpo"] == {"tarefa": "T1", "briefing": "x", "perfil": "local-estrito",
                                              "consentimento_nuvem": False}


def test_leitor_ve_mas_nao_inicia_nem_aprova(leitor, api_falsa):
    assert leitor.get("/api/squadti/tarefas").status_code == 200
    antes = len(api_falsa.pedidos)
    assert leitor.post("/api/squadti/tarefas", json={"tarefa": "T1", "briefing": "x"}).status_code == 403
    assert leitor.post("/api/squadti/tarefas/T1/aprovar", json={}).status_code == 403
    assert leitor.post("/api/squadti/tarefas/T1/aprovar-release", json={}).status_code == 403
    assert len(api_falsa.pedidos) == antes


def test_operador_aprova_spec_e_release(operador, api_falsa):
    assert operador.post("/api/squadti/tarefas/T1/aprovar", json={}).status_code == 202
    assert operador.post("/api/squadti/tarefas/T1/aprovar-release", json={}).status_code == 202
    assert [p["caminho"] for p in api_falsa.pedidos] == ["/api/tarefas/T1/aprovar", "/api/tarefas/T1/aprovar-release"]


# ---------------------------------------------------------------- privacidade
@pytest.mark.parametrize("perfil", ["local", "hibrido", "nuvem"])
def test_perfil_que_pode_sair_da_maquina_exige_consentimento(operador, api_falsa, perfil):
    r = operador.post("/api/squadti/tarefas", json={"tarefa": "T1", "briefing": "x", "perfil": perfil})
    assert r.status_code == 422 and r.json()["erro"]["codigo"] == "consentimento_nuvem"
    assert api_falsa.pedidos == []
    ok = operador.post("/api/squadti/tarefas",
                       json={"tarefa": "T1", "briefing": "x", "perfil": perfil, "consentimento_nuvem": True})
    assert ok.status_code == 202 and api_falsa.pedidos[0]["corpo"]["consentimento_nuvem"] is True


def test_perfil_pago_e_desconhecido_nao_passam(operador, api_falsa):
    for perfil in ("max", "tudoia-auto", ""):
        r = operador.post("/api/squadti/tarefas",
                          json={"tarefa": "T1", "briefing": "x", "perfil": perfil, "consentimento_nuvem": True})
        assert r.status_code == 422, perfil
    assert api_falsa.pedidos == []


# ---------------------------------------------------------------- entrada
@pytest.mark.parametrize("tarefa", ["..", "a/b", "a%2fb", "-x", "x" * 65, "a b"])
def test_id_de_tarefa_invalido_nunca_chega_a_api(operador, api_falsa, tarefa):
    assert operador.get(f"/api/squadti/tarefas/{tarefa}").status_code in (404, 422)
    assert operador.post("/api/squadti/tarefas", json={"tarefa": tarefa, "briefing": "x"}).status_code == 422
    assert api_falsa.pedidos == []


def test_corpo_com_campo_extra_e_briefing_vazio_sao_recusados(operador, api_falsa):
    assert operador.post("/api/squadti/tarefas", json={"tarefa": "T1", "briefing": "x", "modelo": "outro"}).status_code == 422
    assert operador.post("/api/squadti/tarefas", json={"tarefa": "T1", "briefing": ""}).status_code == 422
    assert operador.post("/api/squadti/tarefas/T1/responder", json={"resposta": ""}).status_code == 422
    assert api_falsa.pedidos == []


def test_arquivo_repassa_o_caminho_como_parametro(operador, api_falsa):
    operador.get("/api/squadti/tarefas/T1/arquivo", params={"caminho": "docs/a b.md&x=1"})
    assert api_falsa.pedidos[0]["caminho"].startswith("/api/tarefas/T1/arquivo?caminho=docs%2Fa+b.md%26x%3D1")
    assert operador.get("/api/squadti/tarefas/T1/arquivo").status_code == 422


# ---------------------------------------------------------------- falha fechado
def test_sem_token_no_env_tudo_responde_503(tmp_path):
    with montar(tmp_path, ["TZ=UTC"], PAPEL_OPERADOR) as c:
        assert c.get("/api/squadti/estado").json() == {"configurado": False, "no_ar": False,
                                                       "perfis": ["local-estrito", "local", "hibrido", "nuvem"]}
        for r in (c.get("/api/squadti/tarefas"), c.post("/api/squadti/tarefas/T1/aprovar", json={})):
            assert r.status_code == 503 and r.json()["erro"]["codigo"] == "indisponivel"


def test_token_curto_e_recusado(tmp_path):
    with montar(tmp_path, ["TUDOIA_SQUADTI_TOKEN=curto"], PAPEL_OPERADOR) as c:
        assert c.get("/api/squadti/tarefas").status_code == 503


@pytest.mark.parametrize("url", ["http://evil.example:8790", "https://127.0.0.1:8790", "http://10.0.0.5:8790"])
def test_url_fora_do_loopback_nunca_e_chamada(tmp_path, api_falsa, url):
    with montar(tmp_path, [f"TUDOIA_SQUADTI_TOKEN={TOKEN}", f"TUDOIA_SQUADTI_URL={url}"], PAPEL_OPERADOR) as c:
        assert c.get("/api/squadti/tarefas").status_code == 503
        assert api_falsa.pedidos == []


def test_api_fora_do_ar_vira_503_sem_detalhe_interno(tmp_path, monkeypatch):
    def cai(request):
        raise httpx.ConnectError("Connect refused 127.0.0.1:8790", request=request)
    monkeypatch.setattr(squadti, "TRANSPORTE", httpx.MockTransport(cai))
    with montar(tmp_path, [f"TUDOIA_SQUADTI_TOKEN={TOKEN}"], PAPEL_OPERADOR) as c:
        r = c.get("/api/squadti/tarefas")
        assert r.status_code == 503 and "Connect" not in r.text
        assert c.get("/api/squadti/estado").json()["no_ar"] is False


def test_erro_4xx_da_api_passa_com_codigo_e_mensagem(operador, api_falsa):
    api_falsa.resposta = (409, {"erro": {"codigo": "ocupado", "mensagem": "já há uma execução em andamento (T0)"}})
    r = operador.post("/api/squadti/tarefas/T1/aprovar", json={})
    assert r.status_code == 409 and r.json()["erro"]["codigo"] == "ocupado"


def test_token_recusado_e_erro_5xx_viram_503_sem_vazar_corpo(operador, api_falsa):
    for status in (401, 500):
        api_falsa.resposta = (status, {"erro": {"codigo": "x", "mensagem": "segredo-interno-123"}})
        r = operador.get("/api/squadti/tarefas")
        assert r.status_code == 503 and "segredo-interno-123" not in r.text


def test_estado_no_ar(operador, api_falsa):
    assert operador.get("/api/squadti/estado").json()["no_ar"] is True

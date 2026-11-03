"""Teste direto de modelos na API do provedor: POST /api/provedores/{id}/testar-modelos.

Seam: HTTP (TestClient) com o catálogo real copiado para uma raiz temporária. A rede é falsa no nível do transporte
(httpx.MockTransport dentro do cliente real do serviço): nenhuma chamada sai da máquina."""
import json
import time
from types import SimpleNamespace

import httpx
import pytest

from tests.painel.test_painel import PAPEL_ADMIN, cenario, sessao_assinada  # noqa: F401  (fixture)
from tudoia_painel import provedores_service as ps
from tudoia_painel.autenticacao import PAPEL_LEITOR, PAPEL_OPERADOR, decidir

RESPOSTA_OK = {"choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}}]}
CHAVE_GROQ = "gsk_123456"   # valor do .env do cenário


class Rede:
    """Responde com `self.responder(pedido)` e guarda cada pedido recebido."""

    def __init__(self):
        self.pedidos: list[httpx.Request] = []
        self.responder = lambda req: httpx.Response(200, json=RESPOSTA_OK)
        self.sonos: list[float] = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.pedidos.append(req)
        return self.responder(req)


@pytest.fixture
def rede(monkeypatch):
    r = Rede()
    real = ps._cliente_teste_direto
    monkeypatch.setattr(ps, "_cliente_teste_direto", lambda: real(transporte=httpx.MockTransport(r)))
    monkeypatch.setattr(ps, "time", SimpleNamespace(sleep=r.sonos.append, monotonic=time.monotonic))
    return r


def _env_extra(c, texto: str) -> None:
    with open(c.raiz / ".env", "a", encoding="utf-8") as f:
        f.write(texto)


def _testar(c, pid: str, ids: list[str]):
    return c.post(f"/api/provedores/{pid}/testar-modelos", json={"ids": ids})


# ------------------------------------------------------------ OpenAI-compatível
def test_sucesso_openai_compativel_com_formato_do_contrato(cenario, rede):  # noqa: F811
    r = _testar(cenario, "groq", ["groq/llama-3.1-8b-instant"])
    assert r.status_code == 200, r.text
    dados = r.json()
    assert dados["ok"] is True and dados["provedor"] == "groq" and dados["aprovados"] == 1
    (res,) = dados["resultados"]
    assert set(res) == {"id", "ok", "latencia_ms", "erro", "status_http"}
    assert res["id"] == "groq/llama-3.1-8b-instant"   # o id como chegou
    assert res["ok"] is True and res["erro"] is None and res["status_http"] == 200
    assert isinstance(res["latencia_ms"], int)

    (pedido,) = rede.pedidos
    assert pedido.method == "POST"
    assert str(pedido.url) == "https://api.groq.com/openai/v1/chat/completions"
    assert pedido.headers["authorization"] == f"Bearer {CHAVE_GROQ}"
    corpo = json.loads(pedido.content)
    assert corpo["model"] == "llama-3.1-8b-instant"   # prefixo do LiteLLM removido
    assert corpo["messages"] == [{"role": "user", "content": "Responda apenas: ok"}]
    assert corpo["max_tokens"] == 8 and corpo["temperature"] == 0
    assert CHAVE_GROQ not in r.text


def test_id_cru_da_api_vai_como_esta(cenario, rede):  # noqa: F811
    r = _testar(cenario, "openrouter", ["openrouter/google/gemma:free", "meta-llama/llama-3:free"])
    assert r.json()["aprovados"] == 2
    modelos = [json.loads(p.content)["model"] for p in rede.pedidos]
    assert modelos == ["google/gemma:free", "meta-llama/llama-3:free"]
    assert all(str(p.url) == "https://openrouter.ai/api/v1/chat/completions" for p in rede.pedidos)


def test_nvidia_aceita_prefixo_nvidia_nim_e_cai_no_endpoint_padrao(cenario, rede):  # noqa: F811
    _env_extra(cenario, "NVIDIA_NIM_API_KEY=nvapi-teste\nNVIDIA_NIM_API_BASE=\n")   # api_base vazio no .env
    r = _testar(cenario, "nvidia", ["nvidia_nim/z-ai/glm-5.3-flash"])
    assert r.json()["aprovados"] == 1, r.text
    (pedido,) = rede.pedidos
    assert str(pedido.url) == "https://integrate.api.nvidia.com/v1/chat/completions"
    assert json.loads(pedido.content)["model"] == "z-ai/glm-5.3-flash"


def test_api_base_do_env_tem_prioridade(cenario, rede):  # noqa: F811
    _env_extra(cenario, "NVIDIA_NIM_API_KEY=nvapi-teste\nNVIDIA_NIM_API_BASE=https://nim.exemplo.com/v1/\n")
    _testar(cenario, "nvidia", ["nvidia_nim/x/y"])
    assert str(rede.pedidos[0].url) == "https://nim.exemplo.com/v1/chat/completions"


def test_raciocinio_com_content_vazio_e_200_conta_como_ok(cenario, rede):  # noqa: F811
    rede.responder = lambda req: httpx.Response(200, json={"choices": [{"message": {
        "role": "assistant", "content": "", "reasoning_content": "pensando..."}}]})
    res = _testar(cenario, "groq", ["groq/qwen-think"]).json()["resultados"][0]
    assert res["ok"] is True and res["status_http"] == 200


@pytest.mark.parametrize("corpo", [
    {"error": {"message": "Provider returned error", "code": 429}},   # OpenRouter devolve erro com 200
    {"choices": []},
    {"choices": [{"finish_reason": "error"}]},
    "não é json",
])
def test_200_sem_mensagem_do_assistente_falha(cenario, rede, corpo):  # noqa: F811
    rede.responder = lambda req: (httpx.Response(200, json=corpo) if isinstance(corpo, dict)
                                  else httpx.Response(200, text=corpo))
    res = _testar(cenario, "groq", ["groq/m"]).json()["resultados"][0]
    assert res["ok"] is False and res["status_http"] == 200 and res["erro"]


@pytest.mark.parametrize("status", [400, 401, 404, 429, 500, 503])
def test_status_de_erro_vira_ok_false_com_status(cenario, rede, status):  # noqa: F811
    rede.responder = lambda req: httpx.Response(status, json={"error": {"message": f"falhou {CHAVE_GROQ}"}})
    r = _testar(cenario, "groq", ["groq/m"])
    assert r.status_code == 200
    res = r.json()["resultados"][0]
    assert res["ok"] is False and res["status_http"] == status and str(status) in res["erro"]
    assert CHAVE_GROQ not in r.text   # provedor que ecoa a chave no erro não a vaza


def test_timeout_vira_ok_false_e_nao_aborta_o_lote(cenario, rede):  # noqa: F811
    def responder(req):
        if json.loads(req.content)["model"] == "lento":
            raise httpx.ReadTimeout("timeout", request=req)
        return httpx.Response(200, json=RESPOSTA_OK)
    rede.responder = responder
    dados = _testar(cenario, "groq", ["groq/lento", "groq/rapido"]).json()
    lento, rapido = dados["resultados"]
    assert lento["ok"] is False and lento["status_http"] == 0 and "Tempo esgotado" in lento["erro"]
    assert rapido["ok"] is True and dados["aprovados"] == 1


def test_erro_de_conexao_vira_ok_false(cenario, rede):  # noqa: F811
    def responder(req):
        raise httpx.ConnectError("recusada", request=req)
    rede.responder = responder
    res = _testar(cenario, "groq", ["groq/m"]).json()["resultados"][0]
    assert res["ok"] is False and res["status_http"] == 0 and "ConnectError" in res["erro"]


def test_redirecionamento_nao_e_seguido(cenario, rede):  # noqa: F811
    rede.responder = lambda req: httpx.Response(307, headers={"location": "https://evil.example/roubar"})
    res = _testar(cenario, "groq", ["groq/m"]).json()["resultados"][0]
    assert res["ok"] is False and res["status_http"] == 307
    assert [p.url.host for p in rede.pedidos] == ["api.groq.com"]   # a chave não foi para outro host


def test_cliente_real_tem_timeout_e_nao_segue_redirecionamento():
    with ps._cliente_teste_direto() as cliente:
        assert cliente.follow_redirects is False
        assert cliente.timeout.read == 20.0 and cliente.timeout.connect == 20.0


def test_espaca_as_chamadas_pelo_rpm(cenario, rede):  # noqa: F811
    _testar(cenario, "groq", ["groq/a", "groq/b", "groq/c"])          # groq: rpm 30 -> 2 s
    assert rede.sonos == [2.0, 2.0]
    rede.sonos.clear()
    _testar(cenario, "openrouter", ["openrouter/a", "openrouter/b"])  # rpm 20 -> 3 s (teto)
    assert rede.sonos == [3.0]


# ------------------------------------------------------------ sem chave / sem endpoint
def test_sem_chave_nao_faz_pedido(cenario, rede):  # noqa: F811
    r = _testar(cenario, "anthropic", ["anthropic/claude-x", "claude-y"])
    assert r.status_code == 200
    dados = r.json()
    assert dados["aprovados"] == 0 and rede.pedidos == []
    assert [x["id"] for x in dados["resultados"]] == ["anthropic/claude-x", "claude-y"]
    assert all(not x["ok"] and "ANTHROPIC_API_KEY" in x["erro"] for x in dados["resultados"])


def test_cloudflare_sem_account_id_nao_faz_pedido(cenario, rede):  # noqa: F811
    _env_extra(cenario, "CLOUDFLARE_API_KEY=cf-teste\n")
    res = _testar(cenario, "cloudflare", ["cloudflare/@cf/meta/llama"]).json()["resultados"][0]
    assert res["ok"] is False and "CLOUDFLARE_ACCOUNT_ID" in res["erro"] and rede.pedidos == []


def test_cloudflare_usa_endpoint_openai_da_conta(cenario, rede):  # noqa: F811
    _env_extra(cenario, "CLOUDFLARE_API_KEY=cf-teste\nCLOUDFLARE_ACCOUNT_ID=abc123\n")
    assert _testar(cenario, "cloudflare", ["cloudflare/@cf/meta/llama-3.1-8b-instruct"]).json()["aprovados"] == 1
    (pedido,) = rede.pedidos
    assert str(pedido.url) == "https://api.cloudflare.com/client/v4/accounts/abc123/ai/v1/chat/completions"
    assert pedido.headers["authorization"] == "Bearer cf-teste"
    assert json.loads(pedido.content)["model"] == "@cf/meta/llama-3.1-8b-instruct"


def test_gemini_usa_endpoint_openai_com_bearer(cenario, rede):  # noqa: F811
    _env_extra(cenario, "GEMINI_API_KEY=gm-teste\n")
    _testar(cenario, "gemini", ["gemini/gemini-2.5-flash"])
    (pedido,) = rede.pedidos
    assert str(pedido.url) == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    assert pedido.headers["authorization"] == "Bearer gm-teste" and "x-goog-api-key" not in pedido.headers
    assert json.loads(pedido.content)["model"] == "gemini-2.5-flash"


def test_endpoint_nao_derivavel_falha_todos_sem_pedido(cenario, rede):  # noqa: F811
    assert cenario.post("/api/provedores", json={
        "id": "estranho", "nome": "Estranho", "tier": "PAID", "chave": "ESTRANHO_API_KEY",
        "url_modelos": "https://exemplo.com/lista", "valor_chave": "k-teste"}).status_code == 200
    dados = _testar(cenario, "estranho", ["a", "b"]).json()
    assert rede.pedidos == [] and dados["aprovados"] == 0
    assert all("endpoint de chat" in x["erro"] for x in dados["resultados"])


def test_endpoint_sem_https_e_recusado(cenario, rede):  # noqa: F811
    assert cenario.post("/api/provedores", json={
        "id": "claro", "nome": "Claro", "tier": "PAID", "chave": "CLARO_API_KEY",
        "url_modelos": "http://exemplo.com/v1/models", "valor_chave": "k-teste"}).status_code == 200
    res = _testar(cenario, "claro", ["a"]).json()["resultados"][0]
    assert res["ok"] is False and "https" in res["erro"] and rede.pedidos == []


# ------------------------------------------------------------ Anthropic
def test_anthropic_formato_do_pedido(cenario, rede):  # noqa: F811
    _env_extra(cenario, "ANTHROPIC_API_KEY=sk-ant-teste\n")
    rede.responder = lambda req: httpx.Response(200, json={
        "id": "msg_1", "type": "message", "role": "assistant", "content": [{"type": "text", "text": "ok"}]})
    r = _testar(cenario, "anthropic", ["anthropic/claude-haiku-4-5"])
    assert r.json()["aprovados"] == 1, r.text
    (pedido,) = rede.pedidos
    assert str(pedido.url) == "https://api.anthropic.com/v1/messages"
    assert pedido.headers["x-api-key"] == "sk-ant-teste"
    assert pedido.headers["anthropic-version"] == "2023-06-01"
    assert "authorization" not in pedido.headers
    corpo = json.loads(pedido.content)
    assert corpo == {"model": "claude-haiku-4-5", "messages": [{"role": "user", "content": "Responda apenas: ok"}],
                     "max_tokens": 8}   # sem temperature: os modelos novos da Anthropic respondem 400 a ela
    assert "sk-ant-teste" not in r.text


def test_anthropic_erro_no_corpo_falha(cenario, rede):  # noqa: F811
    _env_extra(cenario, "ANTHROPIC_API_KEY=sk-ant-teste\n")
    rede.responder = lambda req: httpx.Response(200, json={"type": "error", "error": {"type": "overloaded_error"}})
    assert _testar(cenario, "anthropic", ["claude-x"]).json()["resultados"][0]["ok"] is False


# ------------------------------------------------------------ validação, 404 e autorização
@pytest.mark.parametrize("corpo, campo", [
    ({"ids": []}, "ids"),
    ({"ids": [f"m{i}" for i in range(41)]}, "ids"),
    ({"ids": ["a"], "extra": 1}, "extra"),
    ({"ids": [""]}, "ids[0]"),
    ({"ids": ["x" * 257]}, "ids[0]"),
    ({}, "ids"),
])
def test_validacao_422(cenario, rede, corpo, campo):  # noqa: F811
    r = cenario.post("/api/provedores/groq/testar-modelos", json=corpo)
    assert r.status_code == 422, r.text
    assert r.json()["erro"]["codigo"] == "validacao" and r.json()["erro"]["campo"] == campo
    assert rede.pedidos == []


def test_aceita_40_ids(cenario, rede):  # noqa: F811
    r = cenario.post("/api/provedores/groq/testar-modelos", json={"ids": [f"groq/m{i}" for i in range(40)]})
    assert r.status_code == 200 and r.json()["aprovados"] == 40 and len(rede.pedidos) == 40


def test_provedor_desconhecido_da_404(cenario, rede):  # noqa: F811
    r = _testar(cenario, "nao-existe", ["a"])
    assert r.status_code == 404 and r.json()["erro"]["codigo"] == "nao_encontrado"
    assert rede.pedidos == []


@pytest.mark.parametrize("papel", [PAPEL_OPERADOR, PAPEL_LEITOR])
def test_so_admin_testa(papel):
    assert decidir("POST", "/api/provedores/groq/testar-modelos", [papel])[0] == 403
    assert decidir("POST", "/api/provedores/groq/testar-modelos", [PAPEL_ADMIN]) is None


@pytest.mark.parametrize("papel", [PAPEL_OPERADOR, PAPEL_LEITOR])
def test_operador_e_leitor_recebem_403_na_api_real(cenario, rede, papel):  # noqa: F811
    cenario.cookies.set("tudoia_sessao", sessao_assinada([papel]))
    assert _testar(cenario, "groq", ["groq/m"]).status_code == 403
    assert rede.pedidos == []


def test_nao_segura_a_trava_durante_a_rede(cenario, rede):  # noqa: F811
    # Router montado com um Contexto nosso, para enxergar a trava (o painel não a expõe).
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from tudoia_painel.ambiente import Contexto
    from tudoia_painel.rotas import provedores

    ctx = Contexto(raiz=cenario.raiz, home=cenario.home, servicos=None, config_auth=None)
    app = FastAPI()
    app.include_router(provedores.criar_router(ctx))
    livre_na_rede = []

    def responder(req):
        livre = ctx.trava.acquire(blocking=False)
        livre_na_rede.append(livre)
        if livre:
            ctx.trava.release()
        return httpx.Response(200, json=RESPOSTA_OK)
    rede.responder = responder
    with TestClient(app) as c:
        assert _testar(c, "groq", ["groq/m"]).json()["aprovados"] == 1
    assert livre_na_rede == [True]


def test_catalogo_vazio_da_nvidia_sugere_o_prefixo_que_o_litellm_entende():
    from tudoia_painel.provedores_service import _prefixo_litellm
    assert _prefixo_litellm({"modelos": []}, "nvidia") == "nvidia_nim"
    assert _prefixo_litellm({"modelos": []}, "groq") == "groq"
    # Com modelos cadastrados, vale o que já está no catálogo.
    assert _prefixo_litellm({"modelos": [{"id": "nvidia_nim/meta/llama"}]}, "nvidia") == "nvidia_nim"

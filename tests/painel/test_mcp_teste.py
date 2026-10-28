import httpx
import pytest

from tudoia_painel import mcp_teste as mt


@pytest.mark.parametrize("url,esperado", [
    ("http://localhost:8765/mcp", mt.SAUDE_DO_CEREBRO),
    ("http://host.docker.internal:8765/mcp", mt.SAUDE_DO_CEREBRO),
    ("http://cerebro:8765/mcp", mt.SAUDE_DO_CEREBRO),
    ("https://evil.example/8765", "https://evil.example/8765"),            # "8765" no caminho não conta
    ("https://evil.example:18765/mcp", "https://evil.example:18765/mcp"),   # nem na porta de outro host
    ("https://8765.evil.example/mcp", "https://8765.evil.example/mcp"),
    ("http://[::1", "http://[::1"),                                         # URL inválida não derruba
])
def test_so_o_cerebro_local_vai_para_o_saude(url, esperado):
    assert mt.alvo_http(url) == esperado


def test_token_nao_acompanha_redirecionamento(monkeypatch):
    vistos = []

    def servidor(req: httpx.Request):
        vistos.append((req.url.host, req.headers.get("authorization")))
        if req.url.host == "mcp.exemplo":
            return httpx.Response(302, headers={"location": "https://coletor.example/x"})
        return httpx.Response(200)

    real = httpx.Client
    monkeypatch.setattr(mt.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(servidor), **kw))
    cfg = {"url": "https://mcp.exemplo/mcp", "env": {"TOKEN": "${MEU_TOKEN}"}}
    r = mt.testar("x", cfg, {"MEU_TOKEN": "segredo-123"})
    assert r["ok"] is False and r["mensagem"] == "Servidor retornou HTTP 302"
    assert [h for h, _ in vistos] == ["mcp.exemplo"]


def test_variavel_obrigatoria_ausente_nao_faz_requisicao(monkeypatch):
    monkeypatch.setattr(mt.httpx, "Client", lambda **kw: pytest.fail("não deveria conectar"))
    r = mt.testar("x", {"url": "https://mcp.exemplo/mcp", "env": {"T": "${SEM_VALOR}"}}, {})
    assert r["ok"] is False and "SEM_VALOR" in r["mensagem"]


def test_stdio_sem_comando_e_comando_inexistente():
    assert mt.testar("x", {"args": []}, {})["mensagem"] == "Configuração sem comando executável"
    assert "não encontrado" in mt.testar("x", {"command": "comando-que-nao-existe-xyz"}, {})["mensagem"]

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


# ───────── ${VAR} no command e nos args (MCP doutrina-tec: ${TUDOIA_PYTHON} ${DOUTRINA_TEC}/tools/...)
def _stdio_falso(monkeypatch, achados=None):
    vistos = {}
    monkeypatch.setattr(mt.shutil, "which", lambda c: achados.get(c) if achados is not None else c)

    def handshake(argv, env):
        vistos["argv"] = argv
        return {"result": {"serverInfo": {"name": "doutrina-tec", "version": "0.0.1"}, "capabilities": {"tools": {}}}}

    monkeypatch.setattr(mt.mcp_stdio, "handshake", handshake)
    return vistos


def test_command_e_args_com_variavel_sao_resolvidos_pelo_env(monkeypatch):
    py = r"D:\TudoIA\.venv\Scripts\python.exe"
    vistos = _stdio_falso(monkeypatch, {py: py})
    cfg = {"command": "${TUDOIA_PYTHON}", "args": ["${DOUTRINA_TEC}/tools/mcp_doutrina.py", "--x=${OPC:-padrao}"]}
    r = mt.testar("doutrina-tec", cfg, {"TUDOIA_PYTHON": py, "DOUTRINA_TEC": r"D:\Projetos\Doutrina"})
    assert r["ok"] is True and "operacional" in r["mensagem"]
    assert vistos["argv"] == [py, r"D:\Projetos\Doutrina/tools/mcp_doutrina.py", "--x=padrao"]


@pytest.mark.parametrize("env,faltando", [({}, "TUDOIA_PYTHON"), ({"TUDOIA_PYTHON": "  "}, "TUDOIA_PYTHON"),
                                          ({"TUDOIA_PYTHON": "py"}, "DOUTRINA_TEC")])
def test_variavel_ausente_no_command_ou_args_nomeia_a_variavel_e_nao_executa(monkeypatch, env, faltando):
    monkeypatch.setattr(mt.shutil, "which", lambda c: pytest.fail("não deveria procurar o comando"))
    monkeypatch.setattr(mt.mcp_stdio, "handshake", lambda *a: pytest.fail("não deveria executar"))
    r = mt.testar("x", {"command": "${TUDOIA_PYTHON}", "args": ["${DOUTRINA_TEC}/s.py"]}, env)
    assert r["ok"] is False and faltando in r["mensagem"] and "${" not in r["mensagem"]


def test_comando_resolvido_que_nao_existe_mostra_o_resolvido_e_nao_o_placeholder(monkeypatch):
    _stdio_falso(monkeypatch, {})
    r = mt.testar("x", {"command": "${TUDOIA_PYTHON}"}, {"TUDOIA_PYTHON": r"D:\sumiu\python.exe"})
    assert r["ok"] is False and r["mensagem"] == r"Comando 'D:\sumiu\python.exe' não encontrado no PATH"


def test_comando_sem_variavel_continua_igual(monkeypatch):
    vistos = _stdio_falso(monkeypatch)
    assert mt.testar("x", {"command": "serena", "args": ["start"]}, {})["ok"] is True
    assert vistos["argv"] == ["serena", "start"]

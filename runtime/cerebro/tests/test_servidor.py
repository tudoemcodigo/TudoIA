import logging
import re

from starlette.testclient import TestClient

from cerebro.autenticacao import PAPEIS, autorizado
from cerebro.servidor import criar_app_http, criar_servidor

NOMES = {"pesquisar_web", "ler_pagina", "buscar_documentos", "lembrar", "recordar", "esquecer"}
NEGADO = "exige um destes papéis"
CAB = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
INICIALIZAR = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
    "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}}


def _cfg(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    return {"ollama_url": "http://127.0.0.1:1", "searxng_url": "http://127.0.0.1:1",
            "docs": str(docs), "docs_host": "", "dados": str(tmp_path / "dados")}


def _chamar(nome, argumentos):
    return {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": nome, "arguments": argumentos}}


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


async def test_servidor_lista_as_seis_ferramentas(tmp_path):
    mcp = criar_servidor(_cfg(tmp_path))
    assert {t.name for t in await mcp.list_tools()} == NOMES


async def test_ferramenta_sem_autenticacao_nao_executa(tmp_path):
    mcp = criar_servidor(_cfg(tmp_path))
    r = await mcp.call_tool("lembrar", {"fato": "algo"})
    assert NEGADO in str(r)
    r = await mcp.call_tool("pesquisar_web", {"consulta": "x"})
    assert NEGADO in str(r)


async def test_ferramenta_devolve_erro_e_nao_excecao(tmp_path):
    mcp = criar_servidor(_cfg(tmp_path))
    with autorizado(PAPEIS):
        r = await mcp.call_tool("lembrar", {"fato": ""})
        assert "erro" in str(r) and NEGADO not in str(r)
        r = await mcp.call_tool("pesquisar_web", {"consulta": ""})
        assert "erro" in str(r) and NEGADO not in str(r)


def test_host_de_outro_container_e_aceito(tmp_path, emitir, verificador):
    mcp = criar_servidor(_cfg(tmp_path))
    with TestClient(criar_app_http(mcp, verificador), base_url="http://127.0.0.1:8765") as c:
        for host in ("cerebro:8765", "127.0.0.1:8765", "localhost:8765", "host.docker.internal:8765"):
            r = c.post("/mcp", json=INICIALIZAR, headers={**CAB, "Host": host, **_bearer(emitir())})
            assert r.status_code == 200, (host, r.status_code, r.text)
        r = c.post("/mcp", json=INICIALIZAR, headers={**CAB, "Host": "evil.com", **_bearer(emitir())})
        assert r.status_code in (400, 421)
        assert c.get("/saude", headers={"Host": "cerebro:8765"}).json()["ok"] is True


def test_mcp_sem_token_ou_com_token_ruim_e_401(tmp_path, emitir, verificador):
    mcp = criar_servidor(_cfg(tmp_path))
    with TestClient(criar_app_http(mcp, verificador), base_url="http://127.0.0.1:8765") as c:
        assert c.post("/mcp", json=INICIALIZAR, headers=CAB).status_code == 401
        assert c.post("/mcp", json=INICIALIZAR, headers={**CAB, **_bearer("lixo.lixo.lixo")}).status_code == 401
        assert c.post("/mcp", json=INICIALIZAR, headers={**CAB, **_bearer(emitir(exp=1))}).status_code == 401


def test_mcp_com_token_valido_e_initialize_200(tmp_path, emitir, verificador):
    mcp = criar_servidor(_cfg(tmp_path))
    with TestClient(criar_app_http(mcp, verificador), base_url="http://127.0.0.1:8765") as c:
        r = c.post("/mcp", json=INICIALIZAR, headers={**CAB, **_bearer(emitir())})
    assert r.status_code == 200
    assert "cerebro" in r.text


def test_mcp_token_sem_papel_do_cerebro_e_403(tmp_path, emitir, verificador):
    mcp = criar_servidor(_cfg(tmp_path))
    with TestClient(criar_app_http(mcp, verificador), base_url="http://127.0.0.1:8765") as c:
        r = c.post("/mcp", json=INICIALIZAR, headers={**CAB, **_bearer(emitir(realm_access={"roles": []}))})
    assert r.status_code == 403


def test_sem_configuracao_oidc_mcp_e_indexar_respondem_503(tmp_path, emitir):
    mcp = criar_servidor(_cfg(tmp_path))
    with TestClient(criar_app_http(mcp, None), base_url="http://127.0.0.1:8765") as c:
        assert c.post("/mcp", json=INICIALIZAR, headers={**CAB, **_bearer(emitir())}).status_code == 503
        assert c.post("/indexar", headers=_bearer(emitir())).status_code == 503
        assert c.get("/saude").status_code == 200


def test_saude_e_publico(tmp_path, verificador):
    mcp = criar_servidor(_cfg(tmp_path))
    with TestClient(criar_app_http(mcp, verificador), base_url="http://127.0.0.1:8765") as c:
        r = c.get("/saude")
    assert r.status_code == 200 and r.json()["ok"] is True


def test_leitor_pode_ler_mas_nao_gravar_memoria(tmp_path, emitir, verificador):
    mcp = criar_servidor(_cfg(tmp_path))
    leitor = _bearer(emitir(realm_access={"roles": ["tudoia-leitor"]}))
    with TestClient(criar_app_http(mcp, verificador), base_url="http://127.0.0.1:8765") as c:
        gravar = c.post("/mcp", json=_chamar("lembrar", {"fato": "gosto de café"}), headers={**CAB, **leitor})
        assert NEGADO in gravar.text
        esquecer = c.post("/mcp", json=_chamar("esquecer", {"id": 1}), headers={**CAB, **leitor})
        assert NEGADO in esquecer.text
        ler = c.post("/mcp", json=_chamar("recordar", {"consulta": "café"}), headers={**CAB, **leitor})
        assert NEGADO not in ler.text


def test_operador_passa_pela_autorizacao_de_escrita(tmp_path, emitir, verificador):
    mcp = criar_servidor(_cfg(tmp_path))
    operador = _bearer(emitir(realm_access={"roles": ["tudoia-operador"]}))
    with TestClient(criar_app_http(mcp, verificador), base_url="http://127.0.0.1:8765") as c:
        r = c.post("/mcp", json=_chamar("lembrar", {"fato": ""}), headers={**CAB, **operador})
    assert NEGADO not in r.text and "erro" in r.text  # fato vazio é recusado pela própria ferramenta


def test_indexar_exige_papel_de_escrita(tmp_path, emitir, verificador):
    mcp = criar_servidor(_cfg(tmp_path))
    with TestClient(criar_app_http(mcp, verificador), base_url="http://127.0.0.1:8765") as c:
        assert c.post("/indexar").status_code == 401
        leitor = _bearer(emitir(realm_access={"roles": ["tudoia-leitor"]}))
        assert c.post("/indexar", headers=leitor).status_code == 403
        operador = _bearer(emitir(realm_access={"roles": ["tudoia-operador"]}))
        assert c.post("/indexar", headers=operador).status_code not in (401, 403)


async def test_falha_da_indexacao_aparece_em_saude(tmp_path, verificador):
    mcp = criar_servidor(_cfg(tmp_path))

    async def quebra():
        raise RuntimeError("banco travado")

    mcp.indexador.indexar = quebra
    await mcp.passo_fundo()
    with TestClient(criar_app_http(mcp, verificador), base_url="http://127.0.0.1:8765") as c:
        erro = c.get("/saude", headers={"Host": "127.0.0.1:8765"}).json()["erro_indexacao"]
    assert erro["mensagem"] == "banco travado" and erro["quando"]

    async def ok():
        return {"novos": 0}

    mcp.indexador.indexar = ok
    await mcp.passo_fundo()
    with TestClient(criar_app_http(mcp, verificador), base_url="http://127.0.0.1:8765") as c:
        assert c.get("/saude", headers={"Host": "127.0.0.1:8765"}).json()["erro_indexacao"] is None


async def test_ler_pagina_ignora_proxy_do_ambiente(tmp_path, monkeypatch):
    """Com proxy, quem resolve o nome é o proxy: a checagem de IP do Cérebro não valeria no destino final."""
    from cerebro import web

    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.teste:3128")
    vistos = []

    async def falso(url, max_caracteres, cliente):
        vistos.append(cliente.trust_env)
        return "ok"

    monkeypatch.setattr(web, "ler_pagina", falso)
    mcp = criar_servidor(_cfg(tmp_path))
    with autorizado(PAPEIS):
        await mcp.call_tool("ler_pagina", {"url": "https://exemplo.teste/"})
    assert vistos == [False]


async def test_lembrar_aceita_origem(tmp_path):
    mcp = criar_servidor(_cfg(tmp_path))
    [lembrar] = [t for t in await mcp.list_tools() if t.name == "lembrar"]
    assert "origem" in lembrar.input_schema["properties"]
    assert "origem" not in lembrar.input_schema.get("required", [])


async def test_chamada_de_ferramenta_e_registrada_sem_conteudo(tmp_path, caplog):
    mcp = criar_servidor(_cfg(tmp_path))
    caplog.set_level(logging.INFO, logger="cerebro")
    with autorizado(PAPEIS):
        await mcp.call_tool("esquecer", {"id": 999})
        # fato grande demais: erro esperado, devolvido como {"erro": ...}
        await mcp.call_tool("lembrar", {"fato": "minha senha do banco é hunter2 " + "x" * 2000})
    await mcp.call_tool("recordar", {"consulta": "consulta-secreta"})  # sem autenticação
    linhas = [r.getMessage() for r in caplog.records]
    assert any(re.fullmatch(r"ferramenta=esquecer duracao_ms=\d+ resultado=ok", x) for x in linhas), linhas
    assert any(re.fullmatch(r"ferramenta=lembrar duracao_ms=\d+ resultado=erro:ValueError", x) for x in linhas), linhas
    assert "ferramenta negada ferramenta=recordar motivo=sem_autenticacao" in linhas
    assert "hunter2" not in caplog.text and "consulta-secreta" not in caplog.text


def test_negacao_de_auth_e_registrada_com_motivo_e_sem_token(tmp_path, verificador, caplog):
    caplog.set_level(logging.INFO, logger="cerebro")
    mcp = criar_servidor(_cfg(tmp_path))
    token_falso = "eyJhbGciOiJSUzI1NiIsImtpZCI6Im91dHJhIn0.e30.assinatura-falsa-secreta"
    with TestClient(criar_app_http(mcp, verificador), base_url="http://127.0.0.1:8765") as c:
        c.post("/mcp", json=INICIALIZAR, headers=CAB)
        c.post("/mcp", json=INICIALIZAR, headers={**CAB, **_bearer(token_falso)})
    linhas = [r.getMessage() for r in caplog.records]
    assert "auth negada rota='/mcp' status=401 motivo=token_ausente" in linhas
    assert "auth negada rota='/mcp' status=401 motivo=token_invalido" in linhas
    assert "assinatura-falsa-secreta" not in caplog.text and "eyJhbGci" not in caplog.text


async def test_indexar_nao_fica_em_409_depois_de_extracao_travada(tmp_path, emitir, verificador, monkeypatch):
    import threading

    from cerebro import indexador as ix

    cfg = _cfg(tmp_path)
    (tmp_path / "docs" / "trava.pdf").write_bytes(b"%PDF")
    solta = threading.Event()

    def extrair(p):
        solta.wait(5)
        return ""

    monkeypatch.setattr(ix, "extrair_texto", extrair)
    monkeypatch.setattr(ix, "PRAZO_EXTRACAO", 0.2)
    mcp = criar_servidor(cfg)
    operador = _bearer(emitir())
    with TestClient(criar_app_http(mcp, verificador), base_url="http://127.0.0.1:8765") as c:
        try:
            r = c.post("/indexar", headers=operador)
            assert r.status_code == 200 and r.json()["erros"] == 1
            assert c.post("/indexar", headers=operador).status_code == 200
        finally:
            solta.set()  # antes de sair: o fim do loop espera a thread presa


async def test_indexar_que_explode_libera_a_trava(tmp_path, emitir, verificador):
    mcp = criar_servidor(_cfg(tmp_path))

    async def quebra():
        raise RuntimeError("falha inesperada")

    original = mcp.indexador.indexar
    mcp.indexador.indexar = quebra
    with TestClient(criar_app_http(mcp, verificador), base_url="http://127.0.0.1:8765",
                    raise_server_exceptions=False) as c:
        assert c.post("/indexar", headers=_bearer(emitir())).status_code == 500
        mcp.indexador.indexar = original
        assert c.post("/indexar", headers=_bearer(emitir())).status_code == 200


def test_log_do_processo_nao_registra_urls_do_httpx():
    """Em INFO o httpx registra a URL inteira (com ?q=<consulta> do SearXNG); o Cérebro sobe com ele em WARNING."""
    from cerebro.__main__ import _configurar_log

    niveis = {n: logging.getLogger(n).level for n in ("httpx", "httpcore", "cerebro")}
    try:
        _configurar_log()
        assert not logging.getLogger("httpx").isEnabledFor(logging.INFO)
        assert not logging.getLogger("httpcore").isEnabledFor(logging.INFO)
        assert logging.getLogger("cerebro").isEnabledFor(logging.INFO)
        assert logging.getLogger("cerebro.auth").isEnabledFor(logging.INFO)
    finally:
        for nome, nivel in niveis.items():
            logging.getLogger(nome).setLevel(nivel)

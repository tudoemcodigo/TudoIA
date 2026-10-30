"""Seam: criar_app(raiz, servicos, home) -> FastAPI. Nada de métodos privados; só HTTP."""
import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tudoia_painel.app import criar_app
from tudoia_painel.autenticacao import PAPEL_ADMIN, ConfigAuth

SEGREDO_SESSAO = "t" * 48
CONFIG_AUTH = ConfigAuth(issuer="https://idp.teste/realms/tudoia", client_id="tudoia-painel",
                         client_secret="segredo-de-teste", segredo_sessao=SEGREDO_SESSAO)


def sessao_assinada(papeis: list[str]) -> str:
    """Cookie no mesmo formato do SessionMiddleware (JSON -> base64 -> TimestampSigner): sessão real, sem atalho."""
    import base64
    import json
    import time

    from itsdangerous import TimestampSigner

    dados = {"papeis": papeis, "expira_em": time.time() + 3600, "verificado_em": time.time(), "usuario": {"email": "teste@local"}}
    return TimestampSigner(SEGREDO_SESSAO).sign(base64.b64encode(json.dumps(dados).encode("utf-8"))).decode()

REPO = Path(__file__).resolve().parents[2]
BASE = "http://127.0.0.1:3100"
JSON_H = {"content-type": "application/json"}


class ServicosFalso:
    nomes = ("litellm", "litellm-db", "cerebro", "searxng", "open-webui", "kokoro", "n8n", "ollama", "comfyui")

    def __init__(self):
        self.chamadas = []

    def listar(self):
        return [{"nome": n, "tipo": "docker" if n not in ("ollama", "comfyui") else "host",
                 "ativo": n != "cerebro"} for n in self.nomes]

    def acao(self, nome, acao):
        self.chamadas.append((nome, acao))

    def acao_todos(self, acao):
        self.chamadas.append(("todos", acao))


@pytest.fixture
def cenario(tmp_path, monkeypatch):
    monkeypatch.setenv("TUDOIA_PAINEL_PORTA", "3100")
    # A sessão de teste é confirmada sem Keycloak: o painel reconfirma a conta a cada 30 s, e um teste lento
    # passaria desse prazo e seria recusado (401) por falta de IdP.
    async def userinfo_de_teste(issuer, access_token):
        return {"sub": "teste", "groups": [PAPEL_ADMIN]}
    monkeypatch.setattr("tudoia_painel.autenticacao.consultar_userinfo", userinfo_de_teste)
    raiz, home = tmp_path / "raiz", tmp_path / "home"
    shutil.copytree(REPO / "governanca", raiz / "governanca")
    shutil.copytree(REPO / "config", raiz / "config")
    home.mkdir()
    ws = tmp_path / "ws"
    ws.mkdir()
    cfg = json.loads((raiz / "governanca" / "governanca.json").read_text(encoding="utf-8"))
    cfg["workspaces"] = [str(ws)]
    cfg["mcp"] = ["cerebro"]   # sem MCP que exija segredo
    (raiz / "governanca" / "governanca.json").write_text(json.dumps(cfg), encoding="utf-8")
    (raiz / ".env").write_text("OPENAI_API_KEY=sk-super-secreto-1234567890\nGROQ_API_KEY=gsk_123456\nOPENROUTER_API_KEY=sk-or-teste\nTZ=America/Sao_Paulo\nCEREBRO_TOKEN_ESTATICO=token-de-teste\n", encoding="utf-8")
    serv = ServicosFalso()
    with TestClient(criar_app(raiz, serv, home, autenticacao=CONFIG_AUTH), base_url=BASE) as c:
        c.cookies.set("tudoia_sessao", sessao_assinada([PAPEL_ADMIN]))
        c.raiz, c.home, c.serv = raiz, home, serv
        yield c


# ------------------------------------------------------------ segurança
def test_host_estranho_e_recusado(cenario):
    r = cenario.get("/api/servicos", headers={"host": "evil.example:3100"})
    assert r.status_code == 403


@pytest.mark.parametrize("origem", ["http://evil.example", "null", "http://127.0.0.1.evil.example:3100"])
def test_post_com_origem_estranha_e_recusado(cenario, origem):
    r = cenario.post("/api/servicos/litellm/restart", json={}, headers={"origin": origem})
    assert r.status_code == 403
    assert cenario.serv.chamadas == []


def test_post_sem_json_e_recusado(cenario):
    r = cenario.post("/api/servicos/litellm/restart", content=b"x=1", headers={"content-type": "text/plain"})
    assert r.status_code == 415


def test_respostas_da_api_nao_ficam_em_cache(cenario):
    assert cenario.get("/api/servicos").headers["cache-control"] == "no-store"


# ------------------------------------------------------------ serviços
def test_lista_servicos(cenario):
    nomes = {s["nome"] for s in cenario.get("/api/servicos").json()}
    assert {"litellm", "cerebro", "ollama"}.issubset(nomes)


def test_acao_valida_chega_ao_executor(cenario):
    r = cenario.post("/api/servicos/litellm/restart", json={})
    assert r.status_code == 200 and cenario.serv.chamadas == [("litellm", "restart")]


def test_acao_todos_start_e_stop(cenario):
    r1 = cenario.post("/api/servicos/todos/start", json={})
    assert r1.status_code == 200
    r2 = cenario.post("/api/servicos/todos/stop", json={})
    assert r2.status_code == 200
    r3 = cenario.post("/api/servicos/todos/restart", json={})
    assert r3.status_code == 200
    assert ("todos", "start") in cenario.serv.chamadas
    assert ("todos", "stop") in cenario.serv.chamadas
    assert ("todos", "restart") in cenario.serv.chamadas


@pytest.mark.parametrize("nome,acao,status", [("naoexiste", "start", 404), ("litellm", "format", 422),
                                                ("litellm;calc", "start", 404)])
def test_servico_ou_acao_invalidos(cenario, nome, acao, status):
    assert cenario.post(f"/api/servicos/{nome}/{acao}", json={}).status_code == status
    assert cenario.serv.chamadas == []


# ------------------------------------------------------------ segredos
def test_segredos_sao_mascarados_e_categorizados(cenario):
    r = cenario.get("/api/segredos")
    assert r.status_code == 200
    assert "sk-super-secreto-1234567890" not in r.text
    chaves = r.json()
    assert any(s["chave"] == "OPENAI_API_KEY" and s["categoria"] == "PAID" for s in chaves)
    assert any(s["chave"] == "GROQ_API_KEY" and s["categoria"] == "FREE" for s in chaves)


def test_gravar_segredo_com_backup(cenario):
    r = cenario.put("/api/segredos/GROQ_API_KEY", json={"valor": "gsk_novo_valor_123456"})
    assert r.status_code == 200
    assert "GROQ_API_KEY=gsk_novo_valor_123456" in (cenario.raiz / ".env").read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=sk-super" in (cenario.raiz / ".env").read_text(encoding="utf-8")
    assert list((cenario.raiz / "dados" / "backups" / "env").glob(".env.*"))
    assert "gsk_novo_valor_123456" not in r.text


@pytest.mark.parametrize("chave", ["minuscula", "A-B", "1ABC", "A" * 100])
def test_chave_invalida_recusada(cenario, chave):
    assert cenario.put(f"/api/segredos/{chave}", json={"valor": "x"}).status_code in (404, 422)


@pytest.mark.parametrize("valor", ["a\nINJETADA=1", "a\rb"])
def test_valor_com_quebra_de_linha_recusado(cenario, valor):
    antes = (cenario.raiz / ".env").read_text(encoding="utf-8")
    assert cenario.put("/api/segredos/GROQ_API_KEY", json={"valor": valor}).status_code == 422
    assert (cenario.raiz / ".env").read_text(encoding="utf-8") == antes


def test_testar_segredo_funcional(cenario, monkeypatch):
    import httpx
    def mock_get(client, url, **kwargs):
        return httpx.Response(200, json={"data": [{"id": "gpt-4"}]})
    monkeypatch.setattr(httpx.Client, "get", mock_get)
    r = cenario.post("/api/segredos/OPENAI_API_KEY/testar", json={})
    assert r.status_code == 200
    dados = r.json()
    assert dados["valido"] is True
    assert "latencia_ms" in dados


# ------------------------------------------------------------ governança
def test_governanca_mostra_drift_e_sincroniza(cenario):
    g = cenario.get("/api/governanca").json()
    assert g["drift"] and g["mcp"]["cerebro"] is True
    assert cenario.post("/api/governanca/sincronizar", json={}).status_code == 200
    assert cenario.get("/api/governanca").json()["drift"] == []
    assert (cenario.home / ".claude" / "CLAUDE.md").is_file()


def test_alternar_mcp_persiste_e_gera_drift(cenario):
    cenario.post("/api/governanca/sincronizar", json={})
    r = cenario.put("/api/governanca/mcp/playwright", json={"ativo": True})
    assert r.status_code == 200
    cfg = json.loads((cenario.raiz / "governanca" / "governanca.json").read_text(encoding="utf-8"))
    assert "playwright" in cfg["mcp"]
    # Ligar um MCP aplica Claude, OpenCode, Antigravity e regras de uma vez (aplicar_tudo): antes o Antigravity
    # ficava para o próximo sync e sobrava drift.
    assert r.json()["pendencia"] is None and cenario.get("/api/governanca").json()["drift"] == []
    assert not list(cenario.raiz.glob("dados/backups/claude-json/*"))  # backup de JSON com token não fica no workspace


def test_mcp_desconhecido_404_e_nao_altera_config(cenario):
    antes = (cenario.raiz / "governanca" / "governanca.json").read_text(encoding="utf-8")
    assert cenario.put("/api/governanca/mcp/../../x", json={"ativo": True}).status_code in (404, 422)
    assert cenario.put("/api/governanca/mcp/inexistente", json={"ativo": True}).status_code == 404
    assert (cenario.raiz / "governanca" / "governanca.json").read_text(encoding="utf-8") == antes


def test_incluir_nova_regra_pela_tela(cenario):
    corpo = {"id": "seguranca-api", "conteudo": "# Segurança API\nValidar tokens sempre.\n", "ativo": True}
    r = cenario.post("/api/governanca/regras", json=corpo)
    assert r.status_code == 200
    regra_file = cenario.raiz / "governanca" / "regras" / "seguranca-api.md"
    assert regra_file.is_file() and "Validar tokens" in regra_file.read_text(encoding="utf-8")
    cfg = json.loads((cenario.raiz / "governanca" / "governanca.json").read_text(encoding="utf-8"))
    assert "seguranca-api" in cfg["regras"]


def test_incluir_nova_skill_pela_tela(cenario):
    corpo = {"id": "limpeza-codigo", "conteudo": "---\nname: limpeza-codigo\n---\nRefatore com TDD.\n", "ativo": True}
    r = cenario.post("/api/governanca/skills", json=corpo)
    assert r.status_code == 200
    skill_file = cenario.raiz / "governanca" / "skills" / "limpeza-codigo" / "SKILL.md"
    assert skill_file.is_file() and "Refatore com TDD" in skill_file.read_text(encoding="utf-8")


def test_incluir_novo_mcp_pela_tela(cenario):
    mcp_cfg = {"command": "npx", "args": ["-y", "meu-servidor-mcp"], "description": "MCP de Teste"}
    corpo = {"id": "meu-servidor-mcp", "config": mcp_cfg, "ativo": True}
    r = cenario.post("/api/governanca/mcp", json=corpo)
    assert r.status_code == 200
    mcp_json = json.loads((cenario.raiz / "governanca" / "mcp.json").read_text(encoding="utf-8"))
    assert "meu-servidor-mcp" in mcp_json["mcpServers"]
    cfg = json.loads((cenario.raiz / "governanca" / "governanca.json").read_text(encoding="utf-8"))
    assert "meu-servidor-mcp" in cfg["mcp"]


def test_excluir_regra_skill_e_mcp_pela_tela(cenario):
    # 1. Cria regra, skill e mcp
    r1 = cenario.post("/api/governanca/regras", json={"id": "regra-temp", "conteudo": "# Regra de Teste Temporaria\nConteudo suficiente aqui.\n", "ativo": True})
    assert r1.status_code == 200
    r2 = cenario.post("/api/governanca/skills", json={"id": "skill-temp", "conteudo": "---\nname: skill-temp\n---\nConteudo suficiente da skill.\n", "ativo": True})
    assert r2.status_code == 200
    r3 = cenario.post("/api/governanca/mcp", json={"id": "mcp-temp", "config": {"command": "npx"}, "ativo": True})
    assert r3.status_code == 200

    # 2. Exclui regra
    r_regra = cenario.delete("/api/governanca/regras/regra-temp")
    assert r_regra.status_code == 200
    assert not (cenario.raiz / "governanca" / "regras" / "regra-temp.md").exists()
    cfg = json.loads((cenario.raiz / "governanca" / "governanca.json").read_text(encoding="utf-8"))
    assert "regra-temp" not in cfg["regras"]

    # 3. Exclui skill
    r_skill = cenario.delete("/api/governanca/skills/skill-temp")
    assert r_skill.status_code == 200
    assert not (cenario.raiz / "governanca" / "skills" / "skill-temp").exists()
    cfg = json.loads((cenario.raiz / "governanca" / "governanca.json").read_text(encoding="utf-8"))
    assert "skill-temp" not in cfg["skills"]

    # 4. Exclui mcp
    r_mcp = cenario.delete("/api/governanca/mcp/mcp-temp")
    assert r_mcp.status_code == 200
    mcp_json = json.loads((cenario.raiz / "governanca" / "mcp.json").read_text(encoding="utf-8"))
    assert "mcp-temp" not in mcp_json["mcpServers"]
    cfg = json.loads((cenario.raiz / "governanca" / "governanca.json").read_text(encoding="utf-8"))
    assert "mcp-temp" not in cfg["mcp"]

    # 5. Erro ao tentar excluir inexistente
    assert cenario.delete("/api/governanca/regras/inexistente").status_code == 404
    assert cenario.delete("/api/governanca/tipo_invalido/item").status_code == 404


def test_obter_codigo_governanca(cenario):
    # Regra existente
    r1 = cenario.get("/api/governanca/regras/ponytail")
    assert r1.status_code == 200
    dados1 = r1.json()
    assert dados1["id"] == "ponytail"
    assert "Ponytail Guidelines" in dados1["conteudo"]
    assert "governanca/regras/ponytail.md" in dados1["caminho"]

    # Skill existente
    r2 = cenario.get("/api/governanca/skills/disciplined-tdd")
    assert r2.status_code == 200
    dados2 = r2.json()
    assert dados2["id"] == "disciplined-tdd"
    assert "name: disciplined-tdd" in dados2["conteudo"]
    assert "SKILL.md" in dados2["caminho"]

    # MCP existente
    r3 = cenario.get("/api/governanca/mcp/cerebro")
    assert r3.status_code == 200
    dados3 = r3.json()
    assert dados3["id"] == "cerebro"
    assert "8765" in dados3["conteudo"]

    # Inexistente
    assert cenario.get("/api/governanca/regras/inexistente").status_code == 404
    assert cenario.get("/api/governanca/invalido/ponytail").status_code == 404


def test_editar_conteudo_governanca(cenario):
    # 1. Editar Regra
    novo_conteudo_regra = "# Ponytail Guidelines Atualizadas\n\nTexto de teste para edição de regra.\n"
    r1 = cenario.put("/api/governanca/regras/ponytail/conteudo", json={"conteudo": novo_conteudo_regra})
    assert r1.status_code == 200
    dados1 = r1.json()
    assert dados1["ok"] is True
    assert dados1["id"] == "ponytail"
    assert "Ponytail Guidelines Atualizadas" in (cenario.raiz / "governanca" / "regras" / "ponytail.md").read_text(encoding="utf-8")

    # 2. Editar Skill
    novo_conteudo_skill = "---\nname: disciplined-tdd\ndescription: TDD disciplinado atualizado\n---\n# Instrucoes novas\n"
    r2 = cenario.put("/api/governanca/skills/disciplined-tdd/conteudo", json={"conteudo": novo_conteudo_skill})
    assert r2.status_code == 200
    dados2 = r2.json()
    assert dados2["ok"] is True
    assert dados2["id"] == "disciplined-tdd"
    assert "TDD disciplinado atualizado" in (cenario.raiz / "governanca" / "skills" / "disciplined-tdd" / "SKILL.md").read_text(encoding="utf-8")

    # 3. Editar MCP com JSON válido
    novo_cfg_mcp = {"command": "npx", "args": ["-y", "mcp-cerebro-novo"]}
    r3 = cenario.put("/api/governanca/mcp/cerebro/conteudo", json={"conteudo": json.dumps(novo_cfg_mcp)})
    assert r3.status_code == 200
    mcp_json = json.loads((cenario.raiz / "governanca" / "mcp.json").read_text(encoding="utf-8"))
    assert mcp_json["mcpServers"]["cerebro"]["args"] == ["-y", "mcp-cerebro-novo"]

    # 4. MCP com JSON inválido (retorna 422)
    r_invalido = cenario.put("/api/governanca/mcp/cerebro/conteudo", json={"conteudo": "{ json quebrado"})
    assert r_invalido.status_code == 422

    # 5. Adversarial: item inexistente ou path traversal
    assert cenario.put("/api/governanca/regras/inexistente/conteudo", json={"conteudo": "abc"}).status_code == 404
    assert cenario.put("/api/governanca/regras/../../x/conteudo", json={"conteudo": "abc"}).status_code in (404, 422)
    assert cenario.put("/api/governanca/tipo_invalido/ponytail/conteudo", json={"conteudo": "abc"}).status_code == 404

    # 6. Conteúdo vazio (validação Pydantic min_length=1)
    assert cenario.put("/api/governanca/regras/ponytail/conteudo", json={"conteudo": ""}).status_code == 422


def test_importar_skill_via_script_mock(cenario, monkeypatch):
    import subprocess
    from pathlib import Path

    comandos = []

    def fake_subprocess_run(cmd, cwd, capture_output, text, timeout):
        comandos.append(cmd)
        # Simula criação dos arquivos pelo npx skills add
        caminho_skill = Path(cwd) / ".agents" / "skills" / "agent-browser"
        caminho_skill.mkdir(parents=True, exist_ok=True)
        (caminho_skill / "SKILL.md").write_text("---\nname: agent-browser\n---\n# Automação Browser\n", encoding="utf-8")
        (caminho_skill / "ref.txt").write_text("arquivo de referencia", encoding="utf-8")
        class FakeProc:
            returncode = 0
            stdout = "Installed 1 skill"
            stderr = ""
        return FakeProc()

    monkeypatch.setattr(subprocess, "run", fake_subprocess_run)

    corpo = {
        "comando": "npx skills add https://github.com/halt-catch-fire/skills --skill agent-browser",
        "ativo": True
    }
    r = cenario.post("/api/governanca/skills/importar", json=corpo)
    assert r.status_code == 200
    # o pacote que baixa a skill roda com versão fixa, nunca "o que for mais novo"
    assert any(a.startswith("skills@") and a != "skills@latest" and a[len("skills@"):][0].isdigit() for a in comandos[0])
    assert "skills" not in comandos[0]
    dados = r.json()
    assert dados["id"] == "agent-browser"
    assert "SKILL.md" in dados["arquivos"]

    # Verifica se os arquivos foram copiados para a governança canônica
    pasta_final = cenario.raiz / "governanca" / "skills" / "agent-browser"
    assert (pasta_final / "SKILL.md").is_file()
    assert (pasta_final / "ref.txt").is_file()

    # Verifica se foi ativada em governanca.json
    cfg = json.loads((cenario.raiz / "governanca" / "governanca.json").read_text(encoding="utf-8"))
    assert "agent-browser" in cfg["skills"]


def test_importar_skill_validacao_campos(cenario):
    # Sem comando e sem campos
    r = cenario.post("/api/governanca/skills/importar", json={})
    assert r.status_code == 422

    # Comando inválido sem skill
    r2 = cenario.post("/api/governanca/skills/importar", json={"comando": "npx algo sem skill"})
    assert r2.status_code == 422


def test_mcp_com_chave_aparece_automaticamente_em_segredos(cenario):
    # Cadastra novo MCP exigindo BRAVE_API_KEY
    mcp_cfg = {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-brave-search"],
        "env": {
            "BRAVE_API_KEY": "${BRAVE_API_KEY}"
        },
        "description": "Brave Search MCP"
    }
    r = cenario.post("/api/governanca/mcp", json={"id": "brave-search", "config": mcp_cfg, "ativo": True})
    assert r.status_code == 200

    # Verifica se BRAVE_API_KEY agora aparece em /api/segredos automaticamente
    r_segredos = cenario.get("/api/segredos")
    assert r_segredos.status_code == 200
    segredos = r_segredos.json()
    item_brave = next((s for s in segredos if s["chave"] == "BRAVE_API_KEY"), None)
    assert item_brave is not None
    assert item_brave["categoria"] == "GOVERNANCA"
    assert item_brave["nome_provedor"] == "MCP: brave-search"
    assert item_brave["definido"] is False


def test_mcp_com_multiplas_chaves_aparece_automaticamente_em_segredos(cenario):
    mcp_cfg = {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-aws"],
        "env": {
            "AWS_ACCESS_KEY_ID": "${AWS_ACCESS_KEY_ID}",
            "AWS_SECRET_ACCESS_KEY": "${AWS_SECRET_ACCESS_KEY}",
            "AWS_DEFAULT_REGION": "${AWS_DEFAULT_REGION}"
        },
        "description": "AWS MCP Server"
    }
    r = cenario.post("/api/governanca/mcp", json={"id": "aws-cloud", "config": mcp_cfg, "ativo": True})
    assert r.status_code == 200

    r_segredos = cenario.get("/api/segredos")
    assert r_segredos.status_code == 200
    segredos = r_segredos.json()

    for ch in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_DEFAULT_REGION"):
        item = next((s for s in segredos if s["chave"] == ch), None)
        assert item is not None, f"Chave {ch} não encontrada nos segredos"
        assert item["categoria"] == "GOVERNANCA"
        assert item["nome_provedor"] == "MCP: aws-cloud"
        assert item["definido"] is False


def test_sincronizar_com_segredo_ausente_devolve_422_sem_vazar(cenario):
    cenario.put("/api/governanca/mcp/github", json={"ativo": True})   # exige GITHUB_PERSONAL_ACCESS_TOKEN
    r = cenario.post("/api/governanca/sincronizar", json={})
    assert r.status_code == 422 and "GITHUB_PERSONAL_ACCESS_TOKEN" in r.text
    assert not (cenario.home / ".claude").exists()


# ------------------------------------------------------------ modelos
def test_listar_modelos_do_ecossistema(cenario):
    r = cenario.get("/api/modelos")
    assert r.status_code == 200
    dados = r.json()
    assert "provedores" in dados
    assert "locais" in dados
    assert any(p["nome"] == "Groq" for p in dados["provedores"])


# ------------------------------------------------------------ roteador
def test_gerar_config_litellm(cenario):
    (cenario.raiz / ".env").write_text("GROQ_API_KEY=gsk_abc\nOLLAMA_URL=http://x\n", encoding="utf-8")
    r = cenario.post("/api/roteador/gerar", json={})
    assert r.status_code == 200
    cfg = (cenario.raiz / "runtime" / "litellm" / "config.yaml").read_text(encoding="utf-8")
    assert "tudoia-auto" in cfg and "gsk_abc" not in cfg   # referência à variável, nunca o valor


# ------------------------------------------------------------ UI
def test_ui_servida_com_csp_e_sem_script_inline(cenario):
    r = cenario.get("/app/")
    assert r.status_code == 200 and "script-src 'self'" in r.headers["content-security-policy"]
    assert "<script>" not in r.text and "onclick=" not in r.text
    assert cenario.get("/app/painel.js").status_code == 200


# ------------------------------------------------------------ novos recursos (olho, teste modelo, telemetria)
def test_revelar_segredo(cenario):
    r = cenario.post("/api/segredos/OPENAI_API_KEY/revelar", json={})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "chave": "OPENAI_API_KEY", "valor": "sk-super-secreto-1234567890"}


def test_testar_modelo_retorna_diagnostico(cenario):
    r = cenario.post("/api/modelos/testar", json={"modelo": "qwen2.5:7b", "tipo": "ollama"})
    assert r.status_code == 200
    dados = r.json()
    assert "ok" in dados
    assert "latencia_ms" in dados
    assert dados["modelo"] == "qwen2.5:7b"


def test_telemetria_retorna_metricas_e_feed(cenario):
    r = cenario.get("/api/telemetria")
    assert r.status_code == 200
    dados = r.json()
    assert "total_requisicoes" in dados
    assert "total_tokens" in dados
    assert "custo_total_usd" in dados
    assert "latencia_media_ms" in dados
    assert "feed" in dados
    assert "vram_modelos" in dados


def test_hardware_status_retorna_cpu_ram_gpu_e_discos(cenario):
    r = cenario.get("/api/hardware")
    assert r.status_code == 200
    dados = r.json()
    assert "cpu" in dados and "pct" in dados["cpu"]
    assert "ram" in dados and "total_gb" in dados["ram"]
    assert "gpu" in dados and "vram_total_gb" in dados["gpu"]
    assert "discos" in dados and len(dados["discos"]) > 0


def test_estaticos_marca_disponiveis(cenario):
    assert cenario.get("/app/logo.svg").status_code == 200
    assert cenario.get("/favicon.ico").status_code == 200


def test_testar_mcp_com_variavel_ausente_retorna_erro_amigavel(cenario):
    # supabase exige SUPABASE_ACCESS_TOKEN que não está no .env do cenário
    r = cenario.post("/api/governanca/mcp/supabase/testar", json={})
    assert r.status_code == 200
    dados = r.json()
    assert dados["ok"] is False
    assert "SUPABASE_ACCESS_TOKEN" in dados["mensagem"]


@pytest.mark.parametrize("status, ok", [(200, True), (503, False)])
def test_testar_mcp_cerebro_http(cenario, monkeypatch, status, ok):
    # Isolado: antes chamava o Cérebro de verdade e só conferia que as chaves existiam.
    import httpx
    cliente_real = httpx.Client
    monkeypatch.setattr("httpx.Client", lambda **kw: cliente_real(
        transport=httpx.MockTransport(lambda req: httpx.Response(status)), **kw))
    r = cenario.post("/api/governanca/mcp/cerebro/testar", json={})
    assert r.status_code == 200
    dados = r.json()
    assert dados["ok"] is ok
    assert "latencia_ms" in dados


def test_limpar_vram_executa_e_retorna_metricas(cenario, monkeypatch):
    """Isolado: antes este teste descarregava de verdade os modelos do Ollama da máquina a cada execução."""
    import subprocess

    import httpx
    leituras = iter(["6000\n", "1500, 6500\n"])
    monkeypatch.setattr("subprocess.run", lambda cmd, **kw: subprocess.CompletedProcess(
        cmd, 0, stdout=next(leituras), stderr=""))
    pedidos = []

    def ollama(req):
        pedidos.append((req.method, req.url.path, req.content))
        if req.url.path == "/api/ps":
            return httpx.Response(200, json={"models": [{"name": "qwen:9b"}]})
        return httpx.Response(200, json={})
    cliente_real = httpx.Client
    monkeypatch.setattr("httpx.Client",
                        lambda **kw: cliente_real(transport=httpx.MockTransport(ollama), **kw))
    r = cenario.post("/api/hardware/limpar-vram", json={})
    assert r.status_code == 200
    dados = r.json()
    assert dados["ok"] is True
    assert "vram_antes_mb" in dados
    assert "vram_depois_mb" in dados
    assert "mensagem" in dados
    descarga = [p for p in pedidos if p[1] == "/api/generate"]
    assert descarga and b'"keep_alive": 0' in descarga[0][2] or b'"keep_alive":0' in descarga[0][2]


def test_limites_tokens_retorna_estrutura_completa(cenario):
    r = cenario.get("/api/limites-tokens?periodo=24h")
    assert r.status_code == 200
    dados = r.json()
    assert "resumo" in dados
    assert "total_tokens" in dados["resumo"]
    assert "total_entrada" in dados["resumo"]
    assert "total_saida" in dados["resumo"]
    assert "provedores" in dados
    assert "distribuicao" in dados
    assert "ranking_modelos" in dados

    provedores = {p["id"]: p for p in dados["provedores"]}
    assert "ollama" in provedores
    assert "nvidia" in provedores
    assert "groq" in provedores

    # Verifica que dados de consumo e limites possuem tipos corretos
    ollama = provedores["ollama"]
    assert ollama["tier"] == "LOCAL"
    assert "consumo" in ollama
    assert "tokens_total" in ollama["consumo"]
    assert "limites" in ollama


def test_limites_tokens_com_periodo_total_e_customizado(cenario):
    r_total = cenario.get("/api/limites-tokens?periodo=total")
    assert r_total.status_code == 200
    assert r_total.json()["periodo_horas"] is None

    r_7d = cenario.get("/api/limites-tokens?periodo=7d")
    assert r_7d.status_code == 200
    assert r_7d.json()["periodo_horas"] == 168


def test_cadastrar_novo_provedor_com_sucesso(cenario):
    payload = {
        "id": "together",
        "nome": "Together AI",
        "tier": "PAID",
        "chave": "TOGETHER_API_KEY",
        "valor_chave": "tog_1234567890",
        "site_chave": "https://api.together.xyz",
        "url_modelos": "https://api.together.xyz/v1/models",
        "limites": {"rpm": 60}
    }
    r = cenario.post("/api/provedores", json=payload)
    assert r.status_code == 200
    dados = r.json()
    assert dados["ok"] is True
    assert dados["id"] == "together"

    # Confirma que a chave foi persistida no .env
    from tudoia_painel.envfile import ler_env
    env = ler_env(cenario.raiz / ".env")
    assert env.get("TOGETHER_API_KEY") == "tog_1234567890"

    # Tentativa duplicada deve falhar com 422
    r_duplicado = cenario.post("/api/provedores", json=payload)
    assert r_duplicado.status_code == 422


def test_adicionar_modelo_a_provedor(cenario):
    # Primeiro cadastra o provedor
    cenario.post("/api/provedores", json={
        "id": "mistral",
        "nome": "Mistral AI",
        "tier": "PAID",
        "chave": "MISTRAL_API_KEY"
    })
    # Agora adiciona um modelo
    r = cenario.post("/api/provedores/mistral/modelos", json={
        "nome": "mistral/large",
        "id": "mistral/mistral-large-latest",
        "papeis": ["chat", "codigo"],
        "contexto": 128000,
        "ativo": True
    })
    assert r.status_code == 200
    dados = r.json()
    assert dados["ok"] is True
    assert dados["modelo"]["nome"] == "mistral/large"


def test_roteador_detalhes_grupos_e_elegiveis(cenario):
    for g in cenario.get("/api/roteador/detalhes").json().get("grupos", []):
        cenario.delete(f"/api/roteador/grupos/{g['id']}")
    r0 = cenario.get("/api/roteador/detalhes")
    assert r0.status_code == 200
    assert r0.json()["grupos"] == []

    cenario.post("/api/provedores/groq/modelos", json={
        "nome": "groq/llama-cod",
        "id": "groq/llama-3.3-70b",
        "papeis": ["chat", "codigo"],
        "ativo": True,
    })
    cenario.post("/api/roteador/grupos/novo", json={
        "id": "tudoia-codigo",
        "titulo": "Código",
        "descricao": "Grupo de código",
        "modelos": ["groq/llama-cod"],
    })
    r = cenario.get("/api/roteador/detalhes")
    assert r.status_code == 200
    dados = r.json()
    assert "grupos" in dados
    grupos = {g["id"]: g for g in dados["grupos"]}
    assert "tudoia-codigo" in grupos
    assert len(grupos["tudoia-codigo"]["membros"]) == 1

    # Verifica que modelos elegíveis são listados e marcações fictícias não são inventadas
    elegiveis = {m["nome"]: m for m in grupos["tudoia-codigo"]["modelos_elegiveis"]}
    assert "local/tudoia-chat" not in elegiveis


def test_vincular_modelos_locais_manualmente(cenario):
    cenario.post("/api/roteador/grupos/novo", json={
        "id": "tudoia-dev",
        "titulo": "Desenvolvimento Local",
        "descricao": "Grupo híbrido com fallback local",
        "modelos": [],
    })
    # Vincula modelo local real do Ollama manualmente ao grupo
    r_put = cenario.put("/api/roteador/grupos", json={
        "ordem": {
            "tudoia-dev": ["local/qwen2.5-coder:latest"]
        }
    })
    assert r_put.status_code == 200
    r_det = cenario.get("/api/roteador/detalhes")
    assert r_det.status_code == 200
    grupos = {g["id"]: g for g in r_det.json()["grupos"]}
    assert "tudoia-dev" in grupos
    membros = grupos["tudoia-dev"]["membros"]
    assert len(membros) == 1
    assert membros[0]["nome"] == "local/qwen2.5-coder:latest"
    assert membros[0]["provedor_nome"] == "Ollama Local"
    assert membros[0]["origem"] == "local"


def test_atualizar_composicao_grupos(cenario):
    payload = {
        "ordem": {
            "tudoia-nuvem": ["nim/glm-5.3", "groq/gpt-oss-120b"],
            "tudoia-codigo": ["nim/glm-5.3"],
            "tudoia-max": ["gpt-6.1-sol"]
        }
    }
    r = cenario.put("/api/roteador/grupos", json=payload)
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_auto_bind_modelos_por_papeis(cenario):
    cenario.post("/api/provedores/groq/modelos", json={
        "nome": "groq/llama-cod",
        "id": "groq/llama-3.3-70b",
        "papeis": ["codigo"],
        "ativo": True,
    })
    cenario.post("/api/roteador/grupos/novo", json={
        "id": "tudoia-codigo",
        "titulo": "Código",
        "descricao": "Grupo de código",
        "modelos": [],
    })
    r = cenario.post("/api/roteador/auto-bind", json={})
    assert r.status_code == 200
    dados = r.json()
    assert dados["ok"] is True
    assert "ordem" in dados
    assert dados["ordem"]["tudoia-codigo"] == ["groq/llama-cod"]


def test_gerenciamento_grupos_roteador_lifecycle(cenario):
    # 1. Criar novo grupo customizado
    r_novo = cenario.post("/api/roteador/grupos/novo", json={
        "id": "tudoia-pesquisa",
        "titulo": "TudoIA Pesquisa e Análise",
        "descricao": "Grupo para síntese e buscas profundas",
        "modelos": ["groq/gpt-oss-120b"]
    })
    assert r_novo.status_code == 200
    assert r_novo.json()["ok"] is True

    # 2. Verificar que grupo aparece nos detalhes
    r_det = cenario.get("/api/roteador/detalhes")
    assert r_det.status_code == 200
    grupos = {g["id"]: g for g in r_det.json()["grupos"]}
    assert "tudoia-pesquisa" in grupos
    assert grupos["tudoia-pesquisa"]["titulo"] == "TudoIA Pesquisa e Análise"
    assert grupos["tudoia-pesquisa"]["ativo"] is True
    assert grupos["tudoia-pesquisa"]["pode_excluir"] is True

    # 3. Editar grupo (desativar e alterar título)
    r_edit = cenario.patch("/api/roteador/grupos/tudoia-pesquisa", json={
        "titulo": "TudoIA Pesquisa Profunda",
        "ativo": False
    })
    assert r_edit.status_code == 200
    assert r_edit.json()["ok"] is True
    assert r_edit.json()["ativo"] is False

    # 4. Excluir grupo customizado com sucesso
    r_del = cenario.delete("/api/roteador/grupos/tudoia-pesquisa")
    assert r_del.status_code == 200
    assert r_del.json()["ok"] is True

    # Confirma que foi removido
    r_det2 = cenario.get("/api/roteador/detalhes")
    grupos2 = {g["id"]: g for g in r_det2.json()["grupos"]}
    assert "tudoia-pesquisa" not in grupos2


def test_gerenciamento_modelos_locais_endpoints(cenario, monkeypatch):
    # 1. Toggle ativo de modelo local
    r_toggle = cenario.post("/api/modelos/local/qwen2.5-coder:7b/toggle-ativo", json={})
    assert r_toggle.status_code == 200
    assert r_toggle.json()["ok"] is True
    assert r_toggle.json()["ativo"] is False

    # Toggle volta a ser ativo
    r_toggle2 = cenario.post("/api/modelos/local/qwen2.5-coder:7b/toggle-ativo", json={})
    assert r_toggle2.status_code == 200
    assert r_toggle2.json()["ativo"] is True

    # 2. Testar baixar modelo com mock do Ollama
    from tudoia_painel import modelos_service
    monkeypatch.setattr(modelos_service, "verificar_ollama_online", lambda timeout=1.5: True)

    class MockResp:
        def __init__(self, status_code=200, json_data=None, text=""):
            self.status_code = status_code
            self._json = json_data or {}
            self.text = text

        def json(self):
            return self._json

    class MockClient:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def post(self, url, json=None, **kwargs):
            return MockResp(200, {"status": "success"})
        def request(self, method, url, json=None, **kwargs):
            return MockResp(200, {"status": "success"})

    import httpx
    monkeypatch.setattr(httpx, "Client", MockClient)

    r_baixar = cenario.post("/api/modelos/local/baixar", json={"nome": "llama3.2:3b"})
    assert r_baixar.status_code == 200
    assert r_baixar.json()["ok"] is True

    # 3. Testar descarregar VRAM
    r_unload = cenario.post("/api/modelos/local/llama3.2:3b/descarregar", json={})
    assert r_unload.status_code == 200
    assert r_unload.json()["ok"] is True

    # 4. Testar excluir modelo local
    r_del = cenario.delete("/api/modelos/local/llama3.2:3b")
    assert r_del.status_code == 200
    assert r_del.json()["ok"] is True


def test_testar_modelo_embedding_ollama(cenario, monkeypatch):
    class MockResp:
        def __init__(self, status_code, json_data=None, text=""):
            self.status_code = status_code
            self._json = json_data or {}
            self.text = text

        def json(self):
            return self._json

    class MockClient:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def post(self, url, json=None, **kwargs):
            if "api/generate" in url:
                # Simula Ollama recusando generate em modelo de embedding
                return MockResp(400, text='{"error":"\\"bge-m3:latest\\" does not support generate"}')
            elif "api/embed" in url:
                return MockResp(200, {"embeddings": [[0.1] * 1024]})
            return MockResp(404, text="Not Found")

    import httpx
    monkeypatch.setattr(httpx, "Client", MockClient)

    r = cenario.post("/api/modelos/testar", json={"modelo": "bge-m3:latest", "tipo": "ollama"})
    assert r.status_code == 200
    dados = r.json()
    assert dados["ok"] is True
    assert "Embedding" in dados["resposta"]
    assert "1024" in dados["resposta"]



def test_modelos_midia_verificacao_e_exclusao(cenario):
    import struct

    # Cria um modelo safetensors sintético válido (> 1MB)
    dir_modelos = cenario.raiz / "modelos" / "comfyui" / "ComfyUI_windows_portable" / "ComfyUI" / "models" / "diffusion_models"
    dir_modelos.mkdir(parents=True, exist_ok=True)
    arq_sf = dir_modelos / "video_teste.safetensors"
    header_json = b'{"__metadata__": {"format": "pt"}}'
    arq_sf.write_bytes(struct.pack("<Q", len(header_json)) + header_json + (b"\x00" * (1024 * 1024 + 512)))

    # 1. Listar modelos deve retornar modelos detalhados de mídia
    r_list = cenario.get("/api/modelos")
    assert r_list.status_code == 200
    midia = r_list.json()["midia"]
    assert "fluxos" not in midia
    assert any(m["arquivo"] == "video_teste.safetensors" for m in midia["modelos"])

    # 2. Verificar integridade binária do modelo .safetensors via /api/modelos/testar
    r_ver_mod = cenario.post("/api/modelos/testar", json={"modelo": "midia:comfyui/ComfyUI_windows_portable/ComfyUI/models/diffusion_models/video_teste.safetensors", "tipo": "midia"})
    assert r_ver_mod.status_code == 200
    assert r_ver_mod.json()["ok"] is True
    assert "SAFETENSORS íntegro" in r_ver_mod.json()["resposta"]

    # 3. Excluir o modelo .safetensors do disco
    r_del_mod = cenario.delete("/api/modelos/midia/midia:comfyui/ComfyUI_windows_portable/ComfyUI/models/diffusion_models/video_teste.safetensors")
    assert r_del_mod.status_code == 200
    assert r_del_mod.json()["ok"] is True
    assert not arq_sf.exists()


def test_testar_roteador_com_escolha_de_grupo(cenario, monkeypatch):
    chamadas = []

    class MockResp:
        def __init__(self, status_code, json_data):
            self.status_code = status_code
            self._json = json_data
            self.text = ""

        def json(self):
            return self._json

    class MockClient:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def post(self, url, json=None, headers=None, **kwargs):
            chamadas.append(json)
            mod = json.get("model", "")
            return MockResp(200, {
                "model": f"{mod}-resolvido",
                "choices": [{"message": {"content": f"Resposta de teste para {mod}"}}]
            })

    import httpx
    monkeypatch.setattr(httpx, "Client", MockClient)

    # 1. Teste com grupo padrão tudoia-auto
    r_auto = cenario.post("/api/roteador/testar", json={"mensagem": "Olá mundo"})
    assert r_auto.status_code == 200
    d_auto = r_auto.json()
    assert d_auto["ok"] is True
    assert d_auto["modelo_solicitado"] == "tudoia-auto"
    assert "tudoia-auto" in d_auto["modelo_usado"]
    assert chamadas[-1]["model"] == "tudoia-auto"

    # 2. Teste com escolha explícita de grupo (ex: tudoia-codigo)
    r_cod = cenario.post("/api/roteador/testar", json={"mensagem": "Escreva um quicksort", "modelo": "tudoia-codigo"})
    assert r_cod.status_code == 200
    d_cod = r_cod.json()
    assert d_cod["ok"] is True
    assert d_cod["modelo_solicitado"] == "tudoia-codigo"
    assert "tudoia-codigo" in d_cod["modelo_usado"]
    assert chamadas[-1]["model"] == "tudoia-codigo"


# ------------------------------------------------------------ estúdio (chat, imagens, vídeos)
def test_estudio_status_motores(cenario):
    r = cenario.get("/api/estudio/status-motores")
    assert r.status_code == 200
    d = r.json()
    assert "litellm" in d
    assert "ollama" in d
    assert "comfyui" in d


def test_estudio_chat_completions(cenario, monkeypatch):
    chamadas = []

    class MockResp:
        def __init__(self, status, payload):
            self.status_code = status
            self._payload = payload
        def json(self):
            return self._payload

    class MockClient:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def post(self, url, json=None, headers=None, **kwargs):
            chamadas.append(json)
            return MockResp(200, {
                "model": "tudoia-codigo",
                "choices": [{"message": {"role": "assistant", "content": "Código refatorado com sucesso."}}],
                "usage": {"total_tokens": 85}
            })

    import httpx
    monkeypatch.setattr(httpx, "Client", MockClient)

    r = cenario.post("/api/chat/completions", json={
        "model": "tudoia-codigo",
        "messages": [{"role": "user", "content": "Refatore esta função"}],
        "temperature": 0.5,
        "max_tokens": 1024
    })
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert d["model"] == "tudoia-codigo"
    assert "Código refatorado" in d["message"]["content"]
    assert d["usage"]["total_tokens"] == 85


def test_estudio_gerar_imagem(cenario, monkeypatch):
    # Sem isto o teste falava com o ComfyUI de verdade na 8188 (resultado e tempo dependiam da máquina).
    monkeypatch.setattr("tudoia_painel.servicos.porta_aberta", lambda porta: False)
    r = cenario.post("/api/estudio/gerar-imagem", json={
        "prompt": "Cyberpunk city at twilight",
        "aspect_ratio": "16:9",
        "steps": 25
    })
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert d["largura"] == 1344
    assert d["altura"] == 768
    assert "imagem_url" in d


def test_estudio_gerar_imagem_local_comfy_offline(cenario, monkeypatch):
    monkeypatch.setattr("tudoia_painel.servicos.porta_aberta", lambda porta: False)
    r = cenario.post("/api/estudio/gerar-imagem", json={
        "prompt": "Octavio Frias Bridge",
        "modelo": "local:Juggernaut-XL_v9_RunDiffusionPhoto_v2.safetensors",
        "aspect_ratio": "16:9"
    })
    assert r.status_code == 503
    assert r.json()["erro"]["codigo"] == "servico_offline"
    assert r.json()["erro"]["extras"]["servico_offline"] == "comfyui"


def test_estudio_gerar_video(cenario, monkeypatch):
    monkeypatch.setattr("tudoia_painel.servicos.porta_aberta", lambda porta: True)
    monkeypatch.setattr(
        "tudoia_painel.rotas.estudio_video._executar_comfyui_video",
        lambda *args, **kwargs: {"ok": True, "nome_arquivo": "vid_teste.mp4", "prompt_id": "prompt_123", "grafo_usado": "video-minimax-h3.json"}
    )
    r = cenario.post("/api/estudio/gerar-video", json={
        "prompt": "Drone shot over neon metropolis",
        "motor": "auto",
        "duracao_segundos": 4,
        "resolucao": "720p"
    })
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert d["prompt"] == "Drone shot over neon metropolis"
    assert d["duracao_segundos"] == 4
    assert "job_id" in d
    assert d["video_url"] == "/api/estudio/videos/vid_teste.mp4"


PNG_MINIMO = bytes([0x89]) + b"PNG" + bytes([0x0D, 0x0A, 0x1A, 0x0A])


def _subir(cenario, nome, conteudo: bytes, tipo="imagem"):
    import base64

    return cenario.post("/api/estudio/upload", json={
        "nome_arquivo": nome, "tipo": tipo, "conteudo_base64": base64.b64encode(conteudo).decode("ascii")})


def test_upload_recusa_conteudo_que_nao_bate_com_a_extensao(cenario):
    r = _subir(cenario, "foto.png", b"<html><script>alert(1)</script></html>")
    assert r.status_code == 422 and "não é um arquivo" in r.json()["erro"]["mensagem"]
    assert _subir(cenario, "video.mp4", PNG_MINIMO + b"xxxx", tipo="video").status_code == 422
    assert _subir(cenario, "ok.jpg", bytes([0xFF, 0xD8, 0xFF, 0xE0]) + b"x" * 20).json()["ok"] is True


def test_upload_do_mesmo_arquivo_no_mesmo_segundo_nao_sobrescreve(cenario):
    a = _subir(cenario, "rosto.png", PNG_MINIMO + b"A").json()
    b = _subir(cenario, "rosto.png", PNG_MINIMO + b"B").json()
    assert a["nome_arquivo"] != b["nome_arquivo"]
    assert cenario.get(a["url"]).content.endswith(b"A") and cenario.get(b["url"]).content.endswith(b"B")


def test_upload_recusa_base64_gigante_antes_de_decodificar(cenario, monkeypatch):
    import types

    chamado = []
    # só o módulo do painel: o cookie de sessão também usa base64.b64decode
    monkeypatch.setattr("tudoia_painel.rotas.estudio_arquivos.base64", types.SimpleNamespace(b64decode=lambda *a, **k: chamado.append(1) or b""))
    r = cenario.post("/api/estudio/upload", json={"nome_arquivo": "x.png", "tipo": "imagem",
                                                  "conteudo_base64": "A" * (101 * 1024 * 1024 * 4 // 3)})
    assert r.status_code == 413 and "100 MB" in r.json()["erro"]["mensagem"] and not chamado


def test_estudio_upload_midia_e_fluxo_i2v(cenario, monkeypatch):
    import base64

    # 1. Upload de imagem válida
    img_b64 = base64.b64encode(PNG_MINIMO + b"fake-png-content").decode("ascii")
    r_up = cenario.post("/api/estudio/upload", json={
        "nome_arquivo": "rosto_teste.png",
        "conteudo_base64": f"data:image/png;base64,{img_b64}",
        "tipo": "imagem"
    })
    assert r_up.status_code == 200
    d_up = r_up.json()
    assert d_up["ok"] is True
    assert "upload_" in d_up["nome_arquivo"]
    assert d_up["tipo"] == "imagem"
    url_upload = d_up["url"]

    # 2. Servir upload
    r_get = cenario.get(url_upload)
    assert r_get.status_code == 200
    assert r_get.content == PNG_MINIMO + b"fake-png-content"

    # 3. Travessia: `%2F` não é normalizado pelo cliente (o `../` literal era, e o teste antigo passava à toa)
    r_trav = cenario.get("/api/estudio/uploads/..%2F..%2F..%2F.env")
    assert r_trav.status_code == 404

    # 4. Geração com modo i2v sem arquivo (deve falhar amigavelmente)
    r_sem_arq = cenario.post("/api/estudio/gerar-video", json={
        "prompt": "Câmera girando ao redor da pessoa",
        "motor": "auto",
        "modelo": "video-wan14b-i2v",
        "modo_origem": "i2v",
        "arquivo_referencia": None
    })
    assert r_sem_arq.status_code == 422
    assert "requer um arquivo de imagem" in r_sem_arq.json()["erro"]["mensagem"]

    # 5. ComfyUI offline detectado quando porta fechada
    monkeypatch.setattr("tudoia_painel.servicos.porta_aberta", lambda porta: False)
    r_comfy_off = cenario.post("/api/estudio/gerar-video", json={
        "prompt": "Câmera girando ao redor da pessoa",
        "motor": "auto",
        "modelo": "video-wan14b-i2v",
        "modo_origem": "i2v",
        "arquivo_referencia": url_upload
    })
    assert r_comfy_off.status_code == 503
    assert r_comfy_off.json()["erro"]["extras"]["servico_offline"] == "comfyui"

    # 6. Geração com serviço online e arquivo informado (sucesso e renderização)
    monkeypatch.setattr("tudoia_painel.servicos.porta_aberta", lambda porta: True)
    monkeypatch.setattr(
        "tudoia_painel.rotas.estudio_video._executar_comfyui_video",
        lambda *args, **kwargs: {"ok": True, "nome_arquivo": "vid_i2v_teste.mp4", "prompt_id": "prompt_i2v_123", "grafo_usado": "video-wan14b-i2v.json"}
    )
    r_com_arq = cenario.post("/api/estudio/gerar-video", json={
        "prompt": "Câmera girando ao redor da pessoa",
        "motor": "auto",
        "modelo": "svd",
        "modo_origem": "i2v",
        "arquivo_referencia": url_upload
    })
    assert r_com_arq.status_code == 200
    d_com_arq = r_com_arq.json()
    assert d_com_arq["ok"] is True
    assert d_com_arq["modo_origem"] == "i2v"
    assert "upload_" in str(d_com_arq["arquivo_referencia"])


def test_inpaint_recusa_caminho_absoluto_do_disco(cenario, monkeypatch):
    """Regressão: antes, `imagem_base` aceitava qualquer caminho do disco e copiava para a pasta do ComfyUI."""
    segredo = cenario.raiz / "segredo.txt"
    segredo.write_text("CHAVE-DE-TESTE", encoding="utf-8")
    monkeypatch.setattr("tudoia_painel.servicos.porta_aberta", lambda porta, timeout=0.5: True, raising=False)
    r = cenario.post("/api/estudio/inpaint", json={
        "imagem_base": str(segredo),
        "mascara_base64": "data:image/png;base64,iVBORw0KGgo=",
        "prompt": "teste"
    })
    assert r.status_code == 404
    copias = list((cenario.raiz / "modelos").rglob("inpaint_base_*"))
    assert copias == [], "arquivo arbitrário do disco foi copiado para a pasta de entrada do ComfyUI"


def test_estudio_inpaint(cenario, monkeypatch, tmp_path):
    # 1. ComfyUI Offline deve retornar servico_offline amigável
    monkeypatch.setattr("tudoia_painel.servicos.porta_aberta", lambda porta: False)
    r_off = cenario.post("/api/estudio/inpaint", json={
        "imagem_base": "/api/estudio/imagens/inexistente.png",
        "mascara_base64": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
        "prompt": "Regenerar elemento",
        "denoise": 0.75
    })
    assert r_off.status_code == 503
    assert r_off.json()["erro"]["extras"]["servico_offline"] == "comfyui"

    # 2. Imagem base inexistente
    monkeypatch.setattr("tudoia_painel.servicos.porta_aberta", lambda porta: True)
    r_inex = cenario.post("/api/estudio/inpaint", json={
        "imagem_base": "/api/estudio/imagens/nao_existe_mesmo_9999.png",
        "mascara_base64": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
        "prompt": "Regenerar elemento",
        "denoise": 0.75
    })
    assert r_inex.status_code == 404
    assert "não encontrada" in r_inex.json()["erro"]["mensagem"]

    # 3. Upload de imagem base válida para o teste
    import base64
    fake_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc`\x00\x00\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82"
    r_up = cenario.post("/api/estudio/upload", json={
        "nome_arquivo": "inpaint_base_teste.png",
        "conteudo_base64": f"data:image/png;base64,{base64.b64encode(fake_png).decode('ascii')}",
        "tipo": "imagem"
    })
    assert r_up.status_code == 200
    url_base = r_up.json()["url"]

    # Teste com máscara base64 corrompida
    r_mask_err = cenario.post("/api/estudio/inpaint", json={
        "imagem_base": url_base,
        "mascara_base64": "base64_invalido_$$$",
        "prompt": "Regenerar elemento"
    })
    assert r_mask_err.status_code == 422

    # 4. Mock de execução com sucesso no ComfyUI
    class MockResp:
        def __init__(self, status_code, json_data=None, content=b""):
            self.status_code = status_code
            self._json = json_data or {}
            self.content = content
            self.text = ""

        def json(self):
            return self._json

    class MockHttpxClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, **kwargs):
            return MockResp(200, {"prompt_id": "test-prompt-inpaint-123"})

        def get(self, url, **kwargs):
            if "/history/" in url:
                return MockResp(200, {
                    "test-prompt-inpaint-123": {
                        "outputs": {
                            "8": {
                                "images": [{"filename": "inpaint_res_001.png", "subfolder": "", "type": "output"}]
                            }
                        }
                    }
                })
            elif "/view" in url:
                return MockResp(200, content=b"\x89PNG\r\n\x1a\n" + (b"\x00" * 2048))
            return MockResp(404)

    monkeypatch.setattr("httpx.Client", MockHttpxClient)

    r_sucesso = cenario.post("/api/estudio/inpaint", json={
        "imagem_base": url_base,
        "mascara_base64": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
        "prompt": "MASP Museu de Arte de São Paulo moderno com pilares vermelhos",
        "prompt_negativo": "borrado, distorcido",
        "denoise": 0.8,
        "steps": 25,
        "seed": 42
    })
    assert r_sucesso.status_code == 200
    d_suc = r_sucesso.json()
    assert d_suc["ok"] is True
    assert "inpaint_" in d_suc["imagem_url"]
    assert d_suc["motor"] == "comfyui"
    assert d_suc["denoise"] == 0.8


def test_estudio_otimizar_prompt(cenario):
    # Prompt curto em português deve retornar resposta estruturada
    r = cenario.post("/api/estudio/otimizar-prompt", json={
        "prompt": "Incluir o MASP de são paulo/SP"
    })
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert "prompt" in d
    assert "prompt_original" in d
    assert d["prompt_original"] == "Incluir o MASP de são paulo/SP"


def test_telemetria_visual_e_motores(cenario):
    # 1. Gera uma imagem para registrar evento visual
    cenario.post("/api/estudio/gerar-imagem", json={
        "prompt": "Futuristic skyline of Sao Paulo",
        "aspect_ratio": "16:9",
        "steps": 20
    })

    # 2. Consulta telemetria
    r = cenario.get("/api/telemetria")
    assert r.status_code == 200
    d = r.json()

    assert "comfyui" in d
    assert "feed_visual" in d
    assert isinstance(d["feed_visual"], list)
    assert len(d["feed_visual"]) >= 1

    ultimo = d["feed_visual"][0]
    assert ultimo["status"] == "sucesso"
    assert "duracao_s" in ultimo
    assert "prompt" in ultimo


def test_estudio_cancelar(cenario, monkeypatch):
    class MockResp:
        status_code = 200

    class MockClient:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def post(self, url, **kwargs):
            return MockResp()

    monkeypatch.setattr("httpx.Client", MockClient)
    r = cenario.post("/api/estudio/cancelar", json={})
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_estudio_otimizar_prompt_video(cenario):
    r = cenario.post("/api/estudio/otimizar-prompt-video", json={
        "prompt": "Câmera lenta aproximando de um esportivo na chuva"
    })
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert "prompt" in d
    assert d["prompt_original"] == "Câmera lenta aproximando de um esportivo na chuva"


def test_estudio_musicas_rotas(cenario):
    # 1. Listar músicas inicialmente (vazio ou existente)
    r = cenario.get("/api/estudio/musicas")
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert isinstance(d["musicas"], list)

    # 2. Otimizar prompt de música
    r_opt = cenario.post("/api/estudio/otimizar-prompt-musica", json={
        "prompt": "trilha sonora épica de batalha com percussão pesada"
    })
    assert r_opt.status_code == 200
    d_opt = r_opt.json()
    assert d_opt["ok"] is True
    assert "prompt" in d_opt


def test_estudio_gerar_musica(cenario, monkeypatch):
    monkeypatch.setattr("tudoia_painel.servicos.porta_aberta", lambda porta: True)
    monkeypatch.setattr(
        "tudoia_painel.rotas.estudio_musica._executar_comfyui_musica",
        lambda *args, **kwargs: {"ok": True, "nome_arquivo": "comfy_audio_teste.flac", "prompt_id": "mus_123", "grafo_usado": "musica-yue2.json"}
    )
    r = cenario.post("/api/estudio/gerar-musica", json={
        "style": "cinematic dark synthwave",
        "lyrics": "[instrumental]",
        "duracao_segundos": 30.0,
        "modo": "full"
    })
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert d["style"] == "cinematic dark synthwave"
    assert d["duracao_segundos"] == 30.0
    assert d["audio_url"] == "/api/estudio/musicas/comfy_audio_teste.flac"
    assert "job_id" in d


def test_instancias_governanca_crud(cenario):
    # 1. Listar instâncias
    r = cenario.get("/api/governanca/instancias")
    assert r.status_code == 200
    dados = r.json()
    assert "instancias" in dados
    assert "detectadas" in dados

    # 2. Adicionar nova instância
    nova = {
        "id": "claude-dev-teste",
        "cliente": "claude",
        "nome": "Claude Code (Dev)",
        "caminho": "~/.claude-dev",
        "config_json": "~/.claude-dev/.claude.json",
        "ativo": True
    }
    r_add = cenario.post("/api/governanca/instancias", json=nova)
    assert r_add.status_code == 200
    assert r_add.json()["ok"] is True
    assert r_add.json()["instancia"]["id"] == "claude-dev-teste"

    # Conflito de duplicado
    r_dup = cenario.post("/api/governanca/instancias", json=nova)
    assert r_dup.status_code == 409

    # 3. Atualizar instância
    r_up = cenario.put("/api/governanca/instancias/claude-dev-teste", json={"ativo": False, "nome": "Claude Code (Desativado)"})
    assert r_up.status_code == 200
    assert r_up.json()["instancia"]["ativo"] is False
    assert r_up.json()["instancia"]["nome"] == "Claude Code (Desativado)"

    # 4. Detectar
    r_det = cenario.post("/api/governanca/instancias/detectar", json={})
    assert r_det.status_code == 200
    assert "detectadas" in r_det.json()

    # 5. Remover instância
    r_del = cenario.delete("/api/governanca/instancias/claude-dev-teste")
    assert r_del.status_code == 200
    assert r_del.json()["ok"] is True

    # 6. Remover inexistente
    r_del_404 = cenario.delete("/api/governanca/instancias/nao-existe")
    assert r_del_404.status_code == 404















def test_upload_aceita_corpo_maior_que_1mb_so_na_rota_de_upload():
    from tudoia_painel.seguranca import checar
    from starlette.datastructures import Headers

    grande = Headers({"host": "127.0.0.1:3100", "content-type": "application/json", "content-length": str(11 * 1024 * 1024)})
    assert checar("POST", grande, True, 3100, "/api/estudio/upload") is None
    recusa = checar("POST", grande, True, 3100, "/api/outra-rota")
    assert recusa is not None and recusa[0] == 413
    gigante = Headers({"host": "127.0.0.1:3100", "content-type": "application/json", "content-length": str(200 * 1024 * 1024)})
    assert checar("POST", gigante, True, 3100, "/api/estudio/upload")[0] == 413


# ------------------------------------------------------------ sincronização de modelos (OpenRouter e demais provedores)
def _api_falsa(respostas):
    """Substitui a consulta HTTP: respostas[nome_do_provedor] é a lista de modelos, ou uma FalhaApi a levantar."""
    from tudoia_painel.provedores_service import FalhaApi

    def falsa(p, caminho_env):
        valor = respostas.get(p["nome"], FalhaApi("sem resposta de teste"))
        if isinstance(valor, FalhaApi):
            raise valor
        return valor
    return falsa


def _modelos_or(cenario):
    import yaml
    cat = yaml.safe_load((cenario.raiz / "config" / "catalogo-modelos.yaml").read_text(encoding="utf-8"))
    return cat["provedores"]["openrouter"]["modelos"]


def _nomes_catalogo_or(cenario):
    return {m["nome"] for m in _modelos_or(cenario)}


def _modelo_or(cenario, nome):
    return next(m for m in _modelos_or(cenario) if m["nome"] == nome)


def _modelo_api(mid, free=False, contexto=None):
    return {"id": mid, "nome": mid, "contexto": contexto, "free": free, "descricao": ""}


def test_inferir_papeis_pelo_id():
    from tudoia_painel.provedores_service import inferir_papeis
    assert inferir_papeis("deepseek/deepseek-coder-v2") == ["codigo"]
    assert inferir_papeis("qwen/qwen2.5-vl-72b") == ["visao"]
    assert inferir_papeis("deepseek/deepseek-r1") == ["raciocinio"]
    assert inferir_papeis("openai/gpt-oss-120b") == ["chat"]


def test_descobrir_openrouter_reconhece_modelo_cadastrado_com_prefixo(cenario, monkeypatch):
    # Regressão: antes, 'openrouter/google/...' era comparado com 'google/...' e aparecia como ausente.
    cenario.post("/api/provedores/openrouter/modelos", json={
        "nome": "or/gemma-4-26b", "id": "openrouter/google/gemma-4-26b-a4b-it:free", "papeis": ["chat"], "ativo": True,
    })
    cenario.post("/api/provedores/openrouter/modelos", json={
        "nome": "or/lfm-2.5", "id": "openrouter/liquid/lfm-2.5:free", "papeis": ["chat"], "ativo": True,
    })
    monkeypatch.setattr("tudoia_painel.provedores_service._buscar_modelos_api",
                        _api_falsa({"OpenRouter (:free)": [_modelo_api("google/gemma-4-26b-a4b-it:free", free=True)]}))
    dados = cenario.get("/api/provedores/openrouter/descobrir-modelos").json()
    status = {m["nome"]: m["status_api"] for m in dados["cadastrados"]}
    assert status["or/gemma-4-26b"] == "ativo_na_api"
    assert status["or/lfm-2.5"] == "ausente_ou_descontinuado"


def test_sincronizar_previa_nao_grava(cenario, monkeypatch):
    monkeypatch.setattr("tudoia_painel.provedores_service._buscar_modelos_api",
                        _api_falsa({"OpenRouter (:free)": [_modelo_api("deepseek/deepseek-r1", free=True)]}))
    yaml_antes = (cenario.raiz / "config" / "catalogo-modelos.yaml").read_text(encoding="utf-8")
    r = cenario.post("/api/provedores/sincronizar", json={"aplicar": False})
    assert r.status_code == 200
    assert r.json()["aplicado"] is False
    assert r.json()["provedores"]["openrouter"]["adicionados"] == ["openrouter/deepseek-r1"]
    assert (cenario.raiz / "config" / "catalogo-modelos.yaml").read_text(encoding="utf-8") == yaml_antes


def test_sincronizar_adiciona_inativo_remove_descontinuado_e_protege_roteado(cenario, monkeypatch):
    # 'or/descontinuado' não está no roteamento: deve sair. 'or/free' está: deve ficar.
    cenario.post("/api/provedores/openrouter/modelos", json={
        "nome": "or/free", "id": "openrouter/openrouter/free", "papeis": ["chat"], "ativo": True,
    })
    cenario.put("/api/roteador/grupos", json={"ordem": {"tudoia-nuvem": ["or/free"]}})
    cenario.post("/api/provedores/openrouter/modelos", json={
        "nome": "or/descontinuado", "id": "openrouter/vendor/descontinuado:free", "papeis": ["chat"], "ativo": True,
    })
    monkeypatch.setattr("tudoia_painel.provedores_service._buscar_modelos_api", _api_falsa({
        "OpenRouter (:free)": [
            _modelo_api("google/gemma-novo:free", free=True, contexto=8000),
            _modelo_api("deepseek/deepseek-r1"),
        ],
    }))
    r = cenario.post("/api/provedores/sincronizar", json={"aplicar": True})
    assert r.status_code == 200
    resumo = r.json()["provedores"]["openrouter"]
    assert resumo["ok"] is True
    assert resumo["inativados"] == ["or/descontinuado"]
    assert "or/free" in resumo["protegidos_pelo_roteamento"]

    # Inativado, não excluído: continua no catálogo e sai do roteamento.
    assert "or/descontinuado" in _nomes_catalogo_or(cenario)
    assert _modelo_or(cenario, "or/descontinuado")["ativo"] is False


def test_sincronizar_novos_entram_inativos_com_papeis_inferidos(cenario, monkeypatch):
    monkeypatch.setattr("tudoia_painel.provedores_service._buscar_modelos_api", _api_falsa({
        "OpenRouter (:free)": [_modelo_api("deepseek/deepseek-r1"), _modelo_api("google/gemma-novo:free", contexto=8000)],
    }))
    cenario.post("/api/provedores/sincronizar", json={"aplicar": True})

    import yaml
    cat = yaml.safe_load((cenario.raiz / "config" / "catalogo-modelos.yaml").read_text(encoding="utf-8"))
    novos = {m["id"]: m for m in cat["provedores"]["openrouter"]["modelos"] if m["id"] in
             ("openrouter/deepseek/deepseek-r1", "openrouter/google/gemma-novo:free")}
    assert novos["openrouter/deepseek/deepseek-r1"]["ativo"] is False
    assert novos["openrouter/deepseek/deepseek-r1"]["papeis"] == ["raciocinio"]
    assert novos["openrouter/google/gemma-novo:free"]["contexto"] == 8000
    assert "free" not in novos["openrouter/google/gemma-novo:free"]


def test_falha_de_api_nao_altera_provedor(cenario, monkeypatch):
    from tudoia_painel.provedores_service import FalhaApi
    cenario.post("/api/provedores/openrouter/modelos", json={
        "nome": "or/descontinuado", "id": "openrouter/vendor/descontinuado:free", "papeis": ["chat"],
    })
    monkeypatch.setattr("tudoia_painel.provedores_service._buscar_modelos_api", _api_falsa({
        "OpenRouter (:free)": FalhaApi("status 503", status_code=503),
    }))
    r = cenario.post("/api/provedores/sincronizar", json={"aplicar": True}).json()
    assert r["provedores"]["openrouter"]["ok"] is False
    assert r["aplicado"] is False
    assert "or/descontinuado" in _nomes_catalogo_or(cenario)


def test_lista_vazia_da_api_nao_apaga_nada(cenario, monkeypatch):
    cenario.post("/api/provedores/openrouter/modelos", json={
        "nome": "or/descontinuado", "id": "openrouter/vendor/descontinuado:free", "papeis": ["chat"],
    })
    monkeypatch.setattr("tudoia_painel.provedores_service._buscar_modelos_api",
                        _api_falsa({"OpenRouter (:free)": []}))
    r = cenario.post("/api/provedores/sincronizar", json={"aplicar": True}).json()
    assert r["provedores"]["openrouter"]["inativados"] == []
    assert _modelo_or(cenario, "or/descontinuado")["ativo"] is True


def test_escolher_novos_e_lote_recusa_duplicado(cenario, monkeypatch):
    monkeypatch.setattr("tudoia_painel.provedores_service._buscar_modelos_api", _api_falsa({
        "OpenRouter (:free)": [_modelo_api("deepseek/deepseek-r1")],
    }))
    listagem = cenario.get("/api/provedores/novos").json()
    assert [n["id"] for n in listagem["novos"]] == ["openrouter/deepseek/deepseek-r1"]

    item = {"provedor": "openrouter", "nome": "openrouter/r1", "id": "openrouter/deepseek/deepseek-r1",
            "papeis": [], "contexto": None}
    r = cenario.post("/api/provedores/modelos-lote", json={"itens": [item, item]}).json()
    assert r["adicionados"] == ["openrouter/r1"]
    assert len(r["recusados"]) == 1
    assert r["litellm_regenerado"] in (True, False)


def test_lote_rejeita_campos_extras(cenario):
    r = cenario.post("/api/provedores/modelos-lote", json={"itens": [
        {"provedor": "openrouter", "nome": "x", "id": "openrouter/x", "ativo": True}
    ]})
    assert r.status_code == 422


def test_adicionar_modelo_individual_entra_inativo_via_contrato(cenario):
    # O painel envia ativo=false ao adicionar pelo card; o contrato precisa aceitar e respeitar isso.
    r = cenario.post("/api/provedores/openrouter/modelos", json={
        "nome": "or/teste-inativo", "id": "openrouter/vendor/teste-inativo", "papeis": [], "ativo": False,
    })
    assert r.status_code == 200
    assert r.json()["modelo"]["ativo"] is False
    assert r.json()["modelo"]["papeis"] == ["chat"]


def test_url_resolve_conta_cloudflare_e_recusa_variavel_ausente():
    from tudoia_painel.provedores_service import FalhaApi, _resolver_url
    url = "https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/ai/models/search"
    assert _resolver_url(url, {"CLOUDFLARE_ACCOUNT_ID": "abc123"}).endswith("/accounts/abc123/ai/models/search")
    with pytest.raises(FalhaApi, match="CLOUDFLARE_ACCOUNT_ID não configurada"):
        _resolver_url(url, {"CLOUDFLARE_ACCOUNT_ID": "  "})


def test_gemini_usa_header_x_goog_api_key_nao_bearer():
    from tudoia_painel.provedores_service import _montar_cabecalhos
    h = _montar_cabecalhos("https://generativelanguage.googleapis.com/v1beta/models", "chave-x")
    assert h["x-goog-api-key"] == "chave-x"
    assert "Authorization" not in h
    assert "Authorization" in _montar_cabecalhos("https://api.groq.com/openai/v1/models", "chave-x")


def test_401_sem_chave_diz_qual_chave_falta(tmp_path, monkeypatch):
    import httpx
    from tudoia_painel import provedores_service as ps
    env = tmp_path / ".env"
    env.write_text("OUTRA=1\n", encoding="utf-8")
    transporte = httpx.MockTransport(lambda req: httpx.Response(401, text="unauthorized"))
    cliente_real = httpx.Client
    monkeypatch.setattr(ps.httpx, "Client", lambda **kw: cliente_real(transport=transporte, **kw))
    p = {"url_modelos": "https://api.anthropic.com/v1/models", "chave": "ANTHROPIC_API_KEY"}
    with pytest.raises(ps.FalhaApi, match="Chave ANTHROPIC_API_KEY não configurada"):
        ps._buscar_modelos_api(p, env)


def test_listagem_de_novos_traz_tier_do_provedor(cenario, monkeypatch):
    monkeypatch.setattr("tudoia_painel.provedores_service._buscar_modelos_api",
                        _api_falsa({"OpenRouter (:free)": [_modelo_api("deepseek/deepseek-r1")]}))
    novos = cenario.get("/api/provedores/novos").json()["novos"]
    assert novos[0]["tier"] == "FREE"


# ------------------------------------------------------------ modelo que falha no teste sai do roteamento
def _catalogo_e_roteamento_para_falha(tmp_path):
    cat = tmp_path / "catalogo.yaml"
    rot = tmp_path / "roteamento.yaml"
    cat.write_text(
        "provedores:\n"
        "  or:\n"
        "    modelos:\n"
        "      - {nome: or/a, id: openrouter/a, papeis: [chat], ativo: true}\n"
        "      - {nome: or/b, id: openrouter/b, papeis: [chat], ativo: false}\n",
        encoding="utf-8",
    )
    rot.write_text("ordem:\n  g1: [or/a, x]\n  g2: [or/a]\n", encoding="utf-8")
    return cat, rot


def test_falha_tira_modelo_do_roteamento_e_inativa(tmp_path):
    import yaml
    from tudoia_painel.provedores_service import desativar_modelo_por_falha
    cat, rot = _catalogo_e_roteamento_para_falha(tmp_path)

    r = desativar_modelo_por_falha(cat, rot, "or/a", "ReadTimeout")

    assert r == {"desativado": True, "removido_de_grupos": ["g1", "g2"]}
    assert yaml.safe_load(rot.read_text(encoding="utf-8"))["ordem"] == {"g1": ["x"], "g2": []}
    modelo = yaml.safe_load(cat.read_text(encoding="utf-8"))["provedores"]["or"]["modelos"][0]
    assert modelo["ativo"] is False
    assert modelo["desativado_por_falha"] == "ReadTimeout"


def test_falha_em_modelo_ja_inativo_nao_grava_nada(tmp_path):
    from tudoia_painel.provedores_service import desativar_modelo_por_falha
    cat, rot = _catalogo_e_roteamento_para_falha(tmp_path)
    antes = (cat.read_text(encoding="utf-8"), rot.read_text(encoding="utf-8"))

    r = desativar_modelo_por_falha(cat, rot, "or/b", "erro")

    assert r["desativado"] is False
    assert (cat.read_text(encoding="utf-8"), rot.read_text(encoding="utf-8")) == antes


def test_modelo_fora_do_catalogo_local_nao_mexe_em_nada(tmp_path):
    # Modelos locais (Ollama) têm nomes que não estão no catálogo de nuvem; a falha não pode afetar nuvem.
    from tudoia_painel.provedores_service import desativar_modelo_por_falha
    cat, rot = _catalogo_e_roteamento_para_falha(tmp_path)
    antes = (cat.read_text(encoding="utf-8"), rot.read_text(encoding="utf-8"))

    r = desativar_modelo_por_falha(cat, rot, "tudoia-chat", "ReadTimeout")

    assert r == {"desativado": False, "removido_de_grupos": []}
    assert (cat.read_text(encoding="utf-8"), rot.read_text(encoding="utf-8")) == antes


@pytest.mark.parametrize("resultado", [
    {"ok": False, "status_http": 404, "erro": "NotFoundError: model not found"},
    {"ok": False, "status_http": 400, "erro": "The model `llama-x` has been decommissioned"},
    {"ok": False, "status_http": 400, "erro": "The model `x` does not exist or you do not have access"},
])
def test_so_o_provedor_dizendo_que_o_modelo_acabou_e_definitivo(resultado):
    from tudoia_painel.provedores_service import falha_definitiva
    assert falha_definitiva(resultado)


@pytest.mark.parametrize("resultado", [
    {"ok": False, "status_http": 429, "erro": "Rate limit excedido (429)"},
    {"ok": False, "status_http": 408, "erro": "Timeout (>25s)"},
    {"ok": False, "status_http": 0, "erro": "ConnectError: [WinError 10061] Nenhuma conexão pôde ser feita"},
    {"ok": False, "status_http": 500, "erro": "InternalServerError"},
    {"ok": False, "status_http": 503, "erro": "ServiceUnavailable"},
    {"ok": False, "status_http": 401, "erro": "Chave de API inválida (401)"},
    # LiteLLM sem o modelo no config carregado (gerado e ainda não recarregado): não é o provedor
    {"ok": False, "status_http": 400, "erro": "Invalid model name passed in model=or/a"},
    {"ok": False, "status_http": 404, "erro": "ProxyModelNotFoundError: model not found"},
    {"ok": True, "status_http": 200},
])
def test_falha_de_ambiente_nao_desativa_modelo(resultado):
    from tudoia_painel.provedores_service import falha_definitiva
    assert not falha_definitiva(resultado)


def test_testar_com_litellm_fora_nao_mexe_no_catalogo(cenario, monkeypatch):
    """Antes: 'Testar todos' com o LiteLLM parado inativava todo modelo de nuvem e o tirava do roteamento."""
    import httpx
    cenario.post("/api/provedores/groq/modelos", json={
        "nome": "groq/teste", "id": "groq/llama-3", "papeis": ["chat"], "ativo": True,
    })
    cat = cenario.raiz / "config" / "catalogo-modelos.yaml"
    rot = cenario.raiz / "config" / "roteamento.yaml"
    antes = (cat.read_bytes(), rot.read_bytes())

    def recusa(req):
        raise httpx.ConnectError("[WinError 10061] Nenhuma conexão pôde ser feita", request=req)
    cliente_real = httpx.Client
    monkeypatch.setattr("httpx.Client",
                        lambda **kw: cliente_real(transport=httpx.MockTransport(recusa), **kw))
    import yaml
    nome = next(m["nome"] for p in yaml.safe_load(cat.read_text(encoding="utf-8"))["provedores"].values()
                for m in p.get("modelos") or [] if m.get("ativo", True))
    r = cenario.post("/api/modelos/testar", json={"modelo": nome, "tipo": "litellm"}).json()
    assert r["ok"] is False and not r.get("desativado_automaticamente")
    assert (cat.read_bytes(), rot.read_bytes()) == antes


def test_listar_novos_filtra_por_provedor(cenario, monkeypatch):
    monkeypatch.setattr("tudoia_painel.provedores_service._buscar_modelos_api", _api_falsa({
        "OpenRouter (:free)": [_modelo_api("deepseek/deepseek-r1")],
        "Groq": [_modelo_api("meta/llama-x")],
    }))
    r = cenario.get("/api/provedores/novos", params={"provedor": "openrouter"}).json()
    assert {n["provedor"] for n in r["novos"]} == {"openrouter"}
    assert r["erros"] == {}


def test_listar_novos_provedor_desconhecido_e_404(cenario):
    r = cenario.get("/api/provedores/novos", params={"provedor": "nao-existe"})
    assert r.status_code == 404


def test_listar_novos_provedor_sem_url_reporta_erro(cenario):
    # 'mistral' cadastrado sem url_modelos: a listagem não consulta nada e explica o motivo
    cenario.post("/api/provedores", json={"id": "semurl", "nome": "Sem URL", "tier": "PAID", "chave": "SEMURL_API_KEY"})
    r = cenario.get("/api/provedores/novos", params={"provedor": "semurl"}).json()
    assert r["novos"] == []
    assert "url_modelos" in r["erros"]["semurl"]


# ------------------------------------------------------------ estúdio: arquivos só de dentro das pastas
@pytest.mark.parametrize("rota", ["videos", "musicas", "imagens", "uploads"])
def test_estudio_nao_serve_arquivo_fora_da_pasta(cenario, rota):
    """Antes, GET de vídeos e músicas lia qualquer arquivo do disco: o .env (com o segredo de sessão) virava admin."""
    (cenario.raiz / "dados" / "estudio" / rota).mkdir(parents=True, exist_ok=True)
    alvo_absoluto = (cenario.raiz / ".env").resolve().as_posix()
    for caminho in ("..%2F..%2F..%2F.env", alvo_absoluto.replace("/", "%2F"), alvo_absoluto):
        r = cenario.get(f"/api/estudio/{rota}/{caminho}")
        assert r.status_code == 404, (rota, caminho)
        assert b"sk-super-secreto" not in r.content
        assert cenario.delete(f"/api/estudio/{rota}/{caminho}").status_code in (404, 405)
    assert (cenario.raiz / ".env").exists()


@pytest.mark.parametrize("rota, nome, conteudo", [
    ("videos", "clipe.mp4", b"mp4-falso"),
    ("musicas", "trilha.mp3", b"mp3-falso"),
    ("imagens", "foto.png", b"png-falso"),
])
def test_estudio_serve_e_exclui_arquivo_legitimo(cenario, rota, nome, conteudo):
    pasta = cenario.raiz / "dados" / "estudio" / rota
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / nome).write_bytes(conteudo)
    r = cenario.get(f"/api/estudio/{rota}/{nome}")
    assert r.status_code == 200 and r.content == conteudo
    assert cenario.delete(f"/api/estudio/{rota}/{nome}").status_code == 200
    assert not (pasta / nome).exists()


# ------------------------------------------------------------ listagem de modelos paginada
def _api_paginada(monkeypatch, responder):
    import httpx
    from tudoia_painel import provedores_service as ps
    pedidos = []

    def tratar(req):
        pedidos.append(dict(req.url.params))
        return httpx.Response(200, json=responder(dict(req.url.params)))
    cliente_real = httpx.Client
    monkeypatch.setattr(ps.httpx, "Client", lambda **kw: cliente_real(transport=httpx.MockTransport(tratar), **kw))
    return pedidos


def test_anthropic_segue_has_more(tmp_path, monkeypatch):
    from tudoia_painel import provedores_service as ps
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=x\n", encoding="utf-8")
    pedidos = _api_paginada(monkeypatch, lambda q: (
        {"data": [{"id": "claude-a"}], "has_more": True, "last_id": "claude-a"} if "after_id" not in q
        else {"data": [{"id": "claude-b"}], "has_more": False, "last_id": "claude-b"}))
    ids = [m["id"] for m in ps._buscar_modelos_api(
        {"url_modelos": "https://api.anthropic.com/v1/models", "chave": "ANTHROPIC_API_KEY"}, tmp_path / ".env")]
    assert ids == ["claude-a", "claude-b"]
    assert pedidos[1]["after_id"] == "claude-a" and pedidos[0]["limit"] == "1000"


def test_gemini_segue_next_page_token(tmp_path, monkeypatch):
    from tudoia_painel import provedores_service as ps
    (tmp_path / ".env").write_text("GEMINI_API_KEY=x\n", encoding="utf-8")
    _api_paginada(monkeypatch, lambda q: (
        {"models": [{"name": "models/g1"}], "nextPageToken": "p2"} if "pageToken" not in q
        else {"models": [{"name": "models/g2"}]}))
    ids = [m["id"] for m in ps._buscar_modelos_api(
        {"url_modelos": "https://generativelanguage.googleapis.com/v1beta/models", "chave": "GEMINI_API_KEY"},
        tmp_path / ".env")]
    assert ids == ["g1", "g2"]


def test_cloudflare_le_result_e_pagina(tmp_path, monkeypatch):
    from tudoia_painel import provedores_service as ps
    (tmp_path / ".env").write_text("CLOUDFLARE_API_KEY=x\nCLOUDFLARE_ACCOUNT_ID=conta\n", encoding="utf-8")
    _api_paginada(monkeypatch, lambda q: {
        "result": [{"id": "uuid-" + q["page"], "name": "@cf/m" + q["page"]}],
        "result_info": {"page": int(q["page"]), "per_page": 1, "total_count": 2}})
    ids = [m["id"] for m in ps._buscar_modelos_api(
        {"url_modelos": "https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/ai/models/search",
         "chave": "CLOUDFLARE_API_KEY"}, tmp_path / ".env")]
    assert ids == ["@cf/m1", "@cf/m2"]


def test_listagem_sem_fim_vira_falha_e_sincronizar_nao_inativa(tmp_path, monkeypatch):
    """Paginação que não acaba é resposta incompleta: o provedor fica como estava."""
    import yaml
    from tudoia_painel import provedores_service as ps
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=x\n", encoding="utf-8")
    _api_paginada(monkeypatch, lambda q: {"data": [{"id": "outro"}], "has_more": True, "last_id": "outro"})
    cat, rot = tmp_path / "cat.yaml", tmp_path / "rot.yaml"
    cat.write_text("provedores:\n  anthropic:\n    url_modelos: https://api.anthropic.com/v1/models\n"
                   "    chave: ANTHROPIC_API_KEY\n    modelos:\n"
                   "      - {nome: anthropic/claude-x, id: anthropic/claude-x, ativo: true}\n", encoding="utf-8")
    rot.write_text("ordem: {}\n", encoding="utf-8")
    r = ps.sincronizar_catalogo(cat, tmp_path / ".env", rot, aplicar=True)
    assert r["provedores"]["anthropic"]["ok"] is False
    assert yaml.safe_load(cat.read_text(encoding="utf-8"))["provedores"]["anthropic"]["modelos"][0]["ativo"] is True


def test_modelo_que_o_litellm_nao_carregou_ganha_dica_e_continua_ativo(cenario, monkeypatch):
    """Modelo recém-adicionado: config regenerado, LiteLLM não reiniciado. Antes isso desativava o modelo."""
    import httpx
    cat = cenario.raiz / "config" / "catalogo-modelos.yaml"
    antes = cat.read_bytes()
    corpo = {"error": {"message": "/chat/completions: Invalid model name passed in model=or/x"}}
    cliente_real = httpx.Client
    monkeypatch.setattr("httpx.Client", lambda **kw: cliente_real(
        transport=httpx.MockTransport(lambda req: httpx.Response(400, json=corpo)), **kw))
    r = cenario.post("/api/modelos/testar", json={"modelo": "or/x", "tipo": "litellm"}).json()
    assert r["ok"] is False and "reinicie o LiteLLM" in r["dica"]
    assert not r.get("desativado_automaticamente") and cat.read_bytes() == antes


def test_regeneracao_que_falha_vai_para_o_log_e_nao_derruba_a_gravacao(tmp_path, caplog):
    from tudoia_painel.gerador import regenerar_config_litellm
    assert regenerar_config_litellm(tmp_path) is False  # sem catálogo: falha
    assert "config do LiteLLM não regenerado" in caplog.text


# ------------------------------------------------------------ importar skill: só GitHub, sem link simbólico
@pytest.mark.parametrize("repo", [
    "https://github.com/dono/repo & calc.exe",
    "https://github.com/dono/repo\"|whoami",
    "https://evil.example/dono/repo",
    "http://github.com/dono/repo",
    "https://github.com/dono/repo/../../x",
    "dono/repo%COMSPEC%",
    "https://github.com/dono",
])
def test_importar_skill_recusa_repositorio_fora_do_formato(cenario, monkeypatch, repo):
    import subprocess
    chamadas = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: chamadas.append(a))
    r = cenario.post("/api/governanca/skills/importar", json={"repo_url": repo, "skill_nome": "x"})
    assert r.status_code == 422 and r.json()["erro"]["codigo"] == "validacao"
    assert chamadas == []  # nada chegou ao npx


def test_importar_skill_com_link_simbolico_e_recusada(cenario, monkeypatch, tmp_path):
    import os
    import subprocess
    from pathlib import Path
    segredo = tmp_path / "fora" / "id_rsa"
    segredo.parent.mkdir()
    segredo.write_text("CHAVE-PRIVADA", encoding="utf-8")
    # O skip precisa acontecer aqui: dentro do falso ele roda na thread do servidor e derruba o TestClient.
    try:
        os.symlink(segredo, tmp_path / "sonda")
    except OSError:
        pytest.skip("este Windows não permite criar link simbólico sem privilégio")

    def falso(cmd, cwd, capture_output, text, timeout):
        pasta = Path(cwd) / ".agents" / "skills" / "maliciosa"
        pasta.mkdir(parents=True)
        (pasta / "SKILL.md").write_text("# x\n", encoding="utf-8")
        os.symlink(segredo, pasta / "id_rsa")
        return type("P", (), {"returncode": 0, "stdout": "", "stderr": ""})()
    monkeypatch.setattr(subprocess, "run", falso)
    r = cenario.post("/api/governanca/skills/importar", json={"repo_url": "dono/repo", "skill_nome": "maliciosa"})
    assert r.status_code == 422 and r.json()["erro"]["codigo"] == "skill_invalida"
    assert not (cenario.raiz / "governanca" / "skills" / "maliciosa").exists()


# ------------------------------------------------------------ guarda: corpo sem Content-Length e /auth
def test_corpo_chunked_acima_do_limite_e_recusado(cenario):
    """Sem Content-Length (Transfer-Encoding: chunked) o limite antes não era aplicado."""
    def corpo():
        yield b'{"conteudo": "'
        for _ in range(11):
            yield b"x" * (1024 * 1024)
        yield b'"}'
    r = cenario.post("/api/governanca/regras", content=corpo(), headers=JSON_H)
    assert r.status_code == 413 and r.json()["erro"]["codigo"] == "corpo_grande_demais"


def test_corpo_chunked_pequeno_passa(cenario):
    def corpo():
        yield b'{"acao": '
        yield b'"start"}'
    r = cenario.post("/api/servicos/litellm/acao", content=corpo(), headers=JSON_H)
    assert r.status_code != 413


def test_auth_com_host_estranho_e_recusado(cenario):
    r = cenario.get("/auth/login", headers={"host": "evil.example:3100"}, follow_redirects=False)
    assert r.status_code == 403 and r.json()["erro"]["codigo"] == "host_recusado"


def test_sincronizacao_consulta_a_rede_fora_da_trava(cenario, monkeypatch):
    """Com a trava presa durante a rede, toda gravação do painel esperava as APIs dos provedores."""
    import threading
    from tudoia_painel import provedores_service as ps
    resultados = []

    def api(p, env):
        # Enquanto a "rede" responde, outra rota de escrita do painel precisa conseguir rodar (com prazo: se a
        # trava estiver presa, a thread não termina e o teste falha em vez de travar).
        t = threading.Thread(target=lambda: resultados.append(
            cenario.post("/api/governanca/regras", json={"id": "x-trava", "conteudo": "# x"}).status_code))
        t.start()
        t.join(timeout=10)
        resultados.append("terminou" if not t.is_alive() else "travou")
        return []
    monkeypatch.setattr(ps, "_buscar_modelos_api", api)
    r = cenario.post("/api/provedores/sincronizar", json={"aplicar": False})
    assert r.status_code == 200
    assert "travou" not in resultados and "terminou" in resultados


def test_imagem_sem_motor_nao_envia_prompt_ao_pollinations_por_padrao(cenario, monkeypatch):
    """ComfyUI fora e sem Cloudflare: antes o prompt ia em silêncio para um serviço público."""
    import httpx
    monkeypatch.setattr("tudoia_painel.servicos.porta_aberta", lambda porta: False)
    pedidos = []
    cliente_real = httpx.Client

    def registrar(req):
        pedidos.append(str(req.url))
        return httpx.Response(500)
    monkeypatch.setattr("httpx.Client",
                        lambda **kw: cliente_real(transport=httpx.MockTransport(registrar), **kw))
    r = cenario.post("/api/estudio/gerar-imagem", json={"prompt": "<b>segredo</b> do usuário", "modelo": "flux"})
    d = r.json()
    assert d["ok"] is True and d["motor"] == "estudio" and "TUDOIA_ESTUDIO_POLLINATIONS" in d["aviso"]
    assert not [u for u in pedidos if "pollinations" in u]
    svg = (cenario.raiz / "dados" / "estudio" / "imagens" / d["imagem_url"].rsplit("/", 1)[1]).read_text(encoding="utf-8")
    assert "<b>" not in svg and "&lt;b&gt;" in svg


def test_pollinations_ligado_no_env_e_usado(cenario, monkeypatch):
    import httpx
    with open(cenario.raiz / ".env", "a", encoding="utf-8") as f:
        f.write("TUDOIA_ESTUDIO_POLLINATIONS=1\n")
    monkeypatch.setattr("tudoia_painel.servicos.porta_aberta", lambda porta: False)
    cliente_real = httpx.Client
    monkeypatch.setattr("httpx.Client", lambda **kw: cliente_real(transport=httpx.MockTransport(
        lambda req: httpx.Response(200, content=b"\xff\xd8" + b"0" * 2000) if "pollinations" in str(req.url)
        else httpx.Response(500)), **kw))
    d = cenario.post("/api/estudio/gerar-imagem", json={"prompt": "uma ponte", "modelo": "flux"}).json()
    assert d["ok"] is True and d["motor"] == "nuvem" and "aviso" not in d


def test_governanca_sem_mcp_json_nao_quebra(cenario):
    (cenario.raiz / "governanca" / "mcp.json").unlink()
    r = cenario.get("/api/governanca")
    assert r.status_code == 200 and r.json()["mcp_configs"] == {}


@pytest.mark.parametrize("item", ["midia:comfyui/ComfyUI_windows_portable/ComfyUI/main.py", "midia:x/run.bat",
                                  "fluxo:../../governanca/governanca.json", "fluxo:x.py"])
def test_excluir_midia_so_aceita_pesos_e_fluxos(cenario, item):
    alvo = cenario.raiz / "modelos" / "comfyui" / "ComfyUI_windows_portable" / "ComfyUI" / "main.py"
    alvo.parent.mkdir(parents=True, exist_ok=True)
    alvo.write_text("print('comfy')", encoding="utf-8")
    r = cenario.delete(f"/api/modelos/midia/{item}")
    assert r.status_code == 422
    assert alvo.exists() and (cenario.raiz / "governanca" / "governanca.json").exists()


# ------------------------------------------------------------ observabilidade: id do pedido, auditoria, saúde
def test_resposta_traz_id_do_pedido(cenario):
    a, b = cenario.get("/api/servicos"), cenario.get("/api/servicos")
    assert len(a.headers["x-request-id"]) == 16 and a.headers["x-request-id"] != b.headers["x-request-id"]


def test_auditoria_registra_alteracao_e_negacao_sem_o_corpo(cenario):
    import json as _json
    from tudoia_painel.autenticacao import PAPEL_LEITOR
    cenario.put("/api/segredos/GROQ_API_KEY", json={"valor": "gsk_valor_que_nao_pode_vazar_123"})
    cenario.post("/api/servicos/litellm/restart", json={})
    cenario.get("/api/servicos")  # leitura não entra
    cenario.cookies.set("tudoia_sessao", sessao_assinada([PAPEL_LEITOR]))
    cenario.post("/api/servicos/litellm/restart", json={})  # negado
    bruto = (cenario.raiz / "dados" / "logs" / "auditoria.jsonl").read_text(encoding="utf-8")
    assert "gsk_valor_que_nao_pode_vazar" not in bruto
    linhas = [_json.loads(x) for x in bruto.splitlines()]
    assert [(x["metodo"], x["rota"], x["status"]) for x in linhas] == [
        ("PUT", "/api/segredos/GROQ_API_KEY", linhas[0]["status"]),
        ("POST", "/api/servicos/litellm/restart", 200),
        ("POST", "/api/servicos/litellm/restart", 403),
    ]
    assert linhas[1]["usuario"] == "teste@local" and linhas[1]["papeis"] == [PAPEL_ADMIN]
    assert all(len(x["id"]) == 16 for x in linhas)


def test_saude_responde_sem_login(cenario):
    cenario.cookies.clear()
    r = cenario.get("/saude")
    assert r.status_code == 200 and r.json() == {"ok": True}


@pytest.mark.parametrize("periodo, filtra", [(24, True), (168, True), (None, False), (0, False)])
def test_logs_de_gasto_pedem_so_o_periodo(monkeypatch, periodo, filtra):
    """Sem filtro o LiteLLM devolvia ~27 MB a cada atualização da telemetria."""
    import datetime as dt

    import httpx
    from tudoia_painel import limites
    pedidos = []
    cliente_real = httpx.Client

    def responder(req):
        pedidos.append(dict(req.url.params))
        return httpx.Response(200, json=[{"request_id": "r1", "total_tokens": 3}])
    monkeypatch.setattr(limites.httpx, "Client", lambda **kw: cliente_real(transport=httpx.MockTransport(responder), **kw))
    assert limites.ler_logs_litellm("chave", periodo) == [{"request_id": "r1", "total_tokens": 3}]
    if filtra:
        inicio = dt.date.fromisoformat(pedidos[0]["start_date"])
        assert pedidos[0]["summarize"] == "false"
        assert inicio <= (dt.datetime.now() - dt.timedelta(hours=periodo)).date()
        assert dt.date.fromisoformat(pedidos[0]["end_date"]) > dt.date.today()
    else:
        assert pedidos[0] == {}


def test_logs_de_gasto_sem_litellm_devolvem_vazio():
    from tudoia_painel import limites
    assert limites.ler_logs_litellm("chave", 24) == []   # rede bloqueada no conftest: ConnectError
    assert limites.ler_logs_litellm("", 24) == []


def test_listar_novos_catalogo_ignora_provedores_sem_chave(tmp_path, monkeypatch):
    from tudoia_painel import provedores_service as ps
    cat = tmp_path / "catalogo.yaml"
    env_file = tmp_path / ".env"
    cat.write_text("""
provedores:
  openrouter:
    nome: OpenRouter
    tier: FREE
    chave: OPENROUTER_API_KEY
    url_modelos: https://openrouter.ai/api/v1/models
  nvidia:
    nome: NVIDIA
    tier: FREE
    chave: NVIDIA_NIM_API_KEY
    url_modelos: https://integrate.api.nvidia.com/v1/models
""", encoding="utf-8")
    env_file.write_text("NVIDIA_NIM_API_KEY=chave_valida\n", encoding="utf-8")

    # Mock de busca para retornar modelo se chamado
    monkeypatch.setattr(ps, "_buscar_modelos_api", lambda p, env: [{"id": "meta/llama-3"}])

    # 1. Listando todos: openrouter deve ser ignorado sem erro, nvidia deve vir
    res = ps.listar_novos_catalogo(cat, env_file)
    assert res["ok"] is True
    provs = {m["provedor"] for m in res["novos"]}
    assert "nvidia" in provs
    assert "openrouter" not in provs
    assert "openrouter" not in res["erros"]

    # 2. Pedindo openrouter explicitamente: deve avisar que está sem chave no .env
    res_especifico = ps.listar_novos_catalogo(cat, env_file, provedor="openrouter")
    assert "openrouter" in res_especifico["erros"]
    assert "sem chave" in res_especifico["erros"]["openrouter"]


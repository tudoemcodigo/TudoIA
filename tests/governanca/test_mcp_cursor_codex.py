"""MCP para o Cursor (~/.cursor/mcp.json) e o Codex (~/.codex/config.toml): só as entradas do catálogo são nossas."""
import json
import tomllib
from pathlib import Path

import pytest

import governanca
from governanca import ErroGovernanca, aplicar_tudo, sincronizar, verificar

SEGREDO = "segredo-123"

# Conteúdo que o app do Codex mantém: nada disto pode mudar (nem formatação, nem comentários).
CODEX_DO_APP = """notify = ["x"]
model = "gpt-6"
# comentário do usuário

[desktop]
followUpQueueMode = "queue"

[plugins."browser@openai-bundled"]
enabled = true

[mcp_servers.node_repl]
command = 'C:\\Codex\\node_repl.exe'
args = []
env_vars = ["A", "B"]

[mcp_servers.node_repl.env]
CODEX_HOME = 'C:\\Users\\x\\.codex'

[projects.'d:\\projetos\\x']
trust_level = "trusted"
"""


def _montar(tmp_path: Path, catalogo=None, mcp=("github", "cerebro")) -> tuple[Path, Path]:
    raiz, home, ws = tmp_path / "raiz", tmp_path / "home", tmp_path / "ws"
    for p in (raiz, home, ws):
        p.mkdir()
    g = raiz / "governanca"
    (g / "regras").mkdir(parents=True)
    (g / "skills").mkdir()
    (g / "regras" / "base.md").write_text("# Regra\n", encoding="utf-8")
    (g / "mcp.json").write_text(json.dumps({"mcpServers": catalogo or {
        "github": {"command": "npx", "args": ["-y", "srv-github"], "env": {"TOKEN": "${GH_TOKEN}"},
                   "description": "não vai para o cliente"},
        "cerebro": {"type": "http", "url": "http://127.0.0.1:8765/mcp",
                    "headers": {"Authorization": "Bearer ${GH_TOKEN}"}},
        "vercel": {"type": "http", "url": "https://mcp.vercel.com", "auth": "oauth"},
    }}), encoding="utf-8")
    instancias = [
        {"id": "cursor-ws", "cliente": "cursor", "caminho": str(ws), "ativo": True},
        {"id": "codex", "cliente": "codex", "caminho": "~/.codex", "ativo": True},
    ]
    (g / "governanca.json").write_text(json.dumps({
        "regras": ["base"], "skills": [], "mcp": list(mcp), "workspaces": [str(ws)], "clientes": [],
        "instancias": instancias}), encoding="utf-8")
    (raiz / ".env").write_text(f"GH_TOKEN={SEGREDO}\n", encoding="utf-8")
    return raiz, home


# ---------------------------------------------------------------- Cursor

def test_cursor_recebe_mcp_global_na_home_com_formato_do_cursor(tmp_path):
    raiz, home = _montar(tmp_path)
    sincronizar(raiz, home)
    dados = json.loads((home / ".cursor" / "mcp.json").read_text(encoding="utf-8"))["mcpServers"]
    assert dados["github"] == {"command": "npx", "args": ["-y", "srv-github"], "env": {"TOKEN": SEGREDO}}
    # remoto: só url/headers (sem 'type', que é do formato do Claude); description nunca vai
    assert dados["cerebro"] == {"url": "http://127.0.0.1:8765/mcp", "headers": {"Authorization": f"Bearer {SEGREDO}"}}


def test_cursor_nunca_recebe_mcp_com_segredo_dentro_do_workspace(tmp_path):
    """A instância do Cursor aponta para um workspace; o mcp.json com segredo vai para a home, não para lá."""
    raiz, home = _montar(tmp_path)
    sincronizar(raiz, home)
    assert not (tmp_path / "ws" / ".cursor" / "mcp.json").exists()
    assert (tmp_path / "ws" / ".cursor" / "rules" / "tudoia.mdc").is_file()


def test_cursor_preserva_servidor_do_usuario_e_e_idempotente(tmp_path):
    raiz, home = _montar(tmp_path)
    alvo = home / ".cursor" / "mcp.json"
    alvo.parent.mkdir()
    alvo.write_text(json.dumps({"mcpServers": {"meu": {"command": "uvx", "args": ["x"]}}, "outra": 1}), encoding="utf-8")
    sincronizar(raiz, home)
    dados = json.loads(alvo.read_text(encoding="utf-8"))
    assert dados["mcpServers"]["meu"] == {"command": "uvx", "args": ["x"]} and dados["outra"] == 1
    antes = alvo.read_bytes()
    r = sincronizar(raiz, home)
    assert all(v == "igual" for k, v in r.items() if "mcp" in k) and alvo.read_bytes() == antes


def test_cursor_json_malformado_e_recusado_sem_gravar_nada(tmp_path):
    raiz, home = _montar(tmp_path)
    alvo = home / ".cursor" / "mcp.json"
    alvo.parent.mkdir()
    alvo.write_text("{ quebrado", encoding="utf-8")
    with pytest.raises(ErroGovernanca, match="JSON inválido"):
        sincronizar(raiz, home)
    assert alvo.read_text(encoding="utf-8") == "{ quebrado"
    assert not (home / ".codex" / "config.toml").exists()   # fail-closed: nada foi gravado


# ---------------------------------------------------------------- Codex

def _codex(home: Path, texto: str = CODEX_DO_APP) -> Path:
    alvo = home / ".codex" / "config.toml"
    alvo.parent.mkdir(parents=True, exist_ok=True)
    alvo.write_text(texto, encoding="utf-8", newline="\n")
    return alvo


def test_codex_preserva_byte_a_byte_o_que_e_do_app_e_acrescenta_os_nossos(tmp_path):
    raiz, home = _montar(tmp_path)
    alvo = _codex(home)
    sincronizar(raiz, home)
    texto = alvo.read_text(encoding="utf-8")
    assert texto.startswith(CODEX_DO_APP)                      # o arquivo do app intacto, comentário incluído
    dados = tomllib.loads(texto)
    assert dados["mcp_servers"]["node_repl"]["env"]["CODEX_HOME"] == "C:\\Users\\x\\.codex"
    gh = dados["mcp_servers"]["github"]
    assert gh["env"] == {"TOKEN": SEGREDO} and "description" not in gh
    assert dados["mcp_servers"]["cerebro"] == {"url": "http://127.0.0.1:8765/mcp",
                                                "http_headers": {"Authorization": f"Bearer {SEGREDO}"}}


def test_codex_substitui_entrada_antiga_nossa_e_remove_a_desativada(tmp_path):
    raiz, home = _montar(tmp_path, mcp=("github",))
    alvo = _codex(home, CODEX_DO_APP + '\n[mcp_servers.cerebro]\nurl = "http://antigo"\n\n'
                                       '[mcp_servers.github]\ncommand = "velho"\n\n[mcp_servers.github.env]\nX = "1"\n')
    sincronizar(raiz, home)
    dados = tomllib.loads(alvo.read_text(encoding="utf-8"))["mcp_servers"]
    assert "cerebro" not in dados                               # desativado: sai
    assert "X" not in dados["github"].get("env", {})            # subtabela antiga da entrada nossa também sai
    assert set(dados) == {"node_repl", "github"}


def test_codex_e_idempotente(tmp_path):
    raiz, home = _montar(tmp_path)
    alvo = _codex(home)
    sincronizar(raiz, home)
    antes = alvo.read_bytes()
    assert sincronizar(raiz, home)["codex:codex:mcp"] == "igual" and alvo.read_bytes() == antes
    assert verificar(raiz, home) == []


def test_codex_toml_malformado_e_recusado(tmp_path):
    raiz, home = _montar(tmp_path)
    alvo = _codex(home, "model = \n")
    with pytest.raises(ErroGovernanca, match="TOML inválido"):
        sincronizar(raiz, home)
    assert alvo.read_text(encoding="utf-8") == "model = \n"


def test_codex_em_formato_que_nao_da_para_editar_por_tabela_e_recusado(tmp_path):
    """mcp_servers em tabela inline: a edição por tabela não alcança; a checagem semântica recusa em vez de corromper."""
    raiz, home = _montar(tmp_path)
    original = 'mcp_servers = { github = { command = "x" } }\n'
    alvo = _codex(home, original)
    with pytest.raises(ErroGovernanca, match="edite"):
        sincronizar(raiz, home)
    assert alvo.read_text(encoding="utf-8") == original


def test_codex_npx_no_windows_vai_por_cmd(tmp_path, monkeypatch):
    monkeypatch.setattr(governanca, "_WINDOWS", True)
    raiz, home = _montar(tmp_path)
    alvo = _codex(home)
    sincronizar(raiz, home)
    gh = tomllib.loads(alvo.read_text(encoding="utf-8"))["mcp_servers"]["github"]
    assert gh["command"] == "cmd" and gh["args"] == ["/c", "npx", "-y", "srv-github"]


def test_codex_npx_fora_do_windows_fica_como_esta(tmp_path, monkeypatch):
    monkeypatch.setattr(governanca, "_WINDOWS", False)
    raiz, home = _montar(tmp_path)
    sincronizar(raiz, home)
    gh = tomllib.loads((home / ".codex" / "config.toml").read_text(encoding="utf-8"))["mcp_servers"]["github"]
    assert gh["command"] == "npx"


@pytest.mark.parametrize("valor", ['aspas " e \\ barra', "linha\nnova\ttab", "acentuação ç 漢字", "C:\\a\\b", ""])
def test_codex_escapa_qualquer_valor_e_le_de_volta_igual(tmp_path, valor):
    raiz, home = _montar(tmp_path, catalogo={"github": {"command": "npx", "env": {"V": valor}}}, mcp=("github",))
    sincronizar(raiz, home)
    gh = tomllib.loads((home / ".codex" / "config.toml").read_text(encoding="utf-8"))["mcp_servers"]["github"]
    assert gh["env"]["V"] == valor


def test_codex_id_com_ponto_vira_chave_entre_aspas(tmp_path):
    raiz, home = _montar(tmp_path, catalogo={"srv.x": {"command": "uvx"}}, mcp=("srv.x",))
    sincronizar(raiz, home)
    dados = tomllib.loads((home / ".codex" / "config.toml").read_text(encoding="utf-8"))["mcp_servers"]
    assert dados["srv.x"]["command"] == "uvx" and "srv" not in dados


def test_codex_sse_e_recusado_com_mensagem_clara(tmp_path):
    raiz, home = _montar(tmp_path, catalogo={"velho": {"type": "sse", "url": "http://x/sse"}}, mcp=("velho",))
    with pytest.raises(ErroGovernanca, match="Codex"):
        sincronizar(raiz, home)


def test_codex_oauth_vai_sem_cabecalho(tmp_path):
    raiz, home = _montar(tmp_path, mcp=("vercel",))
    sincronizar(raiz, home)
    vercel = tomllib.loads((home / ".codex" / "config.toml").read_text(encoding="utf-8"))["mcp_servers"]["vercel"]
    assert vercel == {"url": "https://mcp.vercel.com"}   # o login OAuth é do próprio Codex (codex mcp login)


# ---------------------------------------------------------------- drift, backup e aplicar_tudo

def test_verificar_aponta_cursor_e_codex_ate_sincronizar(tmp_path):
    raiz, home = _montar(tmp_path)
    _codex(home)
    alvos = " ".join(verificar(raiz, home))
    assert "cursor" in alvos and "codex" in alvos and "mcp" in alvos
    sincronizar(raiz, home)
    assert verificar(raiz, home) == []


def test_aplicar_tudo_faz_backup_dos_dois_fora_do_workspace(tmp_path):
    raiz, home = _montar(tmp_path)
    _codex(home)
    alvo = home / ".cursor" / "mcp.json"
    alvo.parent.mkdir()
    alvo.write_text('{"mcpServers": {}}', encoding="utf-8")
    base = home / ".tudoia" / "backups"
    aplicar_tudo(raiz, home, base)
    assert list((base / "codex-toml").iterdir()) and list((base / "cursor-json").iterdir())

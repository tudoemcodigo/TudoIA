import json
from pathlib import Path

import pytest

from governanca import ErroGovernanca, aplicar_mcp_claude, sincronizar, verificar

SEGREDO = "segredo-123"
MANUAL = {"command": "uvx", "args": ["meu-mcp-manual"], "env": {"TOKEN_MANUAL": "nao-mexer"}}


def _montar(tmp_path: Path, instancias=None, catalogo=None) -> tuple[Path, Path, Path]:
    raiz, home, ws = tmp_path / "raiz", tmp_path / "home", tmp_path / "ws"
    for p in (raiz, home, ws):
        p.mkdir()
    g = raiz / "governanca"
    (g / "regras").mkdir(parents=True)
    (g / "skills").mkdir()
    (g / "regras" / "base.md").write_text("# Regra base\nSeja crítico.\n", encoding="utf-8")
    (g / "mcp.json").write_text(json.dumps({"mcpServers": catalogo or {
        "github": {"command": "npx", "env": {"GH": "${GH_TOKEN}"}},
        "cerebro": {"type": "http", "url": "http://127.0.0.1:8765/mcp"},
    }}), encoding="utf-8")
    cfg = {"regras": ["base"], "skills": [], "mcp": ["github", "cerebro"],
           "workspaces": [str(ws)], "clientes": ["claude"]}
    if instancias is not None:
        cfg["instancias"] = instancias
    (g / "governanca.json").write_text(json.dumps(cfg), encoding="utf-8")
    (raiz / ".env").write_text(f"GH_TOKEN={SEGREDO}\n", encoding="utf-8")
    return raiz, home, ws


def _claude(home: Path, cid="claude-padrao", caminho="~/.claude", config_json="~/.claude.json", ativo=True):
    return {"id": cid, "cliente": "claude", "caminho": caminho, "config_json": config_json, "ativo": ativo}


def _manual(arquivo: Path, extra: dict | None = None) -> bytes:
    dados = {"numStartups": 7, "mcpServers": {"minha-manual": MANUAL, **(extra or {})}}
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(json.dumps(dados, indent=2), encoding="utf-8")
    return arquivo.read_bytes()


# ------------------------------------------------ sync não toca mcpServers do Claude

def test_sincronizar_nao_altera_claude_json_com_servidor_manual(tmp_path):
    raiz, home, _ = _montar(tmp_path)
    antes = _manual(home / ".claude.json")
    sincronizar(raiz, home)
    assert (home / ".claude.json").read_bytes() == antes
    assert "minha-manual" in json.loads(antes)["mcpServers"]


def test_sincronizar_sem_claude_json_nao_cria_arquivo(tmp_path):
    raiz, home, _ = _montar(tmp_path)
    sincronizar(raiz, home)
    assert not (home / ".claude.json").exists()


# ------------------------------------------------ painel: escreve só o que possui

def test_aplicar_preserva_servidor_manual_e_grava_ativos_com_segredo_em_home(tmp_path):
    raiz, home, _ = _montar(tmp_path)
    _manual(home / ".claude.json")
    aplicar_mcp_claude(raiz, home, tmp_path / "bk")
    dados = json.loads((home / ".claude.json").read_text(encoding="utf-8"))
    assert dados["numStartups"] == 7
    assert dados["mcpServers"]["minha-manual"] == MANUAL
    assert dados["mcpServers"]["github"]["env"]["GH"] == SEGREDO
    assert "cerebro" in dados["mcpServers"]


def test_aplicar_remove_catalogo_inativo_mas_nao_manual(tmp_path):
    raiz, home, _ = _montar(tmp_path)
    _manual(home / ".claude.json", {"github": {"command": "velho"}})
    aplicar_mcp_claude(raiz, home, tmp_path / "bk")
    cfg = json.loads((raiz / "governanca" / "governanca.json").read_text(encoding="utf-8"))
    cfg["mcp"] = ["cerebro"]
    (raiz / "governanca" / "governanca.json").write_text(json.dumps(cfg), encoding="utf-8")
    aplicar_mcp_claude(raiz, home, tmp_path / "bk")
    servidores = json.loads((home / ".claude.json").read_text(encoding="utf-8"))["mcpServers"]
    assert "github" not in servidores
    assert servidores["minha-manual"] == MANUAL


def test_aplicar_remover_explicito_retira_id_que_saiu_do_catalogo(tmp_path):
    raiz, home, _ = _montar(tmp_path)
    aplicar_mcp_claude(raiz, home, tmp_path / "bk")
    mcp = json.loads((raiz / "governanca" / "mcp.json").read_text(encoding="utf-8"))
    del mcp["mcpServers"]["github"]
    (raiz / "governanca" / "mcp.json").write_text(json.dumps(mcp), encoding="utf-8")
    cfg = json.loads((raiz / "governanca" / "governanca.json").read_text(encoding="utf-8"))
    cfg["mcp"] = ["cerebro"]
    (raiz / "governanca" / "governanca.json").write_text(json.dumps(cfg), encoding="utf-8")
    aplicar_mcp_claude(raiz, home, tmp_path / "bk", remover=("github",))
    assert "github" not in json.loads((home / ".claude.json").read_text(encoding="utf-8"))["mcpServers"]


def test_aplicar_e_idempotente(tmp_path):
    raiz, home, _ = _montar(tmp_path)
    aplicar_mcp_claude(raiz, home, tmp_path / "bk")
    depois = (home / ".claude.json").read_bytes()
    assert set(aplicar_mcp_claude(raiz, home, tmp_path / "bk").values()) == {"igual"}
    assert (home / ".claude.json").read_bytes() == depois


def test_aplicar_faz_backup_antes_de_sobrescrever(tmp_path):
    raiz, home, _ = _montar(tmp_path)
    antes = _manual(home / ".claude.json")
    bk = tmp_path / "bk"
    aplicar_mcp_claude(raiz, home, bk)
    backups = list(bk.glob("*.claude.json.*"))
    assert len(backups) == 1 and backups[0].read_bytes() == antes


def test_aplicar_nao_deixa_arquivo_temporario(tmp_path):
    raiz, home, _ = _montar(tmp_path)
    _manual(home / ".claude.json")
    aplicar_mcp_claude(raiz, home, tmp_path / "bk")
    assert not (home / ".claude.json.tmp").exists()


def test_backups_sao_limitados(tmp_path):
    raiz, home, _ = _montar(tmp_path)
    _manual(home / ".claude.json")
    bk = tmp_path / "bk"
    for i in range(14):
        (home / ".claude.json").write_text(json.dumps({"mcpServers": {"minha-manual": {"i": i}}}), encoding="utf-8")
        aplicar_mcp_claude(raiz, home, bk)
    assert len(list(bk.glob("*.claude.json.*"))) <= 10


# ------------------------------------------------ fail-closed

@pytest.mark.parametrize("conteudo", ["{nao é json", "[]", json.dumps({"mcpServers": []})])
def test_claude_json_malformado_falha_sem_escrever(tmp_path, conteudo):
    raiz, home, _ = _montar(tmp_path)
    (home / ".claude.json").write_text(conteudo, encoding="utf-8")
    antes = (home / ".claude.json").read_bytes()
    with pytest.raises(ErroGovernanca):
        aplicar_mcp_claude(raiz, home, tmp_path / "bk")
    assert (home / ".claude.json").read_bytes() == antes
    assert not (tmp_path / "bk").exists()


def test_variavel_ausente_falha_antes_de_tocar_claude_json(tmp_path):
    raiz, home, _ = _montar(tmp_path)
    antes = _manual(home / ".claude.json")
    (raiz / ".env").write_text("", encoding="utf-8")
    with pytest.raises(ErroGovernanca, match="GH_TOKEN"):
        aplicar_mcp_claude(raiz, home, tmp_path / "bk")
    assert (home / ".claude.json").read_bytes() == antes


def test_destino_fora_de_home_e_workspace_e_recusado(tmp_path):
    fora = tmp_path / "fora"
    fora.mkdir()
    raiz, home, ws = _montar(tmp_path, instancias=[
        _claude(None, config_json=str(fora / ".claude.json"), caminho=str(fora)),
    ])
    with pytest.raises(ErroGovernanca, match="fora de home e de workspace"):
        aplicar_mcp_claude(raiz, home, tmp_path / "bk")
    with pytest.raises(ErroGovernanca):
        verificar(raiz, home)
    assert not (fora / ".claude.json").exists()
    with pytest.raises(ErroGovernanca):
        sincronizar(raiz, home)
    assert not (fora / "CLAUDE.md").exists()


# ------------------------------------------------ regra de segredos

def test_destino_workspace_recebe_placeholder_nunca_o_segredo(tmp_path):
    raiz, home, ws = _montar(tmp_path)
    alvo = ws / ".claude.json"
    (raiz / "governanca" / "governanca.json").write_text(json.dumps({
        "regras": ["base"], "skills": [], "mcp": ["github"], "workspaces": [str(ws)], "clientes": [],
        "instancias": [_claude(home, cid="repo", caminho=str(ws), config_json=str(alvo))],
    }), encoding="utf-8")
    aplicar_mcp_claude(raiz, home, tmp_path / "bk")
    texto = alvo.read_text(encoding="utf-8")
    assert SEGREDO not in texto
    assert json.loads(texto)["mcpServers"]["github"]["env"]["GH"] == "${GH_TOKEN}"


def test_destino_home_recebe_segredo(tmp_path):
    raiz, home, ws = _montar(tmp_path, instancias=[_claude(None, caminho="~/.claude")])
    aplicar_mcp_claude(raiz, home, tmp_path / "bk")
    assert SEGREDO in (home / ".claude.json").read_text(encoding="utf-8")


def test_workspace_sem_nenhum_segredo_literal_no_disco(tmp_path):
    raiz, home, ws = _montar(tmp_path, instancias=[_claude(None, caminho="~/.claude")])
    (raiz / "governanca" / "governanca.json").write_text(json.dumps({
        "regras": ["base"], "skills": [], "mcp": ["github"], "workspaces": [str(ws)], "clientes": [],
        "instancias": [_claude(None, cid="repo", caminho=str(ws), config_json=str(ws / ".claude.json"))],
    }), encoding="utf-8")
    sincronizar(raiz, home)
    aplicar_mcp_claude(raiz, home, tmp_path / "bk")
    for f in ws.rglob("*"):
        if f.is_file():
            assert SEGREDO not in f.read_text(encoding="utf-8")


def test_catalogo_com_segredo_literal_nao_vai_para_workspace(tmp_path):
    catalogo = {"github": {"command": "npx", "env": {"GH": SEGREDO}},
                "cerebro": {"type": "http", "url": "http://127.0.0.1:8765/mcp"}}
    raiz, home, ws = _montar(tmp_path, catalogo=catalogo)
    (raiz / "governanca" / "governanca.json").write_text(json.dumps({
        "regras": ["base"], "skills": [], "mcp": ["github"], "workspaces": [str(ws)], "clientes": [],
        "instancias": [_claude(None, cid="repo", caminho=str(ws), config_json=str(ws / ".claude.json"))],
    }), encoding="utf-8")
    with pytest.raises(ErroGovernanca, match="valor literal de segredo"):
        aplicar_mcp_claude(raiz, home, tmp_path / "bk")
    assert not (ws / ".claude.json").exists()


# ------------------------------------------------ drift só do que o painel possui

def test_verificar_ignora_servidor_manual_e_detecta_divergencia_do_catalogo(tmp_path):
    raiz, home, _ = _montar(tmp_path)
    _manual(home / ".claude.json")
    sincronizar(raiz, home)
    aplicar_mcp_claude(raiz, home, tmp_path / "bk")
    assert verificar(raiz, home) == []
    dados = json.loads((home / ".claude.json").read_text(encoding="utf-8"))
    dados["mcpServers"]["cerebro"]["url"] = "http://outro"
    (home / ".claude.json").write_text(json.dumps(dados), encoding="utf-8")
    assert any("claude:mcp" in p and "divergente" in p for p in verificar(raiz, home))

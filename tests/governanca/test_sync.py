import json
from pathlib import Path

import pytest

from governanca import ErroGovernanca, aplicar_mcp_claude, aplicar_mcp_opencode, sincronizar, verificar

MARCA_INI = "<!-- tudoia:inicio"


def _montar(tmp_path: Path, **over) -> tuple[Path, Path, Path]:
    raiz, home, ws = tmp_path / "raiz", tmp_path / "home", tmp_path / "ws"
    for p in (raiz, home, ws):
        p.mkdir()
    g = raiz / "governanca"
    (g / "regras").mkdir(parents=True)
    (g / "skills" / "grill-me").mkdir(parents=True)
    (g / "regras" / "base.md").write_text("# Regra base\nSeja crítico.\n", encoding="utf-8")
    (g / "skills" / "grill-me" / "SKILL.md").write_text("---\nname: grill-me\n---\nPergunte.\n", encoding="utf-8")
    (g / "mcp.json").write_text(json.dumps({"mcpServers": {
        "github": {"command": "npx", "env": {"TOKEN": "${GH_TOKEN}"}},
        "cerebro": {"type": "http", "url": "http://127.0.0.1:8765/mcp"},
    }}), encoding="utf-8")
    cfg = {"regras": ["base"], "skills": ["grill-me"], "mcp": ["github", "cerebro"],
           "workspaces": [str(ws)], "clientes": ["antigravity", "claude", "cursor", "codex"]}
    cfg.update(over)
    (g / "governanca.json").write_text(json.dumps(cfg), encoding="utf-8")
    (raiz / ".env").write_text("GH_TOKEN=segredo-123\n", encoding="utf-8")
    return raiz, home, ws


def test_gera_arquivos_para_todos_os_clientes(tmp_path):
    raiz, home, ws = _montar(tmp_path)
    res = sincronizar(raiz, home)
    assert "Seja crítico." in (ws / "AGENTS.md").read_text(encoding="utf-8")
    assert (ws / ".cursor" / "rules" / "tudoia.mdc").is_file()
    assert "Seja crítico." in (home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")
    assert "Seja crítico." in (home / ".gemini" / "GEMINI.md").read_text(encoding="utf-8")
    assert (home / ".gemini" / "antigravity-cli" / "skills" / "grill-me" / "SKILL.md").is_file()
    assert not (home / ".claude.json").exists()   # sync não escreve mcpServers do Claude (é do painel)
    assert set(res.values()) == {"atualizado"}
    assert not any(k.endswith(":mcp") and "claude" in k for k in res)


def test_idempotente(tmp_path):
    raiz, home, _ = _montar(tmp_path)
    sincronizar(raiz, home)
    assert set(sincronizar(raiz, home).values()) == {"igual"}


def test_preserva_conteudo_do_usuario_fora_do_bloco(tmp_path):
    raiz, home, ws = _montar(tmp_path)
    (ws / "AGENTS.md").write_text("MINHA NOTA\n", encoding="utf-8")
    sincronizar(raiz, home)
    txt = (ws / "AGENTS.md").read_text(encoding="utf-8")
    assert "MINHA NOTA" in txt and MARCA_INI in txt


def test_segredo_so_em_home_nunca_em_workspace(tmp_path):
    raiz, home, ws = _montar(tmp_path)
    sincronizar(raiz, home)
    mcp = (home / ".gemini" / "config" / "mcp_config.json").read_text(encoding="utf-8")
    assert "segredo-123" in mcp
    for f in ws.rglob("*"):
        if f.is_file():
            assert "segredo-123" not in f.read_text(encoding="utf-8")


def test_mcp_desativado_nao_aparece(tmp_path):
    raiz, home, _ = _montar(tmp_path, mcp=["cerebro"])
    sincronizar(raiz, home)
    mcp = json.loads((home / ".gemini" / "config" / "mcp_config.json").read_text(encoding="utf-8"))
    assert list(mcp["mcpServers"]) == ["cerebro"]


@pytest.mark.parametrize("skill", ["../fora", "a/b", "nao-existe"])
def test_skill_invalida_falha_sem_escrever(tmp_path, skill):
    raiz, home, ws = _montar(tmp_path, skills=[skill])
    with pytest.raises(ErroGovernanca):
        sincronizar(raiz, home)
    assert not (ws / "AGENTS.md").exists() and not any(home.iterdir())


def test_config_malformada_falha_sem_escrever(tmp_path):
    raiz, home, ws = _montar(tmp_path)
    (raiz / "governanca" / "governanca.json").write_text("{nao é json", encoding="utf-8")
    with pytest.raises(ErroGovernanca):
        sincronizar(raiz, home)
    assert not (ws / "AGENTS.md").exists()


def test_variavel_ausente_de_mcp_ativo_falha_fechado(tmp_path):
    raiz, home, ws = _montar(tmp_path)
    (raiz / ".env").write_text("", encoding="utf-8")
    with pytest.raises(ErroGovernanca, match="GH_TOKEN"):
        sincronizar(raiz, home)
    assert not (ws / "AGENTS.md").exists() and not any(home.iterdir())


def test_verificar_detecta_drift_e_ausencia(tmp_path):
    raiz, home, ws = _montar(tmp_path)
    assert verificar(raiz, home)  # nada gerado ainda
    sincronizar(raiz, home)
    aplicar_mcp_claude(raiz, home, tmp_path / "bk")
    assert verificar(raiz, home) == []
    (raiz / "governanca" / "regras" / "base.md").write_text("# mudou\n", encoding="utf-8")
    assert any("AGENTS.md" in d for d in verificar(raiz, home))


def test_verificar_nao_escreve(tmp_path):
    raiz, home, ws = _montar(tmp_path)
    verificar(raiz, home)
    assert not (ws / "AGENTS.md").exists() and not any(home.iterdir())


def test_variavel_opcional_com_padrao_nao_bloqueia(tmp_path):
    raiz, home, _ = _montar(tmp_path)
    mcp = json.loads((raiz / "governanca" / "mcp.json").read_text(encoding="utf-8"))
    mcp["mcpServers"]["github"]["env"]["TOKEN"] = "${GH_TOKEN_OPCIONAL:-}"
    (raiz / "governanca" / "mcp.json").write_text(json.dumps(mcp), encoding="utf-8")
    sincronizar(raiz, home)
    cfg = json.loads((home / ".gemini" / "config" / "mcp_config.json").read_text(encoding="utf-8"))
    assert cfg["mcpServers"]["github"]["env"]["TOKEN"] == ""


def test_detectar_instancias(tmp_path):
    from governanca import detectar_instancias
    home = tmp_path / "home"
    home.mkdir()
    (home / ".claude").mkdir()
    (home / ".claude-trabalho").mkdir()
    (home / ".claude-trabalho" / ".claude.json").write_text("{}", encoding="utf-8")
    (home / ".gemini").mkdir()
    (home / ".codex").mkdir()
    ws = tmp_path / "ws"
    ws.mkdir()

    detectadas = detectar_instancias(home, [str(ws)])
    ids = [d["id"] for d in detectadas]
    assert "claude-padrao" in ids
    assert "claude-trabalho" in ids
    assert "antigravity" in ids
    assert "codex" in ids
    assert any("cursor" in x for x in ids)


def test_sincroniza_multiplas_instancias_claude(tmp_path):
    raiz, home, ws = _montar(tmp_path)
    claude_trabalho = home / ".claude-trabalho"
    claude_trabalho.mkdir()
    (claude_trabalho / ".claude.json").write_text("{}", encoding="utf-8")

    cfg_instancias = {
        "regras": ["base"],
        "skills": ["grill-me"],
        "mcp": ["github"],
        "workspaces": [str(ws)],
        "instancias": [
            {
                "id": "claude-padrao",
                "cliente": "claude",
                "nome": "Claude Code (Padrão)",
                "caminho": "~/.claude",
                "config_json": "~/.claude.json",
                "ativo": True,
            },
            {
                "id": "claude-trabalho",
                "cliente": "claude",
                "nome": "Claude Code (Trabalho)",
                "caminho": "~/.claude-trabalho",
                "config_json": "~/.claude-trabalho/.claude.json",
                "ativo": True,
            },
        ],
    }
    (raiz / "governanca" / "governanca.json").write_text(json.dumps(cfg_instancias), encoding="utf-8")

    sincronizar(raiz, home)
    assert (home / ".claude" / "CLAUDE.md").is_file()
    assert (home / ".claude" / "skills" / "grill-me" / "SKILL.md").is_file()
    assert (claude_trabalho / "CLAUDE.md").is_file()
    assert (claude_trabalho / "skills" / "grill-me" / "SKILL.md").is_file()
    aplicar_mcp_claude(raiz, home, tmp_path / "bk")
    assert "github" in json.loads((home / ".claude.json").read_text(encoding="utf-8"))["mcpServers"]
    assert "github" in json.loads((claude_trabalho / ".claude.json").read_text(encoding="utf-8"))["mcpServers"]
    assert "Seja crítico." in (claude_trabalho / "CLAUDE.md").read_text(encoding="utf-8")


# ------------------------------------------------------------ OpenCode (opencode.json, seção mcp)
OPENCODE_INSTANCIA = [{"id": "opencode", "cliente": "opencode", "caminho": "~/.config/opencode", "ativo": True}]


def _opencode_json(home: Path, conteudo: dict | str) -> Path:
    alvo = home / ".config" / "opencode" / "opencode.json"
    alvo.parent.mkdir(parents=True, exist_ok=True)
    alvo.write_text(conteudo if isinstance(conteudo, str) else json.dumps(conteudo), encoding="utf-8")
    return alvo


def test_opencode_traduz_catalogo_e_preserva_o_resto(tmp_path):
    raiz, home, _ = _montar(tmp_path, instancias=OPENCODE_INSTANCIA, mcp=["github", "cerebro"])
    alvo = _opencode_json(home, {
        "provider": {"tudoia": {"name": "x"}},
        "model": "tudoia/tudoia-auto",
        "mcp": {"agent-browser": {"type": "local", "command": ["npx", "-y", "agent-browser", "mcp"]}},
    })

    assert aplicar_mcp_opencode(raiz, home, tmp_path / "bk") == {str(alvo.resolve()): "atualizado"}

    dados = json.loads(alvo.read_text(encoding="utf-8"))
    assert dados["provider"] == {"tudoia": {"name": "x"}}          # chaves do usuário intactas
    assert dados["model"] == "tudoia/tudoia-auto"
    assert dados["mcp"]["agent-browser"]["command"][-1] == "mcp"   # entrada manual preservada
    assert dados["mcp"]["github"] == {"type": "local", "command": ["npx"],
                                      "environment": {"TOKEN": "segredo-123"}, "enabled": True}
    assert dados["mcp"]["cerebro"] == {"type": "remote", "url": "http://127.0.0.1:8765/mcp", "enabled": True}
    assert (tmp_path / "bk").exists()   # backup do arquivo anterior


def test_opencode_idempotente_e_segredo_fora_do_workspace(tmp_path):
    raiz, home, ws = _montar(tmp_path, instancias=OPENCODE_INSTANCIA, mcp=["github"])
    _opencode_json(home, {"mcp": {}})
    aplicar_mcp_opencode(raiz, home, tmp_path / "bk")
    assert set(aplicar_mcp_opencode(raiz, home, tmp_path / "bk").values()) == {"igual"}
    assert "segredo-123" not in "".join(p.read_text(encoding="utf-8") for p in ws.rglob("*") if p.is_file())


def test_opencode_malformado_falha_sem_escrever(tmp_path):
    raiz, home, _ = _montar(tmp_path, instancias=OPENCODE_INSTANCIA, mcp=["cerebro"])
    alvo = _opencode_json(home, "{ isto não é json")
    with pytest.raises(ErroGovernanca):
        aplicar_mcp_opencode(raiz, home, tmp_path / "bk")
    assert alvo.read_text(encoding="utf-8") == "{ isto não é json"


def test_opencode_verificar_detecta_divergencia(tmp_path):
    raiz, home, _ = _montar(tmp_path, instancias=OPENCODE_INSTANCIA, mcp=["cerebro"])
    alvo = _opencode_json(home, {"mcp": {}})
    aplicar_mcp_opencode(raiz, home, tmp_path / "bk")
    assert not [p for p in verificar(raiz, home) if "opencode:mcp" in p]

    dados = json.loads(alvo.read_text(encoding="utf-8"))
    dados["mcp"]["cerebro"]["url"] = "http://outro/mcp"   # alteração à mão fora do painel
    alvo.write_text(json.dumps(dados), encoding="utf-8")
    assert any("opencode:mcp: divergente" in p for p in verificar(raiz, home))

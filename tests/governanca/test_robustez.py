"""Gravação atômica, corridas, marcas, Antigravity, junction, exceções, segredos, skills órfãs, aplicar_tudo."""
import json
import os
import stat
import tempfile
import time
from pathlib import Path

import pytest

import governanca
from governanca import ErroGovernanca, aplicar_mcp_claude, aplicar_tudo, sincronizar, verificar

SEGREDO = "segredo-123"
INI = "<!-- tudoia:inicio (gerado por governanca; edite governanca/regras/) -->"
FIM = "<!-- tudoia:fim -->"


def _montar(tmp_path: Path, catalogo=None, env=f"GH_TOKEN={SEGREDO}\n", **over) -> tuple[Path, Path, Path]:
    raiz, home, ws = tmp_path / "raiz", tmp_path / "home", tmp_path / "ws"
    for p in (raiz, home, ws):
        p.mkdir()
    g = raiz / "governanca"
    (g / "regras").mkdir(parents=True)
    (g / "skills" / "grill-me").mkdir(parents=True)
    (g / "regras" / "base.md").write_text("# Regra base\nSeja crítico.\n", encoding="utf-8")
    (g / "skills" / "grill-me" / "SKILL.md").write_text("---\nname: grill-me\n---\nPergunte.\n", encoding="utf-8")
    (g / "mcp.json").write_text(json.dumps({"mcpServers": catalogo or {
        "github": {"command": "npx", "env": {"TOKEN": "${GH_TOKEN}"}},
        "cerebro": {"type": "http", "url": "http://127.0.0.1:8765/mcp"},
    }}), encoding="utf-8")
    cfg = {"regras": ["base"], "skills": ["grill-me"], "mcp": ["github", "cerebro"],
           "workspaces": [str(ws)], "clientes": ["antigravity", "claude", "cursor", "codex"]}
    cfg.update(over)
    (g / "governanca.json").write_text(json.dumps(cfg), encoding="utf-8")
    (raiz / ".env").write_text(env, encoding="utf-8")
    return raiz, home, ws


def _claude_json(home: Path, extra: dict | None = None) -> Path:
    alvo = home / ".claude.json"
    alvo.write_text(json.dumps({"numStartups": 7, "mcpServers": {"manual": {"command": "uvx"}, **(extra or {})}}),
                    encoding="utf-8")
    return alvo


def _temporarios(pasta: Path) -> list[Path]:
    return [p for p in pasta.rglob("*") if p.name.endswith(".tmp")]


def _junction(link: Path, alvo: Path) -> None:
    try:
        os.symlink(alvo, link, target_is_directory=True)
    except OSError:
        if os.name != "nt":
            pytest.skip("sem permissão para criar symlink")
        import _winapi
        _winapi.CreateJunction(str(alvo), str(link))


# ------------------------------------------------ 1. gravação atômica preserva modo; temporário único

def test_gravacao_preserva_modo_do_original_e_arquivo_novo_com_segredo_nasce_0600(tmp_path, monkeypatch):
    raiz, home, _ = _montar(tmp_path)
    chamadas: list[tuple[str, int]] = []
    real = os.chmod
    monkeypatch.setattr(os, "chmod", lambda p, m, *a, **k: (chamadas.append((Path(p).name, m)), real(p, m, *a, **k)))

    aplicar_mcp_claude(raiz, home, tmp_path / "bk")            # ~/.claude.json não existe: nasce com segredo
    assert any(n.startswith("..claude.json.") and m == 0o600 for n, m in chamadas)
    if os.name != "nt":
        assert stat.S_IMODE((home / ".claude.json").stat().st_mode) == 0o600

    alvo = _claude_json(home)
    real(alvo, 0o640)
    esperado = stat.S_IMODE(alvo.stat().st_mode)
    chamadas.clear()
    aplicar_mcp_claude(raiz, home, tmp_path / "bk")
    assert any(n.startswith("..claude.json.") and m == esperado for n, m in chamadas)
    assert stat.S_IMODE(alvo.stat().st_mode) == esperado
    for b in (tmp_path / "bk").iterdir():                      # backup pode ter segredo
        if os.name != "nt":
            assert stat.S_IMODE(b.stat().st_mode) == 0o600


def test_temporario_fixo_ocupado_nao_impede_gravacao(tmp_path):
    raiz, home, _ = _montar(tmp_path)
    _claude_json(home)
    (home / ".claude.json.tmp").mkdir()   # outro escritor (ou sobra) no nome fixo antigo
    aplicar_mcp_claude(raiz, home, tmp_path / "bk")
    assert "github" in json.loads((home / ".claude.json").read_text(encoding="utf-8"))["mcpServers"]
    assert not [p for p in _temporarios(home) if p.is_file()]


# ------------------------------------------------ 2. corrida com o Claude Code e PermissionError no Windows

def test_arquivo_alterado_durante_a_gravacao_e_relido_e_preserva_a_mudanca_alheia(tmp_path, monkeypatch):
    raiz, home, _ = _montar(tmp_path)
    alvo = _claude_json(home)
    real = tempfile.mkstemp
    feito = []

    def concorrente(*a, **k):
        if not feito:   # o Claude Code grava entre a nossa leitura e a nossa troca
            dados = json.loads(alvo.read_text(encoding="utf-8"))
            dados["numStartups"] = 99
            dados["mcpServers"]["concorrente"] = {"command": "x"}
            alvo.write_text(json.dumps(dados), encoding="utf-8")
            feito.append(1)
        return real(*a, **k)

    monkeypatch.setattr(tempfile, "mkstemp", concorrente)
    assert aplicar_mcp_claude(raiz, home, tmp_path / "bk") == {str(alvo.resolve()): "atualizado"}
    dados = json.loads(alvo.read_text(encoding="utf-8"))
    assert dados["numStartups"] == 99
    assert set(dados["mcpServers"]) == {"manual", "concorrente", "github", "cerebro"}
    assert dados["mcpServers"]["github"]["env"]["TOKEN"] == SEGREDO
    assert not _temporarios(home)


def test_arquivo_que_nunca_para_de_mudar_falha_com_erro_claro(tmp_path, monkeypatch):
    raiz, home, _ = _montar(tmp_path)
    alvo = _claude_json(home)
    real = tempfile.mkstemp
    n = []

    def sempre(*a, **k):
        n.append(1)
        alvo.write_text(json.dumps({"mcpServers": {}, "n": len(n)}), encoding="utf-8")
        return real(*a, **k)

    monkeypatch.setattr(tempfile, "mkstemp", sempre)
    with pytest.raises(ErroGovernanca, match="alterado por outro processo"):
        aplicar_mcp_claude(raiz, home, tmp_path / "bk")
    assert json.loads(alvo.read_text(encoding="utf-8")) == {"mcpServers": {}, "n": 3}
    assert not _temporarios(home)


def test_permission_error_persistente_vira_erro_governanca_sem_temporario(tmp_path, monkeypatch):
    raiz, home, _ = _montar(tmp_path)
    alvo = _claude_json(home)
    antes = alvo.read_bytes()
    monkeypatch.setattr(time, "sleep", lambda s: None)

    def bloqueado(src, dst):
        raise PermissionError(32, "O arquivo já está sendo usado por outro processo")

    monkeypatch.setattr(os, "replace", bloqueado)
    with pytest.raises(ErroGovernanca, match="em uso por outro processo"):
        aplicar_mcp_claude(raiz, home, tmp_path / "bk")
    assert alvo.read_bytes() == antes
    assert not _temporarios(home)


def test_permission_error_transitorio_e_tentado_de_novo(tmp_path, monkeypatch):
    raiz, home, _ = _montar(tmp_path)
    _claude_json(home)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    real, falhas = os.replace, []

    def instavel(src, dst):
        if len(falhas) < 2:
            falhas.append(1)
            raise PermissionError(32, "em uso")
        return real(src, dst)

    monkeypatch.setattr(os, "replace", instavel)
    assert set(aplicar_mcp_claude(raiz, home, tmp_path / "bk").values()) == {"atualizado"}
    assert "github" in json.loads((home / ".claude.json").read_text(encoding="utf-8"))["mcpServers"]


# ------------------------------------------------ 3. marcas desbalanceadas

@pytest.mark.parametrize("conteudo", [
    f"nota\n{INI}\nvelho\n\nTEXTO DO USUÁRIO\n",            # marca de fim apagada
    f"{FIM}\nTEXTO DO USUÁRIO\n{INI}\n",                    # fora de ordem
    f"{INI}\na\n{FIM}\nTEXTO\n{INI}\nb\n",                  # início órfão depois de um bloco válido
])
def test_marcas_desbalanceadas_falham_antes_de_qualquer_escrita(tmp_path, conteudo):
    raiz, home, ws = _montar(tmp_path)
    (ws / "AGENTS.md").write_text(conteudo, encoding="utf-8")
    with pytest.raises(ErroGovernanca, match="AGENTS.md"):
        sincronizar(raiz, home)
    assert (ws / "AGENTS.md").read_text(encoding="utf-8") == conteudo
    assert not any(home.iterdir())


def test_marca_de_fim_apagada_depois_do_sync_nao_come_texto(tmp_path):
    raiz, home, ws = _montar(tmp_path)
    sincronizar(raiz, home)
    agents = ws / "AGENTS.md"
    agents.write_text(agents.read_text(encoding="utf-8").replace(FIM, "") + "\nMEU TEXTO\n", encoding="utf-8")
    antes = agents.read_text(encoding="utf-8")
    with pytest.raises(ErroGovernanca):
        sincronizar(raiz, home)
    assert agents.read_text(encoding="utf-8") == antes


# ------------------------------------------------ 4. mcp_config.json do Antigravity: só o que é nosso

def _antigravity(home: Path, conteudo: dict | str) -> Path:
    alvo = home / ".gemini" / "config" / "mcp_config.json"
    alvo.parent.mkdir(parents=True)
    alvo.write_text(conteudo if isinstance(conteudo, str) else json.dumps(conteudo), encoding="utf-8")
    return alvo


def test_antigravity_preserva_servidor_manual_remove_inativo_e_faz_backup(tmp_path):
    raiz, home, _ = _montar(tmp_path, mcp=["cerebro"])
    alvo = _antigravity(home, {"mcpServers": {"meu": {"command": "uvx"}, "github": {"command": "velho"}},
                               "outra": 1})
    sincronizar(raiz, home)
    dados = json.loads(alvo.read_text(encoding="utf-8"))
    assert dados["outra"] == 1
    assert set(dados["mcpServers"]) == {"meu", "cerebro"}
    assert list((home / ".tudoia" / "backups" / "antigravity-json").iterdir())
    assert set(sincronizar(raiz, home).values()) == {"igual"}
    assert not [d for d in verificar(raiz, home) if d.startswith("antigravity")]


def test_antigravity_malformado_nao_vira_objeto_vazio(tmp_path):
    raiz, home, ws = _montar(tmp_path)
    alvo = _antigravity(home, "{ quebrado")
    with pytest.raises(ErroGovernanca, match="mcp_config.json"):
        sincronizar(raiz, home)
    assert alvo.read_text(encoding="utf-8") == "{ quebrado"
    assert not (ws / "AGENTS.md").exists()


# ------------------------------------------------ 5. junction/symlink no destino

def test_junction_no_workspace_para_fora_e_recusada(tmp_path):
    raiz, home, ws = _montar(tmp_path)
    fora = tmp_path / "fora"
    fora.mkdir()
    _junction(ws / ".cursor", fora)
    with pytest.raises(ErroGovernanca, match="fora de home e de workspace"):
        sincronizar(raiz, home)
    assert not any(fora.iterdir())
    assert not (ws / "AGENTS.md").exists()


def test_junction_de_home_para_workspace_nao_leva_segredo(tmp_path):
    raiz, home, ws = _montar(tmp_path)
    (ws / "gemini").mkdir()
    _junction(home / ".gemini", ws / "gemini")
    sincronizar(raiz, home)
    cfg = json.loads((ws / "gemini" / "config" / "mcp_config.json").read_text(encoding="utf-8"))
    assert cfg["mcpServers"]["github"]["env"]["TOKEN"] == "${GH_TOKEN}"
    for f in ws.rglob("*"):
        if f.is_file():
            assert SEGREDO not in f.read_text(encoding="utf-8")


# ------------------------------------------------ 6. exceções viram ErroGovernanca

def test_skill_nao_utf8_vira_erro_governanca(tmp_path):
    raiz, home, ws = _montar(tmp_path)
    (raiz / "governanca" / "skills" / "grill-me" / "icone.bin").write_bytes(b"\xff\xfe\x00binario")
    with pytest.raises(ErroGovernanca, match="UTF-8"):
        sincronizar(raiz, home)
    assert not any(home.iterdir()) and not (ws / "AGENTS.md").exists()


def test_arquivo_gerado_nao_utf8_vira_erro_governanca(tmp_path):
    raiz, home, _ = _montar(tmp_path)
    (home / ".claude").mkdir()
    (home / ".claude" / "CLAUDE.md").write_bytes(b"nota \xe9 latin-1\n")
    with pytest.raises(ErroGovernanca, match="UTF-8"):
        sincronizar(raiz, home)


OPENCODE = [{"id": "opencode", "cliente": "opencode", "caminho": "~/.config/opencode", "ativo": True}]


def test_opencode_traduz_sse_e_recusa_entrada_sem_command(tmp_path):
    catalogo = {"remoto": {"type": "sse", "url": "http://x/sse"}, "ruim": {"args": ["a"]}}
    raiz, home, _ = _montar(tmp_path, catalogo=catalogo, mcp=["remoto"], instancias=OPENCODE)
    (home / ".config" / "opencode").mkdir(parents=True)
    governanca.aplicar_mcp_opencode(raiz, home, tmp_path / "bk")
    dados = json.loads((home / ".config" / "opencode" / "opencode.json").read_text(encoding="utf-8"))
    assert dados["mcp"]["remoto"] == {"type": "remote", "url": "http://x/sse", "enabled": True}

    cfg = json.loads((raiz / "governanca" / "governanca.json").read_text(encoding="utf-8"))
    cfg["mcp"] = ["ruim"]
    (raiz / "governanca" / "governanca.json").write_text(json.dumps(cfg), encoding="utf-8")
    with pytest.raises(ErroGovernanca, match="ruim"):
        governanca.aplicar_mcp_opencode(raiz, home, tmp_path / "bk")


# ------------------------------------------------ 7. guarda de segredo literal

def _so_workspace(raiz: Path, ws: Path, mcp: list[str]) -> None:
    (raiz / "governanca" / "governanca.json").write_text(json.dumps({
        "regras": ["base"], "skills": [], "mcp": mcp, "workspaces": [str(ws)], "clientes": [],
        "instancias": [{"id": "repo", "cliente": "claude", "caminho": str(ws),
                        "config_json": str(ws / ".claude.json")}],
    }), encoding="utf-8")


def test_valor_nao_secreto_no_catalogo_nao_e_acusado(tmp_path):
    catalogo = {"relogio": {"command": "npx", "env": {"TZ": "America/Sao_Paulo"}}}
    raiz, home, ws = _montar(tmp_path, catalogo=catalogo, env="TZ=America/Sao_Paulo\n")
    _so_workspace(raiz, ws, ["relogio"])
    aplicar_mcp_claude(raiz, home, tmp_path / "bk")
    assert json.loads((ws / ".claude.json").read_text(encoding="utf-8"))["mcpServers"]["relogio"]["env"]["TZ"] \
        == "America/Sao_Paulo"


def test_segredo_com_aspas_e_barra_e_achado_na_forma_escapada(tmp_path):
    valor = 'ab"cd\\ef12'
    catalogo = {"api": {"command": "npx", "env": {"K": valor}}}
    raiz, home, ws = _montar(tmp_path, catalogo=catalogo, env=f"OPENAI_API_KEY={valor}\n")
    _so_workspace(raiz, ws, ["api"])
    with pytest.raises(ErroGovernanca, match="OPENAI_API_KEY"):
        aplicar_mcp_claude(raiz, home, tmp_path / "bk")
    assert not (ws / ".claude.json").exists()


def test_variavel_referenciada_por_mcp_conta_como_segredo_mesmo_sem_nome_suspeito(tmp_path):
    catalogo = {"a": {"command": "npx", "env": {"X": "${MEU_ACESSO}"}},
                "b": {"command": "npx", "env": {"Y": "valor-do-acesso-1"}}}
    raiz, home, ws = _montar(tmp_path, catalogo=catalogo, env="MEU_ACESSO=valor-do-acesso-1\n")
    _so_workspace(raiz, ws, ["b"])
    with pytest.raises(ErroGovernanca, match="MEU_ACESSO"):
        aplicar_mcp_claude(raiz, home, tmp_path / "bk")


# ------------------------------------------------ 8. skills órfãs

def test_skill_tirada_da_governanca_e_apontada_e_removida_mas_manual_fica(tmp_path):
    raiz, home, _ = _montar(tmp_path)
    sincronizar(raiz, home)
    pasta = home / ".claude" / "skills" / "grill-me"
    assert (pasta / ".tudoia").is_file()
    manual = home / ".claude" / "skills" / "minha-skill"
    manual.mkdir()
    (manual / "SKILL.md").write_text("minha\n", encoding="utf-8")

    cfg = json.loads((raiz / "governanca" / "governanca.json").read_text(encoding="utf-8"))
    cfg["skills"] = []
    (raiz / "governanca" / "governanca.json").write_text(json.dumps(cfg), encoding="utf-8")

    drift = verificar(raiz, home)
    assert any("órfã" in d and "grill-me" in d for d in drift)
    assert not any("minha-skill" in d for d in drift)
    res = sincronizar(raiz, home)
    assert res["claude:skill:grill-me"] == "removido"
    assert not pasta.exists()
    assert not (home / ".gemini" / "antigravity-cli" / "skills" / "grill-me").exists()
    assert (manual / "SKILL.md").read_text(encoding="utf-8") == "minha\n"
    assert not any("órfã" in d for d in verificar(raiz, home))


def test_skill_copiada_sem_marca_nunca_e_apagada(tmp_path):
    raiz, home, _ = _montar(tmp_path, skills=[])
    antiga = home / ".claude" / "skills" / "velha"
    antiga.mkdir(parents=True)
    (antiga / "SKILL.md").write_text("x\n", encoding="utf-8")
    sincronizar(raiz, home)
    assert (antiga / "SKILL.md").is_file()


# ------------------------------------------------ 10. aplicar_tudo: uma fase de validação para os três

TUDO = [{"id": "claude-padrao", "cliente": "claude", "caminho": "~/.claude", "config_json": "~/.claude.json"},
        {"id": "opencode", "cliente": "opencode", "caminho": "~/.config/opencode"}]


def test_aplicar_tudo_opencode_malformado_nao_grava_claude_json(tmp_path):
    raiz, home, ws = _montar(tmp_path, instancias=TUDO)
    (home / ".claude").mkdir()
    alvo = _claude_json(home)
    antes = alvo.read_bytes()
    (home / ".config" / "opencode").mkdir(parents=True)
    (home / ".config" / "opencode" / "opencode.json").write_text("{ quebrado", encoding="utf-8")
    with pytest.raises(ErroGovernanca, match="opencode.json"):
        aplicar_tudo(raiz, home, tmp_path / "bk")
    assert alvo.read_bytes() == antes
    assert not (ws / "AGENTS.md").exists() and not (home / ".claude" / "CLAUDE.md").exists()


def test_aplicar_tudo_grava_os_tres_e_e_idempotente(tmp_path):
    raiz, home, ws = _montar(tmp_path, instancias=TUDO)
    (home / ".claude").mkdir()
    _claude_json(home)
    (home / ".config" / "opencode").mkdir(parents=True)
    res = aplicar_tudo(raiz, home, tmp_path / "bk")
    assert res[f"claude:mcp:{(home / '.claude.json').resolve()}"] == "atualizado"
    assert res[f"opencode:mcp:{(home / '.config' / 'opencode' / 'opencode.json').resolve()}"] == "atualizado"
    assert (ws / "AGENTS.md").is_file() and (home / ".claude" / "CLAUDE.md").is_file()
    assert (tmp_path / "bk" / "claude-json").is_dir()
    assert set(aplicar_tudo(raiz, home, tmp_path / "bk").values()) == {"igual"}
    assert verificar(raiz, home) == []

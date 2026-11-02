"""instancias.local.json: setup da máquina fora do git, com precedência sobre a lista versionada e falha fechado."""
import json
from pathlib import Path

import pytest

from governanca import ErroGovernanca, aplicar_mcp_claude
from test_mcp_claude import _claude, _montar


def _local(raiz: Path, conteudo) -> None:
    (raiz / "governanca" / "instancias.local.json").write_text(
        conteudo if isinstance(conteudo, str) else json.dumps(conteudo), encoding="utf-8")


def test_arquivo_local_substitui_a_lista_versionada(tmp_path):
    raiz, home, ws = _montar(tmp_path, instancias=[_claude(None, cid="versionada", caminho="~/.versionada",
                                                          config_json="~/.versionada/.claude.json")])
    _local(raiz, {"instancias": [_claude(None, cid="local", caminho="~/.local-x", config_json="~/.local-x/.claude.json")]})
    aplicar_mcp_claude(raiz, home, tmp_path / "bk")
    assert (home / ".local-x" / ".claude.json").is_file()
    assert not (home / ".versionada" / ".claude.json").exists()


def test_sem_arquivo_local_vale_a_lista_versionada(tmp_path):
    raiz, home, ws = _montar(tmp_path, instancias=[_claude(None, cid="versionada", caminho="~/.versionada",
                                                          config_json="~/.versionada/.claude.json")])
    aplicar_mcp_claude(raiz, home, tmp_path / "bk")
    assert (home / ".versionada" / ".claude.json").is_file()


@pytest.mark.parametrize("ruim", ["{nao e json", "[]", json.dumps({"instancias": "texto"}), json.dumps({"instancias": {}})])
def test_arquivo_local_malformado_falha_fechado(tmp_path, ruim):
    raiz, home, ws = _montar(tmp_path)
    _local(raiz, ruim)
    with pytest.raises(ErroGovernanca):
        aplicar_mcp_claude(raiz, home, tmp_path / "bk")


def test_arquivo_local_esta_no_gitignore():
    ignorado = (Path(__file__).resolve().parents[2] / ".gitignore").read_text(encoding="utf-8")
    assert "governanca/instancias.local.json" in ignorado

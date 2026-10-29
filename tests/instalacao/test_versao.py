"""A versão que o .exe mostra é a do produto: uma só, a do pyproject (e da tag de release)."""
import tomllib
from pathlib import Path

from tudoia_instalador import VERSAO

RAIZ = Path(__file__).resolve().parents[2]


def test_versao_do_instalador_e_a_do_pyproject():
    projeto = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    assert VERSAO == projeto

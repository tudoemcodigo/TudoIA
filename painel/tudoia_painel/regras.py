"""Carrega servicos/litellm/roteador_regras.py — a MESMA função que o hook do LiteLLM usa no container."""
import importlib.util
from types import ModuleType

from . import caminhos


def carregar_modulo_regras() -> ModuleType:
    spec = importlib.util.spec_from_file_location("roteador_regras", caminhos.regras_roteador())
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo

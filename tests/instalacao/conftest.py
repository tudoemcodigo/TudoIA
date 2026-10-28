"""Fixtures do instalador: nada aqui executa comando real, baixa arquivo ou mexe no Windows."""
import pytest

from tudoia_instalador.execucao import ErroComando, Redator
from tudoia_instalador.motor import Contexto
from tudoia_instalador.opcoes import Opcoes

from .duplos import ExecutorFalso, diag


@pytest.fixture
def opcoes(tmp_path) -> Opcoes:
    return Opcoes(pasta_instalacao=str(tmp_path / "TudoIA"), admin_email="admin@exemplo.com.br")


@pytest.fixture
def ctx(tmp_path, opcoes):
    logs: list[str] = []
    redator = Redator()
    c = Contexto(o=opcoes, redator=redator, log=logs.append, pasta_estado=tmp_path / "estado",
                 diagnostico=lambda: diag(), esperar=lambda s: None)
    c.executor = ExecutorFalso(logs.append, redator)
    c.logs = logs   # type: ignore[attr-defined]
    return c


@pytest.fixture
def falha_de_comando():
    return lambda msg="falhou", codigo=1: ErroComando(msg, codigo, "saida do comando")

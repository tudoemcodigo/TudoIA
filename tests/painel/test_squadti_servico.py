"""A Squad é um serviço Docker comum do painel (perfil `squadti` do compose): mesmas ações dos demais, nada de processo do host."""
import subprocess

import pytest

from tudoia_painel import servicos as sv


@pytest.fixture
def comandos(monkeypatch):
    registrados: list[list[str]] = []

    def falso(cmd, **kw):
        registrados.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, stdout="squadti\n", stderr="")

    monkeypatch.setattr(sv.subprocess, "run", falso)
    return registrados


def _args(cmd: list[str]) -> list[str]:
    return cmd[cmd.index("--env-file") + 2:]


def test_squadti_e_servico_docker_e_nao_do_host():
    assert "squadti" in sv.DOCKER and "squadti" not in sv.HOST
    assert not hasattr(sv.ServicosDocker, "_start_squadti")
    assert sv.METADADOS["squadti"]["porta"] == 8790


def test_aparece_na_lista_como_docker_e_ativo_quando_o_container_roda(tmp_path, comandos):
    squad = next(x for x in sv.ServicosDocker(tmp_path).listar() if x["nome"] == "squadti")
    assert squad["tipo"] == "docker" and squad["ativo"] is True and squad["porta"] == 8790


def test_ligar_parar_e_reiniciar_usam_o_compose(tmp_path, comandos):
    s = sv.ServicosDocker(tmp_path)
    for acao in ("start", "stop", "restart"):
        s.acao("squadti", acao)
    args = [_args(c) for c in comandos]
    assert args[0] == ["up", "-d", "squadti"] and args[1] == ["stop", "squadti"]
    assert args[2][-1] == "squadti" and args[2][0] in ("restart", "up")   # reiniciar: restart ou up --force-recreate, conforme a versão

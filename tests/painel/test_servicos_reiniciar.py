"""Reiniciar um container pelo painel precisa reler o .env.

`docker compose restart` e `docker restart` reaproveitam as variáveis com que o container foi criado: uma chave
preenchida no .env depois (OPENROUTER_API_KEY, GROQ_API_KEY) nunca chegava ao LiteLLM, que respondia 401 ao provedor.
Seam: o comando docker compose que o ServicosDocker monta (subprocess.run trocado por um registrador)."""
import subprocess

import pytest

from tudoia_painel import servicos as sv


@pytest.fixture
def comandos(monkeypatch):
    registrados: list[list[str]] = []

    def falso(cmd, **kw):
        registrados.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(sv.subprocess, "run", falso)
    return registrados


def _argumentos_do_compose(cmd: list[str]) -> list[str]:
    """O que vem depois de `--env-file <caminho>`: a ação do compose e seus alvos."""
    return cmd[cmd.index("--env-file") + 2:]


def test_reiniciar_container_recria_para_reler_o_env(tmp_path, comandos):
    sv.ServicosDocker(tmp_path).acao("litellm", "restart")
    (cmd,) = comandos
    assert _argumentos_do_compose(cmd) == ["up", "-d", "--no-deps", "--force-recreate", "litellm"]


def test_reiniciar_nao_usa_restart_do_compose(tmp_path, comandos):
    sv.ServicosDocker(tmp_path).acao("litellm", "restart")
    assert "restart" not in _argumentos_do_compose(comandos[0])


def test_ligar_e_parar_container_continuam_iguais(tmp_path, comandos):
    s = sv.ServicosDocker(tmp_path)
    s.acao("litellm", "start")
    s.acao("litellm", "stop")
    assert [_argumentos_do_compose(c) for c in comandos] == [["up", "-d", "litellm"], ["stop", "litellm"]]


def test_reiniciar_todos_recria_a_stack_para_reler_o_env(tmp_path, comandos, monkeypatch):
    s = sv.ServicosDocker(tmp_path)
    for metodo in ("_stop_host", "_start_ollama", "_start_comfyui"):   # processos do host não são o assunto aqui
        monkeypatch.setattr(s, metodo, lambda *a, **k: None)
    s.acao_todos("restart")
    (cmd,) = comandos
    assert _argumentos_do_compose(cmd) == ["up", "-d", "--force-recreate"]


def test_falha_do_compose_ao_reiniciar_levanta_com_a_ultima_linha_do_erro(tmp_path, monkeypatch):
    monkeypatch.setattr(sv.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(
        cmd, 1, stdout="", stderr="linha antiga\nCannot connect to the Docker daemon"))
    with pytest.raises(RuntimeError, match="Cannot connect to the Docker daemon"):
        sv.ServicosDocker(tmp_path).acao("litellm", "restart")


def test_servico_desconhecido_nao_roda_nada(tmp_path, comandos):
    with pytest.raises(ValueError):
        sv.ServicosDocker(tmp_path).acao("nao-existe", "restart")
    assert comandos == []

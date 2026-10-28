"""Handshake MCP stdio com processos de verdade: responde, só escreve log, trava, morre, enche o stderr."""
import sys
import time

import pytest

from tudoia_painel import mcp_stdio


def _servidor(tmp_path, corpo: str) -> list[str]:
    script = tmp_path / "srv.py"
    script.write_text("import sys, json, time\n" + corpo, encoding="utf-8")
    return [sys.executable, str(script)]


def test_responde_mesmo_com_log_e_stderr_cheio_antes(tmp_path):
    argv = _servidor(tmp_path, (
        "sys.stderr.write('x' * 200000); sys.stderr.flush()\n"   # encheria um pipe de stderr não lido
        "print('iniciando servidor...', flush=True)\n"
        "sys.stdin.readline()\n"
        "print(json.dumps({'jsonrpc': '2.0', 'id': 1, 'result': {'serverInfo': {'name': 'falso'}}}), flush=True)\n"
        "time.sleep(60)\n"))
    resp = mcp_stdio.handshake(argv, env=None, prazo_s=15)
    assert resp["result"]["serverInfo"]["name"] == "falso"


def test_servidor_mudo_estoura_o_prazo_e_e_encerrado(tmp_path):
    argv = _servidor(tmp_path, "time.sleep(600)\n")
    inicio = time.monotonic()
    with pytest.raises(mcp_stdio.SemResposta, match="sem resposta"):
        mcp_stdio.handshake(argv, env=None, prazo_s=1.5)
    assert time.monotonic() - inicio < 15


def test_servidor_que_encerra_sem_responder(tmp_path):
    argv = _servidor(tmp_path, "sys.exit(3)\n")
    with pytest.raises(mcp_stdio.SemResposta):
        mcp_stdio.handshake(argv, env=None, prazo_s=10)


def test_processo_nao_fica_vivo_depois_do_teste(tmp_path, monkeypatch):
    vistos = []
    real = mcp_stdio.encerrar_arvore

    def espiar(proc):
        real(proc)
        vistos.append(proc.poll())
    monkeypatch.setattr(mcp_stdio, "encerrar_arvore", espiar)
    argv = _servidor(tmp_path, (
        "sys.stdin.readline()\n"
        "print(json.dumps({'jsonrpc': '2.0', 'id': 1, 'result': {}}), flush=True)\n"
        "time.sleep(600)\n"))
    mcp_stdio.handshake(argv, env=None, prazo_s=15)
    assert vistos and vistos[0] is not None

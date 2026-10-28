"""Handshake `initialize` com um servidor MCP stdio, com prazo e sem deixar processo para trás."""
import json
import os
import queue
import signal
import subprocess
import threading
import time

PEDIDO_INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "tudoia-teste", "version": "1.0"}},
}
MAX_LINHAS = 200  # servidor que só escreve log no stdout não prende o teste até o prazo


class SemResposta(Exception):
    """O servidor não respondeu ao initialize (encerrou, estourou o prazo ou só escreveu lixo)."""


def handshake(argv: list[str], env: dict[str, str], prazo_s: float = 30.0) -> dict:
    """Envia `initialize` e devolve a resposta JSON-RPC de id 1.

    O prazo vale para a conversa inteira (o `npx` baixa o pacote na primeira vez). O stderr vai para DEVNULL: num pipe
    que ninguém lê, o servidor travava ao encher o buffer. Linhas que não são JSON (log no stdout) são ignoradas. No
    fim, a árvore de processos inteira é encerrada: no Windows, matar o `npx.cmd` deixava o `node` filho vivo.
    """
    proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            env=env, text=True, encoding="utf-8", errors="replace",
                            start_new_session=os.name != "nt")  # grupo próprio: o kill alcança os filhos no Linux
    linhas: queue.Queue = queue.Queue()

    def ler() -> None:
        for linha in proc.stdout:
            linhas.put(linha)
        linhas.put(None)

    threading.Thread(target=ler, daemon=True).start()
    try:
        proc.stdin.write(json.dumps(PEDIDO_INITIALIZE) + "\n")
        proc.stdin.flush()
        limite = time.monotonic() + prazo_s
        for _ in range(MAX_LINHAS):
            restante = limite - time.monotonic()
            if restante <= 0:
                raise SemResposta(f"sem resposta ao handshake em {prazo_s:.0f} s")
            try:
                linha = linhas.get(timeout=restante)
            except queue.Empty:
                raise SemResposta(f"sem resposta ao handshake em {prazo_s:.0f} s") from None
            if linha is None:
                raise SemResposta("servidor encerrou sem responder handshake MCP")
            try:
                resp = json.loads(linha)
            except ValueError:
                continue
            if isinstance(resp, dict) and resp.get("id") == 1:
                return resp
        raise SemResposta("servidor não respondeu ao handshake (só escreveu log)")
    except (BrokenPipeError, OSError) as e:
        raise SemResposta(f"servidor encerrou antes do handshake ({type(e).__name__})") from e
    finally:
        encerrar_arvore(proc)


def encerrar_arvore(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, timeout=15)
        else:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()

"""Execução de comandos do instalador: sem shell, com tempo limite e com segredos mascarados em tudo que vai ao log."""
from __future__ import annotations

import os
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
DETACHED = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)


class ErroComando(Exception):
    """Comando terminou com código inesperado. `saida` já está mascarada."""

    def __init__(self, mensagem: str, codigo: int = 1, saida: str = ""):
        super().__init__(mensagem)
        self.codigo, self.saida = codigo, saida


class Redator:
    """Troca valores secretos conhecidos por `***`. Chame `adicionar` assim que um segredo entrar no sistema."""

    def __init__(self) -> None:
        self._segredos: set[str] = set()

    def adicionar(self, *valores: str) -> None:
        self._segredos |= {v for v in valores if v and len(v) >= 4}

    def limpar(self, texto: str) -> str:
        # os mais longos primeiro: um segredo que contém o outro não deixa sobra legível
        for s in sorted(self._segredos, key=len, reverse=True):
            texto = texto.replace(s, "***")
        return texto


@dataclass
class Resultado:
    codigo: int
    saida: str


class Executor:
    def __init__(self, log: Callable[[str], None], redator: Redator):
        self.log, self.redator = log, redator

    def rodar(self, cmd: list[str], *, cwd: Path | str | None = None, env: dict[str, str] | None = None,
              timeout: float = 1800.0, sensivel: bool = False, entrada: str | None = None,
              aceitos: tuple[int, ...] = (0,), mostrar: bool = True) -> Resultado:
        """Roda `cmd` (lista, nunca shell). `sensivel=True` não registra a saída (ela vem no Resultado).
        Código fora de `aceitos` levanta ErroComando com o fim da saída mascarada."""
        if mostrar:
            self.log("$ " + self.redator.limpar(" ".join(_aspas(a) for a in cmd)))
        try:
            proc = subprocess.Popen(
                cmd, cwd=str(cwd) if cwd else None, env={**os.environ, **(env or {})},
                stdin=subprocess.PIPE if entrada is not None else subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                creationflags=CREATE_NO_WINDOW,
            )
        except OSError as e:
            raise ErroComando(f"não consegui executar {Path(cmd[0]).name}: {type(e).__name__}", 127) from e
        estourou = threading.Event()

        def matar() -> None:
            estourou.set()
            proc.kill()

        relogio = threading.Timer(timeout, matar)
        relogio.start()
        linhas: list[str] = []
        try:
            if entrada is not None and proc.stdin:
                proc.stdin.write(entrada)
                proc.stdin.close()
            assert proc.stdout is not None
            for linha in proc.stdout:
                linha = linha.rstrip("\r\n")
                linhas.append(linha)
                if not sensivel and linha.strip():
                    self.log(self.redator.limpar(linha))
            proc.wait()
        finally:
            relogio.cancel()
            if proc.poll() is None:
                proc.kill()
        saida = "\n".join(linhas)
        if estourou.is_set():
            raise ErroComando(f"{Path(cmd[0]).name} passou de {int(timeout)} s e foi encerrado", 124, self._fim(saida, sensivel))
        if proc.returncode not in aceitos:
            raise ErroComando(f"{Path(cmd[0]).name} terminou com código {proc.returncode}", proc.returncode, self._fim(saida, sensivel))
        return Resultado(proc.returncode, saida)

    def _fim(self, saida: str, sensivel: bool) -> str:
        return "" if sensivel else self.redator.limpar("\n".join(saida.splitlines()[-15:]))

    def iniciar_solto(self, cmd: list[str], *, cwd: Path | str | None, env: dict[str, str] | None,
                      arquivo_log: Path) -> None:
        """Processo que continua depois do instalador (painel, ollama serve): destacado, saída num arquivo."""
        self.log("$ (em segundo plano) " + self.redator.limpar(" ".join(_aspas(a) for a in cmd)))
        arquivo_log.parent.mkdir(parents=True, exist_ok=True)
        with arquivo_log.open("ab") as saida:
            subprocess.Popen(cmd, cwd=str(cwd) if cwd else None, env={**os.environ, **(env or {})},
                             stdin=subprocess.DEVNULL, stdout=saida, stderr=subprocess.STDOUT,
                             creationflags=DETACHED | CREATE_NO_WINDOW, close_fds=True)


def _aspas(arg: str) -> str:
    return f'"{arg}"' if " " in arg else arg

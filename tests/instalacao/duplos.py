"""Duplos de teste do instalador: nada aqui executa comando real, baixa arquivo ou mexe no Windows."""
from __future__ import annotations


from tudoia_instalador.execucao import Executor, Resultado
from tudoia_instalador.sistema import Diagnostico


class ExecutorFalso(Executor):
    """Registra os comandos. `respostas`: lista de (trecho do comando, Resultado | Exception); o primeiro que casa vale."""

    def __init__(self, log, redator, respostas=None):
        super().__init__(log, redator)
        self.chamadas: list[tuple[list[str], dict]] = []
        self.soltos: list[list[str]] = []
        self.respostas = list(respostas or [])

    def rodar(self, cmd, **kw):
        self.chamadas.append((list(cmd), kw))
        linha = " ".join(cmd)
        for trecho, resposta in self.respostas:
            if trecho in linha:
                if isinstance(resposta, Exception):
                    raise resposta
                return resposta
        return Resultado(0, "")

    def iniciar_solto(self, cmd, **kw):
        self.soltos.append(list(cmd))

    def comandos(self) -> list[str]:
        return [" ".join(c) for c, _ in self.chamadas]


def diag(**mudancas) -> Diagnostico:
    base = dict(windows_build=22631, windows_ok=True, administrador=False, docker_instalado=True, docker_pronto=True,
                ollama_instalado=True, winget=True, gpu_nome="NVIDIA Teste", gpu_vram_mb=8192, internet=True,
                portas_ocupadas={}, python_instalado=True, python_versao="3.12.15")
    base.update(mudancas)
    return Diagnostico(**base)

"""Motor de instalação: executa as etapas em ordem, registra o progresso e permite retomar depois de uma falha ou de
um reinício do Windows (o estado das etapas concluídas fica em estado.json, sem nenhum segredo)."""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .execucao import ErroComando, Executor, Redator
from .opcoes import Opcoes
from .sistema import Diagnostico, diagnosticar

PENDENTE, EXECUTANDO, OK, FALHOU, PULADA = "pendente", "executando", "ok", "falhou", "pulada"


class ErroInstalacao(Exception):
    """Falha esperada, com mensagem pronta para o usuário (sem segredos)."""


class ReinicioNecessario(Exception):
    """O Windows precisa reiniciar (por exemplo, depois de instalar o WSL2 do Docker Desktop). O instalador retoma."""


def pasta_estado_padrao() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "TudoIA-Setup"


@dataclass
class Contexto:
    o: Opcoes
    redator: Redator
    log: Callable[[str], None]
    pasta_estado: Path = field(default_factory=pasta_estado_padrao)
    diagnostico: Callable[[], Diagnostico] = diagnosticar
    esperar: Callable[[float], None] = time.sleep
    agora: Callable[[], float] = time.monotonic
    efemeros: dict = field(default_factory=dict)   # só em memória: senha temporária do admin etc.
    uv: str | None = None
    zip_codigo: Path | None = None
    executor: Executor | None = None

    def __post_init__(self) -> None:
        self.executor = self.executor or Executor(self.log, self.redator)

    @property
    def raiz(self) -> Path:
        return Path(self.o.pasta_instalacao)

    @property
    def python(self) -> str:
        return str(self.raiz / ".venv" / "Scripts" / "python.exe")

    @property
    def env_projeto(self) -> dict[str, str]:
        """Mesmo ambiente do tudoia.ps1: PYTHONPATH com a raiz e o painel."""
        return {"PYTHONPATH": f"{self.raiz};{self.raiz / 'painel'}", "PYTHONUTF8": "1"}

    def esperar_ate(self, condicao: Callable[[], bool], limite_s: float, descricao: str, intervalo: float = 3.0) -> bool:
        fim = self.agora() + limite_s
        while self.agora() < fim:
            if condicao():
                return True
            self.esperar(intervalo)
        self.log(f"tempo esgotado esperando {descricao}")
        return False


@dataclass
class Etapa:
    id: str
    titulo: str
    executar: Callable[[Contexto], None]
    aplica: Callable[[Opcoes], bool] = lambda o: True


class Estado:
    """estado.json: opções públicas e o resultado de cada etapa. Nunca guarda segredo."""

    def __init__(self, pasta: Path):
        self.arquivo = pasta / "estado.json"
        self.dados: dict = {"opcoes": None, "etapas": {}, "reinicio": False}
        if self.arquivo.is_file():
            try:
                self.dados.update(json.loads(self.arquivo.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                pass

    def salvar(self) -> None:
        self.arquivo.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.arquivo.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.dados, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.arquivo)

    def limpar(self) -> None:
        self.dados = {"opcoes": None, "etapas": {}, "reinicio": False}
        self.arquivo.unlink(missing_ok=True)


class Motor:
    def __init__(self, ctx: Contexto, etapas: list[Etapa], arquivo_log: Path | None = None):
        self.ctx = ctx
        self.etapas = etapas
        self.arquivo_log = arquivo_log
        ctx.log = self.registrar   # tudo que as etapas logam passa por aqui (mascarado, em memória e no arquivo)
        if ctx.executor is not None:
            ctx.executor.log = self.registrar
        self.estado = Estado(ctx.pasta_estado)
        self.situacao: dict[str, dict] = {e.id: {"id": e.id, "titulo": e.titulo, "estado": PENDENTE, "mensagem": ""}
                                          for e in etapas}
        self.linhas: list[str] = []
        self._trava = threading.Lock()
        self.terminou = False
        self.falhou = False
        self.precisa_reiniciar = False
        self.erro: str = ""

    # ---- log em memória (a tela lê com `desde`)
    def registrar(self, texto: str) -> None:
        limpo = self.ctx.redator.limpar(texto)
        with self._trava:
            self.linhas.append(limpo)
            if len(self.linhas) > 5000:
                del self.linhas[:1000]
            if self.arquivo_log is not None:
                try:
                    self.arquivo_log.parent.mkdir(parents=True, exist_ok=True)
                    with self.arquivo_log.open("a", encoding="utf-8") as f:
                        f.write(f"{time.strftime('%H:%M:%S')} {limpo}" + chr(10))
                except OSError:
                    pass

    def instantaneo(self, desde: int = 0) -> dict:
        with self._trava:
            return {"etapas": [dict(v) for v in self.situacao.values()], "linhas": self.linhas[desde:],
                    "proximo": len(self.linhas), "terminou": self.terminou, "falhou": self.falhou,
                    "reinicio": self.precisa_reiniciar, "erro": self.erro}

    def _marcar(self, id_: str, estado: str, mensagem: str = "") -> None:
        with self._trava:
            self.situacao[id_]["estado"] = estado
            self.situacao[id_]["mensagem"] = mensagem

    def rodar(self) -> bool:
        """Executa as etapas que faltam. True = tudo concluído. Para na primeira falha (o usuário corrige e retoma)."""
        self.terminou = self.falhou = self.precisa_reiniciar = False
        self.erro = ""
        if self.estado.dados.get("concluida"):
            # a instalação anterior terminou: uma nova execução (outras opções, reparo) começa do zero, não pula tudo
            self.estado.dados["etapas"] = {}
            self.estado.dados["concluida"] = False
        self.estado.dados["opcoes"] = self.ctx.o.publico()
        concluidas = self.estado.dados["etapas"]
        for etapa in self.etapas:
            if not etapa.aplica(self.ctx.o):
                self._marcar(etapa.id, PULADA, "não se aplica às opções escolhidas")
                continue
            if concluidas.get(etapa.id) == OK:
                self._marcar(etapa.id, OK, "já concluída")
                continue
            self._marcar(etapa.id, EXECUTANDO)
            self.registrar(f"== {etapa.titulo}")
            try:
                etapa.executar(self.ctx)
            except ReinicioNecessario as e:
                self._marcar(etapa.id, FALHOU, str(e))
                self.precisa_reiniciar = True
                self.erro = str(e)
                self.estado.dados["reinicio"] = True
                self.estado.salvar()
                self.registrar(f"!! {e}")
                break
            except (ErroInstalacao, ErroComando) as e:
                detalhe = str(e) + (("\n" + e.saida) if isinstance(e, ErroComando) and e.saida else "")
                self._marcar(etapa.id, FALHOU, str(e))
                self.falhou, self.erro = True, str(e)
                self.registrar(f"!! {detalhe}")
                break
            except Exception as e:   # noqa: BLE001 — falha inesperada: sanitiza antes de registrar
                import traceback
                detalhe_erro = self.ctx.redator.limpar(str(e))
                msg = f"erro inesperado ({type(e).__name__}: {detalhe_erro}); veja o registro do instalador" if detalhe_erro else f"erro inesperado ({type(e).__name__}); veja o registro do instalador"
                self._marcar(etapa.id, FALHOU, msg)
                self.falhou, self.erro = True, msg
                self.registrar(f"!! {msg}")
                if self.arquivo_log is not None:
                    try:
                        self.arquivo_log.parent.mkdir(parents=True, exist_ok=True)
                        with self.arquivo_log.open("a", encoding="utf-8") as f:
                            f.write(self.ctx.redator.limpar(traceback.format_exc()) + "\n")
                    except OSError:
                        pass
                break
            concluidas[etapa.id] = OK
            self._marcar(etapa.id, OK)
            self.estado.salvar()
        else:
            self.estado.dados["reinicio"] = False
            self.estado.dados["concluida"] = True
            self.estado.salvar()
            self.terminou = True
            self.registrar("== Instalação concluída")
            return True
        self.terminou = True
        return False

"""
Trilha de auditoria e controle de execução da Squad.

- Cada chamada ao modelo e cada nó deixam registro (modelo, tokens, tempo, hash do prompt) no estado da tarefa: é o que alimenta o
  cockpit e a auditoria do painel e a proveniência da entrega.
- Orçamento por tarefa (tokens, tempo, chamadas): estourou, a execução PARA e escala ao humano; nada continua gastando em silêncio.
- Estagnação: a mesma falha duas vezes seguidas (mesma assinatura de erro) é loop sem progresso; escala antes de gastar o resto das iterações.
- Calibração: a razão caracteres por token vem do que o gateway reporta (usage), não de um palpite fixo.
"""
import hashlib
import re
import threading
import time
from functools import wraps
from typing import Callable, Dict, List, Optional

ASSINATURAS_MAX = 20
LIMITE_ESTAGNACAO = 2  # mesma assinatura em N verificações seguidas = estagnou


class EscaladaHumana(RuntimeError):
    """A execução parou por decisão de controle (orçamento, estagnação, saída inválida repetida): um humano decide o que fazer."""

    def __init__(self, motivo: str, codigo: str = "escalada"):
        super().__init__(motivo)
        self.motivo, self.codigo = motivo, codigo


# ---------------------------------------------------------------- eventos ao vivo (cockpit)
_SINKS: Dict[str, Callable[[str], None]] = {}
_TRAVA_SINKS = threading.Lock()


def registrar_sink(tarefa: str, funcao: Optional[Callable[[str], None]]) -> None:
    with _TRAVA_SINKS:
        if funcao is None:
            _SINKS.pop(tarefa, None)
        else:
            _SINKS[tarefa] = funcao


def emitir(tarefa: Optional[str], texto: str) -> None:
    """Linha de log do cockpit. Nunca levanta: telemetria não derruba a execução."""
    funcao = _SINKS.get(tarefa or "")
    if funcao:
        try:
            funcao(texto[:500])
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------- chamadas ao modelo
_LOCAL = threading.local()


def _coletor() -> Optional[List[dict]]:
    return getattr(_LOCAL, "chamadas", None)


def registrar_chamada(info: dict) -> None:
    c = _coletor()
    if c is not None:
        c.append(info)


def hash_prompt(sistema: str, humano: str) -> str:
    return hashlib.sha256(f"{sistema}\n\x00\n{humano}".encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------- calibração de contexto
_RAZAO = {"valor": 4.0, "amostras": 0}
_TRAVA_RAZAO = threading.Lock()
RAZAO_MIN, RAZAO_MAX = 1.5, 6.0


def razao_chars_por_token() -> float:
    return _RAZAO["valor"]


def calibrar(caracteres: int, tokens: int) -> None:
    """Média móvel da razão real (caracteres por token) reportada pelo gateway; limitada para um valor absurdo não desligar a guarda."""
    if caracteres <= 0 or tokens <= 0:
        return
    real = min(max(caracteres / tokens, RAZAO_MIN), RAZAO_MAX)
    with _TRAVA_RAZAO:
        n = _RAZAO["amostras"]
        _RAZAO["valor"] = real if n == 0 else (_RAZAO["valor"] * 0.7 + real * 0.3)
        _RAZAO["amostras"] = n + 1


def reiniciar_calibracao() -> None:
    with _TRAVA_RAZAO:
        _RAZAO.update(valor=4.0, amostras=0)


# ---------------------------------------------------------------- orçamento
def totais(state: dict) -> dict:
    registros = state.get("auditoria") or []
    entrada = sum(int(r.get("tokens_entrada") or 0) for r in registros)
    saida = sum(int(r.get("tokens_saida") or 0) for r in registros)
    return {"tokens": entrada + saida, "tokens_entrada": entrada, "tokens_saida": saida,
            "tempo_s": round(sum(float(r.get("duracao_s") or 0) for r in registros), 1),
            "chamadas": sum(int(r.get("chamadas") or 0) for r in registros), "nos": len(registros)}


def verificar_orcamento(state: dict) -> None:
    """Levanta EscaladaHumana se algum teto do `orcamento` da tarefa foi atingido. Teto ausente = sem limite naquele eixo."""
    teto = state.get("orcamento") or {}
    uso = totais(state)
    for eixo, rotulo in (("tokens", "tokens"), ("tempo_s", "segundos de execução"), ("chamadas", "chamadas ao modelo")):
        limite = teto.get(eixo)
        if limite and uso[eixo] >= limite:
            raise EscaladaHumana(f"orçamento da tarefa esgotado: {uso[eixo]} de {limite} {rotulo}", "orcamento")


# ---------------------------------------------------------------- estagnação
_RE_VOLATIL = re.compile(r"0x[0-9a-f]+|\d+|[a-z]:[\\/][^\s:]*|(?:/[\w.-]+){2,}", re.IGNORECASE)


def assinatura_do_erro(texto: Optional[str]) -> str:
    """Hash estável da falha: números, caminhos e horários saem, para 'o mesmo erro' casar entre tentativas."""
    if not texto:
        return ""
    linhas = [_RE_VOLATIL.sub("#", ln.strip().lower()) for ln in str(texto).splitlines() if ln.strip()]
    return hashlib.sha1("\n".join(linhas[:12]).encode("utf-8")).hexdigest()[:12]


def estagnou(state: dict, assinatura: str, limite: int = LIMITE_ESTAGNACAO) -> bool:
    if not assinatura:
        return False
    anteriores = list(state.get("assinaturas_erro") or [])[-(limite - 1):]
    return len(anteriores) == limite - 1 and all(a == assinatura for a in anteriores)


def registrar_assinatura(state: dict, assinatura: str) -> List[str]:
    """Nova lista (o estado usa reducer de concatenação: devolva só o acréscimo)."""
    return [assinatura] if assinatura else []


# ---------------------------------------------------------------- decorador dos nós
def auditar(no: str, papel: Optional[str] = None):
    """Registra duração, chamadas e tokens do nó em `auditoria`, aplica o orçamento ANTES de gastar e emite eventos ao vivo."""

    def decorador(funcao):
        @wraps(funcao)
        def interno(state):
            tarefa = state.get("task_id")
            verificar_orcamento(state)
            _LOCAL.chamadas = []
            inicio = time.time()
            emitir(tarefa, f"[{no}] iniciou")
            falhou: Optional[str] = None
            try:
                resultado = funcao(state)
            except EscaladaHumana:
                falhou = "escalada"
                raise
            except Exception as e:
                falhou = type(e).__name__
                raise
            finally:
                chamadas = _LOCAL.chamadas or []
                _LOCAL.chamadas = None
                duracao = round(time.time() - inicio, 2)
                emitir(tarefa, f"[{no}] {'falhou (' + falhou + ')' if falhou else 'terminou'} em {duracao}s, {len(chamadas)} chamada(s)")
            registro = {"no": no, "papel": papel or no, "inicio": inicio, "duracao_s": duracao, "chamadas": len(chamadas),
                        "tokens_entrada": sum(int(c.get("tokens_entrada") or 0) for c in chamadas),
                        "tokens_saida": sum(int(c.get("tokens_saida") or 0) for c in chamadas),
                        "modelos": sorted({c["modelo"] for c in chamadas if c.get("modelo")}),
                        "detalhe": chamadas}
            if isinstance(resultado, dict):
                resultado = {**resultado, "auditoria": [*(resultado.get("auditoria") or []), registro]}
            return resultado

        return interno

    return decorador

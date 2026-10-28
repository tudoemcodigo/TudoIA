"""Eventos da aba "Ao vivo" do painel: só métricas, NUNCA o texto de pedido ou resposta.

Só biblioteca padrão: usado pelo hook roteador.py (no container) e testado pelo painel.
"""
import json
import os
import time
from datetime import datetime, timedelta, timezone

# Únicos campos que podem ir para logs/eventos.jsonl (lista branca: texto nunca entra por engano)
CAMPOS = {
    "origem", "call_type", "grupo", "pontos", "motivos", "marcador", "modelo_pedido", "stream",
    "modelo", "provedor", "membro", "tentativa", "tokens_entrada", "tokens_saida", "tok_s", "ms",
    "custo_usd", "erro", "ok", "finish_reason",
}
INTERVALO_PROGRESSO = 0.5   # no máximo 2 eventos de progresso por segundo por pedido


def agora() -> datetime:
    return datetime.now(timezone.utc)


def evento(tipo: str, id_pedido: str | None, **campos) -> dict:
    ev = {"ts": agora().isoformat(timespec="milliseconds"), "tipo": tipo, "id": id_pedido}
    ev.update({k: v for k, v in campos.items() if k in CAMPOS})
    return ev


def evento_inicio(data: dict, grupo=None, pontos=None, motivos=None, origem="", call_type="") -> dict:
    return evento("inicio", data.get("litellm_call_id"), origem=str(origem)[:60], call_type=str(call_type),
                  grupo=grupo, pontos=pontos, motivos=motivos, modelo_pedido=data.get("model"),
                  stream=bool(data.get("stream")))


class Progresso:
    """Soma tokens por pedido e diz quando emitir um evento (limitado a 2/s)."""

    def __init__(self, maximo: int = 1000):
        self._tokens: dict[str, int] = {}
        self._ultimo: dict[str, datetime] = {}
        self._inicio: dict[str, datetime] = {}
        self._maximo = maximo

    def registrar(self, id_pedido: str, tokens: int, quando: datetime | None = None) -> bool:
        quando = quando or agora()
        if id_pedido not in self._tokens and len(self._tokens) >= self._maximo:
            velho = next(iter(self._tokens))
            for d in (self._tokens, self._ultimo, self._inicio):
                d.pop(velho, None)
        self._tokens[id_pedido] = self._tokens.get(id_pedido, 0) + tokens
        self._inicio.setdefault(id_pedido, quando)
        ultimo = self._ultimo.get(id_pedido)
        if ultimo is None or (quando - ultimo).total_seconds() >= INTERVALO_PROGRESSO:
            self._ultimo[id_pedido] = quando
            return True
        return False

    def tokens(self, id_pedido: str) -> int:
        return self._tokens.get(id_pedido, 0)

    def tok_s(self, id_pedido: str, quando: datetime | None = None) -> float | None:
        inicio = self._inicio.get(id_pedido)
        if not inicio:
            return None
        seg = ((quando or agora()) - inicio).total_seconds()
        return round(self._tokens[id_pedido] / seg, 1) if seg > 0.2 else None

    def encerrar(self, id_pedido: str) -> None:
        for d in (self._tokens, self._ultimo, self._inicio):
            d.pop(id_pedido, None)


def _get(obj, chave):
    return obj.get(chave) if isinstance(obj, dict) else getattr(obj, chave, None)


def contar_tokens_chunk(chunk) -> int:
    """Estimativa de tokens num pedaço de resposta em streaming (OpenAI ou Anthropic). Nunca levanta."""
    if isinstance(chunk, (bytes, str)):
        # /v1/messages (Claude Code): o iterador recebe o SSE já serializado, com uma ou mais linhas "data: {...}"
        try:
            texto = chunk.decode("utf-8", errors="ignore") if isinstance(chunk, bytes) else chunk
            total = 0
            for linha in texto.splitlines():
                if linha.startswith("data:") and "{" in linha:
                    try:
                        total += contar_tokens_chunk(json.loads(linha[5:].strip()))
                    except ValueError:
                        continue
            return total
        except Exception:
            return 0
    try:
        texto = None
        choices = _get(chunk, "choices")
        if choices:
            delta = _get(choices[0], "delta")
            texto = (_get(delta, "content") or "") + (_get(delta, "reasoning_content") or "") if delta is not None else ""
        else:
            delta = _get(chunk, "delta")
            if delta is not None:
                texto = _get(delta, "text") or _get(delta, "thinking") or ""
        if not isinstance(texto, str) or not texto:
            return 0
        return max(1, len(texto) // 4)
    except Exception:
        return 0


async def repassar(resposta, ao_chunk, ao_terminar=None):
    """Repassa todos os chunks intactos; a contagem (ao_chunk) nunca pode derrubar a resposta do usuário.

    ao_terminar(completo): True se o stream acabou normalmente; False se o cliente desistiu no meio (Esc, aba fechada)
    — nesse caso o LiteLLM não dispara sucesso nem falha, e sem isso o pedido ficaria "em andamento" para sempre.
    """
    completo = False
    try:
        async for item in resposta:
            try:
                ao_chunk(item)
            except Exception:
                pass
            yield item
        completo = True
    finally:
        if ao_terminar:
            try:
                ao_terminar(completo)
            except Exception:
                pass


def resumir_erro(excecao) -> str:
    """Classe da exceção + código HTTP. Nunca a mensagem: provedores às vezes repetem trechos do pedido nela."""
    if excecao is None:
        return "falha"
    status = getattr(excecao, "status_code", None)
    return f"{type(excecao).__name__} (HTTP {status})" if status else type(excecao).__name__


def girar_se_grande(caminho: str, max_mb: float) -> None:
    """Passou de max_mb: vira `.1` (sobrescreve o anterior). Simples e sem ler o arquivo, ao contrário do corte por idade."""
    try:
        if os.path.getsize(caminho) > max_mb * 1024 * 1024:
            os.replace(caminho, caminho + ".1")
    except OSError:
        pass


class Gravador:
    """Grava eventos numa thread própria: o hook só faz put (nunca espera disco) e o corte de 24 h/20 MB roda aqui.

    Também grava os outros arquivos do hook (put com `caminho`): linhas anexadas, giradas para `.1` acima de
    `max_outros_mb`, ou, com `substituir`, o JSON inteiro trocado de forma atômica (ratelimit.json).
    """

    def __init__(self, caminho: str, max_mb: float = 20, horas: int = 24, checar_s: float = 60,
                 tamanho_fila: int = 10000, iniciar: bool = True, max_outros_mb: float = 5):
        import queue
        import threading
        self.caminho, self.max_mb, self.horas, self.checar_s = caminho, max_mb, horas, checar_s
        self.max_outros_mb = max_outros_mb
        self.fila = queue.Queue(maxsize=tamanho_fila)
        self._parar = threading.Event()
        self._ultimo_corte_idade = time.monotonic()   # o 1º corte acontece ao iniciar a thread
        self._thread = threading.Thread(target=self._laco, daemon=True, name="eventos-ao-vivo")
        if iniciar:
            self._thread.start()

    def put(self, ev: dict, caminho: str | None = None, substituir: bool = False) -> None:
        try:
            self.fila.put_nowait((caminho, ev, substituir))
        except Exception:
            pass   # fila cheia: perder um evento de métrica é melhor que atrasar o pedido

    def _gravar_lote(self, lote: list) -> None:
        anexos: dict[str, list] = {}
        trocas: dict[str, dict] = {}
        for caminho, ev, substituir in lote:
            destino = caminho or self.caminho
            if substituir:
                trocas[destino] = ev   # só a versão mais nova importa
            else:
                anexos.setdefault(destino, []).append(ev)
        for destino, evs in anexos.items():
            if destino != self.caminho:   # eventos.jsonl tem o corte por idade/tamanho próprio
                girar_se_grande(destino, self.max_outros_mb)
            try:   # default=str: um valor estranho não pode matar a thread (e com ela todos os logs)
                with open(destino, "a", encoding="utf-8") as f:
                    f.write("".join(json.dumps(e, ensure_ascii=False, default=str) + "\n" for e in evs))
            except Exception:
                pass
        for destino, conteudo in trocas.items():
            try:
                tmp = destino + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(conteudo, f, ensure_ascii=False, default=str)
                os.replace(tmp, destino)
            except Exception:
                pass

    def _cortar_se_preciso(self, forcar: bool = False) -> None:
        try:
            grande = os.path.getsize(self.caminho) > self.max_mb * 1024 * 1024
        except OSError:
            return
        if forcar or grande:
            try:
                cortar_arquivo(self.caminho, horas=self.horas, max_mb=self.max_mb)
            except OSError:
                pass

    def _laco(self) -> None:
        import queue
        self._cortar_se_preciso(forcar=True)   # ao iniciar (o LiteLLM reinicia a cada config salva)
        proxima = time.monotonic() + self.checar_s
        while not self._parar.is_set():
            lote = []
            try:
                lote.append(self.fila.get(timeout=0.5))
                while len(lote) < 500:
                    lote.append(self.fila.get_nowait())
            except queue.Empty:
                pass
            if lote:
                self._gravar_lote(lote)
            if time.monotonic() >= proxima:
                proxima = time.monotonic() + self.checar_s
                self._cortar_se_preciso()
            if time.monotonic() - self._ultimo_corte_idade > 3600:
                self._ultimo_corte_idade = time.monotonic()
                self._cortar_se_preciso(forcar=True)   # remove o que passou de 24 h, ao menos 1×/hora

    def parar(self) -> None:
        self._parar.set()
        self._thread.join(timeout=3)


def anexar(caminho: str, ev: dict) -> None:
    try:
        with open(caminho, "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    except OSError:
        pass


def cortar_arquivo(caminho, momento: datetime | None = None, horas: int = 24, max_mb: float = 20) -> None:
    """Mantém só as últimas `horas` e no máximo `max_mb` MB (descarta do começo)."""
    momento = momento or agora()
    limite = momento - timedelta(hours=horas)
    try:
        with open(caminho, encoding="utf-8") as f:
            linhas = f.read().splitlines()
    except OSError:
        return
    boas = []
    for l in linhas:
        try:
            if datetime.fromisoformat(json.loads(l)["ts"]) >= limite:
                boas.append(l)
        except (ValueError, KeyError, TypeError):
            continue
    teto = int(max_mb * 1024 * 1024)
    tamanho = sum(len(l.encode("utf-8")) + 1 for l in boas)
    while boas and tamanho > teto:
        tamanho -= len(boas.pop(0).encode("utf-8")) + 1
    tmp = str(caminho) + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write("".join(l + "\n" for l in boas))
    os.replace(tmp, caminho)

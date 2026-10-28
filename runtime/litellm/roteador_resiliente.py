"""Resposta do /v1/messages (Claude Code) só sai do proxy quando está inteira.

Por quê: a NVIDIA grátis às vezes trava NO MEIO do streaming. Depois do 1º conteúdo o LiteLLM não faz fallback
(router.py: _anthropic_stream_should_decline_fallback) e o adaptador Anthropic emite `event: error`, que o
Claude Code mostra como "API Error: Server error mid-response". Segurando os bytes até o `message_stop`, nada do
pedido que falhou chega ao cliente e dá para refazer em outro modelo sem ele perceber. Enquanto segura, manda
`event: ping` (previsto no protocolo, ignorado pelo SDK) para a conexão não parecer ociosa.

Sem dependência do LiteLLM: o hook (roteador.py) passa o stream original e uma função que refaz o pedido.
"""
import asyncio
import copy
import re

PING = b'event: ping\ndata: {"type": "ping"}\n\n'
ERRO_FINAL = (b'event: error\ndata: {"type": "error", "error": {"type": "api_error", '
              b'"message": "TudoIA: todos os modelos falharam nesta resposta"}}\n\n')
MAX_TENTATIVAS = 3   # além da original: outro membro, a reserva e o local (as que nem começam são instantâneas)
# Abaixo disso max_tokens é escolha do cliente (o Claude Code faz chamadas curtas de título/resumo) e bater nele é
# resposta válida; num orçamento grande de agente, parar por max_tokens é corte do provedor ou modelo em laço.
ORCAMENTO_PEQUENO = 8192
PING_S = 10.0


def _bytes(item) -> bytes:
    if isinstance(item, (bytes, bytearray)):
        return bytes(item)
    if isinstance(item, str):
        return item.encode("utf-8", "replace")
    return b""


_PARADA = re.compile(rb'"stop_reason"\s*:\s*"([a-z_]+)"')
_SAIDA = re.compile(rb'"output_tokens"\s*:\s*(\d+)')


def _cortada(tudo: bytes, max_saida: int | None) -> bool:
    """Parou por max_tokens sem ter sido o cliente que pediu pouco.

    Caso real (21/10/2026): tudoia-chat local com num_ctx 32k recebeu 32,7k tokens, encheu a janela e parou com 30
    tokens de saída; o adaptador manda stop_reason max_tokens e o Claude Code acusa "exceeded the 32000 output token
    maximum", sem tentar de novo. Também cobre o modelo que se perde e gasta os 32k inteiros.
    """
    paradas = _PARADA.findall(tudo)
    if not paradas or paradas[-1] != b"max_tokens":
        return False
    if not max_saida or max_saida >= ORCAMENTO_PEQUENO:
        return True
    saidas = _SAIDA.findall(tudo)
    return bool(saidas) and int(saidas[-1]) < 0.9 * max_saida


def _eventos(tudo: bytes) -> list[bytes]:
    """Nomes dos eventos SSE (linhas `event:`). O texto do modelo vai escapado dentro de `data: {...}` (JSON não tem
    quebra de linha crua), então nunca começa uma linha: pedir "código de servidor SSE" não parece mais erro."""
    return [linha[6:].strip() for linha in tudo.splitlines() if linha.startswith(b"event:")]


def _completa(itens: list, max_saida: int | None = None) -> bool:
    tudo = b"".join(_bytes(i) for i in itens)
    eventos = _eventos(tudo)
    return b"message_stop" in eventos and b"error" not in eventos and not _cortada(tudo, max_saida)


_TRECHO_GERADO = re.compile(rb'"(?:text|thinking|partial_json)": ?"((?:[^"\\]|\\.)*)"')


class DetectorDeLaco:
    """Modelo grátis em laço repete o mesmo trecho até bater no max_tokens: 32k tokens a ~20 tok/s são ~25 min
    perdidos antes de dar para refazer. Acusa quando os últimos JANELA caracteres gerados (texto, pensamento ou JSON
    de ferramenta) são EXATAMENTE periódicos, com período até PERIODO_MAX: pelo menos ~4 cópias idênticas seguidas.
    Tabela ou código com linhas parecidas não é periódico (números e nomes mudam), então não dispara.
    """
    JANELA = 3000
    PERIODO_MAX = 750
    CHECAR_A_CADA = 256

    def __init__(self):
        self._texto = ""
        self._desde_checagem = 0

    def alimentar(self, item) -> bool:
        novos = "".join(m.decode("utf-8", "replace") for m in _TRECHO_GERADO.findall(_bytes(item)))
        if not novos:
            return False
        self._texto = (self._texto + novos)[-2 * self.JANELA:]
        self._desde_checagem += len(novos)
        if len(self._texto) < self.JANELA or self._desde_checagem < self.CHECAR_A_CADA:
            return False
        self._desde_checagem = 0
        fim = self._texto[-self.JANELA:]
        # Período p <= PERIODO_MAX implica que o rabo de PERIODO_MAX caracteres reaparece em JANELA-PERIODO_MAX-p.
        # Um str.find em C (~1 µs) acha só esses candidatos; testar os 750 períodos com fatias custava ~100 µs.
        rabo, inicio = fim[-self.PERIODO_MAX:], self.JANELA - 2 * self.PERIODO_MAX
        i = fim.find(rabo, inicio, self.JANELA - 1)
        while i != -1:
            p = self.JANELA - self.PERIODO_MAX - i
            if fim[p:] == fim[:-p]:
                return True
            i = fim.find(rabo, i + 1, self.JANELA - 1)
        return False


async def _segurar(stream, fila: asyncio.Queue, max_saida: int | None) -> None:
    """Lê o stream inteiro para a fila; termina com ("fim", itens, completa). Corta cedo se o modelo entrar em laço."""
    itens: list = []
    laco = DetectorDeLaco()
    try:
        async for item in stream:
            itens.append(item)
            if laco.alimentar(item):
                print("[roteador] modelo em laço (texto se repetindo): cortando para refazer", flush=True)
                fechar = getattr(stream, "aclose", None)
                if fechar:
                    try:
                        await fechar()
                    except Exception:
                        pass
                await fila.put(("fim", itens, False))
                return
        await fila.put(("fim", itens, _completa(itens, max_saida)))
    except Exception:
        await fila.put(("fim", itens, False))


async def entregar(primeiro, refazer, plano: list, ping_s: float = PING_S, max_saida: int | None = None):
    """Gera os bytes da primeira tentativa que terminar bem; até lá, só pings.

    refazer(alvo) devolve (ou é corrotina que devolve) um novo stream para o modelo/grupo `alvo`.
    max_saida é o max_tokens do pedido: decide se um stop_reason max_tokens é corte (refaz) ou resposta válida.
    Se todas falharem, entrega a última resposta como veio (com o event: error), para o cliente ver um erro claro.
    """
    alvos = list(plano)
    stream = primeiro
    ultima: list = []
    while True:
        fila: asyncio.Queue = asyncio.Queue()
        tarefa = asyncio.ensure_future(_segurar(stream, fila, max_saida))
        try:
            while True:
                try:
                    _, itens, completa = await asyncio.wait_for(fila.get(), timeout=ping_s)
                    break
                except asyncio.TimeoutError:
                    yield PING
        finally:
            if not tarefa.done():   # cliente desistiu (Esc): não deixa a leitura do provedor órfã
                tarefa.cancel()
        if completa:
            for item in itens:
                yield item
            return
        ultima = itens or ultima
        novo = None
        while alvos and novo is None:
            alvo = alvos.pop(0)
            try:
                novo = refazer(alvo)
                if asyncio.iscoroutine(novo):
                    novo = await novo
            except Exception as e:
                print(f"[roteador] nova tentativa em {alvo} falhou antes de começar ({type(e).__name__})", flush=True)
                novo = None
        if novo is None:
            for item in (ultima or [ERRO_FINAL]):
                yield item
            return
        print(f"[roteador] resposta incompleta ou cortada: refazendo em {alvo}", flush=True)
        stream = novo


# Lista de PERMITIDOS: o proxy enfia no pedido objetos internos depois da 1ª resposta (data["deployment"] é um
# Deployment pydantic) e o router carimba api_base/model_info da tentativa anterior. Reenviar isso quebrava toda
# nova tentativa: Ollama "Object of type Deployment is not JSON serializable", NIM HTTP 400.
CAMPOS_DO_CLIENTE = ("messages", "system", "max_tokens", "stream", "temperature", "top_p", "top_k",
                     "stop_sequences", "tools", "tool_choice", "thinking", "metadata", "litellm_metadata")
CARIMBOS_DO_ROUTER = ("deployment", "model_info", "api_base", "deployment_model_name")
# Quem escolhe o próximo modelo é o plano, não os fallbacks do router: refazer em nim/nemotron-3-ultra em cooldown
# caía no fallback do membro (tudoia-nuvem → Groq → tudoia-chat local), modelos de chat que não aguentam o tamanho
# do pedido do Claude Code (21/10/2026: Groq 400 por 8k TPM, local cortado com 30 tokens).


def pedido_para_refazer(request_data: dict, alvo: str, call_id: str) -> dict:
    """Cópia só com o que o cliente mandou, apontada para `alvo`; o pedido original não é alterado."""
    dados = {k: copy.deepcopy(request_data[k]) for k in CAMPOS_DO_CLIENTE if k in request_data}
    for k in ("metadata", "litellm_metadata"):
        if isinstance(dados.get(k), dict):
            for carimbo in CARIMBOS_DO_ROUTER:
                dados[k].pop(carimbo, None)
    dados["model"] = alvo
    dados["litellm_call_id"] = call_id
    dados["disable_fallbacks"] = True
    return dados


def mapa_de_grupos(cfg: dict) -> dict:
    """{"membros": {grupo: [membro, ...]}, "fallbacks": {grupo: [...]}, "nomes": {model_name, ...}} do config.yaml."""
    membros: dict[str, list] = {}
    nomes = set()
    for m in cfg.get("model_list") or []:
        if not isinstance(m, dict) or not m.get("model_name"):
            continue
        nomes.add(m["model_name"])
        membro = (m.get("model_info") or {}).get("membro")
        if membro and membro != m["model_name"]:
            membros.setdefault(m["model_name"], []).append(membro)
    fallbacks = {}
    for regra in (cfg.get("router_settings") or {}).get("fallbacks") or []:
        if isinstance(regra, dict):
            fallbacks.update(regra)
    return {"membros": membros, "fallbacks": fallbacks, "nomes": nomes}


def plano(mapa: dict, grupo: str | None, membro_que_falhou: str | None) -> list:
    """Outros membros do grupo (pelo nome do deployment) e depois os fallbacks do grupo, sem repetir."""
    saida = []
    for alvo in (mapa["membros"].get(grupo) or []) + list(mapa["fallbacks"].get(grupo) or []):
        if alvo != membro_que_falhou and alvo != grupo and alvo in mapa["nomes"] and alvo not in saida:
            saida.append(alvo)
    return saida[:MAX_TENTATIVAS]

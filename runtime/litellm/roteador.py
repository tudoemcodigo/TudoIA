"""Hook do LiteLLM que implementa o modelo virtual tudoia-auto.

Registrado em config.yaml (litellm_settings.callbacks: roteador.proxy_handler_instance).
As regras estão em roteador_regras.py; os parâmetros em /app/config/roteamento.yaml (relido quando muda).
Grava em /app/logs/roteador.jsonl uma linha por resposta (sem o texto do pedido), em
/app/logs/ratelimit.json os últimos cabeçalhos x-ratelimit-* de cada provedor e, em /app/logs/eventos.jsonl,
os eventos da aba "Ao vivo" (início, modelo de cada tentativa, progresso do streaming, fim/erro) — só métricas.
/app/logs/correcoes.jsonl guarda o rótulo do #local/#nuvem com o hash e o tamanho do prompt, nunca o texto.
Tudo é gravado pela thread do Gravador; roteador.jsonl e correcoes.jsonl viram `.1` ao passar de 5 MB.
"""
import asyncio
import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timezone

import httpx
import yaml
from litellm.integrations.custom_logger import CustomLogger

import roteador_eventos as EV
import roteador_regras as RR
import roteador_resiliente as RS

def _texto(caminho) -> str:
    with open(caminho, encoding="utf-8") as f:
        return f.read()


ARQ_REGRAS = "/app/config/roteamento.yaml"
ARQ_CONFIG = os.environ.get("ROTEADOR_CONFIG", "/app/config.yaml")
ARQ_EXEMPLOS = "/app/config/exemplos-roteamento.yaml"
ARQ_APRENDIDOS = "/app/config/exemplos-aprendidos.yaml"   # opcional
DIR_LOGS = os.environ.get("ROTEADOR_LOGS", "/app/logs")
ARQ_EVENTOS = os.path.join(DIR_LOGS, "eventos.jsonl")   # aba "Ao vivo" do painel (só métricas)
ARQ_VETORES = os.path.join(DIR_LOGS, "exemplos-vetores.json")   # cache {sha1(texto): vetor}
MAX_PENDENTES = 500
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://host.docker.internal:11434")
LIMITE_EMBED_S = 1.5   # o pedido nunca espera mais que isso pelo embedding (bge-m3 frio leva ~2,9 s)
OLLAMA_SAUDE_S = 10          # o resultado do GET /api/version vale por isso: no máximo 1 checagem a cada 10 s
OLLAMA_SAUDE_TIMEOUT = 0.3   # Ollama no ar responde em poucos ms; mais que isso o pedido não espera


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


_CACHE_JSON: dict[str, tuple] = {}   # caminho → ((mtime_ns, tamanho), conteúdo)


def _ler_json(nome: str):
    """JSON de DIR_LOGS relido só quando muda (mtime/tamanho): antes eram 2-3 leituras de disco por pedido.

    Ausente ou inválido = None. Qualquer erro (OSError, JSON inválido, RecursionError...) nunca derruba o roteamento.
    """
    caminho = os.path.join(DIR_LOGS, nome)
    try:
        st = os.stat(caminho)
    except OSError:
        _CACHE_JSON.pop(caminho, None)
        return None
    chave = (st.st_mtime_ns, st.st_size)
    guardado = _CACHE_JSON.get(caminho)
    if guardado is not None and guardado[0] == chave:
        return guardado[1]
    try:
        with open(caminho, encoding="utf-8-sig") as f:
            dados = json.load(f)
    except Exception:
        dados = None
    _CACHE_JSON[caminho] = (chave, dados)
    return dados


def _num(uso, *chaves):
    """Lê um contador de tokens de usage (objeto ou dict, OpenAI ou Anthropic)."""
    if uso is None:
        return None
    for c in chaves:
        v = uso.get(c) if isinstance(uso, dict) else getattr(uso, c, None)
        if isinstance(v, (int, float)):
            return int(v)
    return None


class Roteador(CustomLogger):
    def __init__(self):
        super().__init__()
        self._regras: dict = {}
        self._mtime = None
        self._pendentes: dict[str, dict] = {}
        self._progresso = EV.Progresso()
        self._tentativas: dict[str, int] = {}
        self._modelo_atual: dict[str, str] = {}
        self._membro_atual: dict[str, str | None] = {}
        self._gravador = EV.Gravador(ARQ_EVENTOS)   # thread própria: o hook nunca espera disco
        self._cfg = self._ler_config()
        self._grupos = {m["model_name"] for m in self._cfg.get("model_list") or []
                        if isinstance(m, dict) and m.get("model_name")} if self._cfg else None
        self._mapa = RS.mapa_de_grupos(self._cfg or {})
        self._com_cache = RR.destinos_com_cache(self._cfg or {}, self._mapa["fallbacks"])
        self._ratelimit: dict | None = None    # espelho do ratelimit.json: lido do disco uma vez só
        self._saude_ok, self._saude_em, self._tarefa_saude = True, float("-inf"), None
        self._pronto: list | None = None       # [(vetor, rótulo)] dos exemplos; None enquanto não calculados
        self._mtimes_exemplos = None
        self._tarefa_exemplos = None
        self._tarefa_aquecer = None
        self._aquecido = False
        self._retomar_em = 0.0

    @staticmethod
    def _ler_config() -> dict | None:
        """config.yaml do LiteLLM. Só muda com reinício do LiteLLM, então lê uma vez; None = não sei."""
        try:
            return yaml.safe_load(_texto(ARQ_CONFIG)) or {}
        except Exception as e:
            print(f"[roteador] não li {ARQ_CONFIG}: #max, visão e nova tentativa ficam desligados: {e}", flush=True)
            return None

    # ── eventos da aba "Ao vivo" (nunca derrubam o pedido) ────────────────────────
    def _evento(self, ev: dict) -> None:
        self._gravador.put(ev)

    def _anexar(self, nome: str, linha: dict) -> None:
        self._gravador.put(linha, os.path.join(DIR_LOGS, nome))

    # ── regras e limites ──────────────────────────────────────────────────────────
    def regras(self) -> dict:
        try:
            mtime = os.stat(ARQ_REGRAS).st_mtime
            if mtime != self._mtime:
                novas = yaml.safe_load(_texto(ARQ_REGRAS)) or {}
                RR.validar_regras(novas)
                self._regras, self._mtime = novas, mtime
        except Exception as e:   # mantém a última versão válida
            print(f"[roteador] roteamento.yaml inválido, mantendo o anterior: {e}", flush=True)
            self._mtime = None
        return self._regras

    @staticmethod
    def limites() -> tuple[set, dict | None]:
        # limites.json: velho (painel fechado) é ignorado; quarentena.json: cada entrada tem o próprio `ate`
        # (a validade é recalculada a cada pedido; só a leitura do arquivo é guardada)
        return RR.combinar_limites(_ler_json("limites.json"), _ler_json("quarentena.json"), datetime.now(timezone.utc))

    @staticmethod
    def gpu_ocupada() -> bool:
        try:
            return RR.gpu_ocupada_valida(_ler_json("gpu.json"), datetime.now(timezone.utc))
        except Exception:
            return False

    # ── Ollama no ar? (só para a decisão automática não mandar ao local quando ele caiu) ─
    async def _ollama_no_ar(self) -> bool:
        """Resultado guardado por OLLAMA_SAUDE_S; pedidos simultâneos esperam a mesma checagem (uma só por vez)."""
        if time.monotonic() - self._saude_em < OLLAMA_SAUDE_S:
            return self._saude_ok
        if self._tarefa_saude is None or self._tarefa_saude.done():
            self._tarefa_saude = asyncio.get_running_loop().create_task(self._checar_ollama())
        return await asyncio.shield(self._tarefa_saude)   # um pedido cancelado não cancela a checagem dos outros

    async def _checar_ollama(self) -> bool:
        async def get():
            async with httpx.AsyncClient(timeout=OLLAMA_SAUDE_TIMEOUT) as cli:
                (await cli.get(f"{OLLAMA_URL}/api/version")).raise_for_status()
        try:
            await asyncio.wait_for(get(), OLLAMA_SAUDE_TIMEOUT + 0.2)   # teto total: o timeout do httpx é por fase
            ok = True
        except (httpx.HTTPError, OSError, asyncio.TimeoutError):
            ok = False   # recusado, sem resposta ou HTTP de erro
        except Exception as e:   # erro que não diz nada do Ollama: segue como antes (vai ao local)
            print(f"[roteador] checagem do Ollama: {type(e).__name__}", flush=True)
            ok = True
        if not ok and self._saude_ok:
            print("[roteador] Ollama fora: decisão automática evita o local", flush=True)
        self._saude_ok, self._saude_em = ok, time.monotonic()
        return ok

    # ── classificador semântico ───────────────────────────────────────────────────
    @staticmethod
    async def _embed(textos: list[str], limite: float) -> list[list[float]]:
        corpo = {"model": "bge-m3", "input": textos, "options": {"num_gpu": 0}, "keep_alive": "30m"}   # CPU: 0 de VRAM
        async with httpx.AsyncClient(timeout=limite) as cli:
            r = await cli.post(f"{OLLAMA_URL}/api/embed", json=corpo)
            r.raise_for_status()
            return r.json()["embeddings"]

    async def _vetor(self, texto: str) -> list[float] | None:
        """Embedding do pedido; qualquer erro ou demora acima de 1,5 s devolve None (vale só a heurística)."""
        try:
            return RR.normalizar((await asyncio.wait_for(self._embed([texto[:2000]], LIMITE_EMBED_S), LIMITE_EMBED_S))[0])
        except Exception as e:
            print(f"[roteador] sem embedding ({type(e).__name__}), só heurística", flush=True)
            self._aquecer()   # o modelo deve estar frio/descarregado: recarrega fora do caminho do pedido
            return None

    def _aquecer(self) -> None:
        """Recarrega o bge-m3 no Ollama em segundo plano. Uma só tarefa por vez, não importa quantos timeouts."""
        if self._tarefa_aquecer is not None and not self._tarefa_aquecer.done():
            return
        try:
            self._tarefa_aquecer = asyncio.get_running_loop().create_task(self._aquecer_embed())
        except RuntimeError:
            pass

    async def _aquecer_embed(self) -> None:
        try:
            await self._embed(["x"], 60)
        except Exception as e:
            print(f"[roteador] aquecimento do bge-m3 falhou ({type(e).__name__})", flush=True)

    @staticmethod
    def _ler_exemplos() -> list[tuple[str, str]]:
        dados = {}
        for caminho, chave in ((ARQ_EXEMPLOS, None), (ARQ_APRENDIDOS, "aprendidos")):
            try:
                lido = yaml.safe_load(_texto(caminho)) or {}
            except (OSError, yaml.YAMLError):
                continue   # o de aprendidos pode não existir
            if isinstance(lido, dict):
                dados.update(lido) if chave is None else dados.__setitem__(chave, lido)
        return RR.carregar_exemplos(dados)

    @staticmethod
    def _chave(texto: str) -> str:
        return hashlib.sha1(texto.encode("utf-8")).hexdigest()

    def _exemplos(self) -> list | None:
        """Exemplos com vetor, ou None se ainda não estão prontos. Nunca espera: o que falta é calculado em segundo plano."""
        try:
            mtimes = tuple(os.stat(c).st_mtime if os.path.exists(c) else None for c in (ARQ_EXEMPLOS, ARQ_APRENDIDOS))
            if mtimes != self._mtimes_exemplos and (self._tarefa_exemplos is None or self._tarefa_exemplos.done()):
                exemplos = self._ler_exemplos()
                try:
                    cache = json.loads(_texto(ARQ_VETORES))
                except (OSError, ValueError):
                    cache = {}
                self._mtimes_exemplos = mtimes   # mantém _pronto antigo até a nova lista ficar inteira
                if all(self._chave(t) in cache for t, _ in exemplos):
                    self._pronto = [(RR.normalizar(cache[self._chave(t)]), r) for t, r in exemplos] or None
                else:
                    self._tarefa_exemplos = asyncio.get_running_loop().create_task(self._calcular(exemplos, cache))
            elif self._mtimes_exemplos is not None and self._retomar_em \
                    and time.monotonic() > self._retomar_em and (self._tarefa_exemplos is None or self._tarefa_exemplos.done()):
                self._mtimes_exemplos = None   # o cálculo falhou (Ollama fora): tenta de novo, mesmo servindo a lista antiga
        except Exception as e:
            print(f"[roteador] exemplos semânticos: {e}", flush=True)
            self._pronto = None
        return self._pronto

    async def _calcular(self, exemplos: list[tuple[str, str]], cache: dict) -> None:
        try:
            faltam = [t for t, _ in exemplos if self._chave(t) not in cache]
            for i in range(0, len(faltam), 16):
                lote = faltam[i:i + 16]
                for t, v in zip(lote, await self._embed(lote, 60), strict=True):   # faltar vetor = falha, refaz em 60 s
                    cache[self._chave(t)] = [round(x, 5) for x in v]
            vivos = {self._chave(t) for t, _ in exemplos}
            cache = {k: v for k, v in cache.items() if k in vivos}
            tmp = ARQ_VETORES + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(cache, f)
            os.replace(tmp, ARQ_VETORES)
            self._pronto = [(RR.normalizar(cache[self._chave(t)]), r) for t, r in exemplos] or None
            self._retomar_em = 0.0
        except Exception as e:
            print(f"[roteador] não calculei os vetores dos exemplos ({type(e).__name__}), tento de novo em 60 s", flush=True)
            self._retomar_em = time.monotonic() + 60

    # ── decisão ───────────────────────────────────────────────────────────────────
    async def async_pre_call_hook(self, user_api_key_dict, cache, data, call_type):
        headers = (data.get("proxy_server_request") or {}).get("headers") or {}
        grupos_disponiveis = self._grupos or set()
        # imagem pedida direto a um grupo sem visão vai para a visão; com tools não (sessão de agente fica no código)
        if RR.tem_imagem(data) and not data.get("tools") \
                and data.get("model") in ("tudoia-codigo", "tudoia-nuvem", "tudoia-local") and RR.VISAO in grupos_disponiveis:
            data["model"] = RR.VISAO

        if data.get("model") != "tudoia-auto":
            self._preparar(data)
            self._evento(EV.evento_inicio(data, origem=headers.get("user-agent", ""), call_type=call_type))
            return data
        esgotados, membros = self.limites()
        gpu_busy = self.gpu_ocupada()
        vetor = exemplos = None
        if not self._aquecido:   # primeira requisição: deixa o bge-m3 quente cedo
            self._aquecido = True
            self._aquecer()
        pontuando = RR.precisa_pontuar(data, self._grupos)   # antes do decidir, que tira o #marcador do texto
        if pontuando:
            exemplos = self._exemplos()
            if exemplos:
                vetor = await self._vetor(RR.ultima_do_usuario(data))
        d = RR.decidir(data, self.regras(), esgotados, membros, grupos_existentes=self._grupos,
                       vetor=vetor, exemplos=exemplos, normalizados=True, gpu_ocupada=gpu_busy)
        if pontuando and not (vetor and exemplos):
            d.motivos.append("semantico_indisponivel")
        # #local explícito nunca é desviado (pode ser escolha de privacidade): aí vale o fallback do router
        if d.grupo in (RR.LOCAL, RR.LOCAL_AGENTE) and d.marcador != "local" and not await self._ollama_no_ar():
            d.grupo = RR.NUVEM if d.grupo == RR.LOCAL else RR.CODIGO
            d.motivos.append("ollama fora")
        if d.marcador in ("local", "nuvem"):
            self._gravar_correcao(d.marcador, data)
        self._evento(EV.evento_inicio(data, grupo=d.grupo, pontos=d.pontos, motivos=d.motivos,
                                      origem=headers.get("user-agent", ""), call_type=call_type))
        data["model"] = d.grupo
        self._preparar(data)   # depois do decidir: ele precisa ver a imagem para escolher o grupo
        registro = {
            "ts": _agora(), "call_type": str(call_type), "origem": str(headers.get("user-agent", ""))[:40],
            "pontos": d.pontos, "motivos": d.motivos, "grupo": d.grupo, "marcador": d.marcador,
        }
        call_id = data.get("litellm_call_id")
        if call_id:
            if len(self._pendentes) >= MAX_PENDENTES:
                self._pendentes.pop(next(iter(self._pendentes)))
            self._pendentes[call_id] = registro
        else:
            self._anexar("roteador.jsonl", dict(registro, call_id=None, ok=None))
        return data

    def _preparar(self, data: dict) -> None:
        """Ajusta o pedido ao destino final. Imagem: grupo com visão recebe tudo; sessão de agente (tools) em grupo
        sem visão perde todas (o código não aceita imagem); o resto perde só as de turnos antigos, e só se o turno
        atual não tiver imagem (como antes). cache_control: só fica para pago sem fallback (destinos_com_cache)."""
        destino = data.get("model")
        if destino not in RR.GRUPOS_COM_VISAO:
            if data.get("tools"):
                RR.sanitizar_imagens_historico(data, manter_atual=False)
            elif not RR.tem_imagem(data):
                RR.sanitizar_imagens_historico(data)
        if destino not in self._com_cache:
            RR.remover_cache_control(data)

    def _gravar_correcao(self, rotulo: str, data: dict) -> None:
        """#local/#nuvem do usuário é uma correção rotulada. Só rótulo, hash e tamanho: o prompt não fica em disco."""
        try:
            texto = RR.ultima_do_usuario(data).strip()   # já sem o marcador: decidir() o tirou
            if texto:
                self._anexar("correcoes.jsonl", {"ts": _agora(), "rotulo": rotulo, "sha1": self._chave(texto),
                                                 "caracteres": len(texto)})
        except Exception as e:
            print(f"[roteador] correção não gravada: {e}", flush=True)

    # ── modelo escolhido (uma vez por tentativa: mostra o fallback ao vivo) ────────
    async def async_pre_call_deployment_hook(self, kwargs, call_type):
        # chamado depois que o router escolhe o deployment e antes da chamada; devolve None = não altera o pedido
        try:
            call_id = kwargs.get("litellm_call_id")
            model = kwargs.get("model")
            info = kwargs.get("model_info") or (kwargs.get("metadata") or {}).get("model_info") \
                or (kwargs.get("litellm_metadata") or {}).get("model_info") or self._info(kwargs)
            anterior = self._modelo_atual.get(call_id)
            if anterior == model:   # o /v1/messages chama este gancho 2× para o mesmo deployment
                return None
            n = self._tentativas.get(call_id, 0) + 1
            if len(self._tentativas) > MAX_PENDENTES:
                self._tentativas.pop(next(iter(self._tentativas)))
                self._modelo_atual.pop(next(iter(self._modelo_atual)), None)
                self._membro_atual.pop(next(iter(self._membro_atual)), None)
            self._tentativas[call_id] = n
            self._modelo_atual[call_id] = model
            self._membro_atual[call_id] = info.get("membro")
            self._evento(EV.evento("modelo", call_id, modelo=model, provedor=info.get("provedor"),
                                   membro=info.get("membro"), tentativa=n))
        except Exception as e:
            print(f"[roteador] evento modelo: {e}", flush=True)
        return None

    # ── progresso do streaming (tokens subindo ao vivo) ────────────────────────────
    async def async_post_call_streaming_iterator_hook(self, user_api_key_dict, response, request_data):
        call_id = (request_data or {}).get("litellm_call_id")

        def contar(chunk):
            if not call_id:
                return
            if self._progresso.registrar(call_id, EV.contar_tokens_chunk(chunk)):
                self._evento(EV.evento("progresso", call_id, tokens_saida=self._progresso.tokens(call_id),
                                       tok_s=self._progresso.tok_s(call_id)))

        def terminar(completo):
            if not completo and call_id:   # cliente desistiu: o LiteLLM não manda sucesso nem falha
                self._evento(EV.evento("cancelado", call_id, tokens_saida=self._progresso.tokens(call_id) or None))
                self._progresso.encerrar(call_id)

        saida = EV.repassar(response, contar)
        if self._segurar(request_data):
            plano = RS.plano(self._mapa, request_data.get("model"), self._membro_atual.get(call_id))
            saida = RS.entregar(saida, lambda alvo: self._refazer(request_data, alvo), plano,
                                max_saida=request_data.get("max_tokens"))
        async for item in EV.repassar(saida, lambda _: None, ao_terminar=terminar):
            yield item

    @staticmethod
    def _segurar(request_data) -> bool:
        """Só o /v1/messages em streaming (Claude Code): lá um corte no meio vira "Server error mid-response"."""
        try:
            url = str(((request_data or {}).get("proxy_server_request") or {}).get("url") or "")
            return bool(request_data.get("stream")) and "/v1/messages" in url and "count_tokens" not in url
        except Exception:
            return False

    @staticmethod
    async def _refazer(request_data: dict, alvo: str):
        """Mesmo pedido, outro modelo/grupo, pelo router SEM os fallbacks dele (o plano escolhe). Hooks não rodam de novo."""
        from litellm.proxy.proxy_server import llm_router
        return await llm_router.aanthropic_messages(**RS.pedido_para_refazer(request_data, alvo, str(uuid.uuid4())))

    # ── resposta vazia (falha silenciosa do modelo: chega ok, sem texto) ───────────
    @staticmethod
    def _vazia(resp) -> tuple[bool, str | None]:
        """(vazia, finish_reason). Estrutura desconhecida ou com tool_calls/tool_use não conta como vazia."""
        def ler(o, k):
            return o.get(k) if isinstance(o, dict) else getattr(o, k, None)

        escolhas = ler(resp, "choices")
        if escolhas:
            esc = escolhas[0]
            msg = ler(esc, "message")
            if msg is None:
                return False, None
            conteudo = ler(msg, "content")
            if ler(msg, "tool_calls") or ler(msg, "function_call"):
                return False, None
            vazia = not (conteudo.strip() if isinstance(conteudo, str) else conteudo)
            return vazia, ler(esc, "finish_reason")
        blocos = ler(resp, "content")
        if isinstance(blocos, list):
            if any(ler(b, "type") not in ("text", "thinking") for b in blocos):
                return False, None   # tool_use etc.
            vazia = not any((ler(b, "text") or "").strip() for b in blocos if ler(b, "type") == "text")
            return vazia, ler(resp, "stop_reason")
        return False, None

    # ── resultado ─────────────────────────────────────────────────────────────────
    @staticmethod
    def _info(kwargs) -> dict:
        params = kwargs.get("litellm_params") or {}
        return params.get("model_info") or (params.get("metadata") or {}).get("model_info") or {}

    def _resultado(self, kwargs, response_obj, start_time, end_time, ok: bool, erro: str | None):
        call_id = kwargs.get("litellm_call_id")
        info = self._info(kwargs)
        provedor = info.get("provedor")
        try:
            ms = int((end_time - start_time).total_seconds() * 1000)
        except Exception:
            ms = None
        try:
            uso = getattr(response_obj, "usage", None) or (response_obj.get("usage") if isinstance(response_obj, dict) else None)
            entrada = _num(uso, "prompt_tokens", "input_tokens")
            saida = _num(uso, "completion_tokens", "output_tokens") or self._progresso.tokens(call_id) or None
            tok_s = round(saida / (ms / 1000), 1) if saida and ms else None
            self._evento(EV.evento("fim" if ok else "erro", call_id, modelo=kwargs.get("model"), provedor=provedor,
                                   membro=info.get("membro"), tokens_entrada=entrada, tokens_saida=saida, tok_s=tok_s,
                                   ms=ms, custo_usd=kwargs.get("response_cost"), erro=erro, ok=ok))
            if ok:
                vazia, motivo_fim = self._vazia(response_obj)
                if vazia:
                    self._evento(EV.evento("vazia", call_id, membro=info.get("membro"), finish_reason=motivo_fim))
                self._progresso.encerrar(call_id)
                self._tentativas.pop(call_id, None)
                self._modelo_atual.pop(call_id, None)
                self._membro_atual.pop(call_id, None)
        except Exception as e:
            print(f"[roteador] evento fim: {e}", flush=True)
        if ok:
            self._gravar_ratelimit(provedor, response_obj)
        decisao = self._pendentes.pop(call_id, None) if ok else self._pendentes.get(call_id)
        if decisao is None:
            return
        self._anexar("roteador.jsonl", dict(
            decisao, call_id=call_id, modelo=kwargs.get("model"), provedor=provedor,
            membro=info.get("membro"), ms=ms, ok=ok, erro=erro,
        ))

    def _gravar_ratelimit(self, provedor, response_obj) -> None:
        """Métrica: nenhum erro aqui pode derrubar o pedido. Só o hook grava o arquivo, então ele é lido uma vez e
        depois vale a memória; a gravação (atômica) fica com a thread do Gravador."""
        try:
            if not provedor or provedor == "local":
                return
            ocultos = getattr(response_obj, "_hidden_params", None) or {}
            cabecalhos = ocultos.get("additional_headers") or {}
            rl = {k.replace("llm_provider-", ""): v for k, v in cabecalhos.items() if "ratelimit" in k.lower()}
            if not rl:
                return
            if self._ratelimit is None:
                lido = _ler_json("ratelimit.json")
                self._ratelimit = lido if isinstance(lido, dict) else {}
            self._ratelimit[provedor] = dict(rl, ts=_agora())
            # cópia: a thread serializa enquanto o próximo pedido pode alterar o dict
            self._gravador.put(dict(self._ratelimit), os.path.join(DIR_LOGS, "ratelimit.json"), substituir=True)
        except Exception as e:
            print(f"[roteador] ratelimit não gravado ({type(e).__name__})", flush=True)

    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        self._resultado(kwargs, response_obj, start_time, end_time, True, None)

    async def async_log_failure_event(self, kwargs, response_obj, start_time, end_time):
        erro = EV.resumir_erro(kwargs.get("exception"))   # só classe + HTTP: a mensagem pode repetir o pedido
        self._resultado(kwargs, response_obj, start_time, end_time, False, erro)


proxy_handler_instance = Roteador()

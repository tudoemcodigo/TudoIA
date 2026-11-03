"""Vídeo longo (até 60 s): divide o pedido em clipes, gera cada um num motor (ComfyUI local ou nuvem via LiteLLM),
encadeia o último quadro de um clipe no seguinte (modo contínuo) e monta o MP4 final.

Um trabalho por vez: a GPU é uma só e a nuvem cobra por segundo. O estado vai para dados/estudio/video-longo/<id>/
a cada passo. Se o painel reiniciar no meio, o trabalho volta como "interrompido" (nada é retomado sozinho, para
não gastar sem a pessoa ver) e o Retomar continua do clipe que faltou. Clipe já enviado é consultado pelo id em vez
de reenviado: na nuvem isso evita pagar duas vezes pelo mesmo trecho.
"""
import json
import logging
import math
import os
import queue
import random
import re
import secrets
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Protocol

import httpx

from . import comfyui
from . import upstreams
from . import video_midia
from .caminhos import comfyui_dir
from .estudio_servico import (
    _arbitrar_vram_para_estudio,
    _chamar_ollama_prompt,
    _registrar_historico_visual,
    _submeter_comfyui_video,
    erro_do_historico,
    video_do_historico,
)
from .video_nuvem import ClienteVideoLiteLLM, ErroNuvem, ModeloVideoNuvem, corpo_pedido

_log = logging.getLogger("tudoia.video_longo")

DURACAO_MAXIMA_S = 60
MAX_CENAS = 12
ID_VALIDO = re.compile(r"^vl_[0-9a-f]{12}$")
ESTADOS_FINAIS = ("concluido", "erro", "cancelado", "interrompido")
TIMEOUT_CLIPE_LOCAL_S = 3600     # LTX de 20 s em 8 GB passa de 20 min
TIMEOUT_CLIPE_NUVEM_S = 1800
TENTATIVAS_TRANSITORIAS = 4
MAX_TRABALHOS_GUARDADOS = 50


class ErroMotor(RuntimeError):
    def __init__(self, mensagem: str, transitorio: bool = False):
        super().__init__(mensagem)
        self.transitorio = transitorio


class Cancelado(Exception):
    pass


# ------------------------------------------------------------------ planejamento
def planejar_segmentos(total_s: int, validas: tuple[int, ...]) -> list[int]:
    """Durações dos clipes: o menor número de clipes, os mais parecidos possíveis, cada um numa duração aceita.
    A soma pode passar do total (provedor com duração fixa); a montagem corta no total pedido."""
    if total_s < 1 or not validas:
        raise ValueError("duração ou durações aceitas inválidas")
    validas = tuple(sorted(set(validas)))
    maior = validas[-1]
    saida: list[int] = []
    resto = total_s
    while resto > 0:
        faltam = math.ceil(resto / maior)
        alvo = math.ceil(resto / faltam)
        d = next((v for v in validas if v >= alvo), maior)
        saida.append(d)
        resto -= d
    return saida


def estimar_custo(modelo: ModeloVideoNuvem, segmentos: list[int], resolucao: str) -> float:
    """Cobrança por segundo gerado, inclusive o que a montagem corta."""
    return round(sum(segmentos) * modelo.preco(resolucao), 4)


def dividir_em_cenas(prompt: str, n: int) -> list[str]:
    """Roteiro de n cenas pelo Ollama LOCAL (o texto não sai da máquina). Saída do modelo é dado não confiável:
    só vale uma lista JSON de n textos curtos; qualquer outra coisa vira o prompt repetido com o número da cena."""
    reserva = [f"{prompt}. Scene {i + 1} of {n}." for i in range(n)]
    if n <= 1:
        return [prompt]
    sistema = (
        "You split a video idea into consecutive shots of one short film. Answer ONLY with a JSON array of exactly "
        f"{n} strings, in English, each one a self-contained cinematic shot description (subject, action, camera, "
        "light) that keeps the same characters and style. No markdown, no keys, no commentary."
    )
    bruto = _chamar_ollama_prompt(sistema, prompt, "JSON array:")
    try:
        inicio, fim = bruto.index("["), bruto.rindex("]") + 1
        cenas = json.loads(bruto[inicio:fim])
    except (ValueError, json.JSONDecodeError):
        return reserva
    if not (isinstance(cenas, list) and len(cenas) == n and all(isinstance(c, str) and 0 < len(c.strip()) <= 2000 for c in cenas)):
        return reserva
    return [c.strip() for c in cenas]


# ------------------------------------------------------------------ motores
class MotorVideo(Protocol):
    nuvem: bool

    def submeter(self, prompt: str, duracao_s: int, imagem: Path | None, seed: int) -> str: ...
    def consultar(self, ref: str) -> tuple[str, str | None]: ...   # "andamento" | "pronto" | "erro" | "sumiu"
    def baixar(self, ref: str, destino: Path) -> None: ...
    def cancelar(self, ref: str) -> None: ...


class MotorComfyUI:
    nuvem = False

    def __init__(self, raiz: Path, modelo_id: str, resolucao: str, pasta_videos: Path):
        self.raiz, self.modelo_id, self.resolucao, self.pasta_videos = raiz, modelo_id, resolucao, pasta_videos

    def submeter(self, prompt: str, duracao_s: int, imagem: Path | None, seed: int) -> str:
        r = _submeter_comfyui_video(raiz=self.raiz, modelo_id=self.modelo_id, prompt_texto=prompt, seed=seed,
                                    resolucao=self.resolucao, duracao_s=duracao_s, fps=24, caminho_ref=imagem,
                                    pasta_estudio_videos=self.pasta_videos)
        if not r.get("ok"):
            erro = str(r.get("erro") or "falha ao enviar ao ComfyUI")
            raise ErroMotor(erro[:400], transitorio="comunicação" in erro)
        return str(r["prompt_id"])

    def consultar(self, ref: str) -> tuple[str, str | None]:
        try:
            with httpx.Client(timeout=8.0) as cli:
                h = cli.get(f"{upstreams.COMFYUI}/history/{ref}")
                if h.status_code == 200 and ref in (dados := h.json()):
                    falha = erro_do_historico(dados[ref])
                    if falha:
                        return "erro", falha
                    return ("pronto", None) if video_do_historico(dados[ref]) else ("andamento", None)
                q = cli.get(f"{upstreams.COMFYUI}/queue")
                if q.status_code == 200:
                    fila = q.json()
                    for item in (fila.get("queue_running") or []) + (fila.get("queue_pending") or []):
                        if len(item) > 1 and item[1] == ref:
                            return "andamento", None
                return "sumiu", None
        except (httpx.HTTPError, ValueError) as e:
            raise ErroMotor(f"ComfyUI não respondeu: {type(e).__name__}", transitorio=True) from e

    def baixar(self, ref: str, destino: Path) -> None:
        with httpx.Client(timeout=15.0) as cli:
            h = cli.get(f"{upstreams.COMFYUI}/history/{ref}")
            item = video_do_historico((h.json() or {}).get(ref) or {}) if h.status_code == 200 else None
            if not item:
                raise ErroMotor("o ComfyUI terminou sem gravar vídeo")
            params = comfyui.parametros_view(item)   # recusa nome/pasta com `..`
            base = (comfyui_dir(self.raiz) / "output").resolve()
            local = (base / params.get("subfolder", "") / params["filename"]).resolve()
            if local.is_relative_to(base) and local.is_file():
                shutil.copy2(local, destino)
                return
            v = cli.get(f"{comfyui.BASE}/view", params=params, timeout=120.0)
            if v.status_code != 200 or len(v.content) < 1000:
                raise ErroMotor(f"download do clipe no ComfyUI falhou (HTTP {v.status_code})", transitorio=True)
            destino.write_bytes(v.content)

    def cancelar(self, ref: str) -> None:
        try:
            with httpx.Client(timeout=4.0) as cli:
                r = cli.post(f"{upstreams.COMFYUI}/api/jobs/{ref}/cancel")
                if r.status_code == 404:
                    cli.post(f"{upstreams.COMFYUI}/interrupt", json={"prompt_id": ref})
        except httpx.HTTPError:
            pass


class MotorNuvem:
    """Na nuvem não há cancelamento: o provedor termina e cobra o clipe já enviado (a interface avisa)."""
    nuvem = True

    def __init__(self, cliente: ClienteVideoLiteLLM, modelo: ModeloVideoNuvem, resolucao: str):
        self.cliente, self.modelo, self.resolucao = cliente, modelo, resolucao

    def submeter(self, prompt: str, duracao_s: int, imagem: Path | None, seed: int) -> str:
        try:
            return self.cliente.criar(corpo_pedido(self.modelo, prompt, duracao_s, self.resolucao, seed, imagem))
        except ErroNuvem as e:
            raise ErroMotor(str(e), transitorio=e.transitorio) from e

    def consultar(self, ref: str) -> tuple[str, str | None]:
        try:
            return self.cliente.status(ref)
        except ErroNuvem as e:
            raise ErroMotor(str(e), transitorio=e.transitorio) from e

    def baixar(self, ref: str, destino: Path) -> None:
        try:
            self.cliente.baixar(ref, destino)
        except ErroNuvem as e:
            raise ErroMotor(str(e), transitorio=e.transitorio) from e

    def cancelar(self, ref: str) -> None:
        return None


# ------------------------------------------------------------------ executor
def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _gravar_json(caminho: Path, dados: dict) -> None:
    tmp = caminho.with_name(caminho.name + ".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, caminho)


class ExecutorVideoLongo:
    """Fila de um trabalho por vez numa thread daemon. Todo acesso ao estado passa por `_trava`."""

    def __init__(self, raiz: Path, pasta_videos: Path, fabrica_motor: Callable[[dict], MotorVideo],
                 intervalo_s: float = 3.0, midia=video_midia, dormir: Callable[[float], None] = time.sleep):
        self.raiz = raiz
        self.pasta = raiz / "dados" / "estudio" / "video-longo"
        self.pasta_videos = pasta_videos
        self._fabrica = fabrica_motor
        self._intervalo = intervalo_s
        self._midia = midia
        self._dormir = dormir
        self._trava = threading.Lock()
        self._trabalhos: dict[str, dict] = {}
        self._cancelar: set[str] = set()
        self._fila: queue.Queue[str] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._atual: tuple[str, MotorVideo, str] | None = None   # (trabalho, motor, ref) do clipe em geração
        self._carregar()

    # -------------------------------------------------- persistência
    def _arquivo(self, tid: str) -> Path:
        return self.pasta / tid / "trabalho.json"

    def _salvar(self, t: dict) -> None:
        t["atualizado"] = _agora()
        (self.pasta / t["id"]).mkdir(parents=True, exist_ok=True)
        _gravar_json(self._arquivo(t["id"]), t)

    def _carregar(self) -> None:
        if not self.pasta.is_dir():
            return
        for arq in self.pasta.glob("vl_*/trabalho.json"):
            try:
                t = json.loads(arq.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                _log.warning("trabalho de vídeo longo ilegível ignorado: %s", arq.parent.name)
                continue
            if not ID_VALIDO.match(str(t.get("id", ""))):
                continue
            if t.get("estado") not in ESTADOS_FINAIS:   # o painel caiu no meio: a pessoa decide se retoma
                t["estado"], t["fase"] = "interrompido", "O painel reiniciou durante a geração. Use Retomar."
                self._salvar(t)
            self._trabalhos[t["id"]] = t

    # -------------------------------------------------- API
    def criar(self, pedido: dict, duracoes: list[int], custo_estimado_usd: float | None) -> dict:
        tid = f"vl_{secrets.token_hex(6)}"
        cenas = pedido.get("cenas") or []
        segmentos = [{"indice": i, "duracao_s": d, "prompt": cenas[i] if i < len(cenas) else None,
                      "estado": "pendente", "ref": None, "arquivo": None, "erro": None, "tentativas": 0}
                     for i, d in enumerate(duracoes)]
        t = {"id": tid, "criado": _agora(), "estado": "na_fila", "fase": "Na fila", "pedido": pedido,
             "segmentos": segmentos, "custo_estimado_usd": custo_estimado_usd, "video_final": None, "erro": None}
        with self._trava:
            self._salvar(t)
            self._trabalhos[tid] = t
            self._podar()
        self._enfileirar(tid)
        return self.obter(tid)

    def obter(self, tid: str) -> dict | None:
        with self._trava:
            t = self._trabalhos.get(tid)
            return json.loads(json.dumps(t)) if t else None

    def listar(self, limite: int = 20) -> list[dict]:
        with self._trava:
            itens = sorted(self._trabalhos.values(), key=lambda t: t.get("criado", ""), reverse=True)[:limite]
            return json.loads(json.dumps(itens))

    def cancelar(self, tid: str) -> dict | None:
        with self._trava:
            t = self._trabalhos.get(tid)
            if not t:
                return None
            if t["estado"] in ESTADOS_FINAIS:
                return json.loads(json.dumps(t))
            self._cancelar.add(tid)
            if t["estado"] == "na_fila":
                t["estado"], t["fase"] = "cancelado", "Cancelado antes de começar"
                self._salvar(t)
            atual = self._atual if self._atual and self._atual[0] == tid else None
        if atual:
            atual[1].cancelar(atual[2])
        return self.obter(tid)

    def retomar(self, tid: str) -> dict | None:
        with self._trava:
            t = self._trabalhos.get(tid)
            if not t:
                return None
            if t["estado"] not in ("erro", "interrompido", "cancelado"):
                return json.loads(json.dumps(t))
            for s in t["segmentos"]:
                if s["estado"] == "erro":   # clipe que falhou de vez é refeito do zero; "enviado" é só consultado
                    s.update(estado="pendente", ref=None, erro=None)
            t.update(estado="na_fila", fase="Na fila (retomado)", erro=None)
            self._cancelar.discard(tid)
            self._salvar(t)
        self._enfileirar(tid)
        return self.obter(tid)

    # -------------------------------------------------- execução
    def _podar(self) -> None:
        finais = sorted((t for t in self._trabalhos.values() if t["estado"] in ESTADOS_FINAIS),
                        key=lambda t: t.get("criado", ""))
        excesso = len(self._trabalhos) - MAX_TRABALHOS_GUARDADOS
        for t in finais[:max(0, excesso)]:
            self._trabalhos.pop(t["id"], None)
            pasta = (self.pasta / t["id"]).resolve()
            if pasta.parent == self.pasta.resolve() and ID_VALIDO.match(pasta.name):
                shutil.rmtree(pasta, ignore_errors=True)   # só os clipes intermediários; o MP4 final fica

    def _enfileirar(self, tid: str) -> None:
        self._fila.put(tid)
        with self._trava:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._laco, name="video-longo", daemon=True)
                self._thread.start()

    def _laco(self) -> None:
        while True:
            tid = self._fila.get()
            try:
                self._executar(tid)
            except Exception:  # noqa: BLE001 — a thread não pode morrer: o próximo trabalho ficaria parado
                _log.exception("vídeo longo %s falhou fora do previsto", tid)

    def _atualizar(self, t: dict, **campos: Any) -> None:
        with self._trava:
            t.update(campos)
            self._salvar(t)

    def _checar_cancelamento(self, tid: str) -> None:
        with self._trava:
            if tid in self._cancelar:
                raise Cancelado()

    def _executar(self, tid: str) -> None:
        with self._trava:
            t = self._trabalhos.get(tid)
            if not t or t["estado"] != "na_fila":
                return
            t.update(estado="executando", fase="Preparando")
            self._salvar(t)
        inicio = time.time()
        pedido = t["pedido"]
        pasta = self.pasta / tid
        try:
            motor = self._fabrica(pedido)
            if not motor.nuvem:
                _arbitrar_vram_para_estudio()
            self._roteirizar(t)
            anterior: Path | None = None
            for seg in t["segmentos"]:
                self._checar_cancelamento(tid)
                arquivo = pasta / f"clipe_{seg['indice']:02d}.mp4"
                if seg["estado"] != "concluido" or not arquivo.is_file():
                    imagem = self._imagem_do_segmento(t, seg, anterior, pasta)
                    self._gerar_clipe(t, motor, seg, imagem, arquivo)
                anterior = arquivo
            self._checar_cancelamento(tid)
            final = self._montar(t, pasta)
            dur = time.time() - inicio
            self._atualizar(t, estado="concluido", fase="Vídeo pronto", video_final=final.name, erro=None)
            _registrar_historico_visual("video", "nuvem" if motor.nuvem else "comfyui", pedido["modelo"],
                                        pedido["prompt"], pedido["resolucao"], dur, "sucesso",
                                        f"/api/estudio/videos/{final.name}")
        except Cancelado:
            self._atualizar(t, estado="cancelado", fase="Cancelado pela pessoa")
        except Exception as e:  # noqa: BLE001 — qualquer falha tem de virar "erro", senão o trabalho fica "executando"
            esperado = isinstance(e, (ErroMotor, video_midia.ErroMidia, ValueError, OSError))
            if not esperado:
                _log.exception("vídeo longo %s: falha inesperada", tid)
            self._atualizar(t, estado="erro", fase="Falhou",
                            erro=(str(e) if esperado else f"falha inesperada ({type(e).__name__})")[:500])
            _registrar_historico_visual("video", pedido.get("motor", ""), pedido["modelo"], pedido["prompt"],
                                        pedido["resolucao"], time.time() - inicio, "falha", "")
        finally:
            with self._trava:
                self._cancelar.discard(tid)
                self._atual = None

    def _roteirizar(self, t: dict) -> None:
        segs = t["segmentos"]
        if all(s.get("prompt") for s in segs):
            return
        pedido = t["pedido"]
        if pedido.get("modo") == "cenas":
            self._atualizar(t, fase="Dividindo o roteiro em cenas (Ollama local)")
            cenas = dividir_em_cenas(pedido["prompt"], len(segs))
        else:
            cenas = [pedido["prompt"]] * len(segs)
        with self._trava:
            for s, texto in zip(segs, cenas, strict=True):
                s["prompt"] = s.get("prompt") or texto
            self._salvar(t)

    def _imagem_do_segmento(self, t: dict, seg: dict, anterior: Path | None, pasta: Path) -> Path | None:
        pedido = t["pedido"]
        if seg["indice"] == 0:
            ref = pedido.get("referencia")
            if not ref:
                return None
            ref_p = Path(ref)
            if ref_p.suffix.lower() in (".mp4", ".webm", ".mov", ".mkv"):
                destino = pasta / "referencia.jpg"
                self._midia.primeiro_quadro(self.raiz, ref_p, destino)
                return destino
            return ref_p
        if pedido.get("modo") != "continuo" or anterior is None:
            return None
        destino = pasta / f"quadro_{seg['indice'] - 1:02d}.jpg"
        if not destino.is_file():
            self._midia.ultimo_quadro(self.raiz, anterior, destino)
        return destino

    def _com_repeticao(self, tid: str, acao: Callable[[], Any], rotulo: str) -> Any:
        """Repete só falha transitória (rede, 429, 5xx), com backoff exponencial e jitter."""
        for tentativa in range(TENTATIVAS_TRANSITORIAS):
            self._checar_cancelamento(tid)
            try:
                return acao()
            except ErroMotor as e:
                if not e.transitorio or tentativa == TENTATIVAS_TRANSITORIAS - 1:
                    raise
                espera = min(60.0, self._intervalo * (2 ** tentativa)) * (0.5 + random.random())
                _log.info("%s: %s; nova tentativa em %.1f s", rotulo, e, espera)
                self._dormir(espera)
        raise ErroMotor(f"{rotulo}: sem resposta")

    def _gerar_clipe(self, t: dict, motor: MotorVideo, seg: dict, imagem: Path | None, arquivo: Path) -> None:
        tid, n = t["id"], len(t["segmentos"])
        rotulo = f"clipe {seg['indice'] + 1}/{n}"
        seed = int(t["pedido"].get("seed") or 0) + seg["indice"]
        reenvios = 0
        while True:
            if not seg.get("ref"):
                self._atualizar(t, fase=f"Enviando {rotulo} ({seg['duracao_s']} s)")
                ref = self._com_repeticao(
                    tid, lambda: motor.submeter(seg["prompt"], seg["duracao_s"], imagem, seed), f"{rotulo}: envio")
                with self._trava:
                    seg.update(ref=ref, estado="enviado", tentativas=seg.get("tentativas", 0) + 1)
                    self._salvar(t)
            with self._trava:
                self._atual = (tid, motor, seg["ref"])
            estado, erro = self._esperar(t, motor, seg, rotulo)
            if estado == "pronto":
                break
            if estado == "sumiu" and not motor.nuvem and reenvios < 1:
                reenvios += 1   # o ComfyUI reiniciou e esqueceu o trabalho: refaz o clipe uma vez
                with self._trava:
                    seg.update(ref=None, estado="pendente")
                    self._salvar(t)
                continue
            with self._trava:
                seg.update(estado="erro", erro=erro or "o motor perdeu o clipe")
                self._salvar(t)
            raise ErroMotor(f"{rotulo}: {seg['erro']}")
        self._atualizar(t, fase=f"Baixando {rotulo}")
        self._com_repeticao(tid, lambda: motor.baixar(seg["ref"], arquivo), f"{rotulo}: download")
        with self._trava:
            seg.update(estado="concluido", arquivo=arquivo.name, erro=None)
            self._salvar(t)

    def _esperar(self, t: dict, motor: MotorVideo, seg: dict, rotulo: str) -> tuple[str, str | None]:
        limite = time.monotonic() + (TIMEOUT_CLIPE_NUVEM_S if motor.nuvem else TIMEOUT_CLIPE_LOCAL_S)
        inicio = time.monotonic()
        falhas = 0
        while time.monotonic() < limite:
            self._checar_cancelamento(t["id"])
            try:
                estado, erro = motor.consultar(seg["ref"])
                falhas = 0
            except ErroMotor as e:
                falhas += 1
                if not e.transitorio or falhas >= 10:
                    raise
                estado, erro = "andamento", None
            if estado != "andamento":
                return estado, erro
            self._atualizar(t, fase=f"Gerando {rotulo} · {int(time.monotonic() - inicio)} s")
            self._dormir(self._intervalo)
        return "erro", f"passou de {int(limite - inicio)} s sem terminar"

    def _montar(self, t: dict, pasta: Path) -> Path:
        pedido = t["pedido"]
        clipes = [pasta / s["arquivo"] for s in t["segmentos"]]
        self._atualizar(t, fase=f"Montando {len(clipes)} clipes")
        dados = self._midia.info(self.raiz, clipes[0])
        final = self.pasta_videos / f"video_longo_{t['id']}.mp4"
        trilha = Path(pedido["trilha"]) if pedido.get("trilha") else None
        fps = max(1, min(60, round(dados.get("fps") or 24)))
        self._midia.montar(self.raiz, final, clipes, int(dados["largura"]), int(dados["altura"]), fps,
                           duracao_max_s=float(pedido["duracao_total_s"]), trilha=trilha)
        return final

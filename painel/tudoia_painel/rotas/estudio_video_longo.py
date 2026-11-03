"""Estúdio: vídeo longo (até 60 s) em clipes emendados, no ComfyUI local ou na nuvem pelo LiteLLM."""
import time
from pathlib import Path

from fastapi import APIRouter

from .. import servicos as infra
from .. import video_midia
from ..ambiente import Contexto
from ..envfile import ler_env
from ..erros import ErroApi
from ..estudio_servico import _otimizar_prompt_video, arquivo_em, max_segmento_video_local, perfil_video_local
from ..schemas import RetomarVideoLongoReq, VideoLongoReq
from ..video_longo import ID_VALIDO, ExecutorVideoLongo, MotorComfyUI, MotorNuvem, estimar_custo, planejar_segmentos
from ..video_nuvem import ClienteVideoLiteLLM, ModeloVideoNuvem, catalogo_video
from .estudio_catalogo import modelo_ltx23

VAR_TETO = "TUDOIA_VIDEO_NUVEM_TETO_USD"   # opcional: sem valor, não há teto (a estimativa aparece antes de gerar)


def criar_router(ctx: Contexto) -> APIRouter:
    router = APIRouter()
    raiz = ctx.raiz
    pastas = ctx.pastas_estudio
    clientes: dict[str, ClienteVideoLiteLLM] = {}

    def modelo_nuvem(nome: str) -> ModeloVideoNuvem:
        for m in catalogo_video(raiz):
            if m.nome == nome:
                return m
        raise ErroApi(404, "nao_encontrado", f"Modelo de vídeo na nuvem desconhecido: {nome}", campo="modelo")

    def fabrica(pedido: dict):
        if pedido["motor"] == "nuvem":
            chave = (ler_env(raiz / ".env").get("LITELLM_MASTER_KEY") or "").strip()
            if chave not in clientes:
                clientes.clear()   # chave mestra trocada: o cliente antigo sai
                clientes[chave] = ClienteVideoLiteLLM(chave)
            return MotorNuvem(clientes[chave], modelo_nuvem(pedido["modelo"]), pedido["resolucao"])
        return MotorComfyUI(raiz, pedido["modelo"], pedido["resolucao"], pastas.videos)

    executor = ExecutorVideoLongo(raiz, pastas.videos, fabrica)

    def plano(corpo: VideoLongoReq) -> dict:
        """Clipes, custo e o modelo resolvido. Não tem efeito colateral: serve ao estimar e ao criar."""
        if corpo.motor == "nuvem":
            m = modelo_nuvem(corpo.modelo)
            duracoes = planejar_segmentos(corpo.duracao_segundos, m.duracoes_validas())
            env = ler_env(raiz / ".env")
            return {"duracoes": duracoes, "custo_estimado_usd": estimar_custo(m, duracoes, corpo.resolucao),
                    "preco_usd_s": m.preco(corpo.resolucao), "fonte_preco": m.fonte_preco,
                    "chave_presente": bool((env.get(m.chave) or "").strip()), "chave": m.chave,
                    "continuidade_por_quadro": bool(m.i2v), "nuvem": True}
        if corpo.modelo == "video-ltx23" and not modelo_ltx23(raiz):
            raise ErroApi(422, "validacao", "O LTX-2.3 não está instalado (pesos ou custom nodes ausentes).", campo="modelo")
        perfil = perfil_video_local(corpo.modelo)
        maximo = max_segmento_video_local(perfil, corpo.resolucao)
        return {"duracoes": planejar_segmentos(corpo.duracao_segundos, tuple(range(1, maximo + 1))),
                "custo_estimado_usd": 0.0, "continuidade_por_quadro": True, "nuvem": False}

    def teto_usd() -> float | None:
        bruto = (ler_env(raiz / ".env").get(VAR_TETO) or "").strip().replace(",", ".")
        try:
            return float(bruto) if bruto else None
        except ValueError:
            return None

    def resolver_arquivo(nome: str | None, pastas_validas, rotulo: str) -> Path | None:
        if not nome:
            return None
        n = nome.strip().removeprefix("/api/estudio/uploads/").removeprefix("/api/estudio/musicas/")
        alvo = arquivo_em(pastas_validas, n)   # recusa `..` e caminho absoluto
        if not alvo:
            raise ErroApi(404, "nao_encontrado", f"{rotulo} não encontrado: '{nome}'. Envie o arquivo de novo.")
        return alvo

    @router.post("/api/estudio/video-longo/estimar")
    def estimar(corpo: VideoLongoReq):
        p = plano(corpo)
        return {"ok": True, "segmentos": p["duracoes"], "clipes": len(p["duracoes"]),
                "segundos_gerados": sum(p["duracoes"]), "teto_usd": teto_usd(), **p}

    @router.post("/api/estudio/video-longo")
    def criar(corpo: VideoLongoReq):
        p = plano(corpo)
        if not video_midia.disponivel(raiz):
            raise ErroApi(503, "servico_offline", "O vídeo longo usa o Python do ComfyUI portable para emendar os clipes, "
                          "e ele não foi encontrado.", extras={"servico_offline": "comfyui"})
        if p["nuvem"]:
            if not p["chave_presente"]:
                raise ErroApi(422, "chave_ausente", f"Configure {p['chave']} em Chaves e segredos para usar este modelo.",
                              campo="modelo", extras={"chave": p["chave"]})
            if not corpo.confirmar_nuvem:
                raise ErroApi(422, "confirmacao_necessaria", "Confirme o envio para a nuvem: o texto e as imagens saem da "
                              "máquina e o provedor cobra por segundo.", extras={"custo_estimado_usd": p["custo_estimado_usd"]})
            teto = teto_usd()
            if teto is not None and p["custo_estimado_usd"] > teto:
                raise ErroApi(422, "acima_do_teto", f"Custo estimado US$ {p['custo_estimado_usd']:.2f} passa do teto de "
                              f"US$ {teto:.2f} ({VAR_TETO}).", extras={"custo_estimado_usd": p["custo_estimado_usd"]})
            if not infra.porta_aberta(4000):
                raise ErroApi(503, "servico_offline", "O LiteLLM (:4000) está fora do ar.", extras={"servico_offline": "litellm"})
        elif not infra.porta_aberta(8188):
            raise ErroApi(503, "servico_offline", "O ComfyUI (:8188) está offline. Inicie-o para gerar na GPU.",
                          extras={"servico_offline": "comfyui", "porta": 8188})

        referencia = resolver_arquivo(corpo.arquivo_referencia, (pastas.uploads,), "Arquivo de referência")
        trilha = resolver_arquivo(corpo.trilha, (pastas.musicas,), "Trilha")
        prompt, otimizado, _msg = (_otimizar_prompt_video(corpo.prompt, raiz) if corpo.otimizar_prompt
                                   else (corpo.prompt, False, ""))
        pedido = {"prompt": prompt, "prompt_original": corpo.prompt, "prompt_otimizado": otimizado,
                  "motor": corpo.motor, "modelo": corpo.modelo, "resolucao": corpo.resolucao,
                  "duracao_total_s": corpo.duracao_segundos, "modo": corpo.modo, "cenas": corpo.cenas or [],
                  "seed": corpo.seed if corpo.seed is not None else int(time.time() * 1000) % 1_000_000_000,
                  "referencia": str(referencia) if referencia else None, "trilha": str(trilha) if trilha else None}
        trabalho = executor.criar(pedido, p["duracoes"], p["custo_estimado_usd"] if p["nuvem"] else None)
        return {"ok": True, "trabalho": _publico(trabalho)}

    @router.get("/api/estudio/video-longo")
    def listar():
        return {"ok": True, "trabalhos": [_publico(t) for t in executor.listar()]}

    def _obter(tid: str) -> dict:
        t = executor.obter(tid) if ID_VALIDO.match(tid) else None
        if not t:
            raise ErroApi(404, "nao_encontrado", "Trabalho de vídeo longo não encontrado.")
        return t

    @router.get("/api/estudio/video-longo/{tid}")
    def obter(tid: str):
        return {"ok": True, "trabalho": _publico(_obter(tid))}

    @router.post("/api/estudio/video-longo/{tid}/cancelar")
    def cancelar(tid: str):
        _obter(tid)
        return {"ok": True, "trabalho": _publico(executor.cancelar(tid))}

    @router.post("/api/estudio/video-longo/{tid}/retomar")
    def retomar(tid: str, corpo: RetomarVideoLongoReq | None = None):
        t = _obter(tid)
        if t["pedido"]["motor"] == "nuvem" and not (corpo and corpo.confirmar_nuvem):
            raise ErroApi(422, "confirmacao_necessaria", "Confirme de novo o envio para a nuvem para retomar.")
        return {"ok": True, "trabalho": _publico(executor.retomar(tid))}

    return router


def _publico(t: dict) -> dict:
    """O que a interface vê: sem caminhos do disco (referência e trilha viram só o nome do arquivo)."""
    pedido = dict(t["pedido"])
    for campo in ("referencia", "trilha"):
        if pedido.get(campo):
            pedido[campo] = Path(pedido[campo]).name
    segs = t["segmentos"]
    feitos = sum(1 for s in segs if s["estado"] == "concluido")
    return {"id": t["id"], "estado": t["estado"], "fase": t.get("fase", ""), "erro": t.get("erro"),
            "criado": t.get("criado"), "atualizado": t.get("atualizado"), "pedido": pedido,
            "custo_estimado_usd": t.get("custo_estimado_usd"), "clipes_total": len(segs), "clipes_prontos": feitos,
            "segmentos": [{k: s.get(k) for k in ("indice", "duracao_s", "estado", "erro", "prompt")} for s in segs],
            "video_url": f"/api/estudio/videos/{t['video_final']}" if t.get("video_final") else None,
            "nome_arquivo": t.get("video_final")}

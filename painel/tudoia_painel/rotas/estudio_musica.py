"""Estúdio: geração de música e otimização de prompt musical."""
import time

from fastapi import APIRouter


from .. import servicos as infra
from ..ambiente import Contexto
from ..erros import ErroApi
from ..schemas import GerarMusicaReq, OtimizarPromptReq
from ..estudio_servico import _arbitrar_vram_para_estudio, _executar_comfyui_musica, _otimizar_prompt_musica, _registrar_historico_visual


def criar_router(ctx: Contexto) -> APIRouter:
    router = APIRouter()
    raiz = ctx.raiz
    pastas = ctx.pastas_estudio
    pasta_estudio_musicas = pastas.musicas

    @router.post("/api/estudio/otimizar-prompt-musica")
    def otimizar_prompt_musica_endpoint(corpo: OtimizarPromptReq):
        style_efetivo, foi_otimizado, msg_otimizado = _otimizar_prompt_musica(corpo.prompt, raiz)
        return {
            "ok": True,
            "prompt_original": corpo.prompt,
            "prompt": style_efetivo,
            "prompt_otimizado": foi_otimizado,
            "prompt_msg": msg_otimizado or "Estilo musical mantido (já detalhado em inglês)"
        }

    @router.post("/api/estudio/gerar-musica")
    def gerar_musica(corpo: GerarMusicaReq):
        inicio = time.perf_counter()
        _arbitrar_vram_para_estudio()
        comfy_online = infra.porta_aberta(8188)

        if not comfy_online:
            raise ErroApi(503, "servico_offline", "O serviço ComfyUI (:8188) está offline no host. Inicie-o para carregar o modelo YuE2 na GPU.", extras={"servico_offline": "comfyui", "modelo_solicitado": corpo.modelo, "porta": 8188})

        seed_final = corpo.seed or int(time.time() * 1000) % 1_000_000_000

        # Tradução e enriquecimento musical automático
        style_efetivo, foi_otimizado, msg_otimizado = _otimizar_prompt_musica(corpo.style, raiz)

        res_exec = _executar_comfyui_musica(
            raiz=raiz,
            modelo_id=corpo.modelo,
            style_texto=style_efetivo,
            lyrics_texto=corpo.lyrics,
            seed=seed_final,
            duracao_s=corpo.duracao_segundos,
            modo=corpo.modo,
            pasta_estudio_musicas=pasta_estudio_musicas
        )

        latencia_s = time.perf_counter() - inicio
        latencia_ms = int(latencia_s * 1000)

        if not res_exec.get("ok"):
            _registrar_historico_visual("musica", "comfyui", corpo.modelo, style_efetivo, "audio", latencia_s, "falha", "")
            raise ErroApi(502, "falha_motor", res_exec.get("erro", "Erro desconhecido na geração musical pelo ComfyUI."), extras={"style_original": corpo.style, "style_otimizado": style_efetivo if foi_otimizado else None, "foi_otimizado": foi_otimizado, "msg_otimizacao": msg_otimizado if foi_otimizado else None, "latencia_ms": latencia_ms})

        nome_audio = res_exec["nome_arquivo"]
        audio_url = f"/api/estudio/musicas/{nome_audio}"
        _registrar_historico_visual("musica", "comfyui", corpo.modelo, style_efetivo, "audio", latencia_s, "sucesso", audio_url)

        return {
            "ok": True,
            "motor": "comfyui",
            "modelo": corpo.modelo,
            "style": corpo.style,
            "style_original": corpo.style,
            "style_otimizado": style_efetivo if foi_otimizado else None,
            "foi_otimizado": foi_otimizado,
            "msg_otimizacao": msg_otimizado if foi_otimizado else None,
            "lyrics": corpo.lyrics,
            "modo": corpo.modo,
            "duracao_segundos": corpo.duracao_segundos,
            "seed": seed_final,
            "latencia_ms": latencia_ms,
            "job_id": res_exec.get("prompt_id", f"mus_{int(time.time())}"),
            "status": "completed",
            "audio_url": audio_url,
            "mensagem": "Faixa musical sintetizada com sucesso via YuE 2 no ComfyUI.",
        }

    return router

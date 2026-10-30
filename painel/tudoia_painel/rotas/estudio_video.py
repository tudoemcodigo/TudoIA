"""Estúdio: geração de vídeo, status do job e cancelamento no ComfyUI."""
import shutil
import time

import httpx
from fastapi import APIRouter


from .. import comfyui
from .. import servicos as infra
from ..ambiente import Contexto
from ..erros import ErroApi
from ..schemas import GerarVideoReq, OtimizarPromptReq
from ..estudio_servico import MAX_JOBS_VIDEO, _arbitrar_vram_para_estudio, _executar_comfyui_video, _jobs_video, _otimizar_prompt_video, _registrar_historico_visual, _submeter_comfyui_video
from .. import upstreams


def criar_router(ctx: Contexto) -> APIRouter:
    router = APIRouter()
    raiz = ctx.raiz
    pastas = ctx.pastas_estudio
    pasta_estudio_videos = pastas.videos
    pasta_estudio_uploads = pastas.uploads
    pasta_comfy_output_video = pastas.comfy_video

    @router.get("/api/estudio/status-video/{job_id}")
    def status_video_estudio(job_id: str):
        job = _jobs_video.get(job_id)

        # 1. Verifica se já concluiu no ComfyUI (history)
        try:
            with httpx.Client(timeout=8.0) as cli:
                resp = cli.get(f"{upstreams.COMFYUI}/history/{job_id}")
                if resp.status_code == 200:
                    h_data = resp.json()
                    if job_id in h_data:
                        job_info = h_data[job_id]
                        status_dict = job_info.get("status", {})
                        if status_dict.get("status_str") == "error":
                            if job:
                                job["status"] = "erro"
                            return {
                                "ok": False,
                                "status": "erro",
                                "erro": f"Erro interno no ComfyUI: {status_dict.get('messages', [])}"
                            }

                        outputs = job_info.get("outputs", {})
                        for _nid, nout in outputs.items():
                            midias = nout.get("videos") or nout.get("images") or []
                            for m in midias:
                                fn = m.get("filename", "")
                                if fn.lower().endswith((".mp4", ".webm", ".mkv", ".mov", ".gif")):
                                    params_view = comfyui.parametros_view(m)   # recusa nome/pasta com `..`
                                    caminho_local = pasta_estudio_videos / fn
                                    caminho_comfy = pasta_comfy_output_video / fn

                                    if caminho_comfy.is_file():
                                        try:
                                            shutil.copy2(caminho_comfy, caminho_local)
                                        except Exception:
                                            pass
                                    elif not caminho_local.is_file():
                                        try:
                                            v_resp = cli.get(f"{comfyui.BASE}/view", params=params_view, timeout=60.0)
                                            if v_resp.status_code == 200:
                                                caminho_local.write_bytes(v_resp.content)
                                        except Exception:
                                            pass

                                    dur_s = (time.time() - job["inicio"]) if job else 1.0
                                    video_url = f"/api/estudio/videos/{fn}"
                                    if job:
                                        job["status"] = "concluido"
                                        job["video_url"] = video_url
                                        _registrar_historico_visual(
                                            "video",
                                            "comfyui",
                                            job.get("modelo", "video-minimax-h3"),
                                            job.get("prompt", ""),
                                            job.get("resolucao", "720p"),
                                            dur_s,
                                            "sucesso",
                                            video_url
                                        )

                                    return {
                                        "ok": True,
                                        "status": "concluido",
                                        "nome_arquivo": fn,
                                        "video_url": video_url,
                                        "latencia_ms": int(dur_s * 1000),
                                        "prompt": job.get("prompt", "") if job else "",
                                        "mensagem": "Vídeo cinematográfico renderizado com sucesso!"
                                    }
        except Exception:
            pass

        # 2. Verifica se ainda está em execução na fila do ComfyUI
        try:
            with httpx.Client(timeout=4.0) as cli:
                q_resp = cli.get(f"{upstreams.COMFYUI}/queue")
                if q_resp.status_code == 200:
                    q_data = q_resp.json()
                    for item in q_data.get("queue_running", []):
                        if len(item) > 1 and item[1] == job_id:
                            elapsed = round(time.time() - (job["inicio"] if job else time.time()), 1)
                            return {
                                "ok": True,
                                "status": "executando",
                                "fase": "Renderizando quadros e áudio nativo na GPU...",
                                "tempo_decorrido_s": elapsed
                            }
                    for item in q_data.get("queue_pending", []):
                        if len(item) > 1 and item[1] == job_id:
                            return {
                                "ok": True,
                                "status": "na_fila",
                                "fase": "Aguardando na fila de renderização do ComfyUI..."
                            }
        except Exception:
            pass

        if job and job.get("status") == "executando":
            elapsed = round(time.time() - job["inicio"], 1)
            return {
                "ok": True,
                "status": "executando",
                "fase": "Processando nós no ComfyUI...",
                "tempo_decorrido_s": elapsed
            }

        return {"ok": False, "status": "desconhecido", "erro": "Job não encontrado ou finalizado sem saída de mídia."}

    @router.post("/api/estudio/cancelar")
    def cancelar_estudio():
        try:
            with httpx.Client(timeout=4.0) as cli:
                cli.post(f"{upstreams.COMFYUI}/interrupt")
            return {"ok": True, "mensagem": "Inferência interrompida no ComfyUI."}
        except Exception as e:
            raise ErroApi(502, "falha_motor", f"Falha ao enviar interrupt ao ComfyUI: {type(e).__name__}") from e

    @router.post("/api/estudio/otimizar-prompt-video")
    def otimizar_prompt_video_endpoint(corpo: OtimizarPromptReq):
        prompt_efetivo, foi_otimizado, msg_otimizado = _otimizar_prompt_video(corpo.prompt, raiz, eh_minimax=True)
        return {
            "ok": True,
            "prompt_original": corpo.prompt,
            "prompt": prompt_efetivo,
            "prompt_otimizado": foi_otimizado,
            "prompt_msg": msg_otimizado or "Prompt cinematográfico mantido (já detalhado em inglês)"
        }

    @router.post("/api/estudio/gerar-video")
    def gerar_video(corpo: GerarVideoReq):
        inicio = time.perf_counter()
        _arbitrar_vram_para_estudio()
        comfy_online = infra.porta_aberta(8188)
        nome_modelo_lower = corpo.modelo.lower()
        eh_minimax = "minimax" in nome_modelo_lower or "h3" in nome_modelo_lower

        fluxo_exige_midia = (
            corpo.modo_origem in ("i2v", "v2v")
            or ("i2v" in nome_modelo_lower and "ti2v" not in nome_modelo_lower)
            or "image_to_video" in nome_modelo_lower
            or "image-to-video" in nome_modelo_lower
            or "v2v" in nome_modelo_lower
            or "video_to_video" in nome_modelo_lower
        )

        caminho_referencia_resolvido = None
        if corpo.arquivo_referencia:
            ref_str = corpo.arquivo_referencia.strip()
            if ref_str.startswith("/api/estudio/uploads/"):
                sub_nome = ref_str.replace("/api/estudio/uploads/", "")
                c_cand = (pasta_estudio_uploads / sub_nome).resolve()
                if c_cand.is_file() and c_cand.is_relative_to(pasta_estudio_uploads):
                    caminho_referencia_resolvido = c_cand
            else:
                # Só nome dentro da pasta de uploads (caminho absoluto do disco não é aceito).
                p_cand = (pasta_estudio_uploads / ref_str).resolve()
                if p_cand.is_file() and p_cand.is_relative_to(pasta_estudio_uploads):
                    caminho_referencia_resolvido = p_cand

            if not caminho_referencia_resolvido and fluxo_exige_midia:
                raise ErroApi(404, "nao_encontrado", f"Arquivo de referência não encontrado no host: '{corpo.arquivo_referencia}'. Verifique o caminho ou faça upload novamente.", extras={"modelo_solicitado": corpo.modelo})

        if fluxo_exige_midia and not caminho_referencia_resolvido:
            tipo_esperado = "vídeo" if (corpo.modo_origem == "v2v" or "v2v" in nome_modelo_lower) else "imagem"
            raise ErroApi(422, "validacao", f"O modo ou modelo selecionado ({corpo.modelo}) requer um arquivo de {tipo_esperado} de referência. Faça o upload ou informe o caminho do arquivo.", extras={"modelo_solicitado": corpo.modelo, "midia_requerida": tipo_esperado})

        if not comfy_online:
            raise ErroApi(503, "servico_offline", "O serviço ComfyUI (:8188) está offline no host. Inicie-o para carregar o modelo de vídeo na GPU.", extras={"servico_offline": "comfyui", "modelo_solicitado": corpo.modelo, "porta": 8188})

        seed_final = corpo.seed or int(time.time() * 1000) % 1_000_000_000

        # Tradução e enriquecimento cinematográfico automático
        prompt_efetivo, foi_otimizado, msg_otimizado = _otimizar_prompt_video(corpo.prompt, raiz, eh_minimax=eh_minimax)

        # Modo assíncrono (Job-Based Polling desacoplado)
        if corpo.modo_execucao == "async":
            res_sub = _submeter_comfyui_video(
                raiz=raiz,
                modelo_id=corpo.modelo,
                prompt_texto=prompt_efetivo,
                seed=seed_final,
                resolucao=corpo.resolucao,
                duracao_s=corpo.duracao_segundos,
                fps=corpo.fps,
                caminho_ref=caminho_referencia_resolvido,
                pasta_estudio_videos=pasta_estudio_videos
            )
            if not res_sub.get("ok"):
                raise ErroApi(502, "falha_motor", res_sub.get("erro", "Falha ao iniciar renderização no ComfyUI."), extras={"prompt_original": corpo.prompt})

            pid = res_sub["prompt_id"]
            while len(_jobs_video) >= MAX_JOBS_VIDEO:  # o painel fica aberto por dias: sem teto, o dict só crescia
                _jobs_video.pop(next(iter(_jobs_video)))
            _jobs_video[pid] = {
                "prompt_id": pid,
                "status": "executando",
                "inicio": time.time(),
                "modelo": corpo.modelo,
                "prompt": prompt_efetivo,
                "prompt_original": corpo.prompt,
                "resolucao": corpo.resolucao,
                "duracao_segundos": corpo.duracao_segundos,
                "fps": corpo.fps,
                "modo_origem": corpo.modo_origem
            }
            rotulo_tipo = "Vídeo + Áudio Estéreo (MiniMax H3)" if res_sub.get("eh_minimax") else "Vídeo Wan 2.2 Turbo"
            return {
                "ok": True,
                "job_id": pid,
                "prompt_id": pid,
                "status": "executando",
                "motor": "comfyui",
                "modelo": corpo.modelo,
                "prompt": corpo.prompt,
                "prompt_original": corpo.prompt,
                "prompt_otimizado": prompt_efetivo if foi_otimizado else None,
                "foi_otimizado": foi_otimizado,
                "msg_otimizacao": msg_otimizado if foi_otimizado else None,
                "duracao_segundos": corpo.duracao_segundos,
                "resolucao": corpo.resolucao,
                "fps": corpo.fps,
                "modo_origem": corpo.modo_origem,
                "mensagem": f"{rotulo_tipo} iniciado na GPU!"
            }

        res_exec = _executar_comfyui_video(
            raiz=raiz,
            modelo_id=corpo.modelo,
            prompt_texto=prompt_efetivo,
            seed=seed_final,
            resolucao=corpo.resolucao,
            duracao_s=corpo.duracao_segundos,
            fps=corpo.fps,
            caminho_ref=caminho_referencia_resolvido,
            pasta_estudio_videos=pasta_estudio_videos
        )

        latencia_s = time.perf_counter() - inicio
        latencia_ms = int(latencia_s * 1000)

        if not res_exec.get("ok"):
            _registrar_historico_visual("video", "comfyui", corpo.modelo, prompt_efetivo, corpo.resolucao, latencia_s, "falha", "")
            raise ErroApi(502, "falha_motor", res_exec.get("erro", "Erro desconhecido na renderização de vídeo pelo ComfyUI."), extras={"prompt_original": corpo.prompt, "prompt_otimizado": prompt_efetivo if foi_otimizado else None, "foi_otimizado": foi_otimizado, "msg_otimizacao": msg_otimizado if foi_otimizado else None, "latencia_ms": latencia_ms})

        nome_video = res_exec["nome_arquivo"]
        video_url = f"/api/estudio/videos/{nome_video}"
        _registrar_historico_visual("video", "comfyui", corpo.modelo, prompt_efetivo, corpo.resolucao, latencia_s, "sucesso", video_url)

        rotulo_tipo = "Vídeo + Áudio Estéreo (MiniMax H3)" if eh_minimax else "Vídeo Wan 2.2 Turbo"

        return {
            "ok": True,
            "motor": "comfyui",
            "modelo": corpo.modelo,
            "prompt": corpo.prompt,
            "prompt_original": corpo.prompt,
            "prompt_otimizado": prompt_efetivo if foi_otimizado else None,
            "foi_otimizado": foi_otimizado,
            "msg_otimizacao": msg_otimizado if foi_otimizado else None,
            "modo_origem": corpo.modo_origem,
            "arquivo_referencia": str(caminho_referencia_resolvido) if caminho_referencia_resolvido else None,
            "duracao_segundos": corpo.duracao_segundos,
            "resolucao": corpo.resolucao,
            "fps": corpo.fps,
            "seed": seed_final,
            "latencia_ms": latencia_ms,
            "job_id": res_exec.get("prompt_id", f"vid_{int(time.time())}"),
            "status": "completed",
            "video_url": video_url,
            "audio_incluso": eh_minimax,
            "mensagem": f"{rotulo_tipo} de {corpo.duracao_segundos}s renderizado com sucesso via ComfyUI.",
        }

    return router

"""Serviço do Estúdio: otimização de prompts e execução de grafos no ComfyUI (sem HTTP de entrada)."""
import collections
from dataclasses import dataclass
from datetime import datetime
import re
import shutil
import time
from pathlib import Path
from typing import Any

import httpx


from .envfile import ler_env
from .modelos_service import (
    descarregar_modelo_vram,
    obter_modelos_em_vram,
)
from . import comfyui
from .caminhos import comfyui_dir
from . import upstreams

HISTORICO_VISUAL: collections.deque = collections.deque(maxlen=60)


def _arbitrar_vram_para_estudio() -> None:
    """Arbitrador de VRAM: descarrega modelos ativos do Ollama da GPU antes de inferências visuais pesadas."""
    try:
        modelos = obter_modelos_em_vram()
        for nome in modelos:
            descarregar_modelo_vram(nome)
    except Exception:
        pass


def _registrar_historico_visual(
    tipo: str,
    motor: str,
    modelo: str,
    prompt: str,
    dimensoes: str,
    duracao_s: float,
    status: str,
    imagem_url: str = "",
) -> None:
    try:
        HISTORICO_VISUAL.appendleft({
            "id": f"vis-{int(time.time() * 1000)}",
            "horario": datetime.now().strftime("%H:%M:%S"),
            "tipo": tipo,
            "motor": motor,
            "modelo": modelo,
            "prompt": prompt[:120] + "..." if len(prompt) > 120 else prompt,
            "dimensoes": dimensoes,
            "duracao_s": round(duracao_s, 1),
            "status": status,
            "imagem_url": imagem_url,
        })
    except Exception:
        pass


def _detectar_portugues(texto: str) -> bool:
    if not texto:
        return False
    if re.search(r"[áéíóúãõâêîôûàèìòùçÁÉÍÓÚÃÕÂÊÎÔÛÀÈÌÒÙÇ]", texto):
        return True
    palavras = [w.lower().strip(".,!?;:\"'()[]") for w in texto.split()]
    termos_pt = {
        "de", "do", "da", "dos", "das", "um", "uma", "uns", "umas", "com", "em", "no", "na",
        "nos", "nas", "para", "por", "sobre", "incluir", "colocar", "criar", "video", "vídeo",
        "cena", "filme", "câmera", "camera", "movimento", "luz", "drone", "close", "aberto",
        "carro", "cidade", "rua", "pessoa", "pessoas", "correndo", "andando", "som", "áudio",
        "panorâmica", "lento", "rápido", "cinematográfico", "foto", "imagem", "música", "musica",
        "estilo", "letra", "cancao", "canção", "trilha", "sonora", "bateria", "guitarra", "baixo"
    }
    return bool(set(palavras) & termos_pt)


def _otimizar_prompt_video(prompt_usuario: str, raiz_app: Path, eh_minimax: bool = False) -> tuple[str, bool, str]:
    """
    Traduz e enriquece prompts em português para modelos de vídeo cinematográficos
    (Wan 2.2 e MiniMax H3).
    Retorna (prompt_final, foi_otimizado, mensagem_detalhe).
    """
    if not prompt_usuario or not prompt_usuario.strip():
        return prompt_usuario, False, ""

    texto = prompt_usuario.strip()
    palavras = texto.split()
    tem_acentos = bool(re.search(r"[áéíóúãõâêîôûàèìòùçÁÉÍÓÚÃÕÂÊÎÔÛÀÈÌÒÙÇ]", texto))
    termos_pt = {
        "de", "do", "da", "dos", "das", "um", "uma", "uns", "umas", "com", "em", "no", "na",
        "nos", "nas", "para", "por", "sobre", "incluir", "colocar", "criar", "video", "vídeo",
        "cena", "filme", "câmera", "camera", "movimento", "luz", "drone", "close", "aberto",
        "carro", "cidade", "rua", "pessoa", "pessoas", "correndo", "andando", "som", "áudio",
        "panorâmica", "lento", "rápido", "cinematográfico", "foto", "imagem"
    }
    tem_termos_pt = bool(set(w.lower().strip(".,!?;:\"'()[]") for w in palavras) & termos_pt)

    if len(palavras) >= 30 and not tem_acentos and not tem_termos_pt:
        return texto, False, ""

    env = ler_env(raiz_app / ".env")
    groq_key = env.get("GROQ_API_KEY", "").strip()

    audio_instrucao = (
        " Include a final sentence: 'Audio: [describe ambient room tone, foley sound effects, and musical score]'. "
        if eh_minimax
        else ""
    )
    system_prompt = (
        "You are an expert AI cinematic director and prompt engineer for diffusion video models (Wan 2.2 and MiniMax H3). "
        "Translate any Portuguese/non-English prompt to English and enrich with vivid, photorealistic cinematography: "
        "camera choreographies (e.g. slow cinematic push-in, dynamic tracking shot, fluid 24fps motion, golden hour lighting, lens depth of field)."
        + audio_instrucao +
        " Strictly preserve the core subject. Output ONLY the final English prompt text. Never include explanations, quotes, or markdown."
    )

    if groq_key:
        try:
            with httpx.Client(timeout=6.0) as cli:
                resp = cli.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {groq_key}"},
                    json={
                        "model": "qwen/qwen3.8-27b",
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": texto}
                        ],
                        "max_tokens": 300,
                        "temperature": 0.4
                    }
                )
                if resp.status_code == 200:
                    conteudo = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                    if conteudo and len(conteudo) > 10:
                        return conteudo, True, "Prompt traduzido e enriquecido cinematograficamente para ComfyUI Vídeo (IA Nuvem)"
        except Exception:
            pass

    try:
        with httpx.Client(timeout=8.0) as cli:
            resp = cli.post(
                f"{upstreams.OLLAMA}/api/generate",
                json={
                    "model": "qwen3.5:4b",
                    "prompt": f"{system_prompt}\n\nUser input: {texto}\nEnhanced English video prompt:",
                    "stream": False
                }
            )
            if resp.status_code == 200:
                conteudo = resp.json().get("response", "").strip()
                if conteudo and len(conteudo) > 10:
                    return conteudo, True, "Prompt traduzido e enriquecido cinematograficamente para ComfyUI Vídeo (IA Local Ollama)"
    except Exception:
        pass

    return texto, False, ""


_jobs_video: dict[str, dict[str, Any]] = {}
MAX_JOBS_VIDEO = 200  # os mais antigos saem primeiro (o dict guarda a ordem de inserção)


def _preparar_grafo_video(
    raiz: Path,
    modelo_id: str,
    prompt_texto: str,
    seed: int,
    resolucao: str,
    duracao_s: int,
    fps: int,
    caminho_ref: Path | None,
    pasta_comfy_input: Path
) -> tuple[dict[str, Any], str, bool]:
    nome_modelo_lower = modelo_id.lower()
    eh_minimax = "minimax" in nome_modelo_lower or "h3" in nome_modelo_lower
    eh_i2v = caminho_ref is not None or "i2v" in nome_modelo_lower or "image_to_video" in nome_modelo_lower

    res_dims = {
        "480p": (768, 768) if eh_minimax else (832, 480),
        "720p": (1344, 768) if eh_minimax else (1280, 704),
        "1080p": (1344, 768) if eh_minimax else (1280, 704),
    }
    largura, altura = res_dims.get(resolucao, (1344, 768) if eh_minimax else (1280, 704))

    nome_arquivo_comfy = None
    if caminho_ref and caminho_ref.is_file():
        nome_arquivo_comfy = f"ref_{int(time.time())}_{caminho_ref.name}"
        try:
            shutil.copy2(caminho_ref, pasta_comfy_input / nome_arquivo_comfy)
        except Exception:
            nome_arquivo_comfy = caminho_ref.name

    neg_wan = "色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，最差质量，低质量，JPEG压缩残留，丑陋的，残缺的，多余的手指，画得不好的手部，画得不好的脸部，畸形的，毁容的，形态畸形的肢体，手指融合，静止不动的画面，杂乱的背景，三条腿，背景人很多，倒着走"

    if eh_minimax:
        nome_grafo = "video-minimax-h3"
        qtd_frames = max(5, round(duracao_s * fps))
        grid_length = qtd_frames + (5 - (qtd_frames % 17)) % 17
        grafo: dict[str, Any] = {
            "6": {"class_type": "UNETLoader", "inputs": {"unet_name": "minimax_h3_fl2va_pruned_int8_convrot.safetensors", "weight_dtype": "default"}},
            "121": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["6", 0], "lora_name": "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors", "strength_model": 1.0}},
            "13": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors", "type": "minimax", "device": "default"}},
            "11": {"class_type": "VAELoader", "inputs": {"vae_name": "minimax_h3_video_vae_int8_convrot.safetensors"}},
            "24": {"class_type": "VAELoader", "inputs": {"vae_name": "minimax_h3_audio_vae_fp32.safetensors"}},
            "104": {"class_type": "MiniMaxH3ImageToVideo", "inputs": {"clip": ["13", 0], "vae": ["11", 0], "prompt": prompt_texto, "width": largura, "height": altura, "length": grid_length}},
            "16": {"class_type": "BasicGuider", "inputs": {"model": ["121", 0], "conditioning": ["104", 0]}},
            "17": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}},
            "9": {"class_type": "BasicScheduler", "inputs": {"model": ["121", 0], "scheduler": "simple", "steps": 8, "denoise": 1.0}},
            "15": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
            "14": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["15", 0], "guider": ["16", 0], "sampler": ["17", 0], "sigmas": ["9", 0], "latent_image": ["104", 1]}},
            "10": {"class_type": "VAEDecode", "inputs": {"samples": ["14", 0], "vae": ["11", 0]}},
            "23": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["14", 0], "vae": ["24", 0]}},
            "91": {"class_type": "CreateVideo", "inputs": {"images": ["10", 0], "audio": ["23", 0], "fps": fps, "bit_depth": 8, "color_space": "sRGB", "codec": "none"}},
            "92": {"class_type": "SaveVideo", "inputs": {"video": ["91", 0], "filename_prefix": "video/MiniMax_H3", "format": "auto", "codec": "auto"}},
        }
        if nome_arquivo_comfy:
            grafo["114"] = {"class_type": "LoadImage", "inputs": {"image": nome_arquivo_comfy}}
            grafo["104"]["inputs"]["first_frame"] = ["114", 0]
    elif "5b" in nome_modelo_lower or "ti2v" in nome_modelo_lower:
        nome_grafo = "video-wan5b"
        qtd_frames_5b = max(17, round(duracao_s * fps))
        length_5b = ((qtd_frames_5b - 1) // 4) * 4 + 1
        grafo = {
            "4": {"class_type": "UNETLoader", "inputs": {"unet_name": "wan2.2_ti2v_5B_fp16.safetensors", "weight_dtype": "default"}},
            "10": {"class_type": "CLIPLoader", "inputs": {"clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors", "type": "wan", "device": "default"}},
            "11": {"class_type": "VAELoader", "inputs": {"vae_name": "wan2.2_vae.safetensors"}},
            "12": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["4", 0], "shift": 8.0}},
            "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["10", 0], "text": prompt_texto}},
            "7": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["10", 0], "text": neg_wan}},
            "5": {"class_type": "Wan22ImageToVideoLatent", "inputs": {"vae": ["11", 0], "width": largura, "height": altura, "length": length_5b, "batch_size": 1}},
            "3": {"class_type": "KSampler", "inputs": {"model": ["12", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0], "seed": seed, "steps": 20, "cfg": 5.0, "sampler_name": "uni_pc", "scheduler": "simple", "denoise": 1.0}},
            "8": {"class_type": "VAEDecodeTiled", "inputs": {"samples": ["3", 0], "vae": ["11", 0], "tile_size": 512, "overlap": 64, "temporal_size": 64, "temporal_overlap": 8}},
            "18": {"class_type": "CreateVideo", "inputs": {"images": ["8", 0], "fps": float(fps)}},
            "9": {"class_type": "SaveVideo", "inputs": {"video": ["18", 0], "filename_prefix": "video/video-wan5b", "format": "auto", "format.codec": "auto"}},
        }
        if nome_arquivo_comfy:
            grafo["20"] = {"class_type": "LoadImage", "inputs": {"image": nome_arquivo_comfy}}
            grafo["5"]["inputs"]["start_image"] = ["20", 0]
    elif eh_i2v:
        nome_grafo = "video-wan14b-i2v"
        grafo = {
            "4": {"class_type": "UNETLoader", "inputs": {"unet_name": "wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors", "weight_dtype": "default"}},
            "12": {"class_type": "UNETLoader", "inputs": {"unet_name": "wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors", "weight_dtype": "default"}},
            "13": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["4", 0], "lora_name": "wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors", "strength_model": 1.0}},
            "14": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["12", 0], "lora_name": "wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors", "strength_model": 1.0}},
            "15": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["13", 0], "shift": 5.0}},
            "16": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["14", 0], "shift": 5.0}},
            "10": {"class_type": "CLIPLoader", "inputs": {"clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors", "type": "wan", "device": "default"}},
            "11": {"class_type": "VAELoader", "inputs": {"vae_name": "wan_2.1_vae.safetensors"}},
            "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["10", 0], "text": prompt_texto}},
            "7": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["10", 0], "text": neg_wan}},
            "20": {"class_type": "LoadImage", "inputs": {"image": nome_arquivo_comfy or "exemplo.png"}},
            "5": {"class_type": "WanImageToVideo", "inputs": {"positive": ["6", 0], "negative": ["7", 0], "vae": ["11", 0], "start_image": ["20", 0], "width": 640, "height": 640, "length": 81, "batch_size": 1}},
            "3": {"class_type": "KSamplerAdvanced", "inputs": {"model": ["15", 0], "positive": ["5", 0], "negative": ["5", 1], "latent_image": ["5", 2], "add_noise": "enable", "noise_seed": seed, "steps": 4, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "start_at_step": 0, "end_at_step": 2, "return_with_leftover_noise": "enable"}},
            "17": {"class_type": "KSamplerAdvanced", "inputs": {"model": ["16", 0], "positive": ["5", 0], "negative": ["5", 1], "latent_image": ["3", 0], "add_noise": "disable", "noise_seed": seed, "steps": 4, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "start_at_step": 2, "end_at_step": 4, "return_with_leftover_noise": "disable"}},
            "8": {"class_type": "VAEDecodeTiled", "inputs": {"samples": ["17", 0], "vae": ["11", 0], "tile_size": 512, "overlap": 64, "temporal_size": 64, "temporal_overlap": 8}},
            "18": {"class_type": "CreateVideo", "inputs": {"images": ["8", 0], "fps": 16.0}},
            "9": {"class_type": "SaveVideo", "inputs": {"video": ["18", 0], "filename_prefix": "video/video-wan14b-i2v", "format": "auto", "format.codec": "auto"}},
        }
    else:
        nome_grafo = "video-wan14b-t2v"
        grafo = {
            "4": {"class_type": "UNETLoader", "inputs": {"unet_name": "wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors", "weight_dtype": "default"}},
            "12": {"class_type": "UNETLoader", "inputs": {"unet_name": "wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors", "weight_dtype": "default"}},
            "13": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["4", 0], "lora_name": "wan2.2_t2v_lightx2v_4steps_lora_v1.1_high_noise.safetensors", "strength_model": 1.0}},
            "14": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["12", 0], "lora_name": "wan2.2_t2v_lightx2v_4steps_lora_v1.1_low_noise.safetensors", "strength_model": 1.0}},
            "15": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["13", 0], "shift": 5.0}},
            "16": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["14", 0], "shift": 5.0}},
            "10": {"class_type": "CLIPLoader", "inputs": {"clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors", "type": "wan", "device": "default"}},
            "11": {"class_type": "VAELoader", "inputs": {"vae_name": "wan_2.1_vae.safetensors"}},
            "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["10", 0], "text": prompt_texto}},
            "7": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["10", 0], "text": neg_wan}},
            "5": {"class_type": "EmptyHunyuanLatentVideo", "inputs": {"width": largura, "height": altura, "length": max(17, int(duracao_s * fps)), "batch_size": 1}},
            "3": {"class_type": "KSamplerAdvanced", "inputs": {"model": ["15", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0], "add_noise": "enable", "noise_seed": seed, "steps": 4, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "start_at_step": 0, "end_at_step": 2, "return_with_leftover_noise": "enable"}},
            "17": {"class_type": "KSamplerAdvanced", "inputs": {"model": ["16", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["3", 0], "add_noise": "disable", "noise_seed": seed, "steps": 4, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "start_at_step": 2, "end_at_step": 4, "return_with_leftover_noise": "disable"}},
            "8": {"class_type": "VAEDecodeTiled", "inputs": {"samples": ["17", 0], "vae": ["11", 0], "tile_size": 512, "overlap": 64, "temporal_size": 64, "temporal_overlap": 8}},
            "18": {"class_type": "CreateVideo", "inputs": {"images": ["8", 0], "fps": 16.0}},
            "9": {"class_type": "SaveVideo", "inputs": {"video": ["18", 0], "filename_prefix": "video/video-wan14b-t2v", "format": "auto", "format.codec": "auto"}},
        }

    return grafo, nome_grafo, eh_minimax


def _submeter_comfyui_video(
    raiz: Path,
    modelo_id: str,
    prompt_texto: str,
    seed: int,
    resolucao: str,
    duracao_s: int,
    fps: int,
    caminho_ref: Path | None,
    pasta_estudio_videos: Path
) -> dict[str, Any]:
    pasta_comfy_input = comfyui_dir(raiz) / "input"
    pasta_comfy_input.mkdir(parents=True, exist_ok=True)
    try:
        grafo, nome_fluxo, eh_minimax = _preparar_grafo_video(
            raiz=raiz,
            modelo_id=modelo_id,
            prompt_texto=prompt_texto,
            seed=seed,
            resolucao=resolucao,
            duracao_s=duracao_s,
            fps=fps,
            caminho_ref=caminho_ref,
            pasta_comfy_input=pasta_comfy_input
        )
    except Exception as e:
        return {"ok": False, "erro": f"Erro na preparação do fluxo ComfyUI: {e}"}

    try:
        with httpx.Client(timeout=15.0) as cliente:
            resp = cliente.post(f"{upstreams.COMFYUI}/prompt", json={"prompt": grafo})
            if resp.status_code != 200:
                return {"ok": False, "erro": f"ComfyUI HTTP {resp.status_code}: {resp.text}"}
            d_resp = resp.json()
            if d_resp.get("node_errors"):
                return {"ok": False, "erro": f"Erros nos nós do ComfyUI: {d_resp['node_errors']}"}
            prompt_id = d_resp.get("prompt_id")
            if not prompt_id:
                return {"ok": False, "erro": "ComfyUI não retornou prompt_id."}
            return {"ok": True, "prompt_id": prompt_id, "grafo_usado": nome_fluxo, "eh_minimax": eh_minimax}
    except Exception as e:
        return {"ok": False, "erro": f"Falha na comunicação com ComfyUI (:8188): {e}"}


def _executar_comfyui_video(
    raiz: Path,
    modelo_id: str,
    prompt_texto: str,
    seed: int,
    resolucao: str,
    duracao_s: int,
    fps: int,
    caminho_ref: Path | None,
    pasta_estudio_videos: Path
) -> dict[str, Any]:
    sub = _submeter_comfyui_video(
        raiz=raiz,
        modelo_id=modelo_id,
        prompt_texto=prompt_texto,
        seed=seed,
        resolucao=resolucao,
        duracao_s=duracao_s,
        fps=fps,
        caminho_ref=caminho_ref,
        pasta_estudio_videos=pasta_estudio_videos
    )
    if not sub.get("ok"):
        return sub

    prompt_id = sub["prompt_id"]
    nome_fluxo = sub.get("grafo_usado", "video-minimax-h3.json")
    pasta_comfy_output_video = comfyui_dir(raiz) / "output" / "video"

    inicio_wait = time.time()
    timeout_segundos = 600
    with httpx.Client(timeout=15.0) as cliente:
        while time.time() - inicio_wait < timeout_segundos:
            try:
                h_resp = cliente.get(f"{upstreams.COMFYUI}/history/{prompt_id}")
                if h_resp.status_code == 200:
                    h_data = h_resp.json()
                    if prompt_id in h_data:
                        job_info = h_data[prompt_id]
                        status_dict = job_info.get("status", {})
                        if status_dict.get("status_str") == "error":
                            return {"ok": False, "erro": f"Erro interno no ComfyUI: {status_dict.get('messages', [])}"}

                        outputs = job_info.get("outputs", {})
                        for _nid, nout in outputs.items():
                            lista_midias = nout.get("videos") or nout.get("images") or []
                            for m_item in lista_midias:
                                fn = m_item.get("filename", "")
                                if fn.lower().endswith((".mp4", ".webm", ".mkv", ".mov", ".gif")):
                                    params_view = comfyui.parametros_view(m_item)   # recusa nome/pasta com `..`
                                    nome_local = f"comfy_vid_{int(time.time())}_{fn}"
                                    caminho_local = pasta_estudio_videos / nome_local
                                    caminho_comfy = pasta_comfy_output_video / fn

                                    if caminho_comfy.is_file():
                                        try:
                                            shutil.copy2(caminho_comfy, caminho_local)
                                            return {
                                                "ok": True,
                                                "nome_arquivo": nome_local,
                                                "bytes_len": caminho_local.stat().st_size,
                                                "prompt_id": prompt_id,
                                                "grafo_usado": nome_fluxo
                                            }
                                        except Exception:
                                            pass

                                    v_resp = cliente.get(f"{comfyui.BASE}/view", params=params_view, timeout=60.0)
                                    if v_resp.status_code == 200 and len(v_resp.content) > 1000:
                                        caminho_local.write_bytes(v_resp.content)
                                        return {
                                            "ok": True,
                                            "nome_arquivo": nome_local,
                                            "bytes_len": len(v_resp.content),
                                            "prompt_id": prompt_id,
                                            "grafo_usado": nome_fluxo
                                        }
            except Exception:
                pass
            time.sleep(1)

    return {"ok": False, "erro": f"Tempo limite de {timeout_segundos}s excedido aguardando renderização do vídeo no ComfyUI."}


def _otimizar_prompt_musica(prompt_usuario: str, raiz: Path) -> tuple[str, bool, str]:
    texto = (prompt_usuario or "").strip()
    if not texto:
        return "", False, ""

    eh_portugues = _detectar_portugues(texto)
    eh_curto = len(texto.split()) < 6

    if not eh_portugues and not eh_curto:
        return texto, False, ""

    env = ler_env(raiz / ".env")
    groq_key = env.get("GROQ_API_KEY", "")

    system_prompt = (
        "You are an expert music producer and audio sound designer for YuE2 music generation. "
        "Translate any Portuguese/non-English music prompt to English and enrich it with professional genre tags, "
        "instrumentation (e.g. analog synthesizers, punchy 808 drums, warm electric guitar, reverberant piano), "
        "tempo/BPM, mood and acoustic atmosphere. "
        "Strictly preserve the core musical style and intent. Output ONLY the final English style prompt text. "
        "Never include explanations, quotes, or markdown."
    )

    if groq_key:
        try:
            with httpx.Client(timeout=6.0) as cli:
                resp = cli.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {groq_key}"},
                    json={
                        "model": "qwen/qwen3.8-27b",
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": texto}
                        ],
                        "max_tokens": 200,
                        "temperature": 0.4
                    }
                )
                if resp.status_code == 200:
                    conteudo = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                    if conteudo and len(conteudo) > 10:
                        return conteudo, True, "Estilo musical enriquecido para YuE2 ComfyUI (IA Nuvem)"
        except Exception:
            pass

    try:
        with httpx.Client(timeout=8.0) as cli:
            resp = cli.post(
                f"{upstreams.OLLAMA}/api/generate",
                json={
                    "model": "qwen3.5:4b",
                    "prompt": f"{system_prompt}\n\nUser input: {texto}\nEnhanced English music style prompt:",
                    "stream": False
                }
            )
            if resp.status_code == 200:
                conteudo = resp.json().get("response", "").strip()
                if conteudo and len(conteudo) > 10:
                    return conteudo, True, "Estilo musical enriquecido para YuE2 ComfyUI (IA Local Ollama)"
    except Exception:
        pass

    return texto, False, ""


def _executar_comfyui_musica(
    raiz: Path,
    modelo_id: str,
    style_texto: str,
    lyrics_texto: str,
    seed: int,
    duracao_s: float,
    modo: str,
    pasta_estudio_musicas: Path
) -> dict[str, Any]:
    letra = lyrics_texto or "[instrumental]"
    grafo: dict[str, Any] = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "yue2_3b_int8_convrot.safetensors"}},
        "2": {
            "class_type": "YuE2GenerateABC",
            "inputs": {
                "clip": ["1", 1], "style": style_texto, "lyrics": letra, "seed": seed, "mode": modo,
                "max_abc_tokens": 4096, "temperature": 0.7, "top_p": 0.9, "top_k": 30, "repetition_penalty": 1.005, "penalty_window": 100,
            },
        },
        "3": {
            "class_type": "YuE2GenerateMusic",
            "inputs": {
                "clip": ["1", 1], "style": style_texto, "lyrics": letra, "abc": ["2", 0], "seed": seed, "mode": modo,
                "max_duration": float(duracao_s), "temperature": 1.0, "top_p": 0.95, "top_k": 100, "repetition_penalty": 1.2, "cfg_scale": 1.0,
            },
        },
        "4": {"class_type": "EmptyYuE2LatentAudio", "inputs": {"seconds": ["3", 1], "batch_size": 1}},
        "5": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["3", 0]}},
        "6": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0], "positive": ["3", 0], "negative": ["5", 0], "latent_image": ["4", 0],
                "seed": seed, "steps": 32, "cfg": 1.0, "sampler_name": "dpm_2", "scheduler": "sgm_uniform", "denoise": 1.0,
            },
        },
        "7": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["6", 0], "vae": ["1", 2]}},
        "8": {"class_type": "SaveAudio", "inputs": {"audio": ["7", 0], "filename_prefix": "audio/YuE2_TudoIA"}},
    }

    try:
        with httpx.Client(timeout=15.0) as cliente:
            resp = cliente.post(f"{upstreams.COMFYUI}/prompt", json={"prompt": grafo})
            if resp.status_code != 200:
                return {"ok": False, "erro": f"ComfyUI HTTP {resp.status_code}: {resp.text}"}
            d_resp = resp.json()
            if d_resp.get("node_errors"):
                return {"ok": False, "erro": f"Erros nos nós do ComfyUI: {d_resp['node_errors']}"}
            prompt_id = d_resp.get("prompt_id")
            if not prompt_id:
                return {"ok": False, "erro": "ComfyUI não retornou prompt_id."}
    except Exception as e:
        return {"ok": False, "erro": f"Falha na comunicação com ComfyUI (:8188): {e}"}

    inicio_wait = time.time()
    timeout_segundos = 300
    with httpx.Client(timeout=15.0) as cliente:
        while time.time() - inicio_wait < timeout_segundos:
            try:
                h_resp = cliente.get(f"{upstreams.COMFYUI}/history/{prompt_id}")
                if h_resp.status_code == 200:
                    h_data = h_resp.json()
                    if prompt_id in h_data:
                        job_info = h_data[prompt_id]
                        status_dict = job_info.get("status", {})
                        if status_dict.get("status_str") == "error":
                            return {"ok": False, "erro": f"Erro interno no ComfyUI: {status_dict.get('messages', [])}"}

                        outputs = job_info.get("outputs", {})
                        for _nid, nout in outputs.items():
                            lista_audios = nout.get("audio") or nout.get("audios") or []
                            for a_item in lista_audios:
                                fn = a_item.get("filename", "")
                                if fn.lower().endswith((".flac", ".mp3", ".wav", ".ogg")):
                                    params_view = comfyui.parametros_view(a_item)   # recusa nome/pasta com `..`
                                    sub = params_view["subfolder"]
                                    nome_local = f"comfy_audio_{int(time.time())}_{fn}"
                                    caminho_local = pasta_estudio_musicas / nome_local
                                    
                                    # 1. Tenta copiar direto do disco local do ComfyUI se disponível
                                    pasta_comfy_out = comfyui_dir(raiz) / "output"
                                    candidatos = [
                                        pasta_comfy_out / "audio" / fn,
                                        pasta_comfy_out / sub / fn if sub else None,
                                        pasta_comfy_out / fn
                                    ]
                                    copiado_disco = False
                                    for c in candidatos:
                                        if c and c.is_file() and c.stat().st_size > 500:
                                            try:
                                                shutil.copy2(c, caminho_local)
                                                copiado_disco = True
                                                return {
                                                    "ok": True,
                                                    "nome_arquivo": nome_local,
                                                    "bytes_len": c.stat().st_size,
                                                    "prompt_id": prompt_id,
                                                    "grafo_usado": "musica-yue2"
                                                }
                                            except Exception:
                                                pass

                                    # 2. Fallback via HTTP se não encontrou no caminho padrão local
                                    if not copiado_disco:
                                        a_resp = cliente.get(f"{comfyui.BASE}/view", params=params_view, timeout=60.0)
                                        if a_resp.status_code == 200 and len(a_resp.content) > 500:
                                            caminho_local.write_bytes(a_resp.content)
                                            return {
                                                "ok": True,
                                                "nome_arquivo": nome_local,
                                                "bytes_len": len(a_resp.content),
                                                "prompt_id": prompt_id,
                                                "grafo_usado": "musica-yue2"
                                            }
            except Exception:
                pass
            time.sleep(1)

    return {"ok": False, "erro": f"Tempo limite de {timeout_segundos}s excedido aguardando composição musical no ComfyUI."}


@dataclass(frozen=True)
class PastasEstudio:
    """Pastas de saída do Estúdio e de saída do ComfyUI, derivadas da raiz do projeto."""
    imagens: Path
    videos: Path
    musicas: Path
    uploads: Path
    comfy_video: Path
    comfy_audio: Path

    @classmethod
    def de(cls, raiz: Path) -> "PastasEstudio":
        base = raiz / "dados" / "estudio"
        return cls(base / "imagens", base / "videos", base / "musicas", base / "uploads",
                   comfyui_dir(raiz) / "output" / "video", comfyui_dir(raiz) / "output" / "audio")

    def garantir(self) -> None:
        for p in (self.imagens, self.videos, self.musicas, self.uploads):
            p.mkdir(parents=True, exist_ok=True)


def arquivo_em(pastas, nome_arquivo: str) -> Path | None:
    """Primeiro arquivo `nome_arquivo` que exista DENTRO de uma das pastas; None se não houver.
    Fecha travessia (`..`, `%2F`) e caminho absoluto (`C:/...`), que o `/` do pathlib aceitaria."""
    for pasta in pastas:
        base = pasta.resolve()
        alvo = (base / nome_arquivo).resolve()
        if alvo.is_relative_to(base) and alvo.is_file():
            return alvo
    return None


def executar_comfyui_imagem(raiz: Path, pasta_estudio_imagens: Path, modelo_id: str, prompt_pos: str, prompt_neg: str, seed: int, largura: int, altura: int, steps: int) -> dict[str, Any]:
    nome_ckp = modelo_id.replace("local:", "") if modelo_id.startswith("local:") else modelo_id
    nl = nome_ckp.lower()
    neg = prompt_neg or "blurry, lowres, deformed, bad anatomy, extra fingers, watermark, text, signature, jpeg artifacts"

    if "flux" in nl and modelo_id.startswith("local:"):
        grafo: dict[str, Any] = {
            "3": {"class_type": "KSampler", "inputs": {"seed": seed, "steps": steps if steps > 0 else 4, "cfg": 1, "sampler_name": "euler", "scheduler": "simple", "denoise": 1, "model": ["4", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0]}},
            "4": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": nome_ckp}},
            "5": {"class_type": "EmptySD3LatentImage", "inputs": {"width": largura, "height": altura, "batch_size": 1}},
            "6": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt_pos, "clip": ["10", 0]}},
            "7": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["6", 0]}},
            "10": {"class_type": "DualCLIPLoader", "inputs": {"clip_name1": "t5xxl_fp8_e4m3fn.safetensors", "clip_name2": "clip_l.safetensors", "type": "flux"}},
            "11": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
            "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["11", 0]}},
            "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "flux-schnell", "images": ["8", 0]}},
        }
    elif "z_image" in nl or "zimage" in nl:
        unet = nome_ckp if modelo_id.startswith("local:") else "z_image_turbo_int8_convrot.safetensors"
        grafo = {
            "3": {"class_type": "KSampler", "inputs": {"seed": seed, "steps": steps if steps > 0 else 8, "cfg": 1, "sampler_name": "res_multistep", "scheduler": "simple", "denoise": 1, "model": ["12", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0]}},
            "4": {"class_type": "UNETLoader", "inputs": {"unet_name": unet, "weight_dtype": "default"}},
            "5": {"class_type": "EmptySD3LatentImage", "inputs": {"width": largura, "height": altura, "batch_size": 1}},
            "6": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt_pos, "clip": ["10", 0]}},
            "7": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["6", 0]}},
            "10": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_3_4b_fp8_mixed.safetensors", "type": "lumina2", "device": "default"}},
            "11": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
            "12": {"class_type": "ModelSamplingAuraFlow", "inputs": {"shift": 3, "model": ["4", 0]}},
            "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["11", 0]}},
            "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "zimage-turbo", "images": ["8", 0]}},
        }
    else:
        ckpt = nome_ckp if modelo_id.startswith("local:") else "Juggernaut-XL_v9_RunDiffusionPhoto_v2.safetensors"
        grafo = {
            "3": {"class_type": "KSampler", "inputs": {"seed": seed, "steps": steps if steps > 0 else 30, "cfg": 4.5, "sampler_name": "dpmpp_2m_sde", "scheduler": "karras", "denoise": 1, "model": ["4", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0]}},
            "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt}},
            "5": {"class_type": "EmptyLatentImage", "inputs": {"width": largura, "height": altura, "batch_size": 1}},
            "6": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt_pos, "clip": ["4", 1]}},
            "7": {"class_type": "CLIPTextEncode", "inputs": {"text": neg, "clip": ["4", 1]}},
            "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
            "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "sdxl-foto", "images": ["8", 0]}},
        }

    try:
        with httpx.Client(timeout=15.0) as cliente:
            resp = cliente.post(f"{upstreams.COMFYUI}/prompt", json={"prompt": grafo})
            if resp.status_code != 200:
                return {"ok": False, "erro": f"ComfyUI HTTP {resp.status_code}: {resp.text}"}
            d_resp = resp.json()
            if d_resp.get("node_errors"):
                return {"ok": False, "erro": f"Erros nos nós do ComfyUI: {d_resp['node_errors']}"}
            prompt_id = d_resp.get("prompt_id")
            if not prompt_id:
                return {"ok": False, "erro": "ComfyUI não retornou prompt_id."}
    except Exception as e:
        return {"ok": False, "erro": f"Falha na comunicação com ComfyUI (:8188): {e}"}

    inicio_wait = time.time()
    with httpx.Client(timeout=15.0) as cliente:
        while time.time() - inicio_wait < 180:
            try:
                h_resp = cliente.get(f"{upstreams.COMFYUI}/history/{prompt_id}")
                if h_resp.status_code == 200:
                    h_data = h_resp.json()
                    if prompt_id in h_data:
                        outputs = h_data[prompt_id].get("outputs", {})
                        for _nid, nout in outputs.items():
                            if "images" in nout and len(nout["images"]) > 0:
                                img_info = nout["images"][0]
                                params_view = comfyui.parametros_view(img_info)   # recusa nome/pasta com `..`
                                fn = params_view["filename"]
                                v_resp = cliente.get(f"{comfyui.BASE}/view", params=params_view, timeout=30.0)
                                if v_resp.status_code == 200 and len(v_resp.content) > 1000:
                                    nome_local = f"comfy_{int(time.time())}_{fn}"
                                    caminho_local = pasta_estudio_imagens / nome_local
                                    caminho_local.write_bytes(v_resp.content)
                                    return {
                                        "ok": True,
                                        "nome_arquivo": nome_local,
                                        "bytes_len": len(v_resp.content),
                                        "prompt_id": prompt_id
                                    }
            except Exception:
                pass
            time.sleep(1)

    return {"ok": False, "erro": "Tempo limite de 90s excedido aguardando renderização do ComfyUI."}


def dimensoes_png(dados: bytes) -> tuple[int, int]:
    if len(dados) >= 24 and dados.startswith(b"\x89PNG\r\n\x1a\n"):
        import struct
        w, h = struct.unpack(">II", dados[16:24])
        return w, h
    return 1024, 1024


def otimizar_prompt_visual(prompt_usuario: str, raiz_app: Path) -> tuple[str, bool, str]:
    """
    Traduz e enriquece prompts em português ou não-ingleses para prompts fotorealistas
    em inglês de alta fidelidade para modelos de difusão SDXL/FLUX.
    Retorna (prompt_final, foi_otimizado, mensagem_detalhe).
    """
    if not prompt_usuario or not prompt_usuario.strip():
        return prompt_usuario, False, ""

    texto = prompt_usuario.strip()
    palavras = texto.split()
    tem_acentos = bool(re.search(r"[áéíóúãõâêîôûàèìòùçÁÉÍÓÚÃÕÂÊÎÔÛÀÈÌÒÙÇ]", texto))
    termos_pt = {
        "de", "do", "da", "dos", "das", "um", "uma", "uns", "umas", "com", "em", "no", "na",
        "nos", "nas", "para", "por", "sobre", "incluir", "colocar", "criar", "imagem", "foto",
        "prédio", "predio", "museu", "são", "sao", "paulo", "cidade", "rua", "avenida",
        "carro", "ponte", "árvore", "arvore", "rio", "lago", "sol", "noite", "céu", "ceu",
        "pessoas", "realista", "desenhar", "adicionar", "remover", "trocar", "masp"
    }
    tem_termos_pt = bool(set(w.lower().strip(".,!?;:\"'()[]") for w in palavras) & termos_pt)

    # Se for estritamente inglês longo (> 30 palavras) sem acentos ou termos pt, já é detalhado
    if len(palavras) >= 30 and not tem_acentos and not tem_termos_pt:
        return texto, False, ""

    env = ler_env(raiz_app / ".env")
    groq_key = env.get("GROQ_API_KEY", "").strip()

    system_prompt = (
        "You are an expert AI image prompt engineer and visual translator for SDXL and FLUX diffusion models. "
        "Translate any Portuguese/non-English prompt to English and enrich with vivid, photorealistic architectural, "
        "materials, lighting (e.g. golden hour or natural cinematic light), and camera lens/realism details. "
        "Strictly preserve the intended subject. "
        "Output ONLY the final English prompt text. Never include explanations, reasoning, quotes, or markdown."
    )

    # 1. Tentativa via Groq (modelo qwen/qwen3.8-27b ~0.4s)
    if groq_key:
        try:
            with httpx.Client(timeout=6.0) as cli:
                resp = cli.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {groq_key}"},
                    json={
                        "model": "qwen/qwen3.8-27b",
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": texto}
                        ],
                        "max_tokens": 250,
                        "temperature": 0.4
                    }
                )
                if resp.status_code == 200:
                    d = resp.json()
                    conteudo = d.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                    if conteudo and len(conteudo) > 10:
                        return conteudo, True, "Prompt traduzido e enriquecido automaticamente para SDXL/FLUX (IA Nuvem)"
        except Exception:
            pass

    # 2. Tentativa via Ollama local (:11434) se disponível
    try:
        with httpx.Client(timeout=8.0) as cli:
            resp = cli.post(
                f"{upstreams.OLLAMA}/api/generate",
                json={
                    "model": "qwen3.5:4b",
                    "prompt": f"{system_prompt}\n\nUser input: {texto}\nEnhanced English prompt:",
                    "stream": False
                }
            )
            if resp.status_code == 200:
                conteudo = resp.json().get("response", "").strip()
                if conteudo and len(conteudo) > 10:
                    return conteudo, True, "Prompt traduzido e enriquecido automaticamente para SDXL/FLUX (IA Local Ollama)"
    except Exception:
        pass

    # Fallback gracioso: mantém o texto original
    return texto, False, ""

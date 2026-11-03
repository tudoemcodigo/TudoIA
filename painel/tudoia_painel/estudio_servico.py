"""Serviço do Estúdio: otimização de prompts e execução de grafos no ComfyUI (sem HTTP de entrada)."""
import collections
from dataclasses import dataclass
from datetime import datetime
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx


from .envfile import ler_env
from .modelos_service import (
    descarregar_modelo_vram,
    obter_modelos_em_vram,
)
from . import caminhos
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


def _detectar_modelo_ollama_llm(upstream: str) -> str:
    """Detecta dinamicamente o melhor modelo LLM disponível no Ollama local."""
    try:
        with httpx.Client(timeout=2.5) as cli:
            resp = cli.get(f"{upstream}/api/tags")
            if resp.status_code == 200:
                nomes = [m.get("name", "") for m in resp.json().get("models", [])]
                for prefixo in ("qwen3.5", "qwen3.8", "qwen2.5", "deepseek-r1"):
                    for n in nomes:
                        if prefixo in n.lower():
                            return n
                for n in nomes:
                    n_low = n.lower()
                    if not any(ign in n_low for ign in ("embed", "bert", "bge")):
                        return n
    except Exception:
        pass
    return "qwen3.5:latest"


def _chamar_ollama_prompt(system_prompt: str, user_text: str, label_esperado: str) -> str:
    modelo = _detectar_modelo_ollama_llm(upstreams.OLLAMA)
    try:
        with httpx.Client(timeout=30.0) as cli:
            resp = cli.post(
                f"{upstreams.OLLAMA}/api/chat",
                json={
                    "model": modelo,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"Optimize the following: {user_text}\n{label_esperado}"},
                    ],
                    "options": {"num_predict": 180, "temperature": 0.4},
                    "think": False,
                    "stream": False,
                },
            )
            if resp.status_code == 200:
                conteudo = resp.json().get("message", {}).get("content", "").strip()
                if conteudo.startswith(("```", '"', "'")) and conteudo.endswith(("```", '"', "'")):
                    conteudo = conteudo.strip("`'\" \n")
                if len(conteudo) > 10:
                    return conteudo
    except Exception:
        pass
    return ""


def _extrair_frame_chave_video(caminho_video: Path, destino_png: Path, raiz: Path) -> bool:
    """Extrai o primeiro quadro de um vídeo (V2V) para usar como start_image no Wan 2.2."""
    py_comfy = caminhos.comfyui_portable(raiz) / "python_embeded" / "python.exe"
    if py_comfy.is_file():
        cmd = [
            str(py_comfy),
            "-c",
            "import sys, av; "
            "c = av.open(sys.argv[1]); "
            "f = next(c.decode(video=0)); "
            "f.to_image().save(sys.argv[2]);",
            str(caminho_video),
            str(destino_png),
        ]
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=12)
            if r.returncode == 0 and destino_png.is_file() and destino_png.stat().st_size > 0:
                return True
        except Exception:
            pass
    return False


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
        "1. Camera movement at the very beginning (e.g., 'Cinematic slow push-in', 'Dynamic aerial tracking shot', 'Smooth fluid 24fps pan'). "
        "2. Continuous temporal action of the main subject. "
        "3. Atmospheric environmental motion (wind, particles, moving background reflections, light flares). "
        "4. Cinematic photographic grading: 24fps motion blur, anamorphic lens, 35mm grain, natural cinematic lighting."
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

    conteudo = _chamar_ollama_prompt(system_prompt, texto, "Enhanced English video prompt:")
    if conteudo:
        return conteudo, True, "Prompt traduzido e enriquecido cinematograficamente para ComfyUI Vídeo (IA Local Ollama)"

    return texto, False, ""


_jobs_video: dict[str, dict[str, Any]] = {}
MAX_JOBS_VIDEO = 200  # os mais antigos saem primeiro (o dict guarda a ordem de inserção)


@dataclass(frozen=True)
class PerfilVideoLocal:
    """Limites de um modelo de vídeo local: fps em que o grafo grava e o maior clipe de uma chamada."""
    chave: str
    fps: int
    max_segmento_s: int


# Wan 2.2: treinado em 5 s (121 quadros a 24 fps no 5B, 81 a 16 fps no 14B); passar disso degrada a coerência.
# MiniMax H3: o nó documenta treino em 124–362 quadros a 24 fps; 10 s é o que cabe com folga em 8 GB de VRAM.
# LTX-2.3: gera até 20 s numa chamada (relatos de 8 GB com Q4 GGUF). Vídeo mais longo: video_longo.py emenda clipes.
PERFIS_VIDEO_LOCAL = {
    "minimax": PerfilVideoLocal("minimax", 24, 10),
    "wan5b": PerfilVideoLocal("wan5b", 24, 5),
    "wan14b": PerfilVideoLocal("wan14b", 16, 5),
    "ltx23": PerfilVideoLocal("ltx23", 24, 20),
}


def perfil_video_local(modelo_id: str) -> PerfilVideoLocal:
    nl = modelo_id.lower()
    if "ltx" in nl:
        return PERFIS_VIDEO_LOCAL["ltx23"]
    if "minimax" in nl or "h3" in nl:
        return PERFIS_VIDEO_LOCAL["minimax"]
    if "5b" in nl or "ti2v" in nl:
        return PERFIS_VIDEO_LOCAL["wan5b"]
    return PERFIS_VIDEO_LOCAL["wan14b"]


def max_segmento_video_local(perfil: PerfilVideoLocal, resolucao: str) -> int:
    """Maior clipe de uma chamada. LTX em 720p tem 3,4× mais pixels por quadro: 10 s para caber nos 8 GB."""
    if perfil.chave == "ltx23" and resolucao != "480p":
        return 10
    return perfil.max_segmento_s


def quadros_video(perfil: PerfilVideoLocal, duracao_s: float) -> int:
    """Quadros que o grafo pede para `duracao_s`, na grade de cada modelo e sem passar do clipe máximo."""
    alvo = min(max(duracao_s, 1), perfil.max_segmento_s) * perfil.fps
    if perfil.chave == "minimax":   # grade 17k+5, arredondada para cima (124 ≈ 5,2 s)
        q = max(5, round(alvo))
        return q + (5 - q % 17) % 17
    passo = 8 if perfil.chave == "ltx23" else 4   # LTX: 8n+1; Wan: 4n+1
    q = round(alvo) + 1
    return max(passo + 1, ((q - 1) // passo) * passo + 1)


LTX23_UNET = "ltx-2.3-22b-distilled-1.1-Q4_K_S.gguf"
LTX23_TEXTO = ("gemma-3-12b-it-qat-UD-Q4_K_XL.gguf", "ltx-2.3-22b-distilled_embeddings_connectors.safetensors")
LTX23_VAE_VIDEO = "ltx-2.3-22b-distilled_video_vae.safetensors"
LTX23_VAE_AUDIO = "ltx-2.3-22b-distilled_audio_vae.safetensors"
# Sigmas de 8 passos do distilled (template oficial video_ltx2_3_t2v do ComfyUI, 1º estágio).
LTX23_SIGMAS = "1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0"
LTX23_NEGATIVO = "blurry, low quality, still frame, frames, watermark, overlay, titles, has blurbox, has subtitles"


def _grafo_ltx23(prompt_texto: str, seed: int, largura: int, altura: int, quadros: int, fps: int,
                 imagem_inicial: str | None) -> dict[str, Any]:
    """LTX-2.3 distilled GGUF num estágio (sem upscaler, que não cabe em 8 GB junto). Vídeo e áudio juntos.
    Base: fluxo do unsloth/LTX-2.3-GGUF (custom nodes ComfyUI-GGUF e ComfyUI-KJNodes)."""
    grafo: dict[str, Any] = {
        "1": {"class_type": "VAELoaderKJ", "inputs": {"vae_name": LTX23_VAE_AUDIO, "device": "main_device", "weight_dtype": "bf16"}},
        "2": {"class_type": "VAELoaderKJ", "inputs": {"vae_name": LTX23_VAE_VIDEO, "device": "main_device", "weight_dtype": "bf16"}},
        "3": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": LTX23_UNET}},
        "4": {"class_type": "DualCLIPLoaderGGUF", "inputs": {"clip_name1": LTX23_TEXTO[0], "clip_name2": LTX23_TEXTO[1], "type": "ltxv"}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["4", 0], "text": prompt_texto}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["4", 0], "text": LTX23_NEGATIVO}},
        "7": {"class_type": "LTXVConditioning", "inputs": {"positive": ["5", 0], "negative": ["6", 0], "frame_rate": float(fps)}},
        "8": {"class_type": "EmptyLTXVLatentVideo", "inputs": {"width": largura, "height": altura, "length": quadros, "batch_size": 1}},
        "9": {"class_type": "LTXVEmptyLatentAudio", "inputs": {"frames_number": quadros, "frame_rate": fps, "batch_size": 1, "audio_vae": ["1", 0]}},
        "10": {"class_type": "LTXVConcatAVLatent", "inputs": {"video_latent": ["8", 0], "audio_latent": ["9", 0]}},
        "11": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "12": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "13": {"class_type": "ManualSigmas", "inputs": {"sigmas": LTX23_SIGMAS}},
        "14": {"class_type": "CFGGuider", "inputs": {"model": ["3", 0], "positive": ["7", 0], "negative": ["7", 1], "cfg": 1.0}},
        "15": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["11", 0], "guider": ["14", 0], "sampler": ["12", 0], "sigmas": ["13", 0], "latent_image": ["10", 0]}},
        "16": {"class_type": "LTXVSeparateAVLatent", "inputs": {"av_latent": ["15", 0]}},
        "17": {"class_type": "VAEDecodeTiled", "inputs": {"samples": ["16", 0], "vae": ["2", 0], "tile_size": 512, "overlap": 64, "temporal_size": 128, "temporal_overlap": 16}},
        "18": {"class_type": "LTXVAudioVAEDecode", "inputs": {"samples": ["16", 1], "audio_vae": ["1", 0]}},
        "19": {"class_type": "CreateVideo", "inputs": {"images": ["17", 0], "audio": ["18", 0], "fps": float(fps)}},
        "20": {"class_type": "SaveVideo", "inputs": {"video": ["19", 0], "filename_prefix": "video/video-ltx23", "format": "auto", "codec": "auto"}},
    }
    if imagem_inicial:
        grafo["30"] = {"class_type": "LoadImage", "inputs": {"image": imagem_inicial}}
        grafo["31"] = {"class_type": "ImageScale", "inputs": {"image": ["30", 0], "upscale_method": "lanczos", "width": largura, "height": altura, "crop": "center"}}
        grafo["32"] = {"class_type": "LTXVPreprocess", "inputs": {"image": ["31", 0], "img_compression": 18}}
        grafo["33"] = {"class_type": "LTXVImgToVideoInplace", "inputs": {"vae": ["2", 0], "image": ["32", 0], "latent": ["8", 0], "strength": 1.0, "bypass": False}}
        grafo["10"]["inputs"]["video_latent"] = ["33", 0]
    return grafo


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
    perfil = perfil_video_local(modelo_id)
    quadros = quadros_video(perfil, min(duracao_s, max_segmento_video_local(perfil, resolucao)))
    eh_minimax = perfil.chave == "minimax"
    eh_i2v = caminho_ref is not None or "i2v" in nome_modelo_lower or "image_to_video" in nome_modelo_lower

    res_dims = {
        "480p": (768, 768) if eh_minimax else (832, 480),
        "720p": (1344, 768) if eh_minimax else (1280, 704),
        "1080p": (1344, 768) if eh_minimax else (1280, 704),
    }
    largura, altura = res_dims.get(resolucao, (1344, 768) if eh_minimax else (1280, 704))

    nome_arquivo_comfy = None
    if caminho_ref and caminho_ref.is_file():
        ext_ref = caminho_ref.suffix.lower()
        if ext_ref in (".mp4", ".webm", ".mov", ".mkv", ".avi"):
            # Modo V2V: extrai o frame-chave inicial para guiar a transformação no Wan 2.2
            nome_frame = f"v2v_frame_{int(time.time())}_{caminho_ref.stem}.png"
            caminho_frame = pasta_comfy_input / nome_frame
            if _extrair_frame_chave_video(caminho_ref, caminho_frame, raiz):
                nome_arquivo_comfy = nome_frame
            else:
                nome_arquivo_comfy = f"ref_{int(time.time())}_{caminho_ref.name}"
                try:
                    shutil.copy2(caminho_ref, pasta_comfy_input / nome_arquivo_comfy)
                except Exception:
                    nome_arquivo_comfy = caminho_ref.name
        else:
            nome_arquivo_comfy = f"ref_{int(time.time())}_{caminho_ref.name}"
            try:
                shutil.copy2(caminho_ref, pasta_comfy_input / nome_arquivo_comfy)
            except Exception:
                nome_arquivo_comfy = caminho_ref.name

    neg_wan = "色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，最差质量，低质量，JPEG压缩残留，丑陋的，残缺的，多余的手指，画得不好的手部，画得不好的脸部，畸形的，毁容的，形态畸形的肢体，手指融合，静止不动的画面，杂乱的背景，三条腿，背景人很多，倒着走"

    if perfil.chave == "ltx23":
        nome_grafo = "video-ltx23"
        grafo = _grafo_ltx23(prompt_texto, seed, largura, altura, quadros, perfil.fps, nome_arquivo_comfy)
    elif eh_minimax:
        nome_grafo = "video-minimax-h3"
        grafo: dict[str, Any] = {
            "6": {"class_type": "UNETLoader", "inputs": {"unet_name": "minimax_h3_fl2va_pruned_int8_convrot.safetensors", "weight_dtype": "default"}},
            "121": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["6", 0], "lora_name": "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors", "strength_model": 1.0}},
            "13": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors", "type": "minimax", "device": "default"}},
            "11": {"class_type": "VAELoader", "inputs": {"vae_name": "minimax_h3_video_vae_int8_convrot.safetensors"}},
            "24": {"class_type": "VAELoader", "inputs": {"vae_name": "minimax_h3_audio_vae_fp32.safetensors"}},
            "104": {"class_type": "MiniMaxH3ImageToVideo", "inputs": {"clip": ["13", 0], "vae": ["11", 0], "prompt": prompt_texto, "width": largura, "height": altura, "length": quadros}},
            "16": {"class_type": "BasicGuider", "inputs": {"model": ["121", 0], "conditioning": ["104", 0]}},
            "17": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}},
            "9": {"class_type": "BasicScheduler", "inputs": {"model": ["121", 0], "scheduler": "simple", "steps": 8, "denoise": 1.0}},
            "15": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
            "14": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["15", 0], "guider": ["16", 0], "sampler": ["17", 0], "sigmas": ["9", 0], "latent_image": ["104", 1]}},
            "10": {"class_type": "VAEDecode", "inputs": {"samples": ["14", 0], "vae": ["11", 0]}},
            "23": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["14", 0], "vae": ["24", 0]}},
            "91": {"class_type": "CreateVideo", "inputs": {"images": ["10", 0], "audio": ["23", 0], "fps": perfil.fps, "bit_depth": 8, "color_space": "sRGB", "codec": "none"}},
            "92": {"class_type": "SaveVideo", "inputs": {"video": ["91", 0], "filename_prefix": "video/MiniMax_H3", "format": "auto", "codec": "auto"}},
        }
        if nome_arquivo_comfy:
            grafo["114"] = {"class_type": "LoadImage", "inputs": {"image": nome_arquivo_comfy}}
            grafo["104"]["inputs"]["first_frame"] = ["114", 0]
    elif "5b" in nome_modelo_lower or "ti2v" in nome_modelo_lower:
        nome_grafo = "video-wan5b"
        grafo = {
            "4": {"class_type": "UNETLoader", "inputs": {"unet_name": "wan2.2_ti2v_5B_fp16.safetensors", "weight_dtype": "default"}},
            "10": {"class_type": "CLIPLoader", "inputs": {"clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors", "type": "wan", "device": "default"}},
            "11": {"class_type": "VAELoader", "inputs": {"vae_name": "wan2.2_vae.safetensors"}},
            "12": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["4", 0], "shift": 8.0}},
            "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["10", 0], "text": prompt_texto}},
            "7": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["10", 0], "text": neg_wan}},
            "5": {"class_type": "Wan22ImageToVideoLatent", "inputs": {"vae": ["11", 0], "width": largura, "height": altura, "length": quadros, "batch_size": 1}},
            "3": {"class_type": "KSampler", "inputs": {"model": ["12", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0], "seed": seed, "steps": 20, "cfg": 5.0, "sampler_name": "uni_pc", "scheduler": "simple", "denoise": 1.0}},
            "8": {"class_type": "VAEDecodeTiled", "inputs": {"samples": ["3", 0], "vae": ["11", 0], "tile_size": 512, "overlap": 64, "temporal_size": 64, "temporal_overlap": 8}},
            "18": {"class_type": "CreateVideo", "inputs": {"images": ["8", 0], "fps": float(perfil.fps)}},
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
            "5": {"class_type": "WanImageToVideo", "inputs": {"positive": ["6", 0], "negative": ["7", 0], "vae": ["11", 0], "start_image": ["20", 0], "width": 640, "height": 640, "length": quadros, "batch_size": 1}},
            "3": {"class_type": "KSamplerAdvanced", "inputs": {"model": ["15", 0], "positive": ["5", 0], "negative": ["5", 1], "latent_image": ["5", 2], "add_noise": "enable", "noise_seed": seed, "steps": 4, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "start_at_step": 0, "end_at_step": 2, "return_with_leftover_noise": "enable"}},
            "17": {"class_type": "KSamplerAdvanced", "inputs": {"model": ["16", 0], "positive": ["5", 0], "negative": ["5", 1], "latent_image": ["3", 0], "add_noise": "disable", "noise_seed": seed, "steps": 4, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "start_at_step": 2, "end_at_step": 4, "return_with_leftover_noise": "disable"}},
            "8": {"class_type": "VAEDecodeTiled", "inputs": {"samples": ["17", 0], "vae": ["11", 0], "tile_size": 512, "overlap": 64, "temporal_size": 64, "temporal_overlap": 8}},
            "18": {"class_type": "CreateVideo", "inputs": {"images": ["8", 0], "fps": float(perfil.fps)}},
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
            "5": {"class_type": "EmptyHunyuanLatentVideo", "inputs": {"width": largura, "height": altura, "length": quadros, "batch_size": 1}},
            "3": {"class_type": "KSamplerAdvanced", "inputs": {"model": ["15", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0], "add_noise": "enable", "noise_seed": seed, "steps": 4, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "start_at_step": 0, "end_at_step": 2, "return_with_leftover_noise": "enable"}},
            "17": {"class_type": "KSamplerAdvanced", "inputs": {"model": ["16", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["3", 0], "add_noise": "disable", "noise_seed": seed, "steps": 4, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "start_at_step": 2, "end_at_step": 4, "return_with_leftover_noise": "disable"}},
            "8": {"class_type": "VAEDecodeTiled", "inputs": {"samples": ["17", 0], "vae": ["11", 0], "tile_size": 512, "overlap": 64, "temporal_size": 64, "temporal_overlap": 8}},
            "18": {"class_type": "CreateVideo", "inputs": {"images": ["8", 0], "fps": float(perfil.fps)}},
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

    conteudo = _chamar_ollama_prompt(system_prompt, texto, "Enhanced English music style prompt:")
    if conteudo:
        return conteudo, True, "Estilo musical enriquecido para YuE2 ComfyUI (IA Local Ollama)"

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
                "max_abc_tokens": 8192, "temperature": 0.7, "top_p": 0.9, "top_k": 30, "repetition_penalty": 1.005, "penalty_window": 100,
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
                        falha = erro_do_historico(h_data[prompt_id])
                        if falha:
                            return {"ok": False, "erro": f"Falha no ComfyUI: {falha}"}
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

    return {"ok": False, "erro": "O ComfyUI não terminou a imagem a tempo."}


def erro_do_historico(entrada: dict[str, Any]) -> str | None:
    """Mensagem do erro de execução de um prompt no /history do ComfyUI, ou None se não falhou."""
    status = entrada.get("status") or {}
    if status.get("status_str") != "error":
        return None
    for msg in status.get("messages") or []:
        if isinstance(msg, (list, tuple)) and len(msg) == 2 and msg[0] == "execution_error" and isinstance(msg[1], dict):
            info = msg[1]
            return f"{info.get('node_type', 'nó')}: {str(info.get('exception_message', '')).strip()[:300]}"
    return "o ComfyUI informou erro na execução"


EXTENSOES_VIDEO = (".mp4", ".webm", ".mkv", ".mov", ".gif")


def video_do_historico(entrada: dict[str, Any]) -> dict[str, Any] | None:
    """Primeiro arquivo de vídeo nas saídas de um prompt do /history do ComfyUI, ou None se ainda não há."""
    for nout in (entrada.get("outputs") or {}).values():
        for item in nout.get("videos") or nout.get("images") or []:
            if str(item.get("filename", "")).lower().endswith(EXTENSOES_VIDEO):
                return item
    return None


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
        "You are an expert visual prompt engineer and photographer for SDXL and FLUX diffusion models. "
        "Translate any Portuguese or non-English prompt to English and enrich with a photorealistic 4-layer composition: "
        "1. Core subject and natural pose/action. "
        "2. Environment, authentic architecture, and tactile material textures. "
        "3. Natural cinematic lighting (e.g., golden hour backlight, chiaroscuro shadows, soft diffuse overcast light). "
        "4. Camera specifications (e.g., shot on 85mm f/1.4 lens, shallow depth of field, natural skin texture, subtle 35mm film grain). "
        "Do NOT use buzzwords like 'masterpiece', 'best quality', or '8k'. "
        "Strictly preserve the intended subject. Output ONLY the final English prompt text. Never include explanations, quotes, or markdown."
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

    # 2. Tentativa via Ollama local (:11434) dinâmico
    conteudo = _chamar_ollama_prompt(system_prompt, texto, "Enhanced English prompt:")
    if conteudo:
        return conteudo, True, "Prompt traduzido e enriquecido automaticamente para SDXL/FLUX (IA Local Ollama)"

    # Fallback gracioso: mantém o texto original
    return texto, False, ""

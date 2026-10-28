"""Estúdio: motores disponíveis e catálogo de modelos de imagem, vídeo e música."""
import json

from fastapi import APIRouter


from ..envfile import ler_env
from ..caminhos import comfyui_dir, fluxos_comfyui
from .. import servicos as infra
from ..ambiente import Contexto


def criar_router(ctx: Contexto) -> APIRouter:
    router = APIRouter()
    raiz = ctx.raiz

    @router.get("/api/estudio/status-motores")
    def status_motores_estudio():
        return {
            "litellm": infra.porta_aberta(4000),
            "ollama": infra.porta_aberta(11434),
            "comfyui": infra.porta_aberta(8188),
        }

    @router.get("/api/estudio/catalogo-modelos")
    def catalogo_modelos_estudio():
        modelos_img_locais = []
        modelos_vid_locais = []

        # 1. Varre checkpoints e unets locais do ComfyUI
        pasta_comfy_ckp = comfyui_dir(raiz) / "models" / "checkpoints"
        pasta_comfy_unet = comfyui_dir(raiz) / "models" / "unet"
        for p in (pasta_comfy_ckp, pasta_comfy_unet):
            if p.exists():
                for f in p.glob("*.*"):
                    if f.suffix.lower() in (".safetensors", ".ckpt", ".gguf", ".pt") and f.stat().st_size > 100_000:
                        size_gb = round(f.stat().st_size / (1024**3), 2)
                        modelos_img_locais.append({
                            "id": f"local:{f.name}",
                            "nome": f.name.replace(".safetensors", "").replace(".gguf", ""),
                            "arquivo": f.name,
                            "tipo": "local",
                            "motor": "comfyui",
                            "tamanho_gb": size_gb,
                            "rotulo": f"{f.name} (Local · {size_gb} GB)"
                        })

        # 2. Varre modelos de vídeo locais do ComfyUI (diffusion_models)
        pasta_comfy_diff = comfyui_dir(raiz) / "models" / "diffusion_models"
        if pasta_comfy_diff.exists():
            for f in pasta_comfy_diff.glob("*.safetensors"):
                if f.stat().st_size > 100_000:
                    size_gb = round(f.stat().st_size / (1024**3), 2)
                    nl = f.name.lower()
                    nome_limpo = f.name.replace(".safetensors", "")

                    # Modelos de imagem colocados em diffusion_models (Krea2, Z-Image)
                    if "krea" in nl or "z_image" in nl or "zimage" in nl:
                        modelos_img_locais.append({
                            "id": f"local:{f.name}",
                            "nome": nome_limpo,
                            "arquivo": f.name,
                            "tipo": "local",
                            "motor": "comfyui",
                            "tamanho_gb": size_gb,
                            "rotulo": f"🖼️ {nome_limpo} (ComfyUI Imagem · {size_gb} GB)"
                        })
                        continue

                    modo_ent = "i2v" if ("i2v" in nl or "image_to_video" in nl or "image-to-video" in nl) else ("v2v" if "v2v" in nl else ("ti2v" if "ti2v" in nl else "t2v"))
                    midia_req = "imagem" if modo_ent == "i2v" else ("video" if modo_ent == "v2v" else ("opcional" if modo_ent == "ti2v" else "nenhum"))
                    rotulo = f"🎬 {nome_limpo} (ComfyUI · {size_gb} GB)"
                    if "minimax" in nl:
                        rotulo = f"🎵🎬 {nome_limpo} (MiniMax H3 Omni · Vídeo + Áudio · {size_gb} GB)"
                    elif "wan" in nl:
                        rotulo = f"🎬 {nome_limpo} (Wan 2.2 · {size_gb} GB)"
                    modelos_vid_locais.append({
                        "id": f"local:{f.name}",
                        "nome": nome_limpo,
                        "arquivo": f.name,
                        "tipo": "local",
                        "motor": "comfyui",
                        "tamanho_gb": size_gb,
                        "modo_entrada": modo_ent,
                        "midia_requerida": midia_req,
                        "rotulo": rotulo
                    })

        # 3. Varre Fluxos & Workflows customizados criados no ComfyUI (*.json)
        pasta_fluxos = fluxos_comfyui(raiz)
        pasta_user_workflows = comfyui_dir(raiz) / "user" / "default" / "workflows"
        perfis = {}
        arq_perfis = pasta_fluxos / "perfis.json"
        if arq_perfis.exists():
            try:
                perfis = json.loads(arq_perfis.read_text(encoding="utf-8"))
            except Exception:
                pass

        fluxos_processados = set()
        for p in (pasta_fluxos, pasta_user_workflows):
            if p.exists():
                for f in p.glob("*.json"):
                    if f.name in ("perfis.json", "comfy.settings.json") or f.name in fluxos_processados:
                        continue
                    fluxos_processados.add(f.name)
                    chave_perfil = f.stem
                    info_perfil = perfis.get(chave_perfil, {})
                    is_video = info_perfil.get("tipo") == "video" or "video" in f.stem.lower() or "wan" in f.stem.lower()

                    cfg_img = str(info_perfil.get("imagem", "")).lower()
                    nl = f.stem.lower()
                    if cfg_img == "obrigatoria" or "i2v" in nl or "image_to_video" in nl or "image-to-video" in nl:
                        modo_ent = "i2v"
                        midia_req = "imagem"
                    elif "v2v" in nl or "video_to_video" in nl or "video-to-video" in nl:
                        modo_ent = "v2v"
                        midia_req = "video"
                    elif cfg_img == "opcional" or "ti2v" in nl or "minimax" in nl:
                        modo_ent = "ti2v"
                        midia_req = "opcional"
                    else:
                        modo_ent = "t2v"
                        midia_req = "nenhum"

                    rotulo_fluxo = f"🔀 Fluxo ComfyUI: {f.stem.replace('-', ' ').title()}"
                    if "minimax" in nl:
                        rotulo_fluxo = "🎵🎬 MiniMax H3 Omni Turbo (Vídeo + Áudio Estéreo · 8 Steps · Recomendado)"
                    elif "wan5b" in nl:
                        rotulo_fluxo = "⚡ Wan 2.2 TI2V 5B Turbo (Rápido · 4 Steps)"
                    elif "wan14b-t2v" in nl:
                        rotulo_fluxo = "🎥 Wan 2.2 14B High Quality (Cinema · 4 Steps)"
                    elif "wan14b-i2v" in nl:
                        rotulo_fluxo = "🖼️ Wan 2.2 14B Image-to-Video (I2V · 4 Steps)"

                    item_fluxo = {
                        "id": f"fluxo:{f.name}",
                        "nome": f.stem,
                        "arquivo": f.name,
                        "tipo": "fluxo_comfyui",
                        "motor": "comfyui",
                        "modo_entrada": modo_ent,
                        "midia_requerida": midia_req,
                        "rotulo": rotulo_fluxo
                    }
                    if is_video:
                        modelos_vid_locais.append(item_fluxo)
                    else:
                        modelos_img_locais.append(item_fluxo)

        # Ordena modelos de vídeo para colocar os fluxos recomendados (MiniMax H3) no topo
        def _prioridade_modelo_video(m):
            mid = m["id"].lower()
            if "minimax" in mid:
                return 0
            if "wan5b" in mid:
                return 1
            if "wan14b" in mid:
                return 2
            if m["tipo"] == "fluxo_comfyui":
                return 3
            return 4

        modelos_vid_locais.sort(key=_prioridade_modelo_video)

        # Modelos Nuvem Imagem
        env_atual = ler_env(raiz / ".env")
        cf_ativa = bool(env_atual.get("CLOUDFLARE_API_KEY", "").strip() and env_atual.get("CLOUDFLARE_ACCOUNT_ID", "").strip())

        modelos_img_nuvem = []
        if cf_ativa:
            modelos_img_nuvem.extend([
                {"id": "cf-flux", "nome": "FLUX.1 Schnell (Cloudflare)", "tipo": "nuvem", "motor": "cloudflare", "rotulo": "⚡ FLUX.1 Schnell (Cloudflare Workers AI · Sem Watermark)"},
                {"id": "cf-sdxl", "nome": "SDXL Base 1.0 (Cloudflare)", "tipo": "nuvem", "motor": "cloudflare", "rotulo": "⚡ Stable Diffusion XL (Cloudflare Workers AI · Alta Resolução)"},
                {"id": "cf-dreamshaper", "nome": "DreamShaper LCM (Cloudflare)", "tipo": "nuvem", "motor": "cloudflare", "rotulo": "⚡ DreamShaper LCM (Cloudflare · Arte & Ilustração)"},
            ])

        modelos_img_nuvem.extend([
            {"id": "flux", "nome": "FLUX.1 Schnell", "tipo": "nuvem", "motor": "nuvem", "rotulo": "FLUX.1 Schnell (Nuvem Pública · Fallback)"},
            {"id": "flux-realism", "nome": "FLUX Realism", "tipo": "nuvem", "motor": "nuvem", "rotulo": "FLUX Realism (Nuvem Pública)"},
            {"id": "flux-anime", "nome": "FLUX Anime", "tipo": "nuvem", "motor": "nuvem", "rotulo": "FLUX Anime (Nuvem Pública)"},
            {"id": "turbo", "nome": "SDXL Turbo", "tipo": "nuvem", "motor": "nuvem", "rotulo": "SDXL Turbo (Nuvem Pública)"},
        ])

        # Modelos Nuvem Vídeo
        modelos_vid_nuvem = [
            {"id": "wan2.1-t2v", "nome": "Wan 2.1 Text-to-Video", "tipo": "nuvem", "motor": "nuvem", "modo_entrada": "t2v", "midia_requerida": "nenhum", "rotulo": "Wan 2.1 Nuvem (Standard)"},
            {"id": "svd", "nome": "Stable Video Diffusion", "tipo": "nuvem", "motor": "nuvem", "modo_entrada": "i2v", "midia_requerida": "imagem", "rotulo": "Stable Video Diffusion (SVD Nuvem · Image-to-Video)"},
        ]

        return {
            "ok": True,
            "imagem": {
                "locais": modelos_img_locais,
                "nuvem": modelos_img_nuvem,
            },
            "video": {
                "locais": modelos_vid_locais,
                "nuvem": modelos_vid_nuvem,
            },
            "musica": {
                "locais": [
                    {
                        "id": "fluxo:musica-yue2",
                        "nome": "YuE 2 Music Generator",
                        "arquivo": "musica-yue2.json",
                        "tipo": "local",
                        "motor": "comfyui",
                        "tamanho_gb": 3.77,
                        "rotulo": "🎵 YuE 2 Full Song Generator (ABC Planning · Letra & Estilo · 3B Int8)"
                    }
                ],
                "nuvem": []
            }
        }

    return router

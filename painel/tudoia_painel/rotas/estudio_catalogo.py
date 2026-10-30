"""Estúdio: motores disponíveis e catálogo de modelos de imagem, vídeo e música."""

from fastapi import APIRouter


from ..caminhos import comfyui_dir
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
                        if "yue" in f.name.lower():
                            continue
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

                    modo_ent = "ti2v" if "ti2v" in nl else ("i2v" if ("i2v" in nl or "image_to_video" in nl or "image-to-video" in nl) else ("v2v" if "v2v" in nl else "t2v"))
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

        # Ordena modelos de vídeo locais (MiniMax H3 no topo)
        def _prioridade_modelo_video(m):
            mid = m["id"].lower()
            if "minimax" in mid:
                return 0
            if "wan5b" in mid or "5b" in mid:
                return 1
            if "wan" in mid:
                return 2
            return 3

        modelos_vid_locais.sort(key=_prioridade_modelo_video)

        modelos_img_nuvem = []
        modelos_vid_nuvem = []

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
                        "id": "musica-yue2",
                        "nome": "YuE 2 Music Generator",
                        "arquivo": "yue2_3b_int8_convrot.safetensors",
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

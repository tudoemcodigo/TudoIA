"""Estúdio: motores disponíveis e catálogo de modelos de imagem, vídeo e música."""

from fastapi import APIRouter


from ..caminhos import comfyui_dir
from .. import servicos as infra
from ..ambiente import Contexto
from ..envfile import ler_env
from ..estudio_servico import LTX23_TEXTO, LTX23_UNET, LTX23_VAE_AUDIO, LTX23_VAE_VIDEO, max_segmento_video_local, perfil_video_local
from ..video_nuvem import catalogo_video

# Pastas dos custom nodes que o grafo do LTX-2.3 GGUF usa (UnetLoaderGGUF, DualCLIPLoaderGGUF, VAELoaderKJ).
NODES_LTX23 = ("ComfyUI-GGUF", "ComfyUI-KJNodes")


def modelo_ltx23(raiz) -> dict | None:
    """Entrada do LTX-2.3 no catálogo quando os 5 arquivos e os 2 custom nodes estão no ComfyUI."""
    base = comfyui_dir(raiz)
    arquivos = (base / "models" / "unet" / LTX23_UNET, *(base / "models" / "text_encoders" / n for n in LTX23_TEXTO),
                base / "models" / "vae" / LTX23_VAE_VIDEO, base / "models" / "vae" / LTX23_VAE_AUDIO)
    if not all(a.is_file() for a in arquivos) or not all((base / "custom_nodes" / n).is_dir() for n in NODES_LTX23):
        return None
    size_gb = round(sum(a.stat().st_size for a in arquivos) / (1024**3), 2)
    return {"id": "video-ltx23", "nome": "LTX-2.3 distilled (GGUF)", "arquivo": LTX23_UNET, "tipo": "local",
            "motor": "comfyui", "tamanho_gb": size_gb, "modo_entrada": "ti2v", "midia_requerida": "opcional",
            "rotulo": f"LTX-2.3 (vídeo + áudio · até 20 s por clipe · {size_gb} GB)"}


def modelos_video_nuvem(raiz) -> list[dict]:
    """Modelos de config/video-nuvem.yaml, marcados como disponíveis quando a chave está no .env."""
    env = ler_env(raiz / ".env")
    saida = []
    for m in catalogo_video(raiz):
        validas = m.duracoes_validas()
        saida.append({"id": m.nome, "nome": m.nome, "tipo": "nuvem", "motor": "nuvem", "provedor": m.provedor,
                      "rotulo": m.rotulo, "disponivel": bool((env.get(m.chave) or "").strip()), "chave": m.chave,
                      "i2v": bool(m.i2v), "duracao_min_s": validas[0], "max_segmento_s": {"480p": validas[-1], "720p": validas[-1]},
                      "preco_usd_s": {r: m.preco(r) for r in ("480p", "720p")}, "fonte_preco": m.fonte_preco,
                      "modo_entrada": "ti2v" if m.i2v else "t2v", "midia_requerida": "opcional" if m.i2v else "nenhum"})
    return saida


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
                            "rotulo": f"{nome_limpo} (ComfyUI Imagem · {size_gb} GB)"
                        })
                        continue

                    modo_ent = "ti2v" if "ti2v" in nl else ("i2v" if ("i2v" in nl or "image_to_video" in nl or "image-to-video" in nl) else ("v2v" if "v2v" in nl else "t2v"))
                    midia_req = "imagem" if modo_ent == "i2v" else ("video" if modo_ent == "v2v" else ("opcional" if modo_ent == "ti2v" else "nenhum"))
                    rotulo = f"{nome_limpo} (ComfyUI · {size_gb} GB)"
                    if "minimax" in nl:
                        rotulo = f"{nome_limpo} (MiniMax H3 Omni · Vídeo + Áudio · {size_gb} GB)"
                    elif "wan" in nl:
                        rotulo = f"{nome_limpo} (Wan 2.2 · {size_gb} GB)"
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
        ltx = modelo_ltx23(raiz)
        if ltx:
            modelos_vid_locais.insert(0, ltx)
        for m in modelos_vid_locais:
            perfil = perfil_video_local(m["id"])
            m["max_segmento_s"] = {r: max_segmento_video_local(perfil, r) for r in ("480p", "720p")}

        modelos_img_nuvem = []
        modelos_vid_nuvem = modelos_video_nuvem(raiz)

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
                        "rotulo": "YuE 2 (música com letra e estilo · 3B int8)"
                    }
                ],
                "nuvem": []
            }
        }

    return router

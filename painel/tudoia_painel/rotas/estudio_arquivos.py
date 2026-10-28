"""Estúdio: listar, servir e excluir imagens, vídeos, músicas e uploads; receber upload."""
import base64
import re
import shutil
import time
import uuid
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse


from ..erros import ErroApi
from ..midia import LIMITE_UPLOAD_BYTES, midia_confere
from ..caminhos import comfyui_dir
from ..ambiente import Contexto
from ..schemas import UploadMidiaReq
from ..estudio_servico import arquivo_em


def criar_router(ctx: Contexto) -> APIRouter:
    router = APIRouter()
    raiz = ctx.raiz
    pastas = ctx.pastas_estudio
    pasta_estudio_imagens = pastas.imagens
    pasta_estudio_videos = pastas.videos
    pasta_estudio_musicas = pastas.musicas
    pasta_estudio_uploads = pastas.uploads
    pasta_comfy_output_video = pastas.comfy_video
    pasta_comfy_output_audio = pastas.comfy_audio

    @router.get("/api/estudio/imagens")
    def listar_imagens_estudio():
        imagens = []
        if pasta_estudio_imagens.exists():
            for f in pasta_estudio_imagens.iterdir():
                if f.is_file() and f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".svg"):
                    st = f.stat()
                    imagens.append({
                        "nome": f.name,
                        "url": f"/api/estudio/imagens/{f.name}",
                        "mtime": st.st_mtime,
                        "tamanho": st.st_size
                    })
        imagens.sort(key=lambda x: x["mtime"], reverse=True)
        return {"ok": True, "imagens": imagens}

    @router.get("/api/estudio/imagens/{nome_arquivo:path}")
    def servir_imagem_estudio(nome_arquivo: str):
        alvo = arquivo_em((pasta_estudio_imagens,), nome_arquivo)
        if alvo is None:
            raise ErroApi(404, "nao_encontrado", "Imagem não encontrada no disco.")
        ext = alvo.suffix.lower()
        media_type = "image/jpeg" if ext in (".jpg", ".jpeg") else ("image/png" if ext == ".png" else "application/octet-stream")
        return FileResponse(alvo, media_type=media_type)

    @router.delete("/api/estudio/imagens/{nome_arquivo:path}")
    def excluir_imagem_estudio(nome_arquivo: str):
        alvo = arquivo_em((pasta_estudio_imagens,), nome_arquivo)
        if alvo is None:
            raise ErroApi(404, "nao_encontrado", "Imagem não encontrada no disco.")
        try:
            alvo.unlink()
            return {"ok": True, "removido": nome_arquivo}
        except Exception as e:
            raise ErroApi(500, "erro_exclusao", f"Falha ao excluir arquivo: {e}") from e

    @router.get("/api/estudio/videos")
    def listar_videos_estudio():
        # Sincroniza novos vídeos gerados diretamente pelo ComfyUI
        if pasta_comfy_output_video.exists():
            for f in pasta_comfy_output_video.glob("*.*"):
                if f.is_file() and f.suffix.lower() in (".mp4", ".webm", ".mov", ".mkv"):
                    dest = pasta_estudio_videos / f.name
                    if not dest.exists():
                        try:
                            shutil.copy2(f, dest)
                        except Exception:
                            pass

        videos = []
        if pasta_estudio_videos.exists():
            for f in pasta_estudio_videos.iterdir():
                if f.is_file() and f.suffix.lower() in (".mp4", ".webm", ".mov", ".mkv"):
                    st = f.stat()
                    videos.append({
                        "nome": f.name,
                        "url": f"/api/estudio/videos/{f.name}",
                        "mtime": st.st_mtime,
                        "tamanho": st.st_size
                    })
        videos.sort(key=lambda x: x["mtime"], reverse=True)
        return {"ok": True, "videos": videos}

    @router.get("/api/estudio/videos/{nome_arquivo:path}")
    def servir_video_estudio(nome_arquivo: str):
        alvo = arquivo_em((pasta_estudio_videos, pasta_comfy_output_video), nome_arquivo)
        if alvo is None:
            raise ErroApi(404, "nao_encontrado", "Vídeo não encontrado no disco.")
        ext = alvo.suffix.lower()
        media_type = "video/webm" if ext == ".webm" else "video/mp4"
        return FileResponse(alvo, media_type=media_type)

    @router.delete("/api/estudio/videos/{nome_arquivo:path}")
    def excluir_video_estudio(nome_arquivo: str):
        encontrado = False
        for pasta in (pasta_estudio_videos, pasta_comfy_output_video):
            alvo = arquivo_em((pasta,), nome_arquivo)
            if alvo is not None:
                try:
                    alvo.unlink()
                    encontrado = True
                except Exception:
                    pass
        if not encontrado:
            raise ErroApi(404, "nao_encontrado", "Vídeo não encontrado para exclusão.")
        return {"ok": True, "removido": nome_arquivo}

    @router.get("/api/estudio/musicas")
    def listar_musicas_estudio():
        # Sincroniza novas músicas geradas diretamente pelo ComfyUI
        if pasta_comfy_output_audio.exists():
            for f in pasta_comfy_output_audio.glob("*.*"):
                if f.is_file() and f.suffix.lower() in (".flac", ".mp3", ".wav", ".ogg"):
                    dest = pasta_estudio_musicas / f.name
                    if not dest.exists():
                        try:
                            shutil.copy2(f, dest)
                        except Exception:
                            pass

        musicas = []
        if pasta_estudio_musicas.exists():
            for f in pasta_estudio_musicas.iterdir():
                if f.is_file() and f.suffix.lower() in (".flac", ".mp3", ".wav", ".ogg"):
                    st = f.stat()
                    musicas.append({
                        "nome": f.name,
                        "url": f"/api/estudio/musicas/{f.name}",
                        "mtime": st.st_mtime,
                        "tamanho": st.st_size
                    })
        musicas.sort(key=lambda x: x["mtime"], reverse=True)
        return {"ok": True, "musicas": musicas}

    @router.get("/api/estudio/musicas/{nome_arquivo:path}")
    def servir_musica_estudio(nome_arquivo: str):
        alvo = arquivo_em((pasta_estudio_musicas, pasta_comfy_output_audio), nome_arquivo)
        if alvo is None:
            raise ErroApi(404, "nao_encontrado", "Música não encontrada no disco.")
        ext = alvo.suffix.lower()
        media_type = "audio/flac" if ext == ".flac" else ("audio/mpeg" if ext == ".mp3" else ("audio/wav" if ext == ".wav" else "audio/ogg"))
        return FileResponse(alvo, media_type=media_type)

    @router.delete("/api/estudio/musicas/{nome_arquivo:path}")
    def excluir_musica_estudio(nome_arquivo: str):
        removido = False
        alvo = arquivo_em((pasta_estudio_musicas,), nome_arquivo)
        if alvo is not None:
            try:
                alvo.unlink()
                removido = True
            except Exception as e:
                raise ErroApi(500, "erro_exclusao", f"Falha ao excluir música: {e}") from e

        cand = arquivo_em((pasta_comfy_output_audio,), nome_arquivo)
        if cand is not None:
            try:
                cand.unlink()
                removido = True
            except Exception:
                pass

        if not removido:
            raise ErroApi(404, "nao_encontrado", "Música não encontrada no disco.")
        return {"ok": True, "removido": nome_arquivo}

    @router.post("/api/estudio/upload")
    def upload_midia_estudio(corpo: UploadMidiaReq):
        extensoes_permitidas = {
            "imagem": {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"},
            "video": {".mp4", ".mov", ".webm", ".avi", ".mkv"},
        }
        sufixo = Path(corpo.nome_arquivo).suffix.lower()
        permitidas = extensoes_permitidas.get(corpo.tipo, set())
        if sufixo not in permitidas:
            raise ErroApi(422, "validacao", f"Extensão '{sufixo}' não permitida para {corpo.tipo}. Permitidas: {', '.join(sorted(permitidas))}")

        conteudo_b64 = corpo.conteudo_base64
        if "," in conteudo_b64:
            conteudo_b64 = conteudo_b64.split(",", 1)[1]

        # Tamanho conferido antes de decodificar: base64 ocupa 4 bytes para cada 3 do arquivo.
        if len(conteudo_b64) * 3 // 4 > LIMITE_UPLOAD_BYTES:
            raise ErroApi(413, "corpo_grande_demais", "Arquivo excede o limite máximo permitido de 100 MB.")
        try:
            dados_binarios = base64.b64decode(conteudo_b64)
        except Exception as e:
            raise ErroApi(422, "validacao", "Base64 inválido.") from e

        if len(dados_binarios) == 0:
            raise ErroApi(422, "validacao", "Arquivo enviado está vazio.")
        if len(dados_binarios) > LIMITE_UPLOAD_BYTES:
            raise ErroApi(413, "corpo_grande_demais", "Arquivo excede o limite máximo permitido de 100 MB.")
        if not midia_confere(dados_binarios, sufixo):
            raise ErroApi(422, "validacao", f"O conteúdo não é um arquivo {sufixo} válido.")

        nome_sanitizado = re.sub(r"[^a-zA-Z0-9_.-]", "_", Path(corpo.nome_arquivo).stem)
        # uuid no nome: dois envios do mesmo arquivo no mesmo segundo não se sobrescrevem
        nome_final = f"upload_{int(time.time())}_{uuid.uuid4().hex[:8]}_{nome_sanitizado}{sufixo}"
        destino = pasta_estudio_uploads / nome_final
        destino.write_bytes(dados_binarios)

        # Se for imagem, sincroniza também na pasta de input do ComfyUI se existir
        comfy_input = comfyui_dir(raiz) / "input"
        if corpo.tipo == "imagem" and comfy_input.exists():
            try:
                shutil.copy2(destino, comfy_input / nome_final)
            except Exception:
                pass

        return {
            "ok": True,
            "nome_arquivo": nome_final,
            "caminho_local": str(destino),
            "url": f"/api/estudio/uploads/{nome_final}",
            "tipo": corpo.tipo,
            "tamanho_bytes": len(dados_binarios),
        }

    @router.get("/api/estudio/uploads/{nome_arquivo:path}")
    def servir_upload_estudio(nome_arquivo: str):
        alvo = arquivo_em((pasta_estudio_uploads,), nome_arquivo)
        if alvo is None:
            raise ErroApi(404, "nao_encontrado", "Arquivo de upload não encontrado.")
        ext = alvo.suffix.lower()
        content_type = "image/png"
        if ext in (".jpg", ".jpeg"):
            content_type = "image/jpeg"
        elif ext == ".webp":
            content_type = "image/webp"
        elif ext == ".mp4":
            content_type = "video/mp4"
        elif ext == ".webm":
            content_type = "video/webm"
        return FileResponse(alvo, media_type=content_type)

    return router

"""Serviço do Estúdio: otimização de prompts e execução de grafos no ComfyUI (sem HTTP de entrada)."""
import collections
from dataclasses import dataclass
from datetime import datetime
import json
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
from .caminhos import comfyui_dir, fluxos_comfyui
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
    pasta_fluxos = fluxos_comfyui(raiz)
    nome_modelo_lower = modelo_id.lower()
    eh_minimax = "minimax" in nome_modelo_lower or "h3" in nome_modelo_lower
    eh_i2v = caminho_ref is not None or "i2v" in nome_modelo_lower or "image_to_video" in nome_modelo_lower

    if eh_minimax:
        arq_grafo = pasta_fluxos / "video-minimax-h3.json"
    elif eh_i2v:
        arq_grafo = pasta_fluxos / "video-wan14b-i2v.json"
    elif "5b" in nome_modelo_lower:
        arq_grafo = pasta_fluxos / "video-wan5b.json"
    else:
        arq_grafo = pasta_fluxos / "video-minimax-h3.json" if (pasta_fluxos / "video-minimax-h3.json").is_file() else (pasta_fluxos / "video-wan14b-t2v.json")

    if not arq_grafo.is_file():
        for cand in (pasta_fluxos / "video-minimax-h3.json", pasta_fluxos / "video-wan14b-t2v.json"):
            if cand.is_file():
                arq_grafo = cand
                eh_minimax = "minimax" in arq_grafo.stem
                break

    grafo = json.loads(arq_grafo.read_text(encoding="utf-8"))

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

    if eh_minimax:
        if "104" in grafo and "inputs" in grafo["104"]:
            grafo["104"]["inputs"]["prompt"] = prompt_texto
            grafo["104"]["inputs"]["width"] = largura
            grafo["104"]["inputs"]["height"] = altura
            qtd_frames = max(5, round(duracao_s * fps))
            grid_length = qtd_frames + (5 - (qtd_frames % 17)) % 17
            grafo["104"]["inputs"]["length"] = grid_length
            if nome_arquivo_comfy:
                grafo["114"] = {
                    "inputs": {"image": nome_arquivo_comfy},
                    "class_type": "LoadImage"
                }
                grafo["104"]["inputs"]["first_frame"] = ["114", 0]
            elif "first_frame" in grafo["104"]["inputs"]:
                del grafo["104"]["inputs"]["first_frame"]
        if "15" in grafo and "inputs" in grafo["15"]:
            grafo["15"]["inputs"]["noise_seed"] = seed
        if "91" in grafo and "inputs" in grafo["91"]:
            grafo["91"]["inputs"]["fps"] = fps
    else:
        for _nid, node in grafo.items():
            if not isinstance(node, dict):
                continue
            ct = node.get("class_type", "")
            inputs = node.get("inputs", {})
            if ct == "CLIPTextEncode" and "text" in inputs:
                inputs["text"] = prompt_texto
            elif ct == "LoadImage" and nome_arquivo_comfy and "image" in inputs:
                inputs["image"] = nome_arquivo_comfy
            elif ct in ("KSampler", "KSamplerAdvanced", "RandomNoise"):
                if "noise_seed" in inputs:
                    inputs["noise_seed"] = seed
                elif "seed" in inputs:
                    inputs["seed"] = seed
            elif ct == "EmptyHunyuanLatentVideo":
                if "width" in inputs:
                    inputs["width"] = largura
                if "height" in inputs:
                    inputs["height"] = altura
                if "length" in inputs:
                    inputs["length"] = max(17, int(duracao_s * fps))

    return grafo, arq_grafo.name, eh_minimax


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
    pasta_fluxos = fluxos_comfyui(raiz)
    arq_grafo = pasta_fluxos / "musica-yue2.json"

    if not arq_grafo.is_file():
        return {"ok": False, "erro": "Fluxo 'musica-yue2.json' não encontrado em modelos/comfyui/fluxos."}

    try:
        grafo = json.loads(arq_grafo.read_text(encoding="utf-8"))
    except Exception as e:
        return {"ok": False, "erro": f"Falha ao carregar fluxo ComfyUI '{arq_grafo.name}': {e}"}

    # Nó 2: YuE2GenerateABC
    if "2" in grafo and "inputs" in grafo["2"]:
        grafo["2"]["inputs"]["style"] = style_texto
        grafo["2"]["inputs"]["lyrics"] = lyrics_texto or "[instrumental]"
        grafo["2"]["inputs"]["seed"] = seed
        grafo["2"]["inputs"]["mode"] = modo

    # Nó 3: YuE2GenerateMusic
    if "3" in grafo and "inputs" in grafo["3"]:
        grafo["3"]["inputs"]["style"] = style_texto
        grafo["3"]["inputs"]["lyrics"] = lyrics_texto or "[instrumental]"
        grafo["3"]["inputs"]["seed"] = seed
        grafo["3"]["inputs"]["mode"] = modo
        grafo["3"]["inputs"]["max_duration"] = float(duracao_s)

    # Nó 6: KSampler
    if "6" in grafo and "inputs" in grafo["6"]:
        grafo["6"]["inputs"]["seed"] = seed

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
                                                    "grafo_usado": arq_grafo.name
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
                                                "grafo_usado": arq_grafo.name
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
    pasta_fluxos = fluxos_comfyui(raiz)
    pasta_user_wf = comfyui_dir(raiz) / "user" / "default" / "workflows"

    caminho_grafo = None
    if modelo_id.startswith("fluxo:"):
        nome_limpo = modelo_id.replace("fluxo:", "")
        # Nome de arquivo puro, dentro de uma das duas pastas: nada de "..", subpasta ou caminho absoluto.
        if Path(nome_limpo).name != nome_limpo or nome_limpo in ("", ".", ".."):
            raise ValueError(f"nome de fluxo inválido: {nome_limpo!r}")
        for pasta in (pasta_fluxos, pasta_user_wf):
            for p in (pasta / nome_limpo, pasta / f"{nome_limpo}.json"):
                if p.is_file() and p.resolve().is_relative_to(pasta.resolve()):
                    caminho_grafo = p
                    break
            if caminho_grafo:
                break
    elif modelo_id.startswith("local:"):
        nome_ckp = modelo_id.replace("local:", "")
        if "flux" in nome_ckp.lower():
            caminho_grafo = pasta_fluxos / "flux-schnell.json"
        elif "z_image" in nome_ckp.lower() or "zimage" in nome_ckp.lower():
            caminho_grafo = pasta_fluxos / "zimage-turbo.json"
        else:
            caminho_grafo = pasta_fluxos / "sdxl-foto.json"

    if not caminho_grafo or not caminho_grafo.is_file():
        caminho_grafo = pasta_fluxos / "GeraImagemTudoIA-KREA2.json"
        if not caminho_grafo.is_file():
            caminho_grafo = pasta_fluxos / "sdxl-foto.json"

    try:
        grafo = json.loads(caminho_grafo.read_text(encoding="utf-8"))
    except Exception as e:
        return {"ok": False, "erro": f"Falha ao ler fluxo ComfyUI '{caminho_grafo.name}': {e}"}

    # Injeção específica para o Krea-2 Subgraph se presente
    if "30:19" in grafo and "inputs" in grafo["30:19"]:
        grafo["30:19"]["inputs"]["value"] = prompt_pos
    if "30:3" in grafo and "inputs" in grafo["30:3"]:
        grafo["30:3"]["inputs"]["seed"] = seed

    # Injeção genérica nos nós do grafo
    for _nid, node in grafo.items():
        if not isinstance(node, dict):
            continue
        ct = node.get("class_type", "")
        inputs = node.get("inputs", {})
        if ct == "KSampler":
            if "seed" in inputs:
                inputs["seed"] = seed
            if "steps" in inputs and steps > 0 and "krea" not in caminho_grafo.name.lower():
                inputs["steps"] = steps
        elif ct == "CLIPTextEncode":
            txt = str(inputs.get("text", "")).lower()
            if any(w in txt for w in ["blurry", "bad", "lowres", "watermark", "deformed"]):
                if prompt_neg:
                    inputs["text"] = prompt_neg
            else:
                inputs["text"] = prompt_pos
        elif ct == "EmptyLatentImage":
            if "width" in inputs:
                inputs["width"] = largura
            if "height" in inputs:
                inputs["height"] = altura
        elif ct == "CheckpointLoaderSimple" and modelo_id.startswith("local:"):
            inputs["ckpt_name"] = modelo_id.replace("local:", "")
        elif ct == "UNETLoader" and modelo_id.startswith("local:"):
            inputs["unet_name"] = modelo_id.replace("local:", "")

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
        while time.time() - inicio_wait < 90:
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

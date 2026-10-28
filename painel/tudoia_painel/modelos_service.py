"""Serviço para gerenciamento de modelos locais do Ollama (pull, delete, unload e toggle ativo)."""
from __future__ import annotations

import json
import re
import struct
import time
from pathlib import Path
from typing import Any

import httpx

from .caminhos import comfyui_dir, comfyui_portable, fluxos_comfyui
from . import upstreams

OLLAMA_BASE_URL = f"{upstreams.OLLAMA}"
RE_MODELO_OLLAMA = re.compile(r"^[a-zA-Z0-9_\.-]+(:[a-zA-Z0-9_\.-]+)?$")


def obter_caminho_estado_locais(raiz: Path) -> Path:
    caminho = Path(raiz) / "dados" / "config" / "modelos_locais.json"
    caminho.parent.mkdir(parents=True, exist_ok=True)
    return caminho


def ler_modelos_locais_desativados(raiz: Path) -> set[str]:
    caminho = obter_caminho_estado_locais(raiz)
    if not caminho.is_file():
        return set()
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        desativados = dados.get("desativados", [])
        return set(desativados) if isinstance(desativados, list) else set()
    except Exception:
        return set()


def salvar_modelos_locais_desativados(raiz: Path, desativados: set[str]) -> None:
    caminho = obter_caminho_estado_locais(raiz)
    dados = {"desativados": sorted(list(desativados))}
    caminho.write_text(json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8")


def toggle_ativo_modelo_local(raiz: Path, nome_modelo: str) -> dict[str, Any]:
    desativados = ler_modelos_locais_desativados(raiz)
    if nome_modelo in desativados:
        desativados.remove(nome_modelo)
        ativo = True
    else:
        desativados.add(nome_modelo)
        ativo = False
    salvar_modelos_locais_desativados(raiz, desativados)
    return {"ok": True, "modelo": nome_modelo, "ativo": ativo}


def verificar_ollama_online(timeout: float = 1.5) -> bool:
    try:
        with httpx.Client(timeout=timeout) as cliente:
            r = cliente.get(f"{OLLAMA_BASE_URL}/api/tags")
            return r.status_code == 200
    except Exception:
        return False


def obter_modelos_em_vram() -> dict[str, dict[str, Any]]:
    """Consulta quais modelos estão alocados na VRAM/memória pelo Ollama via GET /api/ps."""
    if not verificar_ollama_online():
        return {}
    try:
        with httpx.Client(timeout=2.0) as cliente:
            r = cliente.get(f"{OLLAMA_BASE_URL}/api/ps")
            if r.status_code == 200:
                resultado = {}
                for m in r.json().get("models", []):
                    nome = m.get("name") or m.get("model", "")
                    size_vram = m.get("size_vram", 0)
                    resultado[nome] = {
                        "size_vram_gb": round(size_vram / (1024**3), 2),
                        "expires_at": m.get("expires_at", "")
                    }
                return resultado
    except Exception:
        pass
    return {}


def baixar_modelo_ollama(nome_modelo: str, timeout: float = 600.0) -> dict[str, Any]:
    nome = nome_modelo.strip()
    if not RE_MODELO_OLLAMA.match(nome):
        raise ValueError(f"Nome de modelo Ollama inválido '{nome}'. Exemplo válido: 'qwen2.5-coder:7b' ou 'llama3.2:3b'")

    if not verificar_ollama_online():
        raise RuntimeError("O serviço Ollama não está ativo na porta 11434. Inicie o Ollama antes de baixar modelos.")

    try:
        with httpx.Client(timeout=timeout) as cliente:
            # stream=False aguarda a conclusão do pull
            resp = cliente.post(f"{OLLAMA_BASE_URL}/api/pull", json={"name": nome, "stream": False})
            if resp.status_code == 200:
                dados = resp.json()
                return {"ok": True, "modelo": nome, "status": dados.get("status", "success")}
            else:
                raise RuntimeError(f"Ollama retornou status {resp.status_code}: {resp.text[:200]}")
    except httpx.TimeoutException as e:
        raise TimeoutError(f"Download do modelo {nome} excedeu o tempo limite.") from e
    except Exception as e:
        raise RuntimeError(f"Falha ao baixar modelo {nome}: {str(e)}") from e


def excluir_modelo_ollama(nome_modelo: str) -> dict[str, Any]:
    nome = nome_modelo.strip()
    if not verificar_ollama_online():
        raise RuntimeError("O serviço Ollama não está ativo na porta 11434. Inicie o Ollama para excluir modelos.")

    # Primeiro descarrega da VRAM caso esteja alocado
    try:
        descarregar_modelo_vram(nome)
    except Exception:
        pass

    try:
        with httpx.Client(timeout=10.0) as cliente:
            resp = cliente.request("DELETE", f"{OLLAMA_BASE_URL}/api/delete", json={"name": nome})
            if resp.status_code == 200:
                return {"ok": True, "modelo": nome, "mensagem": f"Modelo {nome} excluído com sucesso do disco."}
            else:
                raise RuntimeError(f"Ollama retornou status {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        raise RuntimeError(f"Falha ao excluir modelo {nome}: {str(e)}") from e


def descarregar_modelo_vram(nome_modelo: str) -> dict[str, Any]:
    nome = nome_modelo.strip()
    if not verificar_ollama_online():
        return {"ok": True, "modelo": nome, "mensagem": "Ollama já está desligado."}

    try:
        with httpx.Client(timeout=5.0) as cliente:
            resp = cliente.post(f"{OLLAMA_BASE_URL}/api/generate", json={"model": nome, "keep_alive": 0})
            if resp.status_code == 200:
                return {"ok": True, "modelo": nome, "mensagem": f"Modelo {nome} descarregado da VRAM com sucesso."}
            else:
                return {"ok": False, "modelo": nome, "erro": f"Status {resp.status_code}: {resp.text[:150]}"}
    except Exception as e:
        return {"ok": False, "modelo": nome, "erro": str(e)}


CATEGORIAS_COMFY = {
    "checkpoints": "Checkpoint SDXL/Flux",
    "diffusion_models": "Modelo de Difusão (Vídeo/Imagem)",
    "unet": "UNet (GGUF / Quantizado)",
    "vae": "VAE (Autoencoder)",
    "clip": "CLIP Text Encoder",
    "text_encoders": "Text Encoder (T5 / Qwen)",
    "loras": "LoRA (Adaptador Rápido)",
}

CHAVES_MODELOS_WORKFLOW = (
    "ckpt_name",
    "unet_name",
    "vae_name",
    "clip_name",
    "clip_name1",
    "clip_name2",
    "lora_name",
    "model_name",
)


def extrair_modelos_do_workflow(dados_json: dict[str, Any]) -> list[str]:
    """Extrai todos os nomes de arquivos de modelos referenciados nos nós de um workflow ComfyUI."""
    encontrados: list[str] = []
    if not isinstance(dados_json, dict):
        return encontrados
    for _node_id, node in dados_json.items():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        for chave in CHAVES_MODELOS_WORKFLOW:
            val = inputs.get(chave)
            if isinstance(val, str) and (val.endswith(".safetensors") or val.endswith(".gguf") or val.endswith(".ckpt") or val.endswith(".pt")):
                if val not in encontrados:
                    encontrados.append(val)
    return encontrados


def listar_midia_detalhada(raiz: Path) -> dict[str, Any]:
    """Lista detalhadamente todos os modelos de Vídeo & Imagem (ComfyUI) e fluxos JSON."""
    raiz = Path(raiz)
    desativados = ler_modelos_locais_desativados(raiz)
    pasta_modelos = raiz / "modelos"

    modelos_midia: list[dict[str, Any]] = []
    nomes_arquivos_instalados: set[str] = set()

    # 1. Modelos ComfyUI (em modelos/comfyui/ComfyUI_windows_portable/ComfyUI/models)
    dir_comfy_models = comfyui_dir(raiz) / "models"
    if dir_comfy_models.is_dir():
        for pasta_cat, label_cat in CATEGORIAS_COMFY.items():
            sub_dir = dir_comfy_models / pasta_cat
            if not sub_dir.is_dir():
                continue
            for arq in sorted(sub_dir.rglob("*")):
                if not arq.is_file() or arq.suffix.lower() not in (".safetensors", ".gguf", ".ckpt", ".pt"):
                    continue
                # Ignora arquivos placeholder minúsculos (< 1MB)
                tamanho_bytes = arq.stat().st_size
                if tamanho_bytes < 1024 * 1024:
                    continue
                tam_gb = round(tamanho_bytes / (1024**3), 2)
                rel_path = arq.relative_to(pasta_modelos).as_posix()
                rel_id = f"midia:{rel_path}"
                nomes_arquivos_instalados.add(arq.name)
                modelos_midia.append({
                    "id": rel_id,
                    "nome": arq.name,
                    "arquivo": arq.name,
                    "motor": "ComfyUI",
                    "categoria": label_cat,
                    "pasta": pasta_cat,
                    "formato": arq.suffix.lstrip("."),
                    "tamanho_gb": tam_gb,
                    "ativo": rel_id not in desativados and arq.name not in desativados,
                })

    # 2. Fluxos ComfyUI (versionados em runtime/comfyui/fluxos)
    dir_fluxos = fluxos_comfyui(raiz)
    perfis_map: dict[str, Any] = {}
    arq_perfis = dir_fluxos / "perfis.json"
    if arq_perfis.is_file():
        try:
            perfis_map = json.loads(arq_perfis.read_text(encoding="utf-8"))
        except Exception:
            perfis_map = {}

    fluxos_legado: list[str] = []
    fluxos_detalhados: list[dict[str, Any]] = []
    if dir_fluxos.is_dir():
        for arq_fl in sorted(dir_fluxos.glob("*.json")):
            if arq_fl.name == "perfis.json":
                continue
            stem = arq_fl.stem
            fluxos_legado.append(stem)
            rel_id = f"fluxo:{arq_fl.name}"

            dados_wf: dict[str, Any] = {}
            try:
                dados_wf = json.loads(arq_fl.read_text(encoding="utf-8"))
            except Exception:
                dados_wf = {}

            deps = extrair_modelos_do_workflow(dados_wf)
            perfil = perfis_map.get(stem, {})
            if not deps and perfil.get("modelo"):
                deps = [perfil["modelo"]]

            faltantes = [d for d in deps if d not in nomes_arquivos_instalados]
            tipo_midia = perfil.get("tipo") or ("video" if "video" in stem.lower() or "wan" in stem.lower() else "imagem")
            res = perfil.get("tamanho") or (f"{perfil['largura']}x{perfil['altura']}" if "largura" in perfil else "Padrão")
            extra_info = f"{perfil['fps']} FPS" if "fps" in perfil else (f"{perfil['passos']} passos" if "passos" in perfil else f"{len(dados_wf)} nós")

            fluxos_detalhados.append({
                "id": rel_id,
                "nome": stem,
                "arquivo": arq_fl.name,
                "tipo": tipo_midia,
                "resolucao": res,
                "detalhe_execucao": extra_info,
                "quantidade_nos": len(dados_wf) if isinstance(dados_wf, dict) else 0,
                "modelos_requeridos": deps,
                "modelos_faltantes": faltantes,
                "integro": len(faltantes) == 0 and len(dados_wf) > 0,
                "ativo": rel_id not in desativados and stem not in desativados,
            })

    return {
        "comfyui_fluxos": fluxos_legado,
        "modelos": modelos_midia,
        "fluxos": fluxos_detalhados,
    }


def _resolver_caminho_midia(raiz: Path, item_id: str) -> Path:
    raiz = Path(raiz)
    pasta_modelos = (raiz / "modelos").resolve()
    if item_id.startswith("fluxo:"):
        nome_arq = item_id.removeprefix("fluxo:").strip()
        pastas = [fluxos_comfyui(raiz).resolve()]
        alvo = (pastas[0] / nome_arq).resolve()
    elif item_id.startswith("midia:"):
        rel = item_id.removeprefix("midia:").strip()
        pastas = [pasta_modelos, comfyui_portable(raiz).resolve()]
        alvo = (pasta_modelos / rel).resolve()
    else:
        raise ValueError(f"Identificador de mídia inválido: '{item_id}'")

    if not any(alvo.is_relative_to(pasta) for pasta in pastas):
        raise ValueError("Caminho fora das pastas de mídia permitidas não é permitido.")
    # Só o que a tela lista: pesos e fluxos. Sem isto a exclusão apagava qualquer arquivo dentro de modelos\,
    # inclusive o código do ComfyUI portable.
    permitidas = EXT_FLUXO if item_id.startswith("fluxo:") else EXT_PESOS
    if alvo.suffix.lower() not in permitidas:
        raise ValueError(f"Só arquivos {', '.join(sorted(permitidas))} podem ser verificados ou excluídos aqui.")
    return alvo


EXT_PESOS = frozenset({".safetensors", ".gguf", ".ckpt", ".pt"})
EXT_FLUXO = frozenset({".json"})


def verificar_item_midia(raiz: Path, item_id: str) -> dict[str, Any]:
    """Verifica a integridade binária de um modelo .safetensors/.gguf ou dependências de um fluxo ComfyUI."""
    inicio = time.perf_counter()
    alvo = _resolver_caminho_midia(raiz, item_id)
    if not alvo.is_file():
        lat = int((time.perf_counter() - inicio) * 1000)
        return {"ok": False, "modelo": item_id, "motor": "midia", "latencia_ms": lat, "erro": "Arquivo não encontrado no disco"}

    if item_id.startswith("fluxo:"):
        try:
            dados = json.loads(alvo.read_text(encoding="utf-8"))
            if not isinstance(dados, dict) or len(dados) == 0:
                lat = int((time.perf_counter() - inicio) * 1000)
                return {"ok": False, "modelo": item_id, "motor": "comfyui", "latencia_ms": lat, "erro": "JSON de workflow vazio ou inválido"}
            info_midia = listar_midia_detalhada(raiz)
            instalados = {m["arquivo"] for m in info_midia.get("modelos", [])}
            deps = extrair_modelos_do_workflow(dados)
            faltantes = [d for d in deps if d not in instalados]
            lat = int((time.perf_counter() - inicio) * 1000)
            if faltantes:
                return {
                    "ok": False,
                    "modelo": item_id,
                    "motor": "comfyui",
                    "latencia_ms": lat,
                    "erro": f"Falta(m) {len(faltantes)} modelo(s): {', '.join(faltantes[:2])}",
                }
            return {
                "ok": True,
                "modelo": item_id,
                "motor": "comfyui",
                "latencia_ms": lat,
                "resposta": f"Íntegro ({len(dados)} nós, {len(deps)}/{len(deps)} modelos OK)",
            }
        except Exception as e:
            lat = int((time.perf_counter() - inicio) * 1000)
            return {"ok": False, "modelo": item_id, "motor": "comfyui", "latencia_ms": lat, "erro": f"JSON inválido: {e}"}

    # Verificação binária de cabeçalho para .safetensors ou .gguf
    try:
        tamanho_bytes = alvo.stat().st_size
        tam_gb = round(tamanho_bytes / (1024**3), 2)
        ext = alvo.suffix.lower()
        with alvo.open("rb") as f:
            head = f.read(16)

        if ext == ".gguf":
            if head[:4] != b"GGUF":
                lat = int((time.perf_counter() - inicio) * 1000)
                return {"ok": False, "modelo": item_id, "motor": "midia", "latencia_ms": lat, "erro": "Assinatura binária GGUF inválida"}
        elif ext == ".safetensors":
            if len(head) < 8:
                lat = int((time.perf_counter() - inicio) * 1000)
                return {"ok": False, "modelo": item_id, "motor": "midia", "latencia_ms": lat, "erro": "Arquivo safetensors truncado"}
            header_size = struct.unpack("<Q", head[:8])[0]
            if header_size == 0 or header_size > 100 * 1024 * 1024 or header_size >= tamanho_bytes:
                lat = int((time.perf_counter() - inicio) * 1000)
                return {"ok": False, "modelo": item_id, "motor": "midia", "latencia_ms": lat, "erro": "Cabeçalho safetensors corrompido"}

        lat = int((time.perf_counter() - inicio) * 1000)
        return {
            "ok": True,
            "modelo": item_id,
            "motor": "midia",
            "latencia_ms": lat,
            "resposta": f"Cabeçalho {ext.lstrip('.').upper()} íntegro ({tam_gb} GB)",
        }
    except Exception as e:
        lat = int((time.perf_counter() - inicio) * 1000)
        return {"ok": False, "modelo": item_id, "motor": "midia", "latencia_ms": lat, "erro": str(e)}


def excluir_item_midia(raiz: Path, item_id: str) -> dict[str, Any]:
    """Remove do disco um modelo de mídia ou fluxo ComfyUI de forma segura."""
    alvo = _resolver_caminho_midia(raiz, item_id)
    if not alvo.is_file():
        raise FileNotFoundError(f"Arquivo '{alvo.name}' não encontrado no disco.")
    tam_gb = round(alvo.stat().st_size / (1024**3), 2)
    nome = alvo.name
    alvo.unlink()
    return {"ok": True, "id": item_id, "arquivo": nome, "liberado_gb": tam_gb}


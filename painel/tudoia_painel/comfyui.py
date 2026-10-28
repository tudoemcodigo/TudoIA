"""Fronteira com o ComfyUI: nomes de arquivo e parâmetros de /view vindos da resposta dele são validados antes de virar
caminho em disco ou query string. O ComfyUI é local, mas o grafo pode carregar nós de terceiros."""
from pathlib import PurePosixPath, PureWindowsPath

from . import upstreams

BASE = upstreams.COMFYUI
TIPOS_VIEW = ("output", "input", "temp")


def nome_seguro(valor: object) -> str:
    """Nome de arquivo puro: sem separador, sem `..`, sem unidade (`C:`), sem byte nulo."""
    if not isinstance(valor, str) or not valor or valor in (".", "..") or "\x00" in valor:
        raise ValueError("nome de arquivo inválido vindo do ComfyUI")
    if PureWindowsPath(valor).name != valor or PurePosixPath(valor).name != valor or ":" in valor:
        raise ValueError("nome de arquivo inválido vindo do ComfyUI")
    return valor


def subpasta_segura(valor: object) -> str:
    """Subpasta relativa dentro de output/input/temp, ou vazio."""
    if valor in (None, ""):
        return ""
    if not isinstance(valor, str) or "\x00" in valor or ":" in valor:
        raise ValueError("subpasta inválida vinda do ComfyUI")
    partes = valor.replace("\\", "/").split("/")
    if valor.startswith(("/", "\\")) or any(p in ("", ".", "..") for p in partes):
        raise ValueError("subpasta inválida vinda do ComfyUI")
    return valor


def parametros_view(arquivo: dict) -> dict[str, str]:
    """Query de GET /view montada de um item de saída do histórico (`httpx` faz o escape)."""
    tipo = arquivo.get("type", "output")
    if tipo not in TIPOS_VIEW:
        raise ValueError("tipo de saída inválido vindo do ComfyUI")
    return {"filename": nome_seguro(arquivo.get("filename")), "subfolder": subpasta_segura(arquivo.get("subfolder")),
            "type": tipo}

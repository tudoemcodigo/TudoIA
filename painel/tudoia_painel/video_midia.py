"""Ponte do painel para midia_av.py: roda as operações de mídia com o python_embeded do ComfyUI (que tem o PyAV).

O painel não instala PyAV nem FFmpeg. `-I` isola o subprocesso: não lê variáveis PYTHON*, não põe a pasta do script
nem a atual no sys.path.
"""
import json
import subprocess
import tempfile
from pathlib import Path

from . import caminhos

SCRIPT = Path(__file__).with_name("midia_av.py")
TIMEOUT_INFO = 30
TIMEOUT_QUADRO = 120
TIMEOUT_MONTAGEM = 1800   # 60 s em 720p reencodados em H.264 levam poucos minutos; folga para disco lento


class ErroMidia(RuntimeError):
    pass


def python_comfy(raiz: Path) -> Path:
    return caminhos.comfyui_portable(raiz) / "python_embeded" / "python.exe"


def disponivel(raiz: Path) -> bool:
    return python_comfy(raiz).is_file()


def _rodar(raiz: Path, args: list[str], timeout: int) -> dict:
    py = python_comfy(raiz)
    if not py.is_file():
        raise ErroMidia("python do ComfyUI portable não encontrado: o vídeo longo usa o PyAV que vem com ele")
    try:
        r = subprocess.run([str(py), "-I", str(SCRIPT), *args], capture_output=True, timeout=timeout,
                           text=True, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired as e:
        raise ErroMidia(f"operação de mídia '{args[0]}' passou de {timeout} s") from e
    if r.returncode != 0:
        raise ErroMidia((r.stderr or "").strip()[-400:] or f"operação de mídia '{args[0]}' falhou")
    try:
        return json.loads((r.stdout or "").strip().splitlines()[-1])
    except (IndexError, ValueError) as e:
        raise ErroMidia(f"resposta inesperada da operação '{args[0]}'") from e


def info(raiz: Path, video: Path) -> dict:
    return _rodar(raiz, ["info", str(video)], TIMEOUT_INFO)


def ultimo_quadro(raiz: Path, video: Path, destino: Path) -> dict:
    return _rodar(raiz, ["ultimo-quadro", str(video), str(destino)], TIMEOUT_QUADRO)


def primeiro_quadro(raiz: Path, video: Path, destino: Path) -> dict:
    return _rodar(raiz, ["primeiro-quadro", str(video), str(destino)], TIMEOUT_QUADRO)


def montar(raiz: Path, saida: Path, entradas: list[Path], largura: int, altura: int, fps: int,
           duracao_max_s: float | None = None, trilha: Path | None = None) -> dict:
    spec = {"saida": str(saida), "entradas": [str(e) for e in entradas], "largura": largura, "altura": altura,
            "fps": fps, "duracao_max_s": duracao_max_s, "trilha": str(trilha) if trilha else None}
    with tempfile.TemporaryDirectory(prefix="tudoia-montagem-") as d:
        arq = Path(d) / "spec.json"
        arq.write_text(json.dumps(spec), encoding="utf-8")
        return _rodar(raiz, ["montar", str(arq)], TIMEOUT_MONTAGEM)

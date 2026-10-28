"""Detecção do que já existe na máquina. Cada função é pequena e recebe o que precisa por parâmetro (testável)."""
from __future__ import annotations

import ctypes
import os
import platform
import shutil
import socket
import subprocess
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path

PORTAS = {
    "painel": 3100, "litellm": 4000, "litellm-db": 5433, "cerebro": 8765, "searxng": 8080, "open-webui": 3000,
    "kokoro": 8880, "n8n": 5678, "keycloak": 8180, "ollama": 11434, "comfyui": 8188,
}
# Porta de cada serviço por componente: o que a tela confere antes de instalar.
PORTAS_POR_COMPONENTE = {
    "nucleo": ("painel", "litellm", "litellm-db"),
    "cerebro": ("cerebro", "searxng"),
    "webui": ("open-webui", "kokoro", "searxng"),
    "n8n": ("n8n",),
    "keycloak": ("keycloak",),
    "ollama": ("ollama",),
    "comfyui": ("comfyui",),
}
# Espaço estimado (GB) sem contar os pesos dos modelos, que ficam fora da instalação.
GB_POR_COMPONENTE = {"nucleo": 4, "cerebro": 2, "webui": 6, "n8n": 2, "keycloak": 1, "ollama": 2, "comfyui": 12}
MIN_WINDOWS_BUILD = 19041   # Windows 10 2004: primeira versão com WSL2, que o Docker Desktop exige


@dataclass
class Gpu:
    nome: str = ""
    vram_mb: int = 0

    @property
    def presente(self) -> bool:
        return bool(self.nome)


def rodar(cmd: list[str], timeout: float = 15.0) -> tuple[int, str]:
    """(código, saída). Falha ao executar vira (127, ''): detecção nunca levanta."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except (OSError, subprocess.SubprocessError):
        return 127, ""


def build_windows() -> int:
    """Número de build do Windows (0 fora do Windows)."""
    if os.name != "nt":
        return 0
    try:
        return int(platform.version().split(".")[-1])
    except ValueError:
        return 0


def eh_administrador() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())   # type: ignore[attr-defined]
    except (AttributeError, OSError):
        return False


def disco_livre_gb(caminho: str) -> float:
    """GB livres na unidade do caminho (sobe até a primeira pasta que exista)."""
    p = Path(caminho)
    while not p.exists() and p != p.parent:
        p = p.parent
    try:
        return shutil.disk_usage(p).free / 1024 ** 3
    except OSError:
        return 0.0


def gpu_nvidia(executar=rodar) -> Gpu:
    codigo, saida = executar(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"])
    if codigo != 0 or not saida.strip():
        return Gpu()
    nome, _, vram = saida.strip().splitlines()[0].partition(",")
    try:
        return Gpu(nome.strip(), int(vram.strip()))
    except ValueError:
        return Gpu(nome.strip(), 0)


def porta_ocupada(porta: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", porta)) == 0


def achar_executavel(nome: str, extras: tuple[str, ...] = ()) -> str | None:
    achado = shutil.which(nome)
    if achado:
        return achado
    for caminho in extras:
        caminho = os.path.expandvars(caminho)
        if os.path.isfile(caminho):
            return caminho
    return None


def docker_exe() -> str | None:
    return achar_executavel("docker", (r"%ProgramFiles%\Docker\Docker\resources\bin\docker.exe",))


def docker_desktop_exe() -> str | None:
    return achar_executavel("Docker Desktop", (r"%ProgramFiles%\Docker\Docker\Docker Desktop.exe",))


def ollama_exe() -> str | None:
    return achar_executavel("ollama", (r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe", r"%ProgramFiles%\Ollama\ollama.exe"))


def docker_pronto(executar=rodar) -> bool:
    exe = docker_exe()
    return bool(exe) and executar([exe, "info", "--format", "{{.ServerVersion}}"], 25.0)[0] == 0


def tem_internet(url: str = "https://github.com", abrir=urllib.request.urlopen) -> bool:
    try:
        abrir(urllib.request.Request(url, method="HEAD"), timeout=6).close()
        return True
    except OSError:
        return False
    except ValueError:
        return False


@dataclass
class Diagnostico:
    windows_build: int
    windows_ok: bool
    administrador: bool
    docker_instalado: bool
    docker_pronto: bool
    ollama_instalado: bool
    winget: bool
    gpu_nome: str
    gpu_vram_mb: int
    internet: bool
    portas_ocupadas: dict[str, int]

    def como_dict(self) -> dict:
        return asdict(self)


def diagnosticar(executar=rodar) -> Diagnostico:
    build = build_windows()
    gpu = gpu_nvidia(executar)
    return Diagnostico(
        windows_build=build, windows_ok=build >= MIN_WINDOWS_BUILD, administrador=eh_administrador(),
        docker_instalado=docker_exe() is not None, docker_pronto=docker_pronto(executar),
        ollama_instalado=ollama_exe() is not None, winget=shutil.which("winget") is not None,
        gpu_nome=gpu.nome, gpu_vram_mb=gpu.vram_mb, internet=tem_internet(),
        portas_ocupadas={nome: p for nome, p in PORTAS.items() if porta_ocupada(p)},
    )


def portas_necessarias(componentes: list[str], keycloak_existente: bool = False) -> dict[str, int]:
    """Porta de cada serviço que as opções escolhidas vão usar."""
    usados = ["nucleo", *componentes]
    nomes: list[str] = []
    for c in usados:
        if c == "keycloak" and keycloak_existente:
            continue
        nomes += [n for n in PORTAS_POR_COMPONENTE.get(c, ()) if n not in nomes]
    return {n: PORTAS[n] for n in nomes}


def espaco_necessario_gb(componentes: list[str]) -> int:
    return sum(GB_POR_COMPONENTE.get(c, 0) for c in ["nucleo", *componentes])

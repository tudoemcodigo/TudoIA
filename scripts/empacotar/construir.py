"""Gera dist/TudoIA-Setup.exe: o instalador de um clique, com o código do TudoIA embutido.

Uso (na raiz do repositório):
    python -m scripts.empacotar.construir          # ou: .\\scripts\\tudoia.ps1 empacotar

Passos: 1) gera o payload.zip e varre segredos e dados pessoais (reprova = nada é construído); 2) PyInstaller em modo
onefile, com a tela e o payload dentro; 3) sha256 do .exe; 4) teste de fumaça (`--versao`).
O .exe não é assinado digitalmente: o SmartScreen avisa na primeira execução (Mais informações > Executar assim mesmo).
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

from . import payload

RAIZ = payload.RAIZ
DIST = RAIZ / "dist"
BUILD = RAIZ / "build" / "pyinstaller"
PYINSTALLER = "pyinstaller==6.22.3"


def construir() -> Path:
    if payload.principal() != 0:
        raise SystemExit("o pacote de código não passou na verificação: nada foi construído")
    uv = shutil.which("uv")
    if not uv:
        raise SystemExit("uv não encontrado no PATH (https://docs.astral.sh/uv/)")
    inst = RAIZ / "instalador"
    cmd = [
        uv, "run", "--no-project", "--with", PYINSTALLER, "pyinstaller", "--noconfirm", "--clean", "--onefile",
        "--name", "TudoIA-Setup", "--distpath", str(DIST), "--workpath", str(BUILD), "--specpath", str(BUILD),
        "--paths", str(inst), "--icon", str(inst / "tudoia_instalador" / "static" / "favicon.ico"),
        "--add-data", f"{inst / 'dados'};dados", "--add-data", f"{inst / 'tudoia_instalador' / 'static'};static",
        str(inst / "entrada.py"),
    ]
    subprocess.run(cmd, check=True, cwd=RAIZ)
    exe = DIST / "TudoIA-Setup.exe"
    h = hashlib.sha256(exe.read_bytes()).hexdigest()
    (DIST / "TudoIA-Setup.exe.sha256").write_text(f"{h}  TudoIA-Setup.exe\n", encoding="utf-8")
    saida = subprocess.run([str(exe), "--versao"], capture_output=True, text=True, timeout=120)
    if saida.returncode != 0 or "TudoIA Setup" not in saida.stdout:
        raise SystemExit(f"o .exe construído não rodou: {saida.stderr.strip()[:300]}")
    print(f"{exe} ({exe.stat().st_size / 1024 ** 2:.1f} MB), sha256 {h}")
    return exe


if __name__ == "__main__":
    construir()
    sys.exit(0)

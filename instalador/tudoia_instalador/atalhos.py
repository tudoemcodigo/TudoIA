"""Atalhos do Windows (área de trabalho e menu Iniciar) para iniciar, parar e desinstalar o TudoIA."""
from __future__ import annotations

import os
from pathlib import Path

from .motor import Contexto

POWERSHELL = r"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"

# Cada atalho: (nome do arquivo .lnk, script dentro de scripts\, argumentos extras do script, janela oculta?)
ATALHOS = (
    ("TudoIA - Iniciar", "iniciar.ps1", "", True),
    ("TudoIA - Parar", "parar.ps1", "", True),
    ("TudoIA - Desinstalar", "desinstalar.ps1", "", False),
)


def pastas_de_atalho() -> list[Path]:
    desktop = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"
    menu = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "TudoIA"
    return [desktop, menu]


def _script_criar(lnk: Path, alvo: str, argumentos: str, pasta_trabalho: Path, icone: str) -> str:
    """PowerShell que cria um .lnk. Todos os valores são validados antes e vão entre aspas simples (sem expansão)."""
    def lit(v: str) -> str:
        return "'" + v.replace("'", "''") + "'"
    return (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut(" + lit(str(lnk)) + "); "
        "$s.TargetPath = " + lit(alvo) + "; "
        "$s.Arguments = " + lit(argumentos) + "; "
        "$s.WorkingDirectory = " + lit(str(pasta_trabalho)) + "; "
        "$s.IconLocation = " + lit(icone) + "; "
        "$s.Save()"
    )


def criar_atalhos(c: Contexto) -> None:
    raiz = c.raiz
    icone = str(raiz / "painel" / "tudoia_painel" / "static" / "favicon.ico")
    for pasta in pastas_de_atalho():
        pasta.mkdir(parents=True, exist_ok=True)
        for nome, script, extra, oculto in ATALHOS:
            alvo_script = raiz / "scripts" / script
            if not alvo_script.is_file():
                c.log(f"aviso: {script} não existe nesta versão; atalho '{nome}' não criado")
                continue
            argumentos = ("-NoProfile -ExecutionPolicy Bypass " + ("-WindowStyle Hidden " if oculto else "")
                          + f'-File "{alvo_script}" {extra}').strip()
            exe = os.path.expandvars(POWERSHELL)
            c.executor.rodar(["powershell", "-NoProfile", "-Command",
                              _script_criar(pasta / f"{nome}.lnk", exe, argumentos, raiz, icone)], mostrar=False, timeout=60)
    c.log("atalhos criados na área de trabalho e no menu Iniciar (pasta TudoIA)")

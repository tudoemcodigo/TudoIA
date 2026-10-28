"""Desinstalação: para os serviços, remove atalhos e arquivos. Dados e modelos só saem se o usuário pedir.

Só mexe numa pasta que tenha a marca `.tudoia-instalacao.json` deixada pelo instalador, e nunca segue junção ao apagar.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import sys
from pathlib import Path
from typing import Callable

from .atalhos import ATALHOS, pastas_de_atalho
from .execucao import ErroComando, Executor, Redator
from .sistema import docker_exe

MARCA = ".tudoia-instalacao.json"
DADOS_DO_USUARIO = ("dados", "modelos")


class ErroDesinstalacao(Exception):
    pass


def _validar_pasta(p: Path, rotulo: str) -> Path:
    p = p.resolve()
    if not p.is_absolute() or len(p.parts) < 2 or p == Path(p.anchor) or p == Path.home().resolve():
        raise ErroDesinstalacao(f"{rotulo} inválida para apagar: {p}")
    return p


def _eh_juncao(p: Path) -> bool:
    return hasattr(os.path, "isjunction") and os.path.isjunction(p)


def _apagar_arvore(p: Path) -> None:
    """rmtree que não segue junção/link: remove o elo e nunca o conteúdo do destino."""
    def forcar(func, caminho, _exc):
        os.chmod(caminho, stat.S_IWRITE)
        func(caminho)

    if p.is_symlink() or _eh_juncao(p):
        os.rmdir(p)
        return
    for filho in list(p.iterdir()):
        if filho.is_symlink() or _eh_juncao(filho):
            os.rmdir(filho)
        elif filho.is_dir():
            _apagar_arvore(filho)
        else:
            try:
                filho.unlink()
            except PermissionError:
                os.chmod(filho, stat.S_IWRITE)
                filho.unlink()
    shutil.rmtree(p, onerror=forcar)


def desinstalar(raiz: Path, remover_dados: bool, log: Callable[[str], None] = print,
                executor: Executor | None = None) -> None:
    raiz = _validar_pasta(raiz, "pasta de instalação")
    marca = raiz / MARCA
    if not marca.is_file():
        raise ErroDesinstalacao(f"{raiz} não tem a marca do instalador do TudoIA; nada foi apagado")
    info = json.loads(marca.read_text(encoding="utf-8"))
    projeto = info.get("projeto_compose") or "tudoia"
    executor = executor or Executor(log, Redator())

    parar = raiz / "scripts" / "parar.ps1"
    if parar.is_file():
        try:
            executor.rodar(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(parar)], timeout=300)
        except ErroComando as e:
            log(f"aviso: não consegui parar tudo ({e})")
    docker = docker_exe()
    if docker and (raiz / "runtime" / "docker-compose.yml").is_file():
        down = [docker, "compose", "-p", projeto, "-f", str(raiz / "runtime" / "docker-compose.yml"), "--env-file",
                str(raiz / ".env"), "down", "--remove-orphans"]
        try:
            executor.rodar(down + (["-v"] if remover_dados else []), timeout=600)
        except ErroComando as e:
            log(f"aviso: docker compose down falhou ({e})")

    for pasta in pastas_de_atalho():
        for nome, *_ in ATALHOS:
            (pasta / f"{nome}.lnk").unlink(missing_ok=True)
        if pasta.name == "TudoIA":
            try:
                pasta.rmdir()
            except OSError:
                pass

    pasta_dados = Path(info["pasta_dados"]) if info.get("pasta_dados") else None
    # Sem resolver: a junção raiz\dados já aponta para a pasta de dados, e é essa pasta (fora da raiz) que precisa sair.
    if remover_dados and pasta_dados and os.path.abspath(pasta_dados) != os.path.abspath(raiz / "dados"):
        _apagar_arvore(_validar_pasta(pasta_dados, "pasta de dados"))
        log(f"dados removidos: {pasta_dados}")
    for filho in list(raiz.iterdir()):
        if filho.name in DADOS_DO_USUARIO and not remover_dados:
            log(f"mantido: {filho.name} (dados e modelos; apague à mão se não precisar)")
            continue
        if filho.is_symlink() or _eh_juncao(filho):
            os.rmdir(filho)          # elo (junção ou link): remove o elo, nunca o destino
        elif filho.is_dir():
            _apagar_arvore(filho)
        else:
            try:
                filho.unlink()
            except PermissionError:
                os.chmod(filho, stat.S_IWRITE)
                filho.unlink()
    if not any(raiz.iterdir()):
        raiz.rmdir()
    log("TudoIA desinstalado")


def principal(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Desinstala o TudoIA")
    p.add_argument("--raiz", required=True, type=Path)
    p.add_argument("--remover-dados", action="store_true", help="apaga também dados, volumes Docker e modelos")
    args = p.parse_args(argv)
    try:
        desinstalar(args.raiz, args.remover_dados)
    except (ErroDesinstalacao, OSError) as e:
        print(f"erro: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(principal())

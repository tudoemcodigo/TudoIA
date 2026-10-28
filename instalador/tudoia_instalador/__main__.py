"""Ponto de entrada: assistente no navegador (padrão), instalação sem interface (--config) ou desinstalação."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import VERSAO
from .desinstalar import ErroDesinstalacao, desinstalar
from .etapas import montar_etapas
from .execucao import Redator
from .motor import Contexto, Motor, pasta_estado_padrao
from .opcoes import Opcoes, validar
from .servidor import Aplicacao, servir


def instalar_sem_interface(arquivo: Path) -> int:
    """Instala a partir de um JSON de opções (mesmos nomes de campo da tela). O arquivo pode ter segredos: apague-o depois."""
    try:
        o = Opcoes.de_dict(json.loads(arquivo.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError) as e:
        print(f"opções inválidas: {e}", file=sys.stderr)
        return 2
    erros = validar(o)
    if erros:
        for campo, msg in erros:
            print(f"{campo}: {msg}", file=sys.stderr)
        return 2
    redator = Redator()
    redator.adicionar(*o.chaves_provedores.values(), o.keycloak_existente_senha)
    ctx = Contexto(o=o, redator=redator, log=print)
    motor = Motor(ctx, montar_etapas(), arquivo_log=pasta_estado_padrao() / "instalador.log")
    original = motor.registrar
    motor.registrar = lambda t: (original(t), print(redator.limpar(t), flush=True))[0]   # type: ignore[method-assign]
    ctx.log = motor.registrar
    if ctx.executor is not None:
        ctx.executor.log = motor.registrar
    ok = motor.rodar()
    senha = ctx.efemeros.get("admin_senha")
    if ok:
        print(f"\nPainel: http://127.0.0.1:3100/app/  (login: {o.admin_email})")
        if senha:
            print(f"Senha temporária (troca obrigatória no 1º login): {senha}")
        return 0
    return 3 if motor.precisa_reiniciar else 1


def _configurar_saida() -> None:
    """Console do Windows costuma ser cp1252: uma linha de comando externo com acento estragado não pode derrubar a etapa."""
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def principal(argv: list[str] | None = None) -> int:
    _configurar_saida()
    p = argparse.ArgumentParser(prog="TudoIA-Setup", description="Instalador do TudoIA para Windows")
    p.add_argument("--versao", action="store_true")
    p.add_argument("--config", type=Path, help="JSON de opções: instala sem abrir a tela")
    p.add_argument("--desinstalar", type=Path, metavar="PASTA", help="desinstala a instalação em PASTA")
    p.add_argument("--remover-dados", action="store_true", help="com --desinstalar: apaga dados e modelos também")
    p.add_argument("--sem-navegador", action="store_true", help="não abre o navegador (mostra só o endereço)")
    args = p.parse_args(argv)
    if args.versao:
        print(f"TudoIA Setup {VERSAO}")
        return 0
    if args.desinstalar:
        try:
            desinstalar(args.desinstalar, args.remover_dados)
        except (ErroDesinstalacao, OSError) as e:
            print(f"erro: {e}", file=sys.stderr)
            return 1
        return 0
    if args.config:
        return instalar_sem_interface(args.config)
    return servir(Aplicacao(), abrir_navegador=not args.sem_navegador)


if __name__ == "__main__":
    sys.exit(principal())

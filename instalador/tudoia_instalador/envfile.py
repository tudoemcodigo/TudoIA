"""Montagem do `.env` da instalação a partir do `.env.example` e das opções.

Formato do projeto: `CHAVE=valor`, sem aspas e sem espaço em volta do `=`; comentários e ordem do modelo ficam como
estão. Numa reinstalação parte do `.env` que já existe e só mexe nas chaves que as opções controlam.
"""
from __future__ import annotations

import re

from .opcoes import Opcoes


def ler(texto: str) -> dict[str, str]:
    valores: dict[str, str] = {}
    for linha in texto.splitlines():
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", linha)
        if m:
            valores[m.group(1)] = m.group(2).strip()
    return valores


def definir(texto: str, chave: str, valor: str) -> str:
    """Troca `CHAVE=...` (primeira ocorrência não comentada) ou acrescenta no fim."""
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", chave):
        raise ValueError(f"nome de variável inválido: {chave!r}")
    if re.search(r"[\r\n\x00]", valor):
        raise ValueError(f"valor de {chave} tem quebra de linha")
    linha = f"{chave}={valor}"
    novo, n = re.subn(rf"^{re.escape(chave)}=.*$", lambda _m: linha, texto, count=1, flags=re.M)
    if n:
        return novo
    return texto.rstrip("\n") + "\n" + linha + "\n"


def montar(base: str, o: Opcoes) -> str:
    """`.env` com as opções aplicadas sobre `base` (o modelo, ou o `.env` de uma instalação anterior)."""
    texto = base.replace("\r\n", "\n")
    for chave, valor in (
        ("COMPOSE_PROFILES", ",".join(o.perfis)),
        ("TUDOIA_COMPOSE_PROJETO", o.projeto_compose),
        ("TZ", o.fuso),
        ("TUDOIA_OLLAMA_MODELS", str(o.pesos_ollama) if o.usa("ollama") else ""),
        ("TUDOIA_COMFYUI_PORTABLE", str(o.comfyui) if o.usa("comfyui") else ""),
    ):
        texto = definir(texto, chave, valor)
    if o.keycloak_existente:
        texto = definir(texto, "TUDOIA_KEYCLOAK_ADMIN", o.keycloak_existente_admin)
        texto = definir(texto, "TUDOIA_KEYCLOAK_ADMIN_PASSWORD", o.keycloak_existente_senha)
    for chave, valor in o.chaves_provedores.items():
        if valor.strip():
            texto = definir(texto, chave, valor.strip())
    return texto

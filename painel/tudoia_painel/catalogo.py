"""Catálogo de provedores/modelos (FREE/PAID) e regras de roteamento."""
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml


@dataclass(frozen=True)
class Modelo:
    nome: str
    id: str
    papeis: tuple[str, ...]
    contexto: int | None
    ativo: bool


@dataclass(frozen=True)
class Provedor:
    chave_id: str
    nome: str
    tier: Literal["FREE", "PAID"]
    chave: str
    chaves_extras: tuple[str, ...]
    site_chave: str
    api_base: str | None
    url_modelos: str | None
    limites: dict
    fonte_limites: str | None
    modelos: tuple[Modelo, ...]
    descartar_params: tuple[str, ...] = ()   # params que o provedor recusa com 400 e drop_params não remove
    repeticoes: int | None = None            # num_retries do deployment

    def todas_as_chaves(self) -> tuple[str, ...]:
        return (self.chave, *self.chaves_extras)


@dataclass(frozen=True)
class Catalogo:
    provedores: tuple[Provedor, ...]

    def provedor(self, chave_id: str) -> Provedor:
        for p in self.provedores:
            if p.chave_id == chave_id:
                return p
        raise KeyError(chave_id)


def carregar_catalogo(path: Path) -> Catalogo:
    dados = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    provedores = []
    for pid, p in (dados.get("provedores") or {}).items():
        if p.get("tier") not in ("FREE", "PAID"):
            raise ValueError(f"{pid}: tier deve ser FREE ou PAID")
        modelos = tuple(
            Modelo(
                nome=m["nome"],
                id=m["id"],
                papeis=tuple(m.get("papeis") or ()),
                contexto=m.get("contexto"),
                ativo=m.get("ativo", True),
            )
            for m in p.get("modelos") or ()
        )
        provedores.append(
            Provedor(
                chave_id=pid,
                nome=p.get("nome", pid),
                tier=p["tier"],
                chave=p["chave"],
                chaves_extras=tuple(p.get("chaves_extras") or ()),
                site_chave=p.get("site_chave", ""),
                api_base=p.get("api_base"),
                url_modelos=p.get("url_modelos"),
                limites=p.get("limites") or {},
                fonte_limites=p.get("fonte_limites"),
                modelos=modelos,
                descartar_params=tuple(p.get("descartar_params") or ()),
                repeticoes=p.get("repeticoes"),
            )
        )
    return Catalogo(tuple(provedores))


def provedores_ligados(cat: Catalogo, env: dict[str, str]) -> list[Provedor]:
    return [p for p in cat.provedores if all((env.get(k) or "").strip() for k in p.todas_as_chaves())]


def carregar_roteamento(path: Path) -> dict:
    from .regras import carregar_modulo_regras   # mesma validação que o hook do LiteLLM usa
    rot = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    carregar_modulo_regras().validar_regras(rot)
    return rot

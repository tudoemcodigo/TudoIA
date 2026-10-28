"""Painel de Controle TudoIA. Seam: criar_app(). As rotas ficam em `rotas/`, uma por domínio."""
from pathlib import Path

from fastapi import FastAPI

from .ambiente import Contexto
from .autenticacao import _AUTO, carregar_config_auth, registrar_autenticacao
from .erros import instalar_tratadores
from .rotas import chat, estudio_arquivos, estudio_catalogo, estudio_imagem, estudio_musica, estudio_video, governanca, hardware, modelos, provedores, roteador, segredos, servicos, telemetria, ui
from .seguranca import GuardaApi
from .servicos import ServicosDocker

ROTAS = (servicos, segredos, governanca, modelos, roteador, telemetria, provedores, hardware, estudio_catalogo, estudio_arquivos,
         estudio_imagem, estudio_video, estudio_musica, chat, ui)


def criar_app(raiz: Path, servicos=None, home: Path | None = None, autenticacao=_AUTO) -> FastAPI:
    """Monta o painel. `autenticacao`: ConfigAuth, None (sem IdP: /api responde 503) ou o padrão, que lê o .env."""
    raiz = Path(raiz)
    config_auth = carregar_config_auth(raiz, raiz / "dados" / "backups" / "env") if autenticacao is _AUTO else autenticacao
    ctx = Contexto(raiz=raiz, home=Path(home) if home else Path.home(),
                   servicos=servicos or ServicosDocker(raiz), config_auth=config_auth)
    app = FastAPI(title="Painel de Controle TudoIA", docs_url=None, redoc_url=None, openapi_url=None)
    instalar_tratadores(app)
    for modulo in ROTAS:
        app.include_router(modulo.criar_router(ctx))
    registrar_autenticacao(app, config_auth, raiz / "dados" / "logs" / "auditoria.jsonl")
    app.add_middleware(GuardaApi)
    return app

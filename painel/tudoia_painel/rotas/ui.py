"""SPA estática, favicon e /saude."""
import re
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, RedirectResponse


from ..erros import ErroApi
from ..ambiente import Contexto


ESTATICO = Path(__file__).parent.parent / "static"


def criar_router(ctx: Contexto) -> APIRouter:
    router = APIRouter()


    # ------------------------------------------------ UI
    @router.get("/")
    def raiz_():
        return RedirectResponse("/app/")

    @router.get("/favicon.ico")
    def fav_ico():
        return FileResponse(ESTATICO / "favicon.ico")

    @router.get("/app/")
    def ui():
        return FileResponse(ESTATICO / "index.html")

    @router.get("/app/{arquivo}")
    def estatico(arquivo: str):
        alvo = ESTATICO / arquivo
        permitidos = {"painel.js", "painel.css", "fontes.css", "logo.svg", "favicon.ico", "logo-512.png"}
        fonte = re.fullmatch(r"fonte-\d{1,2}\.woff2", arquivo)
        if (arquivo not in permitidos and not fonte) or not alvo.is_file():
            raise ErroApi(404, "nao_encontrado", "arquivo não encontrado")
        return FileResponse(alvo)

    @router.get("/saude")
    def saude():
        # Fora de /api e sem login: só diz que o processo responde (para launcher, healthcheck e monitor).
        return {"ok": True}

    return router

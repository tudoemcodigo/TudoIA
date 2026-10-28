"""Serviços Docker e do host: listar, iniciar, parar e reiniciar."""

from fastapi import APIRouter


from ..erros import ErroApi
from ..servicos import ACOES
from ..ambiente import Contexto


def criar_router(ctx: Contexto) -> APIRouter:
    router = APIRouter()
    servicos = ctx.servicos

    # ------------------------------------------------ serviços
    @router.get("/api/servicos")
    def listar_servicos():
        return servicos.listar()

    @router.post("/api/servicos/todos/{acao}")
    def acao_todos_servicos(acao: str):
        if acao not in ("start", "stop", "restart"):
            raise ErroApi(422, "validacao", "ação global deve ser start, stop ou restart", campo="acao")
        try:
            if hasattr(servicos, "acao_todos"):
                servicos.acao_todos(acao)
            else:
                for s in servicos.listar():
                    servicos.acao(s["nome"], acao)
        except Exception as e:
            raise ErroApi(503, "indisponivel", f"falha na operação global: {e}") from e
        return {"ok": True, "acao": acao}

    @router.post("/api/servicos/{nome}/{acao}")
    def acao_servico(nome: str, acao: str):
        if nome not in {s["nome"] for s in servicos.listar()}:
            raise ErroApi(404, "nao_encontrado", "serviço desconhecido")
        if acao not in ACOES:
            raise ErroApi(422, "validacao", "ação deve ser start, stop ou restart", campo="acao")
        try:
            servicos.acao(nome, acao)
        except ValueError as e:
            raise ErroApi(422, "validacao", str(e)) from e
        except RuntimeError as e:
            raise ErroApi(503, "indisponivel", str(e)) from e
        return {"ok": True}

    return router

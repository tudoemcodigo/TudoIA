"""Cadastro dinâmico de provedores e modelos."""

from fastapi import APIRouter


from ..erros import ErroApi
from ..provedores_service import (
    adicionar_modelo_provedor,
    adicionar_modelos_lote,
    buscar_listagens,
    cadastrar_provedor,
    descobrir_modelos_api,
    listar_novos_catalogo,
    sincronizar_catalogo,
)
from ..ambiente import Contexto
from ..schemas import CorpoModelosLote, CorpoNovoModeloProvedor, CorpoNovoProvedor, CorpoSincronizacao


def criar_router(ctx: Contexto) -> APIRouter:
    router = APIRouter()
    raiz = ctx.raiz
    trava = ctx.trava

    # ------------------------------------------------ gerenciamento dinâmico de provedores & modelos
    @router.post("/api/provedores")
    def criar_provedor(corpo: CorpoNovoProvedor):
        with trava:
            try:
                res = cadastrar_provedor(
                    raiz / "config" / "catalogo-modelos.yaml",
                    raiz / ".env",
                    corpo.model_dump(),
                    dir_backup=raiz / "dados" / "backups" / "env"
                )
            except ValueError as e:
                raise ErroApi(422, "validacao", str(e)) from e
        return res

    @router.get("/api/provedores/{provedor_id}/descobrir-modelos")
    def descobrir_modelos(provedor_id: str):
        try:
            return descobrir_modelos_api(
                raiz / "config" / "catalogo-modelos.yaml",
                raiz / ".env",
                provedor_id
            )
        except ValueError as e:
            raise ErroApi(404, "nao_encontrado", str(e)) from e
        except Exception as e:
            raise ErroApi(502, "conexao", f"Erro ao consultar API externa ({type(e).__name__}): {e}") from e

    @router.post("/api/provedores/{provedor_id}/modelos")
    def adicionar_modelo(provedor_id: str, corpo: CorpoNovoModeloProvedor):
        with trava:
            try:
                res = adicionar_modelo_provedor(
                    raiz / "config" / "catalogo-modelos.yaml",
                    provedor_id,
                    corpo.model_dump()
                )
            except ValueError as e:
                raise ErroApi(422, "validacao", str(e)) from e
            ctx.regenerar_litellm()
        return res

    @router.get("/api/provedores/novos")
    def listar_novos(provedor: str | None = None):
        try:
            return listar_novos_catalogo(raiz / "config" / "catalogo-modelos.yaml", raiz / ".env", provedor)
        except ValueError as e:
            raise ErroApi(404, "nao_encontrado", str(e)) from e

    @router.post("/api/provedores/sincronizar")
    def sincronizar_provedores(corpo: CorpoSincronizacao):
        # Rede fora da trava: com ela presa, toda gravação do painel esperava as ~10 APIs (até 10 s cada).
        listagens = buscar_listagens(raiz / "config" / "catalogo-modelos.yaml", raiz / ".env")
        with trava:
            res = sincronizar_catalogo(
                raiz / "config" / "catalogo-modelos.yaml",
                raiz / ".env",
                raiz / "config" / "roteamento.yaml",
                aplicar=corpo.aplicar,
                listagens=listagens,
            )
            if res["aplicado"]:
                res["litellm_regenerado"] = ctx.regenerar_litellm()
        return res

    @router.post("/api/provedores/modelos-lote")
    def adicionar_modelos_em_lote(corpo: CorpoModelosLote):
        with trava:
            res = adicionar_modelos_lote(
                raiz / "config" / "catalogo-modelos.yaml",
                [item.model_dump() for item in corpo.itens],
            )
            if res["adicionados"]:
                res["litellm_regenerado"] = ctx.regenerar_litellm()
        return res

    return router

"""Cadastro dinâmico de provedores e modelos."""

from fastapi import APIRouter


from ..erros import ErroApi
from ..provedores_service import (
    EmUsoNoRoteamento,
    ProvedorNaoEncontrado,
    adicionar_modelo_provedor,
    adicionar_modelos_lote,
    buscar_listagens,
    cadastrar_provedor,
    descobrir_modelos_api,
    editar_modelo_provedor,
    editar_provedor,
    listar_novos_catalogo,
    listar_provedores,
    obter_provedor,
    remover_modelo_provedor,
    remover_provedor,
    sincronizar_catalogo,
    testar_modelos_direto,
)
from ..ambiente import Contexto
from ..schemas import (
    CorpoEditarModeloProvedor,
    CorpoEditarProvedor,
    CorpoModelosLote,
    CorpoNovoModeloProvedor,
    CorpoNovoProvedor,
    CorpoSincronizacao,
    CorpoTestarModelos,
)


def criar_router(ctx: Contexto) -> APIRouter:
    router = APIRouter()
    raiz = ctx.raiz
    trava = ctx.trava
    catalogo = raiz / "config" / "catalogo-modelos.yaml"
    roteamento = raiz / "config" / "roteamento.yaml"
    env = raiz / ".env"

    def _em_uso(e: EmUsoNoRoteamento) -> ErroApi:
        return ErroApi(409, "em_uso_no_roteamento", str(e), extras={"referencias": e.referencias})

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

    @router.post("/api/provedores/{provedor_id}/testar-modelos")
    def testar_modelos(provedor_id: str, corpo: CorpoTestarModelos):
        # Direto na API do provedor, sem o LiteLLM: testa o que ainda não está no catálogo. Rede fora da trava
        # (até 40 chamadas de 20 s); só lê o catálogo e o .env.
        try:
            resultados = testar_modelos_direto(catalogo, env, provedor_id, corpo.ids)
        except ProvedorNaoEncontrado as e:
            raise ErroApi(404, "nao_encontrado", str(e)) from e
        return {"ok": True, "provedor": provedor_id, "resultados": resultados,
                "aprovados": sum(1 for r in resultados if r["ok"])}

    # ------------------------------------------------ CRUD (só admin: PREFIXOS_SO_ADMIN cobre /api/provedores)
    @router.get("/api/provedores")
    def listar():
        return listar_provedores(catalogo, env, roteamento)

    @router.patch("/api/provedores/{provedor_id}")
    def editar(provedor_id: str, corpo: CorpoEditarProvedor):
        with trava:
            try:
                if editar_provedor(catalogo, provedor_id, corpo.model_dump(exclude_unset=True)):
                    ctx.regenerar_litellm()
            except ProvedorNaoEncontrado as e:
                raise ErroApi(404, "nao_encontrado", str(e)) from e
            except ValueError as e:
                raise ErroApi(422, "validacao", str(e)) from e
            return obter_provedor(catalogo, env, roteamento, provedor_id)

    @router.delete("/api/provedores/{provedor_id}")
    def remover(provedor_id: str):
        with trava:
            try:
                res = remover_provedor(catalogo, roteamento, provedor_id)
            except ProvedorNaoEncontrado as e:
                raise ErroApi(404, "nao_encontrado", str(e)) from e
            except EmUsoNoRoteamento as e:
                raise _em_uso(e) from e
            res["litellm_regenerado"] = ctx.regenerar_litellm()
        return res

    @router.patch("/api/provedores/{provedor_id}/modelos/{nome:path}")
    def editar_modelo(provedor_id: str, nome: str, corpo: CorpoEditarModeloProvedor):
        with trava:
            try:
                res = editar_modelo_provedor(catalogo, provedor_id, nome, corpo.model_dump(exclude_unset=True))
            except ProvedorNaoEncontrado as e:
                raise ErroApi(404, "nao_encontrado", str(e)) from e
            if res["alterado"]:
                res["litellm_regenerado"] = ctx.regenerar_litellm()
        return res

    @router.delete("/api/provedores/{provedor_id}/modelos/{nome:path}")
    def remover_modelo(provedor_id: str, nome: str):
        with trava:
            try:
                res = remover_modelo_provedor(catalogo, roteamento, provedor_id, nome)
            except ProvedorNaoEncontrado as e:
                raise ErroApi(404, "nao_encontrado", str(e)) from e
            except EmUsoNoRoteamento as e:
                raise _em_uso(e) from e
            res["litellm_regenerado"] = ctx.regenerar_litellm()
        return res

    return router

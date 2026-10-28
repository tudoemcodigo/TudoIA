"""Roteador tudoia-auto: grupos, teste e geração do config do LiteLLM."""
import time

import httpx
from fastapi import APIRouter


from ..catalogo import carregar_catalogo, carregar_roteamento
from ..envfile import ler_env
from ..erros import ErroApi
from ..gerador import gerar_config, gravar_config, regenerar_config_litellm
from ..roteador_service import (
    auto_vincular_modelos_por_papeis,
    atualizar_grupo_roteador,
    criar_grupo_roteador,
    excluir_grupo_roteador,
    obter_detalhes_grupos_roteador,
    salvar_composicao_grupos,
)
from ..ambiente import Contexto
from ..schemas import CorpoCriarGrupo, CorpoEditarGrupo, CorpoOrdemGrupos, TesteRoteador
from .. import upstreams


def criar_router(ctx: Contexto) -> APIRouter:
    router = APIRouter()
    raiz = ctx.raiz
    trava = ctx.trava

    # ------------------------------------------------ roteador
    @router.get("/api/roteador")
    def info_roteador():
        rot = carregar_roteamento(raiz / "config" / "roteamento.yaml")
        return {
            "limiar": rot.get("limiar", 3),
            "pesos": rot.get("pesos", {}),
            "limites_texto": rot.get("limites_texto", {}),
            "ordem": rot.get("ordem", {}),
            "palavras_dificeis": rot.get("palavras_dificeis", []),
            "palavras_triviais": rot.get("palavras_triviais", [])
        }

    @router.post("/api/roteador/testar")
    def testar_roteador(corpo: TesteRoteador):
        env = ler_env(raiz / ".env")
        k = env.get("LITELLM_MASTER_KEY", "")
        modelo_alvo = corpo.modelo.strip() or "tudoia-auto"
        inicio = time.perf_counter()
        try:
            with httpx.Client(timeout=45.0) as cliente:
                resp = cliente.post(
                    f"{upstreams.LITELLM}/v1/chat/completions",
                    headers={"Authorization": f"Bearer {k}", "content-type": "application/json"},
                    json={"model": modelo_alvo, "messages": [{"role": "user", "content": corpo.mensagem}], "max_tokens": 100}
                )
                latencia_ms = int((time.perf_counter() - inicio) * 1000)
                if resp.status_code == 200:
                    dados = resp.json()
                    conteudo = dados.get("choices", [{}])[0].get("message", {}).get("content", "")
                    modelo_final = dados.get("model", modelo_alvo)
                    return {
                        "ok": True,
                        "modelo_solicitado": modelo_alvo,
                        "modelo_usado": modelo_final,
                        "latencia_ms": latencia_ms,
                        "resposta": conteudo
                    }
                else:
                    return {
                        "ok": False,
                        "modelo_solicitado": modelo_alvo,
                        "status_http": resp.status_code,
                        "erro": resp.text[:300],
                        "latencia_ms": latencia_ms
                    }
        except Exception as e:
            latencia_ms = int((time.perf_counter() - inicio) * 1000)
            return {"ok": False, "modelo_solicitado": modelo_alvo, "erro": f"LiteLLM indisponível: {e}", "latencia_ms": latencia_ms}

    @router.post("/api/roteador/gerar")
    def gerar():
        with trava:
            try:
                cfg = gerar_config(carregar_catalogo(raiz / "config" / "catalogo-modelos.yaml"),
                                   ler_env(raiz / ".env"), carregar_roteamento(raiz / "config" / "roteamento.yaml"))
                gravar_config(cfg, raiz / "runtime" / "litellm" / "config.yaml")
            except (OSError, ValueError, RuntimeError) as e:
                raise ErroApi(422, "validacao", f"não foi possível gerar o config ({type(e).__name__})") from e
        return {"ok": True, "modelos": len(cfg["model_list"])}

    @router.get("/api/roteador/detalhes")
    def detalhes_roteador():
        return obter_detalhes_grupos_roteador(raiz)

    @router.put("/api/roteador/grupos")
    def atualizar_grupos(corpo: CorpoOrdemGrupos):
        with trava:
            try:
                return salvar_composicao_grupos(raiz, corpo.ordem)
            except ValueError as e:
                raise ErroApi(422, "validacao", str(e)) from e

    @router.post("/api/roteador/auto-bind")
    def auto_bind_grupos():
        with trava:
            try:
                return auto_vincular_modelos_por_papeis(raiz)
            except ValueError as e:
                raise ErroApi(422, "validacao", str(e)) from e

    @router.post("/api/roteador/grupos/novo")
    def novo_grupo_roteador(corpo: CorpoCriarGrupo):
        with trava:
            try:
                res = criar_grupo_roteador(raiz, corpo.id, corpo.titulo, corpo.descricao, corpo.modelos)
                regenerar_config_litellm(raiz)
                return res
            except ValueError as e:
                raise ErroApi(422, "validacao", str(e)) from e

    @router.patch("/api/roteador/grupos/{grupo_id}")
    def editar_grupo_roteador(grupo_id: str, corpo: CorpoEditarGrupo):
        with trava:
            try:
                res = atualizar_grupo_roteador(
                    raiz,
                    grupo_id,
                    titulo=corpo.titulo,
                    descricao=corpo.descricao,
                    ativo=corpo.ativo,
                    modelos=corpo.modelos
                )
                regenerar_config_litellm(raiz)
                return res
            except ValueError as e:
                raise ErroApi(422, "validacao", str(e)) from e

    @router.delete("/api/roteador/grupos/{grupo_id}")
    def remover_grupo_roteador(grupo_id: str):
        with trava:
            try:
                res = excluir_grupo_roteador(raiz, grupo_id)
                regenerar_config_litellm(raiz)
                return res
            except ValueError as e:
                raise ErroApi(422, "validacao", str(e)) from e

    return router

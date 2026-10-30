"""Modelos locais e de mídia."""
import time

import httpx
from fastapi import APIRouter


from ..catalogo import carregar_catalogo
from ..envfile import ler_env
from ..erros import ErroApi
from ..gerador import regenerar_config_litellm
from ..modelos_service import (
    baixar_modelo_ollama,
    descarregar_modelo_vram,
    excluir_item_midia,
    excluir_modelo_ollama,
    ler_modelos_locais_desativados,
    listar_midia_detalhada,
    obter_modelos_em_vram,
    toggle_ativo_modelo_local,
    verificar_item_midia,
)
from ..provedores_service import (
    desativar_modelo_por_falha,
    falha_definitiva,
    litellm_sem_o_modelo,
)
from ..caminhos import modelfiles_ollama
from ..ambiente import Contexto
from ..schemas import CorpoBaixarModeloLocal, TesteModelo
from .. import upstreams


def criar_router(ctx: Contexto) -> APIRouter:
    router = APIRouter()
    raiz = ctx.raiz
    trava = ctx.trava

    # ------------------------------------------------ modelos
    @router.get("/api/modelos")
    def listar_modelos():
        catalogo = carregar_catalogo(raiz / "config" / "catalogo-modelos.yaml")
        env = ler_env(raiz / ".env")

        # Provedores de nuvem do catálogo
        provedores = []
        for p in catalogo.provedores:
            tem_chave = bool(env.get(p.chave))
            modelos_prov = [{
                "nome": m.nome,
                "id": m.id,
                "contexto": m.contexto,
                "papeis": list(m.papeis),
                "ativo": m.ativo
            } for m in p.modelos]
            provedores.append({
                "chave_id": p.chave_id,
                "nome": p.nome,
                "tier": p.tier,
                "chave": p.chave,
                "tem_chave": tem_chave,
                "site_chave": p.site_chave,
                "limites": p.limites,
                "modelos": modelos_prov
            })

        # Modelos locais (Ollama)
        desativados_locais = ler_modelos_locais_desativados(raiz)
        vram_locais = obter_modelos_em_vram()

        locais = []
        try:
            with httpx.Client(timeout=2.0) as cliente:
                resp = cliente.get(f"{upstreams.OLLAMA}/api/tags")
                if resp.status_code == 200:
                    for item in resp.json().get("models", []):
                        detalhes = item.get("details", {})
                        nome = item.get("name", "")
                        familia = detalhes.get("family", "")
                        is_emb = familia in ("bert", "nomic-bert") or "embed" in nome.lower() or "bge" in nome.lower()
                        em_vram_info = vram_locais.get(nome)
                        locais.append({
                            "nome": nome,
                            "tamanho_gb": round(item.get("size", 0) / (1024**3), 2),
                            "formato": detalhes.get("format", "gguf"),
                            "familia": familia,
                            "categoria": "Embedding" if is_emb else "LLM",
                            "quantizacao": detalhes.get("quantization_level", ""),
                            "ativo": nome not in desativados_locais,
                            "em_vram": em_vram_info is not None,
                            "vram_gb": em_vram_info.get("size_vram_gb", 0) if em_vram_info else 0
                        })
        except Exception:
            # Fallback para arquivos Modelfile locais
            for mf in modelfiles_ollama(raiz).glob("Modelfile.*"):
                nome = mf.name.replace("Modelfile.", "") + ":latest"
                locais.append({
                    "nome": nome,
                    "tamanho_gb": 0,
                    "formato": "Modelfile",
                    "familia": "local",
                    "quantizacao": "q4_k_m",
                    "ativo": nome not in desativados_locais,
                    "em_vram": False,
                    "vram_gb": 0
                })

        # Mídia (ComfyUI detalhado: checkpoints, diffusion_models, safetensors, gguf e workflows)
        midia_info = listar_midia_detalhada(raiz)

        return {
            "provedores": provedores,
            "locais": locais,
            "midia": midia_info
        }

    @router.post("/api/modelos/testar")
    def testar_modelo(corpo: TesteModelo):
        res = executar_teste_modelo(corpo)
        if litellm_sem_o_modelo(res):
            res["dica"] = "O LiteLLM ainda não carregou o config novo: reinicie o LiteLLM em Serviços e teste de novo."
        if falha_definitiva(res):
            # Provedor disse que o modelo não existe mais: sai do roteamento e fica inativo. Outras falhas só aparecem
            # no resultado. Modelo local ou fora do catálogo não casa.
            motivo = str(res.get("erro") or f"status {res.get('status_http', 0)}")
            with trava:
                desativacao = desativar_modelo_por_falha(
                    raiz / "config" / "catalogo-modelos.yaml",
                    raiz / "config" / "roteamento.yaml",
                    corpo.modelo.strip(),
                    motivo,
                )
                if desativacao["desativado"]:
                    res["desativado_automaticamente"] = True
                    res["removido_de_grupos"] = desativacao["removido_de_grupos"]
                    res["litellm_regenerado"] = ctx.regenerar_litellm()
        return res

    def executar_teste_modelo(corpo: TesteModelo):
        modelo = corpo.modelo.strip()
        tipo = corpo.tipo.strip().lower()
        inicio = time.perf_counter()

        if tipo == "midia" or modelo.startswith("midia:"):
            try:
                return verificar_item_midia(raiz, modelo)
            except Exception as e:
                latencia_ms = int((time.perf_counter() - inicio) * 1000)
                return {"ok": False, "modelo": modelo, "motor": "midia", "latencia_ms": latencia_ms, "status_http": 0, "erro": str(e)}

        e_ollama = tipo == "ollama" or (tipo == "auto" and ("/" not in modelo or modelo.startswith("ollama/")))
        try:
            if e_ollama:
                tag = modelo.removeprefix("ollama/")
                with httpx.Client(timeout=35.0) as cliente:
                    # 1. Tenta inferência gerativa padrão (chat / completion)
                    resp = cliente.post(
                        f"{upstreams.OLLAMA}/api/generate",
                        json={"model": tag, "prompt": "ping", "stream": False, "options": {"num_predict": 5}}
                    )
                    latencia_ms = int((time.perf_counter() - inicio) * 1000)
                    if resp.status_code == 200:
                        dados = resp.json()
                        resp_texto = dados.get("response", "").strip() or "ok"
                        return {"ok": True, "modelo": modelo, "motor": "ollama", "latencia_ms": latencia_ms, "resposta": resp_texto, "status_http": 200}

                    # 2. Se for modelo de Embedding (como bge-m3), o Ollama retorna 'does not support generate'
                    if "does not support generate" in resp.text:
                        resp_emb = cliente.post(
                            f"{upstreams.OLLAMA}/api/embed",
                            json={"model": tag, "input": "ping"}
                        )
                        if resp_emb.status_code != 200:
                            resp_emb = cliente.post(
                                f"{upstreams.OLLAMA}/api/embeddings",
                                json={"model": tag, "prompt": "ping"}
                            )
                        latencia_ms = int((time.perf_counter() - inicio) * 1000)
                        if resp_emb.status_code == 200:
                            d_emb = resp_emb.json()
                            vetor = d_emb.get("embeddings", [[]])[0] if "embeddings" in d_emb else d_emb.get("embedding", [])
                            dims = len(vetor)
                            return {
                                "ok": True,
                                "modelo": modelo,
                                "motor": "ollama (embed)",
                                "latencia_ms": latencia_ms,
                                "resposta": f"Embedding ({dims}d)",
                                "status_http": 200
                            }
                        return {"ok": False, "modelo": modelo, "motor": "ollama", "latencia_ms": latencia_ms, "status_http": resp_emb.status_code, "erro": resp_emb.text[:200]}

                    return {"ok": False, "modelo": modelo, "motor": "ollama", "latencia_ms": latencia_ms, "status_http": resp.status_code, "erro": resp.text[:200]}
            else:
                env = ler_env(raiz / ".env")
                k = env.get("LITELLM_MASTER_KEY", "")
                with httpx.Client(timeout=25.0) as cliente:
                    resp = cliente.post(
                        f"{upstreams.LITELLM}/v1/chat/completions",
                        headers={"Authorization": f"Bearer {k}", "content-type": "application/json"},
                        json={"model": modelo, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 5}
                    )
                    latencia_ms = int((time.perf_counter() - inicio) * 1000)
                    if resp.status_code == 200:
                        try:
                            dados = resp.json()
                            choices = dados.get("choices") if isinstance(dados, dict) else []
                            conteudo = ""
                            if isinstance(choices, list) and len(choices) > 0 and isinstance(choices[0], dict):
                                msg = choices[0].get("message")
                                if isinstance(msg, dict):
                                    conteudo = (msg.get("content") or "").strip()
                                elif isinstance(msg, str):
                                    conteudo = msg.strip()
                                elif "text" in choices[0]:
                                    conteudo = str(choices[0].get("text") or "").strip()
                            if not conteudo:
                                conteudo = "ok"
                            return {"ok": True, "modelo": modelo, "motor": "litellm", "latencia_ms": latencia_ms, "resposta": conteudo, "status_http": 200}
                        except Exception:
                            return {"ok": True, "modelo": modelo, "motor": "litellm", "latencia_ms": latencia_ms, "resposta": "ok (HTTP 200)", "status_http": 200}
                    else:
                        erro_amigavel = ""
                        try:
                            d_err = resp.json()
                            if isinstance(d_err, dict):
                                erro_obj = d_err.get("error")
                                if isinstance(erro_obj, dict):
                                    erro_amigavel = str(erro_obj.get("message") or "")
                                elif isinstance(erro_obj, str):
                                    erro_amigavel = erro_obj
                        except Exception:
                            pass
                        if not erro_amigavel:
                            erro_amigavel = resp.text.strip()
                        if "/chat/completions is not supported" in erro_amigavel:
                            erro_amigavel = "Não suporta chat (modelo de embedding)"
                        elif "Rate limit" in erro_amigavel or resp.status_code == 429:
                            erro_amigavel = "Rate limit excedido (429)"
                        elif "timed out" in erro_amigavel.lower() or resp.status_code == 408:
                            erro_amigavel = "Timeout do provedor (>25s)"
                        elif "Unauthorized" in erro_amigavel or resp.status_code == 401:
                            erro_amigavel = "Chave de API inválida (401)"
                        return {"ok": False, "modelo": modelo, "motor": "litellm", "latencia_ms": latencia_ms, "status_http": resp.status_code, "erro": erro_amigavel[:120]}
        except httpx.TimeoutException:
            latencia_ms = int((time.perf_counter() - inicio) * 1000)
            return {"ok": False, "modelo": modelo, "motor": "ollama" if e_ollama else "litellm", "latencia_ms": latencia_ms, "status_http": 408, "erro": "Timeout (>25s)"}
        except Exception as e:
            latencia_ms = int((time.perf_counter() - inicio) * 1000)
            err_msg = str(e)
            if "timed out" in err_msg.lower():
                err_msg = "Timeout (>25s)"
            return {"ok": False, "modelo": modelo, "motor": "ollama" if e_ollama else "litellm", "latencia_ms": latencia_ms, "status_http": 0, "erro": err_msg[:120]}

    @router.post("/api/modelos/local/baixar")
    def baixar_modelo(corpo: CorpoBaixarModeloLocal):
        try:
            return baixar_modelo_ollama(corpo.nome)
        except ValueError as e:
            raise ErroApi(422, "validacao", str(e), campo="nome") from e
        except TimeoutError as e:
            raise ErroApi(408, "timeout", str(e)) from e
        except Exception as e:
            raise ErroApi(500, "erro_ollama", str(e)) from e

    @router.delete("/api/modelos/local/{nome_modelo:path}")
    def excluir_modelo(nome_modelo: str):
        try:
            return excluir_modelo_ollama(nome_modelo)
        except Exception as e:
            raise ErroApi(500, "erro_ollama", str(e)) from e

    @router.post("/api/modelos/local/{nome_modelo:path}/descarregar")
    def descarregar_modelo(nome_modelo: str):
        try:
            res = descarregar_modelo_vram(nome_modelo)
            if not res.get("ok"):
                raise ErroApi(500, "erro_ollama", res.get("erro", "Falha ao descarregar da VRAM"))
            return res
        except ErroApi:
            raise
        except Exception as e:
            raise ErroApi(500, "erro_ollama", str(e)) from e

    @router.post("/api/modelos/local/{nome_modelo:path}/toggle-ativo")
    def toggle_ativo_local(nome_modelo: str):
        with trava:
            try:
                res = toggle_ativo_modelo_local(raiz, nome_modelo)
                regenerar_config_litellm(raiz)
                return res
            except Exception as e:
                raise ErroApi(500, "erro_toggle", str(e)) from e

    @router.delete("/api/modelos/midia/{item_id:path}")
    def excluir_midia(item_id: str):
        with trava:
            try:
                return excluir_item_midia(raiz, item_id)
            except ValueError as e:
                raise ErroApi(422, "validacao", str(e)) from e
            except FileNotFoundError as e:
                raise ErroApi(404, "nao_encontrado", str(e)) from e
            except Exception as e:
                raise ErroApi(500, "erro_midia", str(e)) from e

    return router

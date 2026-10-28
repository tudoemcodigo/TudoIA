"""Chat do painel pelo gateway LiteLLM, com queda para o Ollama."""
import logging
import time

import httpx
from fastapi import APIRouter


from ..envfile import ler_env
from ..ambiente import Contexto
from ..erros import ErroApi
from ..schemas import ChatReq
from .. import upstreams


log = logging.getLogger(__name__)


def criar_router(ctx: Contexto) -> APIRouter:
    router = APIRouter()
    raiz = ctx.raiz

    @router.post("/api/chat/completions")
    def chat_completions(corpo: ChatReq):
        env = ler_env(raiz / ".env")
        k = env.get("LITELLM_MASTER_KEY", "")
        modelo_alvo = corpo.model.strip() or "tudoia-auto"
        inicio = time.perf_counter()

        # 1. Tenta gateway LiteLLM (:4000)
        try:
            with httpx.Client(timeout=60.0) as cliente:
                resp = cliente.post(
                    f"{upstreams.LITELLM}/v1/chat/completions",
                    headers={"Authorization": f"Bearer {k}", "content-type": "application/json"},
                    json={
                        "model": modelo_alvo,
                        "messages": [m.model_dump() for m in corpo.messages],
                        "temperature": corpo.temperature,
                        "max_tokens": corpo.max_tokens,
                    }
                )
                latencia_ms = int((time.perf_counter() - inicio) * 1000)
                if resp.status_code == 200:
                    dados = resp.json()
                    msg = dados.get("choices", [{}])[0].get("message", {})
                    return {
                        "ok": True,
                        "motor": "litellm",
                        "model": dados.get("model", modelo_alvo),
                        "message": msg,
                        "usage": dados.get("usage", {}),
                        "latencia_ms": latencia_ms,
                    }
        except Exception as e:
            log.warning("chat: LiteLLM falhou (%s); tentando o Ollama", type(e).__name__)

        # 2. Fallback direto para Ollama (:11434) se for modelo local ou LiteLLM estiver offline
        try:
            with httpx.Client(timeout=45.0) as cliente:
                resp_ollama = cliente.post(
                    f"{upstreams.OLLAMA}/api/chat",
                    json={
                        "model": modelo_alvo.replace("ollama/", ""),
                        "messages": [m.model_dump() for m in corpo.messages],
                        "stream": False,
                        "options": {"temperature": corpo.temperature}
                    }
                )
                latencia_ms = int((time.perf_counter() - inicio) * 1000)
                if resp_ollama.status_code == 200:
                    d = resp_ollama.json()
                    return {
                        "ok": True,
                        "motor": "ollama",
                        "model": modelo_alvo,
                        "message": d.get("message", {}),
                        "usage": {"total_tokens": d.get("eval_count", 0)},
                        "latencia_ms": latencia_ms,
                    }
        except Exception as e:
            latencia_ms = int((time.perf_counter() - inicio) * 1000)
            log.warning("chat: Ollama também falhou (%s)", type(e).__name__)
            raise ErroApi(502, "modelo_indisponivel", "Motores LiteLLM e Ollama inacessíveis.", extras={"model": modelo_alvo, "latencia_ms": latencia_ms}) from e

        latencia_ms = int((time.perf_counter() - inicio) * 1000)
        raise ErroApi(502, "modelo_indisponivel", f"Não foi possível obter resposta do modelo {modelo_alvo}.", extras={"model": modelo_alvo, "latencia_ms": latencia_ms})

    return router

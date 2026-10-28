"""Telemetria e limites por provedor."""

import httpx
from fastapi import APIRouter


from ..envfile import ler_env
from ..limites import ler_logs_litellm, obter_metricas_limites
from ..ambiente import Contexto
from ..estudio_servico import HISTORICO_VISUAL
from .. import upstreams


def criar_router(ctx: Contexto) -> APIRouter:
    router = APIRouter()
    raiz = ctx.raiz

    # ------------------------------------------------ telemetria
    @router.get("/api/telemetria")
    def telemetria():
        env = ler_env(raiz / ".env")
        k = env.get("LITELLM_MASTER_KEY", "")

        # Últimas 24 h (era o histórico inteiro: ~27 MB a cada atualização da tela)
        logs_litellm = ler_logs_litellm(k, 24)

        vram_modelos = []
        try:
            with httpx.Client(timeout=2.0) as cliente:
                resp = cliente.get(f"{upstreams.OLLAMA}/api/ps")
                if resp.status_code == 200:
                    vram_modelos = resp.json().get("models", [])
        except Exception:
            vram_modelos = []

        total_requisicoes = len(logs_litellm)
        total_tokens = sum(log.get("total_tokens", 0) or 0 for log in logs_litellm)
        custo_total = sum(float(log.get("spend", 0.0) or 0.0) for log in logs_litellm)

        amostra_recente = logs_litellm[:30]
        latencias = [log.get("request_duration_ms", 0) for log in amostra_recente if log.get("request_duration_ms")]
        latencia_media = int(sum(latencias) / len(latencias)) if latencias else 0

        falhas = sum(1 for log in amostra_recente if str(log.get("status", "")).lower() == "failure")
        taxa_sucesso = round(100.0 * (len(amostra_recente) - falhas) / len(amostra_recente), 1) if amostra_recente else 100.0

        feed = []
        for item in amostra_recente:
            meta = item.get("metadata") or {}
            feed.append({
                "id": str(item.get("request_id", "")),
                "inicio": str(item.get("startTime", "")),
                "modelo": str(item.get("model", "")),
                "grupo": str(item.get("model_group", "") or "geral"),
                "total_tokens": int(item.get("total_tokens", 0) or 0),
                "prompt_tokens": int(item.get("prompt_tokens", 0) or 0),
                "completion_tokens": int(item.get("completion_tokens", 0) or 0),
                "latencia_ms": int(item.get("request_duration_ms", 0) or 0),
                "custo": float(item.get("spend", 0.0) or 0.0),
                "status": str(item.get("status", "success")),
                "cliente": str(meta.get("user_agent", "") or item.get("user", "agente"))
            })

        vram_formatada = []
        for vm in vram_modelos:
            vram_formatada.append({
                "nome": vm.get("name", ""),
                "tamanho_mb": round((vm.get("size", 0) or 0) / (1024 * 1024), 1),
                "tamanho_vram_mb": round((vm.get("size_vram", 0) or 0) / (1024 * 1024), 1),
                "contexto": vm.get("context_length", 0),
                "expira_em": vm.get("expires_at", "")
            })

        comfy_telemetria = {
            "ativo": False,
            "gpu_nome": "GPU NVIDIA",
            "vram_total_mb": 0,
            "vram_livre_mb": 0,
            "vram_usada_mb": 0,
            "vram_pct_usada": 0,
            "ram_total_gb": 0,
            "ram_livre_gb": 0,
            "fila_executando": 0,
            "fila_pendente": 0,
        }
        try:
            with httpx.Client(timeout=1.2) as cliente:
                r_stats = cliente.get(f"{upstreams.COMFYUI}/system_stats")
                if r_stats.status_code == 200:
                    dados_stats = r_stats.json()
                    comfy_telemetria["ativo"] = True
                    sys_info = dados_stats.get("system", {})
                    comfy_telemetria["ram_total_gb"] = round(sys_info.get("ram_total", 0) / (1024**3), 1)
                    comfy_telemetria["ram_livre_gb"] = round(sys_info.get("ram_free", 0) / (1024**3), 1)
                    devices = dados_stats.get("devices", [])
                    for dev in devices:
                        if dev.get("type") == "cuda":
                            total = dev.get("vram_total", 0)
                            livre = dev.get("vram_free", 0)
                            usada = max(0, total - livre)
                            nome_gpu = dev.get("name", "NVIDIA RTX")
                            if ":" in nome_gpu:
                                partes = nome_gpu.split(":")
                                nome_gpu = partes[1].strip() if len(partes) > 1 else partes[0].strip()
                            comfy_telemetria["gpu_nome"] = nome_gpu
                            comfy_telemetria["vram_total_mb"] = round(total / (1024 * 1024), 1)
                            comfy_telemetria["vram_livre_mb"] = round(livre / (1024 * 1024), 1)
                            comfy_telemetria["vram_usada_mb"] = round(usada / (1024 * 1024), 1)
                            comfy_telemetria["vram_pct_usada"] = round((usada / total) * 100, 1) if total else 0
                            break

                r_queue = cliente.get(f"{upstreams.COMFYUI}/queue")
                if r_queue.status_code == 200:
                    dados_queue = r_queue.json()
                    comfy_telemetria["fila_executando"] = len(dados_queue.get("queue_running", []))
                    comfy_telemetria["fila_pendente"] = len(dados_queue.get("queue_pending", []))
        except Exception:
            pass

        return {
            "total_requisicoes": total_requisicoes,
            "total_tokens": total_tokens,
            "custo_total_usd": round(custo_total, 5),
            "latencia_media_ms": latencia_media,
            "taxa_sucesso": taxa_sucesso,
            "vram_modelos": vram_formatada,
            "feed": feed,
            "comfyui": comfy_telemetria,
            "feed_visual": list(HISTORICO_VISUAL),
        }

    # limites & tokens por provedor
    @router.get("/api/limites-tokens")
    def limites_tokens(periodo: str = "24h"):
        horas = None if periodo == "total" else 24
        if periodo.endswith("h") and periodo[:-1].isdigit():
            horas = int(periodo[:-1])
        elif periodo.endswith("d") and periodo[:-1].isdigit():
            horas = int(periodo[:-1]) * 24
        return obter_metricas_limites(raiz, periodo_horas=horas)

    return router

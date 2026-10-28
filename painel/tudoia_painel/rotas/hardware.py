"""Hardware e VRAM do host."""
import subprocess

import httpx
from fastapi import APIRouter


from ..ambiente import Contexto
from .. import upstreams


def criar_router(ctx: Contexto) -> APIRouter:
    router = APIRouter()


    # ------------------------------------------------ hardware & servidor
    @router.get("/api/hardware")
    def status_hardware():
        import psutil
        cpu_pct = psutil.cpu_percent(interval=None)
        cpu_freq = psutil.cpu_freq()
        ram = psutil.virtual_memory()

        gpu_info = {
            "nome": "GPU NVIDIA",
            "utilizacao": 0.0,
            "vram_total_mb": 8151.0,
            "vram_usada_mb": 0.0,
            "vram_livre_mb": 8151.0,
            "temp_c": 0.0
        }
        try:
            cmd = ["nvidia-smi", "--query-gpu=utilization.gpu,memory.total,memory.used,memory.free,temperature.gpu,name", "--format=csv,noheader,nounits"]
            res = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=2.0)
            parts = [p.strip() for p in res.stdout.strip().split(",")]
            if len(parts) >= 6:
                gpu_info = {
                    "utilizacao": float(parts[0]),
                    "vram_total_mb": float(parts[1]),
                    "vram_usada_mb": float(parts[2]),
                    "vram_livre_mb": float(parts[3]),
                    "temp_c": float(parts[4]),
                    "nome": parts[5]
                }
        except Exception:
            pass

        discos = []
        for d in ("D:\\", "C:\\"):
            try:
                du = psutil.disk_usage(d)
                discos.append({
                    "drive": d[:2],
                    "total_gb": round(du.total / (1024**3), 1),
                    "usado_gb": round(du.used / (1024**3), 1),
                    "livre_gb": round(du.free / (1024**3), 1),
                    "pct": du.percent
                })
            except Exception:
                pass

        vram_total_gb = round(gpu_info["vram_total_mb"] / 1024, 1)
        vram_usada_gb = round(gpu_info["vram_usada_mb"] / 1024, 1)
        vram_livre_gb = round(gpu_info["vram_livre_mb"] / 1024, 1)
        vram_pct = round(100.0 * gpu_info["vram_usada_mb"] / max(gpu_info["vram_total_mb"], 1), 1)

        return {
            "cpu": {
                "pct": cpu_pct,
                "cores_fisicos": psutil.cpu_count(logical=False) or 8,
                "cores_logicos": psutil.cpu_count(logical=True) or 16,
                "freq_mhz": round(cpu_freq.current, 0) if cpu_freq else 0
            },
            "ram": {
                "total_gb": round(ram.total / (1024**3), 1),
                "usada_gb": round(ram.used / (1024**3), 1),
                "livre_gb": round(ram.available / (1024**3), 1),
                "pct": ram.percent
            },
            "gpu": {
                "nome": gpu_info["nome"],
                "utilizacao_pct": gpu_info["utilizacao"],
                "temp_c": gpu_info["temp_c"],
                "vram_total_gb": vram_total_gb,
                "vram_usada_gb": vram_usada_gb,
                "vram_livre_gb": vram_livre_gb,
                "vram_pct": vram_pct
            },
            "discos": discos
        }

    @router.post("/api/hardware/limpar-vram")
    def limpar_vram():
        vram_antes_mb = 0.0
        try:
            cmd = ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"]
            res = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=2.0)
            vram_antes_mb = float(res.stdout.strip().splitlines()[0])
        except Exception:
            pass

        modelos_descarregados = []
        try:
            with httpx.Client(timeout=3.0) as cliente:
                ps = cliente.get(f"{upstreams.OLLAMA}/api/ps").json()
                for m in ps.get("models", []):
                    nome_m = m.get("name")
                    if nome_m:
                        cliente.post(f"{upstreams.OLLAMA}/api/generate", json={"model": nome_m, "keep_alive": 0}, timeout=4.0)
                        modelos_descarregados.append(nome_m)
        except Exception:
            pass

        vram_depois_mb = vram_antes_mb
        vram_livre_mb = 0.0
        try:
            cmd = ["nvidia-smi", "--query-gpu=memory.used,memory.free", "--format=csv,noheader,nounits"]
            res = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=2.0)
            parts = [float(p.strip()) for p in res.stdout.strip().splitlines()[0].split(",")]
            vram_depois_mb = parts[0]
            vram_livre_mb = parts[1]
        except Exception:
            pass

        liberada_mb = max(0, int(vram_antes_mb - vram_depois_mb))
        nomes_str = ", ".join(modelos_descarregados) if modelos_descarregados else "nenhum modelo ativo no Ollama"
        return {
            "ok": True,
            "modelos": modelos_descarregados,
            "vram_antes_mb": vram_antes_mb,
            "vram_depois_mb": vram_depois_mb,
            "vram_liberada_mb": liberada_mb,
            "vram_livre_gb": round(vram_livre_mb / 1024, 1),
            "mensagem": f"{liberada_mb} MB de VRAM liberados ({nomes_str})"
        }

    return router

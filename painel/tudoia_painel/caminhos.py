"""Caminhos do TudoIA. TUDOIA_RAIZ troca a raiz (usado pelos testes e por outra instalação)."""
import os
from pathlib import Path


def raiz() -> Path:
    env_raiz = os.environ.get("TUDOIA_RAIZ")
    if env_raiz and Path(env_raiz).exists():
        return Path(env_raiz)
    return Path(__file__).resolve().parents[2]


def env() -> Path:
    return raiz() / ".env"


def catalogo() -> Path:
    return raiz() / "config" / "catalogo-modelos.yaml"


def roteamento() -> Path:
    return raiz() / "config" / "roteamento.yaml"


def config_litellm() -> Path:
    return raiz() / "runtime" / "litellm" / "config.yaml"


def regras_roteador() -> Path:
    return raiz() / "runtime" / "litellm" / "roteador_regras.py"


def logs() -> Path:
    return raiz() / "dados" / "logs"


def backups_env() -> Path:
    return raiz() / "dados" / "backups" / "env"


def quarentena_json() -> Path:
    return raiz() / "dados" / "logs" / "quarentena.json"


def _configurado(raiz_: Path, chave: str, padrao: Path) -> Path:
    """Valor de `chave` no ambiente ou no .env da raiz informada; senão o caminho padrão."""
    from .envfile import ler_env

    valor = os.environ.get(chave) or ler_env(raiz_ / ".env").get(chave, "")
    return Path(valor.strip()) if valor.strip() else padrao


def comfyui_portable(raiz_: Path) -> Path:
    """Pasta do ComfyUI portable (run_*.bat e a pasta ComfyUI). Troque com TUDOIA_COMFYUI_PORTABLE."""
    return _configurado(raiz_, "TUDOIA_COMFYUI_PORTABLE", raiz_ / "modelos" / "comfyui" / "ComfyUI_windows_portable")


def comfyui_dir(raiz_: Path) -> Path:
    """Pasta ComfyUI de dentro do portable (input, output, models, user)."""
    return comfyui_portable(raiz_) / "ComfyUI"


def modelfiles_ollama(raiz_: Path) -> Path:
    """Modelfiles versionados para `ollama create`."""
    return raiz_ / "runtime" / "ollama" / "modelfiles"


def pesos_ollama(raiz_: Path) -> Path:
    """Pasta de pesos do Ollama (OLLAMA_MODELS). Troque com TUDOIA_OLLAMA_MODELS."""
    return _configurado(raiz_, "TUDOIA_OLLAMA_MODELS", raiz_ / "modelos" / "ollama" / "models")

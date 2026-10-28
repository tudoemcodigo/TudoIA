"""Contexto compartilhado pelos routers: raiz do projeto, home, serviços e a trava de escrita em arquivos de config."""
import threading
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Any

from .autenticacao import ConfigAuth
from .estudio_servico import PastasEstudio
from .gerador import regenerar_config_litellm


@dataclass
class Contexto:
    raiz: Path
    home: Path
    servicos: Any
    config_auth: ConfigAuth | None
    # Uma trava para tudo que lê-edita-grava .env, governanca.json, mcp.json e o catálogo de modelos.
    trava: threading.Lock = field(default_factory=threading.Lock)

    @cached_property
    def pastas_estudio(self) -> PastasEstudio:
        pastas = PastasEstudio.de(self.raiz)
        pastas.garantir()
        return pastas

    def regenerar_litellm(self) -> bool:
        return regenerar_config_litellm(self.raiz)

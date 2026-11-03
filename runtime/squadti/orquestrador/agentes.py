"""
Configuração dos agentes da Squad: modelo, temperatura, limite de saída e modo de revisão por papel, mais o orçamento da tarefa.

O painel edita este arquivo pela API; ao iniciar uma tarefa a configuração vigente é COPIADA para o estado dela (a tarefa não muda
de comportamento no meio por causa de uma edição). Tudo é validado e limitado aqui: valor fora da faixa é recusado, nunca "ajustado
em silêncio", e um modelo que pode sair da máquina só vale se a tarefa tiver consentimento explícito de nuvem.
"""
import json
import os
import threading
from pathlib import Path
from typing import Optional

from perfis import PERFIS, modelo_e_local

# Papéis com modelo (o CHEFE é o canal único do usuário; os demais agentes falam com ele, não com você).
AGENTES = ("chefe", "analista", "arquiteto", "dba", "backend", "frontend", "revisor", "senior", "hacker", "mantenedor",
           "documentacao")
TEMPERATURA = (0.0, 1.5)
MAX_TOKENS = (256, 32000)
MODOS_REVISAO = ("simples", "dupla")
MODOS_VALIDACAO = ("auto", "sempre", "nunca")   # validação em execução (macaco, hacker, carga): auto = roda se o Docker responder
PERFIS_CARGA = ("escalado", "completo", "nunca")
SLO_LIMITES = {"p95_ms": (50.0, 60_000.0), "p99_ms": (50.0, 120_000.0), "erro_max": (0.0, 1.0)}
UI_SEGUNDOS = (10, 600)
ORCAMENTO_LIMITES = {"tokens": (1_000, 50_000_000), "tempo_s": (60, 86_400), "chamadas": (1, 10_000)}

PADRAO_AGENTE = {"perfil": None, "temperatura": 0.1, "max_tokens": None}  # perfil None = o da tarefa
PADRAO = {
    "agentes": {a: dict(PADRAO_AGENTE) for a in AGENTES},
    "revisao": {"modo": "simples"},
    "validacao": {"modo": "auto", "carga": "escalado", "slo": {"p95_ms": 800.0, "p99_ms": 2000.0, "erro_max": 0.01}, "ui_segundos": 60},
    "orcamento": {"tokens": 2_000_000, "tempo_s": 7200, "chamadas": 300},
}


class ConfigInvalida(ValueError):
    pass


def validar(cfg: Optional[dict]) -> dict:
    """Config completa e normalizada a partir de uma parcial. Qualquer campo desconhecido ou fora da faixa levanta ConfigInvalida."""
    cfg = cfg or {}
    desconhecidos = set(cfg) - set(PADRAO)
    if desconhecidos:
        raise ConfigInvalida(f"campo(s) desconhecido(s): {sorted(desconhecidos)}")
    saida = json.loads(json.dumps(PADRAO))  # cópia profunda
    for nome, valores in (cfg.get("agentes") or {}).items():
        if nome not in AGENTES:
            raise ConfigInvalida(f"agente desconhecido: {nome!r} (use um de {list(AGENTES)})")
        extra = set(valores) - set(PADRAO_AGENTE)
        if extra:
            raise ConfigInvalida(f"agente {nome}: campo(s) desconhecido(s): {sorted(extra)}")
        alvo = saida["agentes"][nome]
        if valores.get("perfil") is not None:
            if valores["perfil"] not in PERFIS:
                raise ConfigInvalida(f"agente {nome}: perfil inválido {valores['perfil']!r} (use um de {sorted(PERFIS)})")
            alvo["perfil"] = valores["perfil"]
        if "temperatura" in valores:
            t = valores["temperatura"]
            if isinstance(t, bool) or not isinstance(t, (int, float)) or not TEMPERATURA[0] <= t <= TEMPERATURA[1]:
                raise ConfigInvalida(f"agente {nome}: temperatura deve estar entre {TEMPERATURA[0]} e {TEMPERATURA[1]}")
            alvo["temperatura"] = float(t)
        if valores.get("max_tokens") is not None:
            m = valores["max_tokens"]
            if isinstance(m, bool) or not isinstance(m, int) or not MAX_TOKENS[0] <= m <= MAX_TOKENS[1]:
                raise ConfigInvalida(f"agente {nome}: max_tokens deve ser inteiro entre {MAX_TOKENS[0]} e {MAX_TOKENS[1]}")
            alvo["max_tokens"] = m
    modo = (cfg.get("revisao") or {}).get("modo", "simples")
    if modo not in MODOS_REVISAO:
        raise ConfigInvalida(f"revisao.modo deve ser um de {list(MODOS_REVISAO)}")
    saida["revisao"] = {"modo": modo}
    val = cfg.get("validacao") or {}
    extra = set(val) - set(PADRAO["validacao"])
    if extra:
        raise ConfigInvalida(f"validacao: campo(s) desconhecido(s): {sorted(extra)}")
    if val.get("modo", "auto") not in MODOS_VALIDACAO:
        raise ConfigInvalida(f"validacao.modo deve ser um de {list(MODOS_VALIDACAO)}")
    if val.get("carga", "escalado") not in PERFIS_CARGA:
        raise ConfigInvalida(f"validacao.carga deve ser um de {list(PERFIS_CARGA)}")
    ui = val.get("ui_segundos", 60)
    if isinstance(ui, bool) or not isinstance(ui, int) or not UI_SEGUNDOS[0] <= ui <= UI_SEGUNDOS[1]:
        raise ConfigInvalida(f"validacao.ui_segundos deve ser inteiro entre {UI_SEGUNDOS[0]} e {UI_SEGUNDOS[1]}")
    slo = {**PADRAO["validacao"]["slo"]}
    for chave, valor in (val.get("slo") or {}).items():
        if chave not in SLO_LIMITES:
            raise ConfigInvalida(f"validacao.slo: campo desconhecido {chave!r} (use {sorted(SLO_LIMITES)})")
        lo, hi = SLO_LIMITES[chave]
        if isinstance(valor, bool) or not isinstance(valor, (int, float)) or not lo <= valor <= hi:
            raise ConfigInvalida(f"validacao.slo.{chave} deve estar entre {lo} e {hi}")
        slo[chave] = float(valor)
    saida["validacao"] = {"modo": val.get("modo", "auto"), "carga": val.get("carga", "escalado"), "slo": slo, "ui_segundos": ui}
    for eixo, valor in (cfg.get("orcamento") or {}).items():
        if eixo not in ORCAMENTO_LIMITES:
            raise ConfigInvalida(f"orcamento: eixo desconhecido {eixo!r} (use {sorted(ORCAMENTO_LIMITES)})")
        if valor is None:
            saida["orcamento"][eixo] = None
            continue
        lo, hi = ORCAMENTO_LIMITES[eixo]
        if isinstance(valor, bool) or not isinstance(valor, int) or not lo <= valor <= hi:
            raise ConfigInvalida(f"orcamento.{eixo} deve ser inteiro entre {lo} e {hi} (ou nulo para sem limite)")
        saida["orcamento"][eixo] = valor
    return saida


def modelos_que_saem_da_maquina(cfg: dict) -> list:
    """Agentes cujo perfil pode enviar código e esquema para a nuvem (exigem consentimento da tarefa)."""
    return [a for a, v in cfg["agentes"].items() if v["perfil"] and not modelo_e_local(PERFIS[v["perfil"]])]


# ---------------------------------------------------------------- persistência (volume do container)
_TRAVA = threading.Lock()


def caminho() -> Path:
    return Path(os.getenv("SQUADTI_AGENTES_ARQUIVO", "agentes.json"))


def carregar() -> dict:
    """Configuração salva; arquivo ausente = padrão; arquivo corrompido = erro visível (nunca cai em silêncio no padrão)."""
    p = caminho()
    with _TRAVA:
        if not p.is_file():
            return validar(None)
        try:
            return validar(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, ValueError) as e:
            raise ConfigInvalida(f"{p.name} ilegível ou inválido: {e}") from e


def salvar(cfg: dict) -> dict:
    final = validar(cfg)
    p = caminho()
    with _TRAVA:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(final, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(p)
    return final


def do_estado(state: Optional[dict]) -> dict:
    """Config da tarefa (copiada ao iniciar). Tarefa antiga sem config usa o padrão."""
    return validar((state or {}).get("agentes_cfg"))

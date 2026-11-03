"""
Proveniência da entrega: quem (qual modelo) fez o quê, sob qual Doutrina, com quais aprovações e qual o hash de cada arquivo.

É o que permite auditar uma entrega meses depois: a versão e o hash da Doutrina, o modelo e o hash do prompt de cada chamada, os
tokens e o tempo gastos, os hashes das aprovações humanas e o hash de cada arquivo gerado. Não contém prompt nem resposta de modelo
(só o hash do prompt) e nenhum segredo.
"""
import hashlib
import time
from pathlib import Path
from typing import List

import auditoria
from execucao import caminho_seguro

ARQUIVO = "docs/proveniencia.json"
MAX_ARQUIVOS = 500
MAX_BYTES = 5_000_000


def _hash(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(65536), b""):
            h.update(bloco)
    return h.hexdigest()


def _arquivos(raiz: Path, relativos: List[str]) -> List[dict]:
    saida = []
    for rel in sorted(set(relativos))[:MAX_ARQUIVOS]:
        try:
            destino = caminho_seguro(raiz, rel)
            if destino.is_file() and destino.stat().st_size <= MAX_BYTES:
                saida.append({"caminho": rel, "sha256": _hash(destino)})
        except (ValueError, OSError):
            continue
    return saida


def gerar(state: dict, raiz: Path) -> dict:
    registros = state.get("auditoria") or []
    chamadas = [{"no": r.get("no"), "agente": c.get("agente"), "modelo": c.get("modelo"), "tentativa": c.get("tentativa"),
                 "tokens_entrada": c.get("tokens_entrada"), "tokens_saida": c.get("tokens_saida"), "duracao_s": c.get("duracao_s"),
                 "prompt_sha": c.get("prompt_sha")}
                for r in registros for c in (r.get("detalhe") or [])]
    modelos = {}
    for c in chamadas:
        modelos.setdefault(c["agente"], set()).add(c["modelo"])
    return {
        "tarefa": state.get("task_id"), "projeto": state.get("project_name"), "gerado_em": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "doutrina": {"versao": state.get("doutrina_versao"), "hash": state.get("doutrina_hash"),
                     "familias_excluidas": state.get("doutrina_excluir") or []},
        "stack": state.get("stack_id"), "plano": state.get("plano"),
        "modelo_da_tarefa": state.get("modelo"), "consentimento_nuvem": state.get("consentimento_nuvem") is True,
        "modelos_por_agente": {a: sorted(m for m in ms if m) for a, ms in modelos.items()},
        "totais": auditoria.totais(state), "chamadas": chamadas,
        "aprovacoes": {"business_spec_hash": state.get("business_spec_hash"), "release_gate_hash": state.get("release_gate_hash")},
        "verificacoes": {k: state.get(k) for k in ("tests_passed", "review_passed", "security_passed", "devops_passed")},
        "arquivos": _arquivos(raiz, list(state.get("arquivos_gerados") or [])),
    }

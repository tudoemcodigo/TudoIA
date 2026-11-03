"""
Camada de serviço da Squad: o que a CLI (main.py) e a API local (api.py) compartilham. Sem entrada e saída de console.

- `situacao` descreve em que ponto uma tarefa está (estado legível por máquina e mensagem para humanos).
- `montar_entrada` cria o estado inicial; nada aqui roda o grafo.
"""
import os
import re
import time
from pathlib import Path
from typing import Optional

import agentes
import aprovacao
import entrada as entrada_texto
import stacks
from execucao import workspace

RE_TAREFA = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")  # vira nome de pasta do workspace: nada de separador nem '..'


class ErroUso(Exception):
    """Entrada inválida do usuário; mensagem pronta para exibir."""


def tarefa_valida(tarefa: str) -> str:
    if not RE_TAREFA.match(tarefa or "") or ".." in tarefa:
        raise ErroUso(f"identificador de tarefa inválido: {tarefa!r} (use letras, números, '.', '_' ou '-', até 64)")
    return tarefa


def cfg_da_tarefa(tarefa: str) -> dict:
    return {"configurable": {"thread_id": tarefa_valida(tarefa)}}


def situacao(app, cfg) -> dict:
    """{'estado', 'fase', 'aguardando', 'mensagem'}. `estado` é um de: inexistente, aguardando_respostas,
    aguardando_aprovacao_spec, aguardando_aprovacao_release, em_fase, concluida, bloqueada, escalada_qa, escalada_revisao."""
    snap = app.get_state(cfg)
    v = snap.values or {}
    fase = v.get("current_phase")
    if snap.next:
        if "arquiteto" in snap.next:
            return {"estado": "aguardando_aprovacao_spec", "fase": fase, "aguardando": list(snap.next),
                    "mensagem": f"aguardando antes de {', '.join(snap.next)} (aprove o BUSINESS_SPEC com `aprovar`)"}
        if "release" in snap.next:
            return {"estado": "aguardando_aprovacao_release", "fase": fase, "aguardando": list(snap.next),
                    "mensagem": f"aguardando antes de {', '.join(snap.next)} (revise as notas e aprove o release com "
                                "`aprovar-release`; nada é commitado, tagueado nem publicado)"}
        return {"estado": "em_fase", "fase": fase, "aguardando": list(snap.next),
                "mensagem": f"aguardando antes de {', '.join(snap.next)}"}
    if not v:
        return {"estado": "inexistente", "fase": None, "aguardando": [], "mensagem": "tarefa inexistente"}
    if fase == "ENTREGA_CONCLUIDA" and v.get("release_notes_file"):
        return {"estado": "concluida", "fase": fase, "aguardando": [],
                "mensagem": f"verificações aprovadas e notas de release em {v['release_notes_file']} (tag e publicação são manuais)"}
    if fase == "ENTREGA_BLOQUEADA":
        quem = "AppSec" if v.get("security_passed") is False else "DevOps"
        return {"estado": "bloqueada", "fase": fase, "aguardando": [],
                "mensagem": f"{quem} reprovou; veja tests/reports/ no workspace"}
    if v.get("tests_passed") is False and v.get("iteration_count", 0) >= 3:
        return {"estado": "escalada_qa", "fase": fase, "aguardando": [],
                "mensagem": "QA reprovou 3 vezes; veja tests/reports/qa_report.json no workspace"}
    if v.get("review_passed") is False and v.get("iteration_count", 0) >= 3:
        return {"estado": "escalada_revisao", "fase": fase, "aguardando": [],
                "mensagem": "a revisão de código reprovou e o limite de iterações acabou; veja docs/revisao/REVISAO.md"}
    if v.get("escalada"):  # parada que exige humano: estagnação, orçamento, critério de pronto, saída inválida
        return {"estado": "escalada", "fase": fase, "aguardando": [], "mensagem": str(v["escalada"])}
    if v.get("business_spec_file"):
        return {"estado": "em_fase", "fase": fase, "aguardando": [], "mensagem": f"{fase}"}
    return {"estado": "aguardando_respostas", "fase": fase, "aguardando": [],
            "mensagem": "responda às perguntas com `responder`"}


def aprovar_spec(app, cfg) -> None:
    """Aprovação da especificação AMARRADA ao texto que o usuário viu: grava o hash do arquivo junto com o sim."""
    v = app.get_state(cfg).values or {}
    ws = workspace(v)
    try:
        hash_ = aprovacao.hash_arquivo(ws, v["business_spec_file"])
    except (KeyError, aprovacao.AprovacaoInvalida) as e:
        raise ErroUso(f"não há especificação para aprovar: {e}") from e
    app.update_state(cfg, {"business_spec_approved": True, "business_spec_hash": hash_})


def aprovar_release(app, cfg) -> None:
    """Aprovação do release amarrada ao pacote de verificações (relatórios, revisão e documentação) que o usuário viu."""
    v = app.get_state(cfg).values or {}
    app.update_state(cfg, {"release_approved": True, "release_gate_hash": aprovacao.hash_do_pacote(workspace(v), v)})


def montar_entrada(tarefa: str, briefing: str, config: dict, modelo: Optional[str] = None,
                   consentimento_nuvem: bool = False, stack: Optional[str] = None, cfg_agentes: Optional[dict] = None) -> dict:
    """Estado inicial de uma tarefa nova. Recusa pasta de workspace que já tenha conteúdo (IA-ORQ-10). O briefing é sanitizado
    (caracteres invisíveis e de controle saem) e a configuração dos agentes vigente é COPIADA para a tarefa."""
    tarefa_valida(tarefa)
    briefing, _ = entrada_texto.limpar_entrada(briefing, 20_000)
    if not (briefing or "").strip():
        raise ErroUso("o briefing não pode ser vazio")
    cfg_agentes = agentes.validar(cfg_agentes)
    if stack is not None and stack not in stacks.STACKS:
        raise ErroUso(f"stack inválida: use uma de {sorted(stacks.STACKS)}")
    pasta = Path("workspace") / tarefa
    if pasta.exists() and (not pasta.is_dir() or any(pasta.iterdir())):
        # IA-ORQ-10: a Squad só cria projeto novo em área isolada; nunca escreve sobre conteúdo que já existe
        raise ErroUso(f"a pasta {pasta} já tem conteúdo; a Squad só trabalha em projeto novo (escolha outro identificador de tarefa)")
    entrada = {
        "task_id": tarefa,
        "project_name": config["project_name"],
        "target_stack": config["stack"],
        "architecture_source_path": os.getenv("DOUTRINA_TEC") or config.get("architecture_source_path", ""),
        "doutrina_familias": config.get("doutrina_familias"),
        "workspace_dir": os.path.join("workspace", tarefa),
        "arquivos_gerados": [],
        "user_initial_briefing": briefing,
        "interview_questions": [],
        "interview_answers": [],
        "business_spec_approved": False,
        "iteration_count": 0,
        "tests_passed": False,
        "review_passed": False,
        "security_passed": False,
        "devops_passed": False,
        "release_approved": False,  # só `aprovar-release` muda; nunca é padrão
        "agentes_cfg": cfg_agentes,
        "orcamento": cfg_agentes["orcamento"],
        "auditoria": [], "assinaturas_erro": [], "observacoes_usuario": [], "escalada": None,
        "mensagens": [{"de": "usuario", "para": "chefe", "texto": briefing[:4000], "em": time.time()}],
    }
    if stack:
        entrada["stack_id"], entrada["stack_fixa"] = stack, True
    if modelo:
        entrada["modelo"] = modelo
        entrada["consentimento_nuvem"] = consentimento_nuvem is True
    return entrada

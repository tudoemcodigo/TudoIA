"""
Montagem e compilação do grafo LangGraph da Squad de TI.

O CHEFE é o primeiro e o último a falar: planeja a demanda, confere os critérios de pronto entre as fases e escreve o relatório de
escalada quando a execução para. O resto segue o fluxo de portões: nenhum nó "aprova" por omissão, e toda parada que exige humano
passa pelo CHEFE.
"""
import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, StateGraph

from chefe import node_chefe_escalada, node_chefe_gate_design, node_chefe_gate_requisitos, node_chefe_intake
from nodes import (
    node_analista_requisitos,
    node_appsec,
    node_arquiteto,
    node_dba,
    node_dev_backend,
    node_dev_frontend,
    node_devops,
    node_documentacao,
    node_qa_testes,
    node_release,
    node_revisor,
)
from state import SquadState

LIMITE_ITERACOES = 3  # QA e revisor dividem o mesmo contador: 3 passagens de verificação no total, depois escalação humana
ESCALADA = "chefe_escalada"


def _plano(state: SquadState) -> dict:
    return state.get("plano") or {}


def construcao(state: SquadState) -> list:
    """Quem constrói: sempre o backend; o frontend só se o plano do CHEFE pede (sem plano, como antes: frontend incluso)."""
    return ["dev_backend"] + (["dev_frontend"] if _plano(state).get("precisa_frontend", True) else [])


def build_squad_graph(db_path: str = "squad_state.db"):
    """Constrói e compila o StateGraph com persistência SQLite e interrupções humanas."""
    workflow = StateGraph(SquadState)

    workflow.add_node("chefe_intake", node_chefe_intake)
    workflow.add_node("analista_requisitos", node_analista_requisitos)
    workflow.add_node("chefe_gate_requisitos", node_chefe_gate_requisitos)
    workflow.add_node("arquiteto", node_arquiteto)
    workflow.add_node("chefe_gate_design", node_chefe_gate_design)
    workflow.add_node("dba", node_dba)
    workflow.add_node("dev_backend", node_dev_backend)
    workflow.add_node("dev_frontend", node_dev_frontend)
    workflow.add_node("qa_testes", node_qa_testes)
    workflow.add_node("revisor", node_revisor)
    workflow.add_node("appsec", node_appsec)
    workflow.add_node("devops", node_devops)
    workflow.add_node("documentacao", node_documentacao)
    workflow.add_node("release", node_release)
    workflow.add_node(ESCALADA, node_chefe_escalada)

    workflow.set_entry_point("chefe_intake")
    workflow.add_edge("chefe_intake", "analista_requisitos")

    def rota_pos_requisitos(state: SquadState):
        # Sem BUSINESS_SPEC gravado só há perguntas: a execução termina e espera as respostas do usuário (via CHEFE).
        # Com ele, o CHEFE confere o critério de pronto; só então o grafo pausa (interrupt_before) para a aprovação humana.
        return "chefe_gate_requisitos" if state.get("business_spec_file") else END

    workflow.add_conditional_edges("analista_requisitos", rota_pos_requisitos,
                                   {"chefe_gate_requisitos": "chefe_gate_requisitos", END: END})

    def rota_pos_gate_requisitos(state: SquadState):
        if state.get("escalada"):
            return ESCALADA
        return "analista_requisitos" if state.get("feedback_chefe") else "arquiteto"

    workflow.add_conditional_edges("chefe_gate_requisitos", rota_pos_gate_requisitos,
                                   {ESCALADA: ESCALADA, "analista_requisitos": "analista_requisitos", "arquiteto": "arquiteto"})

    workflow.add_edge("arquiteto", "chefe_gate_design")

    def rota_pos_design(state: SquadState):
        if state.get("escalada"):
            return [ESCALADA]
        return ["dba"] if _plano(state).get("precisa_banco", True) else construcao(state)

    mapa_construcao = {"dba": "dba", "dev_backend": "dev_backend", "dev_frontend": "dev_frontend", ESCALADA: ESCALADA}
    workflow.add_conditional_edges("chefe_gate_design", rota_pos_design, mapa_construcao)
    workflow.add_conditional_edges("dba", construcao, mapa_construcao)

    def rota_correcao(state: SquadState):
        # A falha vai a quem a causou: frontend quebrado não manda o backend "corrigir" (e vice-versa).
        return "dev_frontend" if state.get("falha_origem") == "frontend" else "dev_backend"

    def rota_pos_qa(state: SquadState):
        if state.get("escalada"):
            return ESCALADA  # estagnação: a mesma falha de novo, sem progresso
        if not state.get("tests_passed", False):
            if state.get("iteration_count", 0) >= LIMITE_ITERACOES:
                print("[Escalação Humana]: Testes falharam 3 vezes consecutivas. Requer intervenção.")
                return ESCALADA
            return rota_correcao(state)
        return "revisor"

    def rota_pos_revisor(state: SquadState):
        if state.get("escalada"):
            return ESCALADA
        if not state.get("review_passed", False):
            if state.get("iteration_count", 0) >= LIMITE_ITERACOES:
                print("[Escalação Humana]: Revisão de código reprovou e o limite de iterações foi atingido. Requer intervenção.")
                return ESCALADA
            return rota_correcao(state)
        return "appsec"

    def rota_pos_appsec(state: SquadState):
        return "devops" if state.get("security_passed", False) else ESCALADA  # ENTREGA_BLOQUEADA

    def rota_pos_devops(state: SquadState):
        return "documentacao" if state.get("devops_passed", False) else ESCALADA  # ENTREGA_BLOQUEADA

    workflow.add_edge("dev_backend", "qa_testes")
    workflow.add_edge("dev_frontend", "qa_testes")
    workflow.add_conditional_edges("qa_testes", rota_pos_qa, {"dev_backend": "dev_backend", "dev_frontend": "dev_frontend",
                                                                "revisor": "revisor", ESCALADA: ESCALADA})
    workflow.add_conditional_edges("revisor", rota_pos_revisor, {"dev_backend": "dev_backend", "dev_frontend": "dev_frontend",
                                                                   "appsec": "appsec", ESCALADA: ESCALADA})
    workflow.add_conditional_edges("appsec", rota_pos_appsec, {"devops": "devops", ESCALADA: ESCALADA})
    workflow.add_conditional_edges("devops", rota_pos_devops, {"documentacao": "documentacao", ESCALADA: ESCALADA})
    workflow.add_edge("documentacao", "release")
    workflow.add_edge("release", END)
    workflow.add_edge(ESCALADA, END)

    # Checkpointer em SQLite para persistência e recuperação de estado
    conn = sqlite3.connect(db_path, check_same_thread=False)
    memory = SqliteSaver(conn)

    # Compilação do grafo com interrupção humana (Human-in-the-Loop): o usuário DEVE aprovar o BUSINESS_SPEC antes de gastar
    # esforço técnico e DEVE aprovar o release antes das notas finais. Os nós também recusam rodar sem a aprovação no estado.
    return workflow.compile(checkpointer=memory, interrupt_before=["arquiteto", "release"])

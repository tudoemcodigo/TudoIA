"""
Montagem e Compilação do Grafo LangGraph da Squad de TI.
"""
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
import sqlite3

from state import SquadState
from nodes import (
    node_analista_requisitos,
    node_arquiteto,
    node_dba,
    node_dev_backend,
    node_dev_frontend,
    node_qa_testes,
    node_revisor,
    node_appsec,
    node_devops,
    node_documentacao,
    node_release,
)

LIMITE_ITERACOES = 3  # QA e revisor dividem o mesmo contador: 3 passagens de verificação no total, depois escalação humana

def build_squad_graph(db_path: str = "squad_state.db"):
    """
    Constrói e compila o StateGraph com persistência SQLite e interrupções humanas.
    """
    workflow = StateGraph(SquadState)
    
    # Registro dos nós da Squad
    workflow.add_node("analista_requisitos", node_analista_requisitos)
    workflow.add_node("arquiteto", node_arquiteto)
    workflow.add_node("dba", node_dba)
    workflow.add_node("dev_backend", node_dev_backend)
    workflow.add_node("dev_frontend", node_dev_frontend)
    workflow.add_node("qa_testes", node_qa_testes)
    workflow.add_node("revisor", node_revisor)
    workflow.add_node("appsec", node_appsec)
    workflow.add_node("devops", node_devops)
    workflow.add_node("documentacao", node_documentacao)
    workflow.add_node("release", node_release)

    # Transições condicionais e arestas
    workflow.set_entry_point("analista_requisitos")
    
    def rota_pos_requisitos(state: SquadState):
        # Sem BUSINESS_SPEC gravado só há perguntas: a execução termina e espera as respostas do usuário.
        # Com ele, segue ao arquiteto, onde o grafo pausa (interrupt_before) até a aprovação humana.
        return "arquiteto" if state.get("business_spec_file") else END

    workflow.add_conditional_edges("analista_requisitos", rota_pos_requisitos, {
        "arquiteto": "arquiteto",
        END: END
    })

    def rota_correcao(state: SquadState):
        # A falha vai a quem a causou: frontend quebrado não manda o backend "corrigir" (e vice-versa).
        return "dev_frontend" if state.get("falha_origem") == "frontend" else "dev_backend"

    def rota_pos_qa(state: SquadState):
        if not state.get("tests_passed", False):
            if state.get("iteration_count", 0) >= LIMITE_ITERACOES:
                print("[Escalação Humana]: Testes falharam 3 vezes consecutivas. Requer intervenção.")
                return END
            return rota_correcao(state)
        return "revisor"

    def rota_pos_revisor(state: SquadState):
        if not state.get("review_passed", False):
            if state.get("iteration_count", 0) >= LIMITE_ITERACOES:
                print("[Escalação Humana]: Revisão de código reprovou e o limite de iterações foi atingido. Requer intervenção.")
                return END
            return rota_correcao(state)
        return "appsec"

    def rota_pos_appsec(state: SquadState):
        return "devops" if state.get("security_passed", False) else END  # ENTREGA_BLOQUEADA

    def rota_pos_devops(state: SquadState):
        return "documentacao" if state.get("devops_passed", False) else END  # ENTREGA_BLOQUEADA

    workflow.add_edge("arquiteto", "dba")
    workflow.add_edge("dba", "dev_backend")
    workflow.add_edge("dba", "dev_frontend")
    workflow.add_edge("dev_backend", "qa_testes")
    workflow.add_edge("dev_frontend", "qa_testes")
    
    workflow.add_conditional_edges("qa_testes", rota_pos_qa, {
        "dev_backend": "dev_backend",
        "dev_frontend": "dev_frontend",
        "revisor": "revisor",
        END: END
    })
    workflow.add_conditional_edges("revisor", rota_pos_revisor, {
        "dev_backend": "dev_backend",
        "dev_frontend": "dev_frontend",
        "appsec": "appsec",
        END: END
    })
    workflow.add_conditional_edges("appsec", rota_pos_appsec, {"devops": "devops", END: END})
    workflow.add_conditional_edges("devops", rota_pos_devops, {"documentacao": "documentacao", END: END})
    workflow.add_edge("documentacao", "release")
    workflow.add_edge("release", END)
    
    # Checkpointer em SQLite para persistência e recuperação de estado
    conn = sqlite3.connect(db_path, check_same_thread=False)
    memory = SqliteSaver(conn)
    
    # Compilação do grafo com interrupção humana (Human-in-the-Loop): o usuário DEVE aprovar o BUSINESS_SPEC antes de gastar
    # esforço técnico e DEVE aprovar o release antes das notas finais. Os nós também recusam rodar sem a aprovação no estado.
    app = workflow.compile(
        checkpointer=memory,
        interrupt_before=["arquiteto", "release"]
    )
    return app

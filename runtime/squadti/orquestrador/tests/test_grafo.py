"""Topologia e execuÃ§Ã£o do grafo REAL do LangGraph, com os nÃ³s substituÃ­dos por dublÃªs que gravam a ordem de execuÃ§Ã£o.

Os testes de nÃ³s (test_nos.py) usam dublÃªs do LangChain e nunca montam o grafo; sem estes testes um grafo que nÃ£o
chega a lugar nenhum passa despercebido. Exigem `langgraph` e `langgraph-checkpoint-sqlite` (requirements.txt)."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import graph
    TEM_LANGGRAPH = True
except ImportError:  # dependÃªncias nÃ£o instaladas: o restante da suÃ­te continua valendo
    TEM_LANGGRAPH = False


def dubles(ordem, qa_aprova=True, qa_origem=None, revisor_aprova=True, revisor_origem=None, appsec_aprova=True,
           devops_aprova=True, revisor_reprova_vezes=0):
    """NÃ³s falsos que imitam as chaves que os nÃ³s reais devolvem (inclusive as que os dois devs gravam em paralelo)."""
    def analista(state):
        ordem.append("analista_requisitos")
        if state.get("interview_answers") and state.get("workspace_dir"):
            # a aprovação agora é amarrada ao hash do arquivo: ele precisa existir de verdade
            from execucao import workspace
            alvo = workspace(state) / "docs/negocio/BUSINESS_SPEC.md"
            alvo.parent.mkdir(parents=True, exist_ok=True)
            alvo.write_text("# especificacao de teste", encoding="utf-8")
        if not state.get("interview_answers"):
            return {"interview_questions": ["pergunta"], "business_spec_approved": False}
        return {"business_spec_file": "docs/negocio/BUSINESS_SPEC.md", "business_spec_approved": False,
                "current_phase": "APROVACAO_REQUISITOS", "arquivos_gerados": ["docs/negocio/BUSINESS_SPEC.md"]}

    def simples(nome, fase):
        def no(state):
            ordem.append(nome)
            return {"current_phase": fase}
        return no

    def dev(nome, arquivo):
        def no(state):
            ordem.append(nome)
            return {"current_phase": nome.upper(), "arquivos_gerados": list(state.get("arquivos_gerados") or []) + [arquivo]}
        return no

    def qa(state):
        ordem.append("qa_testes")
        origem = None if qa_aprova else (qa_origem or "backend")
        return {"tests_passed": qa_aprova, "falha_origem": origem, "iteration_count": state.get("iteration_count", 0) + 1}

    def revisor(state):
        ordem.append("revisor")
        aprova = revisor_aprova and ordem.count("revisor") > revisor_reprova_vezes
        origem = None if aprova else (revisor_origem or "backend")
        return {"review_passed": aprova, "falha_origem": origem, "iteration_count": state.get("iteration_count", 0) + 1}

    def appsec(state):
        ordem.append("appsec")
        return {"security_passed": appsec_aprova, "current_phase": "APPSEC_APROVADO" if appsec_aprova else "ENTREGA_BLOQUEADA"}

    def devops(state):
        ordem.append("devops")
        return {"devops_passed": devops_aprova, "current_phase": "DEVOPS_APROVADO" if devops_aprova else "ENTREGA_BLOQUEADA"}

    def release(state):
        # imita o nÃ³ real: o interrupt nÃ£o basta, o prÃ³prio nÃ³ recusa sem aprovaÃ§Ã£o no estado
        if state.get("release_approved") is not True:
            raise RuntimeError("release nÃ£o aprovado")
        ordem.append("release")
        return {"current_phase": "ENTREGA_CONCLUIDA", "release_notes_file": "docs/release/RELEASE_NOTES.md"}

    def silencioso(fase):
        # o CHEFE não conta na ordem dos agentes que trabalham: só planeja, confere e escala
        return lambda state: {"current_phase": fase}

    return {"node_chefe_intake": silencioso("PLANEJADO"), "node_chefe_gate_requisitos": lambda state: {},
            "node_chefe_gate_design": lambda state: {}, "node_chefe_escalada": lambda state: {},
            "node_analista_requisitos": analista, "node_arquiteto": simples("arquiteto", "ARQ"),
            "node_dba": simples("dba", "DBA"), "node_dev_backend": dev("dev_backend", "src/a.cs"),
            "node_dev_frontend": dev("dev_frontend", "frontend/a.ts"), "node_qa_testes": qa, "node_revisor": revisor,
            "node_appsec": appsec, "node_devops": devops, "node_documentacao": simples("documentacao", "DOC"),
            "node_release": release}


@unittest.skipUnless(TEM_LANGGRAPH, "langgraph nÃ£o instalado")
class GrafoReal(unittest.TestCase):
    def montar(self, qa_aprova=True, qa_origem=None, **kw):
        self.ordem = []
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patcher = mock.patch.multiple(graph, **dubles(self.ordem, qa_aprova, qa_origem, **kw))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.app = graph.build_squad_graph(str(Path(tmp.name) / "estado.db"))
        self.addCleanup(self.app.checkpointer.conn.close)
        return {"configurable": {"thread_id": "T"}}

    def rodar(self, entrada, cfg):
        for _ in self.app.stream(entrada, cfg):
            pass

    def test_topologia_liga_requisitos_a_arquitetura_e_pausa_antes_dela(self):
        self.montar()
        arestas = {(e.source, e.target) for e in self.app.get_graph().edges}
        self.assertIn(("chefe_intake", "analista_requisitos"), arestas)  # o CHEFE recebe a demanda primeiro
        self.assertIn(("analista_requisitos", "chefe_gate_requisitos"), arestas)
        self.assertIn(("chefe_gate_requisitos", "arquiteto"), arestas)
        self.assertIn(("arquiteto", "chefe_gate_design"), arestas)
        self.assertIn(("chefe_gate_design", "dba"), arestas)
        self.assertIn(("qa_testes", "chefe_escalada"), arestas)  # toda parada que exige humano passa pelo CHEFE
        self.assertIn(("qa_testes", "revisor"), arestas)
        self.assertIn(("revisor", "appsec"), arestas)
        self.assertIn(("appsec", "devops"), arestas)
        self.assertIn(("devops", "documentacao"), arestas)
        self.assertIn(("documentacao", "release"), arestas)
        self.assertIn(("release", "__end__"), arestas)
        self.assertNotIn("appsec_devops", self.app.get_graph().nodes)
        self.assertEqual(list(self.app.interrupt_before_nodes), ["arquiteto", "release"])

    def test_sem_respostas_a_squad_para_e_espera_o_usuario_sem_chegar_a_arquitetura(self):
        cfg = self.montar()
        self.rodar({"task_id": "T", "interview_answers": []}, cfg)
        self.assertEqual(self.ordem, ["analista_requisitos"])
        self.assertEqual(self.app.get_state(cfg).next, ())

    def test_com_spec_pausa_antes_do_arquiteto_e_so_segue_apos_aprovacao(self):
        cfg = self.montar()
        self.rodar({"task_id": "T", "interview_answers": ["resp"]}, cfg)
        self.assertEqual(self.ordem, ["analista_requisitos"])
        self.assertEqual(self.app.get_state(cfg).next, ("arquiteto",))

        self.app.update_state(cfg, {"business_spec_approved": True})
        self.rodar(None, cfg)
        self.assertEqual(self.ordem[1:3], ["arquiteto", "dba"])
        self.assertEqual(set(self.ordem[3:5]), {"dev_backend", "dev_frontend"})  # paralelos
        self.assertEqual(self.ordem[5:], ["qa_testes", "revisor", "appsec", "devops", "documentacao"])
        self.assertEqual(self.app.get_state(cfg).next, ("release",))  # pausa humana antes do release

        self.app.update_state(cfg, {"release_approved": True})
        self.rodar(None, cfg)
        self.assertEqual(self.ordem[-1], "release")
        self.assertEqual(self.app.get_state(cfg).next, ())
        self.assertEqual(self.app.get_state(cfg).values["current_phase"], "ENTREGA_CONCLUIDA")

    def chegar_ao_release(self, cfg):
        self.rodar({"task_id": "T", "interview_answers": ["resp"]}, cfg)
        self.app.update_state(cfg, {"business_spec_approved": True})
        self.rodar(None, cfg)
        self.assertEqual(self.app.get_state(cfg).next, ("release",))

    def test_resume_sem_aprovacao_nao_pula_a_pausa_do_release(self):
        cfg = self.montar()
        self.chegar_ao_release(cfg)
        with self.assertRaises(RuntimeError):  # resume cego: o nÃ³ recusa
            self.rodar(None, cfg)
        self.assertNotIn("release", self.ordem)
        self.app.update_state(cfg, {"release_approved": False})
        with self.assertRaises(RuntimeError):
            self.rodar(None, cfg)
        self.assertNotIn("release", self.ordem)
        self.assertNotEqual(self.app.get_state(cfg).values.get("current_phase"), "ENTREGA_CONCLUIDA")

    def test_revisor_reprova_e_volta_ao_dev_certo_depois_segue(self):
        for origem, dev in (("backend", "dev_backend"), ("frontend", "dev_frontend")):
            cfg = self.montar(revisor_aprova=False, revisor_origem=origem)
            cfg["configurable"]["thread_id"] = f"R-{origem}"
            self.rodar({"task_id": "T", "interview_answers": ["resp"]}, cfg)
            self.app.update_state(cfg, {"business_spec_approved": True})
            self.rodar(None, cfg)
            # 1a passagem: dev_backend e dev_frontend (paralelo); a correÃ§Ã£o volta SÃ“ ao dev apontado
            self.assertEqual(self.ordem.count(dev), 2, origem)
            outro = "dev_frontend" if dev == "dev_backend" else "dev_backend"
            self.assertEqual(self.ordem.count(outro), 1, origem)
            self.assertIn("revisor", self.ordem)
            self.assertLess(self.ordem.index("qa_testes"), self.ordem.index("revisor"))

    def test_revisor_reprovado_escala_ao_humano_sem_chamar_appsec_devops_docs_release(self):
        cfg = self.montar(revisor_aprova=False)
        self.chegar_ao_fim_sem_release(cfg)
        # QA(1) revisor(2) -> dev -> QA(3) revisor(4>=3): escala; o contador Ã© dividido entre QA e revisor
        self.assertEqual(self.ordem.count("revisor"), 2)
        self.assertEqual(self.ordem.count("qa_testes"), 2)
        for no in ("appsec", "devops", "documentacao", "release"):
            self.assertNotIn(no, self.ordem)
        self.assertGreaterEqual(self.app.get_state(cfg).values["iteration_count"], 3)
        self.assertEqual(self.app.get_state(cfg).next, ())

    def chegar_ao_fim_sem_release(self, cfg):
        self.rodar({"task_id": "T", "interview_answers": ["resp"]}, cfg)
        self.app.update_state(cfg, {"business_spec_approved": True})
        self.rodar(None, cfg)

    def test_revisor_reprova_uma_vez_corrige_e_o_fluxo_completa(self):
        cfg = self.montar(revisor_reprova_vezes=1)
        self.chegar_ao_release(cfg)
        self.assertEqual(self.ordem.count("revisor"), 2)
        self.assertEqual(self.ordem.count("dev_backend"), 2)
        self.assertEqual(self.ordem.count("qa_testes"), 2)

    def test_appsec_bloqueado_nao_chama_devops_documentacao_nem_release(self):
        cfg = self.montar(appsec_aprova=False)
        self.chegar_ao_fim_sem_release(cfg)
        self.assertEqual(self.ordem[-2:], ["revisor", "appsec"])
        for no in ("devops", "documentacao", "release"):
            self.assertNotIn(no, self.ordem)
        v = self.app.get_state(cfg)
        self.assertEqual((v.next, v.values["current_phase"]), ((), "ENTREGA_BLOQUEADA"))

    def test_devops_bloqueado_nao_chama_documentacao_nem_release(self):
        cfg = self.montar(devops_aprova=False)
        self.chegar_ao_fim_sem_release(cfg)
        self.assertEqual(self.ordem[-3:], ["revisor", "appsec", "devops"])
        for no in ("documentacao", "release"):
            self.assertNotIn(no, self.ordem)
        v = self.app.get_state(cfg)
        self.assertEqual((v.next, v.values["current_phase"]), ((), "ENTREGA_BLOQUEADA"))
    def test_arquivos_dos_dois_devs_em_paralelo_sao_unidos_sem_duplicar(self):
        cfg = self.montar()
        self.rodar({"task_id": "T", "interview_answers": ["resp"]}, cfg)
        self.app.update_state(cfg, {"business_spec_approved": True})
        self.rodar(None, cfg)
        arquivos = self.app.get_state(cfg).values["arquivos_gerados"]
        self.assertEqual(sorted(arquivos), ["docs/negocio/BUSINESS_SPEC.md", "frontend/a.ts", "src/a.cs"])

    def test_falha_atribuida_ao_frontend_volta_ao_dev_frontend_e_nao_ao_backend(self):
        cfg = self.montar(qa_aprova=False, qa_origem="frontend")
        self.rodar({"task_id": "T", "interview_answers": ["resp"]}, cfg)
        self.app.update_state(cfg, {"business_spec_approved": True})
        self.rodar(None, cfg)
        # dba -> (dev_backend || dev_frontend) -> qa; as 2 correÃ§Ãµes seguintes sÃ£o sÃ³ do frontend
        self.assertEqual(self.ordem.count("dev_backend"), 1)
        self.assertEqual(self.ordem.count("dev_frontend"), 3)
        self.assertEqual(self.ordem.count("qa_testes"), 3)

    def test_qa_reprovado_tres_vezes_escala_ao_humano_sem_chamar_appsec(self):
        cfg = self.montar(qa_aprova=False)
        self.rodar({"task_id": "T", "interview_answers": ["resp"]}, cfg)
        self.app.update_state(cfg, {"business_spec_approved": True})
        self.rodar(None, cfg)
        self.assertEqual(self.ordem.count("qa_testes"), 3)
        self.assertNotIn("appsec", self.ordem)
        self.assertEqual(self.app.get_state(cfg).next, ())


if __name__ == "__main__":
    unittest.main()

"""CLI: ciclo iniciar -> responder -> aprovar com o grafo real e nós substituídos por dublês (ver test_grafo.py)."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import graph
    import main
    from test_grafo import dubles
    TEM_LANGGRAPH = True
except ImportError:
    TEM_LANGGRAPH = False


@unittest.skipUnless(TEM_LANGGRAPH, "langgraph não instalado")
class Cli(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        self.db = str(base / "estado.db")
        self.config = base / "stack.json"
        self.config.write_text(json.dumps({"project_name": "Demo", "stack": {"backend": {}}}), encoding="utf-8")
        import os
        antigo = os.getcwd()
        os.chdir(base)  # o workspace é relativo ao diretório de trabalho: nada de sujar o repositório
        self.addCleanup(os.chdir, antigo)
        self.ordem, self.apps = [], []
        patch_nos = mock.patch.multiple(graph, **dubles(self.ordem))
        patch_nos.start()
        self.addCleanup(patch_nos.stop)

        def construir(db_path):
            app = graph.build_squad_graph(db_path)
            self.apps.append(app)
            return app
        patch_app = mock.patch.object(main, "construir_app", construir)
        patch_app.start()
        self.addCleanup(patch_app.stop)
        self.addCleanup(lambda: [a.checkpointer.conn.close() for a in self.apps])

    def cli(self, *args):
        saida, erro = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(saida), contextlib.redirect_stderr(erro):
            codigo = main.main([*args, "--db", self.db])
        return codigo, saida.getvalue(), erro.getvalue()

    def iniciar(self, tarefa="T1"):
        return self.cli("iniciar", "--tarefa", tarefa, "--briefing", "x", "--config", str(self.config))

    def test_recusa_workspace_com_conteudo_existente(self):
        import os
        with tempfile.TemporaryDirectory() as cwd:
            antigo = os.getcwd()
            os.chdir(cwd)
            self.addCleanup(os.chdir, antigo)
            pasta = Path("workspace") / "T9"
            pasta.mkdir(parents=True)
            (pasta / "existente.txt").write_text("não pode ser tocado", encoding="utf-8")
            codigo, _, erro = self.iniciar("T9")
            os.chdir(antigo)
        self.assertEqual(codigo, 2)
        self.assertIn("projeto novo", erro)
        self.assertEqual(self.ordem, [])  # nenhum nó rodou

    def test_ciclo_completo_entre_execucoes_do_processo(self):
        codigo, saida, _ = self.iniciar()
        self.assertEqual(codigo, 0)
        self.assertIn("Aguardando o usuário", saida)

        codigo, saida, _ = self.cli("responder", "--tarefa", "T1", "--resposta", "ok")
        self.assertEqual(codigo, 0)
        self.assertIn("Pausada", saida)
        self.assertNotIn("arquiteto", self.ordem)

        codigo, saida, _ = self.cli("aprovar", "--tarefa", "T1")
        self.assertEqual(codigo, 0)
        self.assertIn("Pausada", saida)  # a entrega para antes do release, à espera do humano
        self.assertIn("aprovar-release", saida)
        self.assertEqual(self.ordem[-1], "documentacao")
        self.assertNotIn("release", self.ordem)

        codigo, saida, _ = self.cli("aprovar-release", "--tarefa", "T1")
        self.assertEqual(codigo, 0)
        self.assertIn("Concluída", saida)
        self.assertIn("RELEASE_NOTES.md", saida)
        self.assertEqual(self.ordem[-1], "release")

    def test_aprovar_nao_aprova_o_release_e_aprovar_release_exige_a_pausa(self):
        self.iniciar()
        self.cli("responder", "--tarefa", "T1", "--resposta", "ok")
        codigo, _, erro = self.cli("aprovar-release", "--tarefa", "T1")  # pausada antes do arquiteto, não do release
        self.assertEqual(codigo, 2)
        self.assertIn("antes do release", erro)
        self.cli("aprovar", "--tarefa", "T1")
        codigo, _, erro = self.cli("aprovar", "--tarefa", "T1")  # agora está no release: `aprovar` não vale
        self.assertEqual(codigo, 2)
        self.assertIn("nada a aprovar", erro)
        self.assertNotIn("release", self.ordem)
        self.assertEqual(self.cli("aprovar-release", "--tarefa", "NAO")[0], 2)  # inexistente: não pausada

    def test_tarefa_existente_nao_e_sobrescrita(self):
        self.iniciar()
        codigo, _, erro = self.iniciar()
        self.assertEqual(codigo, 2)
        self.assertIn("já existe", erro)

    def test_identificador_de_tarefa_hostil_e_recusado_antes_de_tocar_o_disco(self):
        for ruim in ("../fora", "a/b", "a\\b", "", " ", "..", "x" * 65, "-x"):
            codigo, _, erro = self.cli("estado", f"--tarefa={ruim}")  # '=' para o argparse não ler "-x" como opção
            self.assertEqual(codigo, 2, ruim)
            self.assertIn("inválido", erro)

    def test_responder_tarefa_inexistente_ou_resposta_vazia(self):
        self.assertEqual(self.cli("responder", "--tarefa", "NAO", "--resposta", "x")[0], 2)
        self.iniciar()
        self.assertEqual(self.cli("responder", "--tarefa", "T1", "--resposta", "  ")[0], 2)

    def test_aprovar_sem_estar_pausada_e_recusado(self):
        self.iniciar()
        codigo, _, erro = self.cli("aprovar", "--tarefa", "T1")
        self.assertEqual(codigo, 2)
        self.assertIn("nada a aprovar", erro)

    def test_perfil_define_o_modelo_e_e_exclusivo_com_modelo(self):
        with mock.patch.dict("os.environ", {}, clear=False):
            self.iniciar_com("--perfil", "local-estrito")
            self.assertEqual(__import__("os").environ["TUDOIA_MODEL"], "tudoia-local-estrito")
        with self.assertRaises(SystemExit):  # argparse recusa --perfil junto de --modelo
            self.cli("iniciar", "--tarefa", "T3", "--briefing", "x", "--perfil", "local", "--modelo", "x")
        with self.assertRaises(SystemExit):  # perfil desconhecido
            self.cli("iniciar", "--tarefa", "T4", "--briefing", "x", "--perfil", "inventado")

    def iniciar_com(self, *extra):
        return self.cli("iniciar", "--tarefa", "TP", "--briefing", "x", "--config", str(self.config), *extra)

    def test_config_ilegivel_falha_com_mensagem(self):
        codigo, _, erro = self.cli("iniciar", "--tarefa", "T2", "--briefing", "x", "--config", "nao-existe.json")
        self.assertEqual(codigo, 2)
        self.assertIn("ilegível", erro)


if __name__ == "__main__":
    unittest.main()

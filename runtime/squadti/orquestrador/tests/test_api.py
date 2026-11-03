"""API local: fronteiras HTTP (token, Host, tipo, tamanho), consentimento de nuvem, ciclo com o grafo real e nós falsos."""
import http.client
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import api
    import graph
    from test_grafo import dubles
    TEM_LANGGRAPH = True
except ImportError:
    TEM_LANGGRAPH = False

TOKEN = "t" * 40


@unittest.skipUnless(TEM_LANGGRAPH, "langgraph não instalado")
class Api(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        antigo = os.getcwd()
        os.chdir(base)  # o workspace é relativo ao diretório de trabalho
        self.addCleanup(os.chdir, antigo)
        self.ordem = []
        patch = mock.patch.multiple(graph, **dubles(self.ordem))
        patch.start()
        self.addCleanup(patch.stop)
        app = graph.build_squad_graph(str(base / "estado.db"))
        self.addCleanup(app.checkpointer.conn.close)
        self.servico = api.Servico(app, {"project_name": "Demo", "stack": {"backend": {}}}, TOKEN)
        self.httpd = api.ThreadingHTTPServer(("127.0.0.1", 0), api.criar_handler(self.servico, 0))
        self.porta = self.httpd.server_address[1]
        self.httpd.RequestHandlerClass = api.criar_handler(self.servico, self.porta)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)

    def req(self, metodo, caminho, corpo=None, token=TOKEN, host=None, tipo="application/json", bruto=None):
        c = http.client.HTTPConnection("127.0.0.1", self.porta, timeout=10)
        cab = {"Host": host or f"127.0.0.1:{self.porta}"}
        if token:
            cab["Authorization"] = f"Bearer {token}"
        dados = bruto if bruto is not None else (json.dumps(corpo).encode() if corpo is not None else None)
        if dados is not None:
            cab["Content-Type"] = tipo
        c.request(metodo, caminho, body=dados, headers=cab)
        r = c.getresponse()
        texto = r.read().decode("utf-8")
        c.close()
        return r.status, json.loads(texto)

    def esperar(self, tarefa, ate=("ok", "erro")):
        for _ in range(100):
            ex = self.servico.execucoes.de(tarefa)
            if ex and ex["estado"] in ate:
                return ex
            time.sleep(0.05)
        self.fail("a execução não terminou")

    # ---------------------------------------------------------------- fronteiras
    def test_saude_sem_token_e_api_exige_token(self):
        self.assertEqual(self.req("GET", "/saude", token=None), (200, {"ok": True}))
        for token in (None, "x" * 40, TOKEN[:-1]):
            status, corpo = self.req("GET", "/api/tarefas", token=token)
            self.assertEqual((status, corpo["erro"]["codigo"]), (401, "nao_autenticado"))

    def test_host_estranho_e_recusado_ate_com_token(self):
        status, corpo = self.req("GET", "/api/tarefas", host="evil.example")
        self.assertEqual((status, corpo["erro"]["codigo"]), (403, "host_recusado"))
        self.assertEqual(self.req("GET", "/saude", host="evil.example")[0], 403)

    def test_post_exige_json_e_limita_tamanho_e_forma(self):
        self.assertEqual(self.req("POST", "/api/tarefas", bruto=b"{}", tipo="text/plain")[0], 415)
        self.assertEqual(self.req("POST", "/api/tarefas", bruto=b"{nao-json")[0], 400)
        self.assertEqual(self.req("POST", "/api/tarefas", bruto=b"[1]")[0], 422)
        self.assertEqual(self.req("POST", "/api/tarefas", bruto=b"x" * (api.MAX_CORPO + 1))[0], 413)

    def test_rota_inexistente_e_tarefa_inexistente(self):
        self.assertEqual(self.req("GET", "/api/nada")[0], 404)
        self.assertEqual(self.req("GET", "/fora")[0], 404)
        self.assertEqual(self.req("GET", "/api/tarefas/T404")[0], 404)
        self.assertEqual(self.req("POST", "/api/tarefas/T404/aprovar", {})[0], 404)

    def test_lista_vazia_em_banco_novo(self):
        self.assertEqual(self.req("GET", "/api/tarefas"), (200, {"tarefas": []}))

    def test_bind_so_em_loopback_ou_todas_as_interfaces_do_container(self):
        self.assertEqual(api.HOSTS_DE_BIND, ("127.0.0.1", "0.0.0.0"))
        with self.assertRaises(SystemExit):  # argparse recusa qualquer outro valor antes de abrir socket
            with mock.patch.dict(os.environ, {"TUDOIA_SQUADTI_TOKEN": TOKEN}):
                api.main(["--host", "192.168.0.10"])

    def test_token_curto_impede_a_api_de_subir(self):
        with mock.patch.dict(os.environ, {"TUDOIA_SQUADTI_TOKEN": "curto"}):
            with self.assertRaises(SystemExit):
                api.token_do_ambiente()

    # ---------------------------------------------------------------- validação e privacidade
    def test_iniciar_valida_entrada(self):
        for corpo in ({}, {"tarefa": "../x", "briefing": "b"}, {"tarefa": "T1"}, {"tarefa": "T1", "briefing": "  "},
                      {"tarefa": "T1", "briefing": "b", "perfil": "inexistente"},
                      {"tarefa": "T1", "briefing": "b", "perfil": "nuvem", "consentimento_nuvem": "sim"}):
            status, _ = self.req("POST", "/api/tarefas", corpo)
            self.assertEqual(status, 422, corpo)
        self.assertEqual(self.ordem, [])

    def test_perfil_de_nuvem_so_com_consentimento_explicito(self):
        for perfil in ("nuvem", "hibrido", "max"):
            status, corpo = self.req("POST", "/api/tarefas", {"tarefa": "T1", "briefing": "b", "perfil": perfil})
            self.assertEqual((status, corpo["erro"]["codigo"]), (422, "consentimento_nuvem"), perfil)
        self.assertEqual(self.ordem, [])
        status, corpo = self.req("POST", "/api/tarefas",
                                 {"tarefa": "T1", "briefing": "b", "perfil": "nuvem", "consentimento_nuvem": True})
        self.assertEqual(status, 202)
        self.assertEqual(corpo["modelo"], "tudoia-nuvem")
        self.esperar("T1")
        self.assertTrue(self.req("GET", "/api/tarefas/T1")[1]["consentimento_nuvem"])

    # ---------------------------------------------------------------- ciclo
    def test_ciclo_completo_pela_api(self):
        status, corpo = self.req("POST", "/api/tarefas", {"tarefa": "T1", "briefing": "b"})
        self.assertEqual((status, corpo["modelo"]), (202, "tudoia-local-estrito"))
        self.assertEqual(self.esperar("T1")["estado"], "ok")
        d = self.req("GET", "/api/tarefas/T1")[1]
        self.assertEqual(d["situacao"]["estado"], "aguardando_respostas")
        self.assertEqual(d["perguntas"], ["pergunta"])
        self.assertEqual(self.req("POST", "/api/tarefas", {"tarefa": "T1", "briefing": "b"})[0], 409)

        # aprovar antes da hora é recusado
        self.assertEqual(self.req("POST", "/api/tarefas/T1/aprovar", {})[0], 409)
        self.assertEqual(self.req("POST", "/api/tarefas/T1/responder", {"resposta": " "})[0], 422)
        self.assertEqual(self.req("POST", "/api/tarefas/T1/responder", {"resposta": "ok"})[0], 202)
        self.esperar("T1")
        self.assertEqual(self.req("GET", "/api/tarefas/T1")[1]["situacao"]["estado"], "aguardando_aprovacao_spec")
        self.assertEqual(self.req("POST", "/api/tarefas/T1/aprovar-release", {})[0], 409)

        self.assertEqual(self.req("POST", "/api/tarefas/T1/aprovar", {})[0], 202)
        self.esperar("T1")
        self.assertEqual(self.req("GET", "/api/tarefas/T1")[1]["situacao"]["estado"], "aguardando_aprovacao_release")
        self.assertNotIn("release", self.ordem)

        self.assertEqual(self.req("POST", "/api/tarefas/T1/aprovar-release", {})[0], 202)
        ex = self.esperar("T1")
        self.assertIn("release", [n["no"] for n in ex["nos"]])
        lista = self.req("GET", "/api/tarefas")[1]["tarefas"]
        self.assertEqual([t["tarefa"] for t in lista], ["T1"])

    def test_uma_execucao_por_vez(self):
        liberar = threading.Event()
        self.servico.execucoes.iniciar("A", "iniciar", lambda registrar: liberar.wait(5))
        try:
            with self.assertRaises(api.ErroHttp) as cm:
                self.servico.execucoes.iniciar("B", "iniciar", lambda registrar: None)
            self.assertEqual(cm.exception.status, 409)
        finally:
            liberar.set()
        self.esperar("A")

    def test_falha_do_no_vira_erro_visivel_sem_derrubar_a_api(self):
        def quebra(registrar):
            raise RuntimeError("boom")
        self.servico.execucoes.iniciar("X", "iniciar", quebra)
        ex = self.esperar("X")
        self.assertEqual(ex["estado"], "erro")
        self.assertIn("boom", ex["erro"])
        self.assertEqual(self.req("GET", "/saude", token=None)[0], 200)

    # ---------------------------------------------------------------- arquivos
    def test_arquivo_recusa_travessia_omite_segredo_e_limita(self):
        self.req("POST", "/api/tarefas", {"tarefa": "T1", "briefing": "b"})
        self.esperar("T1")
        ws = Path("workspace") / "T1"
        ws.mkdir(parents=True, exist_ok=True)
        (ws / "a.txt").write_text('linha boa\npassword = "SenhaMuitoSecreta123"\nfim\n', encoding="utf-8")
        (ws / "bin.dat").write_bytes(b"\xff\xfe\x00\x01")
        (ws / "grande.txt").write_text("x" * (api.MAX_ARQUIVO + 50), encoding="utf-8")
        status, corpo = self.req("GET", "/api/tarefas/T1/arquivo?caminho=a.txt")
        self.assertEqual(status, 200)
        self.assertIn("linha boa", corpo["conteudo"])
        self.assertNotIn("SenhaMuitoSecreta123", corpo["conteudo"])
        self.assertEqual(corpo["linhas_omitidas"], 1)
        for ruim in ("../../estado.db", "..%2F..%2Festado.db", "/etc/passwd", "C:/Windows/win.ini", "a.txt:fluxo", ""):
            self.assertEqual(self.req("GET", f"/api/tarefas/T1/arquivo?caminho={ruim}")[0], 422, ruim)
        self.assertEqual(self.req("GET", "/api/tarefas/T1/arquivo?caminho=nao-existe.txt")[0], 404)
        self.assertEqual(self.req("GET", "/api/tarefas/T1/arquivo?caminho=bin.dat")[0], 415)
        corpo = self.req("GET", "/api/tarefas/T1/arquivo?caminho=grande.txt")[1]
        self.assertTrue(corpo["truncado"])
        self.assertLessEqual(len(corpo["conteudo"]), api.MAX_ARQUIVO)


if __name__ == "__main__":
    unittest.main()

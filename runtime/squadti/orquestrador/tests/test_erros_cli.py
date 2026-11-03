"""Erros do gateway viram mensagens acionáveis na CLI, sem repetir o corpo da resposta (que pode ter o hash da chave)."""
import contextlib
import io
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import httpx
    import openai
    TEM_OPENAI = True
except ImportError:
    TEM_OPENAI = False

import main

SEGREDO_NO_CORPO = "Received API Key = sk-...abcd, Key Hash (Token) =7501b6654e379aa4cb8e7db65733bb18"


def erro(classe, status):
    resposta = httpx.Response(status, request=httpx.Request("POST", "http://localhost:4000/v1/chat/completions"))
    return classe(f"Error code: {status} - {SEGREDO_NO_CORPO}", response=resposta, body=None)


@unittest.skipUnless(TEM_OPENAI, "openai não instalado")
class TraducaoDeErros(unittest.TestCase):
    def setUp(self):
        env = mock.patch.dict(os.environ, {"TUDOIA_MODEL": "tudoia-local-estrito"})
        env.start()
        self.addCleanup(env.stop)

    def mensagem(self, excecao):
        return main.explicar_falha(excecao)

    def test_401_manda_definir_a_chave_e_nao_repete_o_corpo(self):
        m = self.mensagem(erro(openai.AuthenticationError, 401))
        self.assertIn("TUDOIA_API_KEY", m)
        self.assertNotIn("7501b665", m)
        self.assertNotIn("sk-...abcd", m)

    def test_403_diz_qual_modelo_a_chave_nao_alcanca(self):
        m = self.mensagem(erro(openai.PermissionDeniedError, 403))
        self.assertIn("tudoia-local-estrito", m)
        self.assertIn("TUDOIA_API_KEY", m)
        self.assertNotIn("7501b665", m)

    def test_404_manda_regerar_config_e_reiniciar(self):
        m = self.mensagem(erro(openai.NotFoundError, 404))
        self.assertIn("tudoia-local-estrito", m)
        self.assertIn("reinicie", m.lower())
        self.assertNotIn("7501b665", m)

    def test_gateway_fora_do_ar_cita_o_endereco(self):
        req = httpx.Request("POST", "http://localhost:4000/v1/chat/completions")
        for e in (openai.APIConnectionError(request=req), openai.APITimeoutError(request=req)):
            self.assertIn("gateway", self.mensagem(e))

    def test_outros_erros_nao_sao_traduzidos(self):
        self.assertIsNone(self.mensagem(RuntimeError("doutrina ilegível")))
        self.assertIsNone(self.mensagem(erro(openai.InternalServerError, 500)))


@unittest.skipUnless(TEM_OPENAI, "openai não instalado")
class CliComErroDoGateway(unittest.TestCase):
    def rodar(self, excecao):
        class App:
            def get_state(self, cfg):
                raise excecao
        saida, err = io.StringIO(), io.StringIO()
        with mock.patch.object(main, "construir_app", lambda db: App()), \
                contextlib.redirect_stdout(saida), contextlib.redirect_stderr(err):
            codigo = main.main(["estado", "--tarefa", "T1", "--db", "x.db"])
        return codigo, err.getvalue()

    def test_401_sai_com_mensagem_acionavel_e_sem_o_hash(self):
        codigo, err = self.rodar(erro(openai.AuthenticationError, 401))
        self.assertEqual(codigo, 1)
        self.assertIn("TUDOIA_API_KEY", err)
        self.assertNotIn("7501b665", err)

    def test_erro_nao_traduzido_continua_visivel(self):
        codigo, err = self.rodar(RuntimeError("doutrina ilegível"))
        self.assertEqual(codigo, 1)
        self.assertIn("RuntimeError: doutrina ilegível", err)


if __name__ == "__main__":
    unittest.main()

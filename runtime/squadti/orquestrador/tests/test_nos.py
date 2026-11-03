"""Testes dos nós com o LangChain substituído por dublês (o pacote não é necessário para testar a lógica)."""
import importlib
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_fronteiras import doutrina_falsa  # noqa: E402


class _Msg:
    def __init__(self, content):
        self.content = content


class _LlmFalso:
    resposta = ""
    chamadas = []

    def __init__(self, **kw):
        pass

    def invoke(self, mensagens):
        _LlmFalso.chamadas.append(mensagens)
        return _Msg(_LlmFalso.resposta)


def importar_nodes(**env):
    core = types.ModuleType("langchain_core")
    msgs = types.ModuleType("langchain_core.messages")
    msgs.HumanMessage = msgs.SystemMessage = _Msg
    oai = types.ModuleType("langchain_openai")
    oai.ChatOpenAI = _LlmFalso
    mods = {"langchain_core": core, "langchain_core.messages": msgs, "langchain_openai": oai}
    sys.modules.pop("nodes", None)
    with mock.patch.dict(sys.modules, mods), mock.patch.dict(os.environ, env):
        return importlib.import_module("nodes")


class PrivacidadeDoModelo(unittest.TestCase):
    def test_padrao_e_local(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TUDOIA_MODEL", None)
            self.assertEqual(importar_nodes().TUDOIA_MODEL, "tudoia-local")

    def test_roteador_automatico_e_recusado(self):
        os.environ.pop("TUDOIA_PERMITIR_NUVEM", None)
        with self.assertRaises(RuntimeError):
            importar_nodes(TUDOIA_MODEL="tudoia-auto")

    def test_nuvem_so_com_consentimento_explicito(self):
        n = importar_nodes(TUDOIA_MODEL="tudoia-auto", TUDOIA_PERMITIR_NUVEM="1")
        self.assertEqual(n.TUDOIA_MODEL, "tudoia-auto")

    def test_perfil_local_estrito_passa_sem_consentimento(self):
        os.environ.pop("TUDOIA_PERMITIR_NUVEM", None)
        self.assertEqual(importar_nodes(TUDOIA_MODEL="tudoia-local-estrito").TUDOIA_MODEL, "tudoia-local-estrito")

    def test_perfis_que_podem_sair_da_maquina_exigem_consentimento(self):
        os.environ.pop("TUDOIA_PERMITIR_NUVEM", None)
        for modelo in ("tudoia-hibrido", "tudoia-nuvem", "tudoia-max", "tudoia-local-estrito-x", "tudoia-local-agente"):
            with self.assertRaises(RuntimeError, msg=modelo):
                importar_nodes(TUDOIA_MODEL=modelo)
        self.assertEqual(importar_nodes(TUDOIA_MODEL="tudoia-hibrido", TUDOIA_PERMITIR_NUVEM="1").TUDOIA_MODEL,
                         "tudoia-hibrido")

    def test_modelo_local_especifico_passa(self):
        self.assertEqual(importar_nodes(TUDOIA_MODEL="local/qwen3.5:latest").TUDOIA_MODEL, "local/qwen3.5:latest")


class Nos(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        doutrina_falsa(base / "doutrina")
        self.ws = base / "ws"
        self.state = {
            "task_id": "T1", "project_name": "Demo", "workspace_dir": str(self.ws),
            "architecture_source_path": str(base / "doutrina"), "iteration_count": 0,
            "doutrina_versao": "9.9.9", "doutrina_hash": "aaaa",
            "target_stack": {"backend": {"build_command": "dotnet build", "test_command": "dotnet test"},
                             "frontend": {}, "database": {"engine": "mssql"}},
        }
        self.env = mock.patch.dict(os.environ, {}, clear=False)
        self.env.start()
        os.environ.pop("DOUTRINA_TEC", None)
        os.environ.pop("TUDOIA_MODEL", None)
        self.n = importar_nodes()
        _LlmFalso.chamadas = []

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_arquiteto_recusa_comecar_sem_aprovacao_do_usuario(self):
        self.ws.mkdir(parents=True)
        for estado in ({**self.state, "business_spec_file": "docs/negocio/BUSINESS_SPEC.md"},
                       {**self.state, "business_spec_file": "docs/negocio/BUSINESS_SPEC.md",
                        "business_spec_approved": False}):
            with self.assertRaises(RuntimeError):
                self.n.node_arquiteto(estado)
        self.assertEqual(_LlmFalso.chamadas, [])  # nem chegou a chamar o modelo

    def test_qa_sem_projeto_reprova(self):
        r = self.n.node_qa_testes(self.state)
        self.assertFalse(r["tests_passed"])
        self.assertEqual(r["iteration_count"], 1)
        rel = json.loads((self.ws / r["qa_report_file"]).read_text(encoding="utf-8"))
        self.assertFalse(rel["aprovado"])
        self.assertIn("nada a testar", rel["motivo"])

    def test_qa_preserva_erro_anterior_quando_nao_ha_projeto(self):
        r = self.n.node_qa_testes({**self.state, "last_error_log": "scaffold falhou: template ausente"})
        self.assertIn("scaffold falhou", r["last_error_log"])

    def test_qa_com_projeto_quebrado_reprova_com_log(self):
        self.ws.mkdir(parents=True)
        (self.ws / "A.csproj").write_text("<Project Sdk='Microsoft.NET.Sdk'><nao fecha", encoding="utf-8")
        r = self.n.node_qa_testes(self.state)
        self.assertFalse(r["tests_passed"])
        self.assertTrue(r["last_error_log"])

    def test_appsec_sem_projeto_nao_aprova(self):
        r = self.n.node_appsec(self.state)
        self.assertFalse(r["security_passed"])
        self.assertEqual(r["current_phase"], "ENTREGA_BLOQUEADA")

    # ---- QA: frontend à prova de falha aberta, gate de cobertura e rota de correção
    def qa_com_dotnet_ok(self, frontend=None):
        self.ws.mkdir(parents=True, exist_ok=True)
        (self.ws / "A.csproj").write_text("<Project/>", encoding="utf-8")
        p = mock.patch.object(self.n, "executar", return_value=(0, "ok"))
        p.start()
        self.addCleanup(p.stop)
        return {**self.state, "target_stack": {**self.state["target_stack"], "frontend": frontend or {}}}

    def cobertura_xml(self, linhas_cobertas, total=10, nome="TestResults/a.cobertura.xml"):
        ls = "".join(f'<line number="{i}" hits="{1 if i < linhas_cobertas else 0}" branch="false"/>' for i in range(total))
        arq = self.ws / nome
        arq.parent.mkdir(parents=True, exist_ok=True)
        arq.write_text(f'<coverage><class filename="a.cs"><lines>{ls}</lines></class></coverage>', encoding="utf-8")

    def test_qa_frontend_esperado_sem_package_json_reprova_mesmo_com_backend_ok(self):
        estado = self.qa_com_dotnet_ok(frontend={"framework": "react19"})
        self.cobertura_xml(10)
        r = self.n.node_qa_testes(estado)
        self.assertFalse(r["tests_passed"])
        self.assertEqual(r["falha_origem"], "frontend")
        self.assertIn("package.json", r["last_error_log"])

    def test_qa_sem_cobertura_medida_reprova_e_atribui_ao_backend(self):
        estado = self.qa_com_dotnet_ok()
        r = self.n.node_qa_testes(estado)
        self.assertFalse(r["tests_passed"])
        self.assertEqual(r["falha_origem"], "backend")
        self.assertIn("cobertura não medida", r["last_error_log"])
        rel = json.loads((self.ws / r["qa_report_file"]).read_text(encoding="utf-8"))
        self.assertEqual(rel["etapas"][-1]["etapa"], "cobertura")

    def test_qa_cobertura_abaixo_de_90_reprova_e_em_90_aprova(self):
        estado = self.qa_com_dotnet_ok()
        self.cobertura_xml(8)
        r = self.n.node_qa_testes(estado)
        self.assertFalse(r["tests_passed"])
        self.assertIn("abaixo de 90", r["last_error_log"])
        self.cobertura_xml(9)
        r = self.n.node_qa_testes(estado)
        self.assertTrue(r["tests_passed"])
        self.assertIsNone(r["falha_origem"])

    def test_qa_gate_desligado_so_por_configuracao_explicita(self):
        estado = self.qa_com_dotnet_ok()
        estado["target_stack"]["quality"] = {"coverage_min": 0}
        r = self.n.node_qa_testes(estado)
        self.assertTrue(r["tests_passed"])
        rel = json.loads((self.ws / r["qa_report_file"]).read_text(encoding="utf-8"))
        self.assertIn("desligado", rel["etapas"][-1]["saida_final"])

    def test_dev_backend_nao_recebe_erro_do_frontend(self):
        (self.ws / "docs/arquitetura").mkdir(parents=True)
        (self.ws / "docs/arquitetura/PRD_TECNICO.md").write_text("prd", encoding="utf-8")
        (self.ws / "A.csproj").write_text("<Project/>", encoding="utf-8")
        _LlmFalso.resposta = "### ARQUIVO: src/A.cs\n```cs\nclass A{}\n```\n"
        base = {**self.state, "technical_prd_file": "docs/arquitetura/PRD_TECNICO.md"}
        self.n.node_dev_backend({**base, "last_error_log": "error TS2304: x", "falha_origem": "frontend"})
        self.assertNotIn("TS2304", _LlmFalso.chamadas[-1][0].content)
        self.n.node_dev_backend({**base, "last_error_log": "error CS1002: y", "falha_origem": "backend"})
        self.assertIn("CS1002", _LlmFalso.chamadas[-1][0].content)

    def test_dev_frontend_recebe_so_erro_do_frontend_e_usa_o_nucleo_do_perfil(self):
        self.ws.mkdir(parents=True, exist_ok=True)
        (self.ws / "contracts").mkdir()
        (self.ws / "contracts/openapi.yaml").write_text("openapi: 3.1.0", encoding="utf-8")
        _LlmFalso.resposta = "### ARQUIVO: frontend/package.json\n```json\n{}\n```\n"
        base = {**self.state, "openapi_file": "contracts/openapi.yaml"}
        self.n.node_dev_frontend({**base, "last_error_log": "error TS2322: z", "falha_origem": "frontend"})
        self.assertIn("TS2322", _LlmFalso.chamadas[-1][0].content)
        self.n.node_dev_frontend({**base, "last_error_log": "error TS2322: z", "falha_origem": "backend"})
        self.assertNotIn("TS2322", _LlmFalso.chamadas[-1][0].content)

    # ---- AppSec: segredo bloqueia, e o valor nunca aparece no relatório
    def test_appsec_bloqueia_segredo_sem_vazar_o_valor(self):
        self.ws.mkdir(parents=True, exist_ok=True)
        (self.ws / "A.csproj").write_text("<Project/>", encoding="utf-8")
        (self.ws / "appsettings.json").write_text('{"c":"Server=x;Password=Valor-Secreto-9;"}', encoding="utf-8")
        with mock.patch.object(self.n, "executar", return_value=(0, "ok")):
            r = self.n.node_appsec(self.state)
        self.assertFalse(r["security_passed"])
        self.assertEqual(r["current_phase"], "ENTREGA_BLOQUEADA")
        texto = (self.ws / r["security_report_file"]).read_text(encoding="utf-8")
        self.assertIn("senha-em-connection-string", texto)
        self.assertNotIn("Valor-Secreto-9", texto)
        self.assertIn("NÃO cobre", texto)

    def test_appsec_limpo_aprova_e_declara_o_que_nao_cobre(self):
        self.ws.mkdir(parents=True, exist_ok=True)
        (self.ws / "A.csproj").write_text("<Project/>", encoding="utf-8")
        with mock.patch.object(self.n, "executar", return_value=(0, "ok")):
            r = self.n.node_appsec(self.state)
        self.assertTrue(r["security_passed"])
        rel = json.loads((self.ws / r["security_report_file"]).read_text(encoding="utf-8"))
        self.assertIn("não significa 'segura'", rel["cobertura"])

    # ---- Janela de contexto: prompt maior que a janela é recusado antes de chegar ao modelo (truncamento silencioso derrubaria as regras)
    def test_prompt_maior_que_a_janela_e_recusado_sem_chamar_o_modelo(self):
        (self.ws / "docs/arquitetura").mkdir(parents=True)
        (self.ws / "docs/arquitetura/PRD_TECNICO.md").write_text("prd " * 2000, encoding="utf-8")
        with mock.patch.dict(os.environ, {"TUDOIA_CONTEXTO_TOKENS": "1024"}):
            with self.assertRaises(RuntimeError) as cm:
                self.n.node_dba({**self.state, "technical_prd_file": "docs/arquitetura/PRD_TECNICO.md"})
        self.assertIn("não cabe na janela", str(cm.exception))
        self.assertIn("Nada foi enviado", str(cm.exception))
        self.assertEqual(_LlmFalso.chamadas, [])

    def test_resposta_minuscula_gera_dica_de_janela_e_resposta_longa_nao(self):
        with self.assertRaises(RuntimeError) as cm:
            self.n._gravar("**\n```", self.state, ("docs/",), ("docs/a.md",))
        self.assertIn("só 6 caracteres", str(cm.exception))
        self.assertIn("TUDOIA_CONTEXTO_TOKENS", str(cm.exception))
        with self.assertRaises(RuntimeError) as cm:
            self.n._gravar("texto sem bloco " * 30, self.state, ("docs/",), ("docs/a.md",))
        self.assertNotIn("caracteres:", str(cm.exception))

    def test_timeout_do_modelo_tem_padrao_e_ignora_valor_invalido(self):
        for ruim in ("abc", "", "-1", "0", "1", "99999"):
            with mock.patch.dict(os.environ, {"TUDOIA_TIMEOUT_S": ruim}):
                self.assertEqual(self.n.timeout_do_modelo(), 300.0, ruim)
        with mock.patch.dict(os.environ, {"TUDOIA_TIMEOUT_S": "90"}):
            self.assertEqual(self.n.timeout_do_modelo(), 90.0)

    def test_modelo_por_tarefa_so_perfil_conhecido_e_nuvem_so_com_consentimento(self):
        base = {**self.state}
        self.assertEqual(self.n.modelo_da_tarefa(base), self.n.TUDOIA_MODEL)
        self.assertEqual(self.n.modelo_da_tarefa({**base, "modelo": "tudoia-local"}), "tudoia-local")
        with self.assertRaises(RuntimeError) as cm:
            self.n.modelo_da_tarefa({**base, "modelo": "gpt-qualquer"})
        self.assertIn("perfil conhecido", str(cm.exception))
        with self.assertRaises(RuntimeError) as cm:
            self.n.modelo_da_tarefa({**base, "modelo": "tudoia-nuvem"})
        self.assertIn("consentimento", str(cm.exception))
        with self.assertRaises(RuntimeError):
            self.n.modelo_da_tarefa({**base, "modelo": "tudoia-nuvem", "consentimento_nuvem": "sim"})
        self.assertEqual(self.n.modelo_da_tarefa({**base, "modelo": "tudoia-nuvem", "consentimento_nuvem": True}), "tudoia-nuvem")
        # tudoia-auto (roteador) é perfil da Squad, mas pode sair da máquina: só com o consentimento explícito da tarefa
        with self.assertRaises(RuntimeError) as cm:
            self.n.modelo_da_tarefa({**base, "modelo": "tudoia-auto"})
        self.assertIn("consentimento", str(cm.exception))
        self.assertEqual(self.n.modelo_da_tarefa({**base, "modelo": "tudoia-auto", "consentimento_nuvem": True}), "tudoia-auto")
        # modelo que não é perfil da Squad: nunca, nem com consentimento
        with self.assertRaises(RuntimeError):
            self.n.modelo_da_tarefa({**base, "modelo": "tudoia-qualquer", "consentimento_nuvem": True})

    def test_janela_invalida_volta_ao_padrao_e_nunca_desliga_a_checagem(self):
        for ruim in ("abc", "", "-5", "0", "10", "999999999999"):
            with mock.patch.dict(os.environ, {"TUDOIA_CONTEXTO_TOKENS": ruim}):
                self.assertEqual(self.n.janela_de_contexto(), self.n.JANELA_PADRAO_TOKENS, ruim)
        with mock.patch.dict(os.environ, {"TUDOIA_CONTEXTO_TOKENS": "8192"}):
            self.assertEqual(self.n.janela_de_contexto(), 8192)

    def test_prompt_que_cabe_passa_e_a_folga_de_resposta_conta(self):
        self.assertGreater(self.n.verificar_contexto("x" * 400, "y" * 400), 0)
        with mock.patch.dict(os.environ, {"TUDOIA_CONTEXTO_TOKENS": "1024"}):
            self.n.verificar_contexto("x" * 3000, "")  # ~750 tokens: cabe (limite ~870)
            with self.assertRaises(RuntimeError):
                self.n.verificar_contexto("x" * 3600, "")  # ~900 tokens: passa de 85% da janela

    def test_no_aborta_se_a_doutrina_mudou(self):
        with self.assertRaises(self.n.dout.DoutrinaIndisponivel):
            self.n.node_qa_testes({**self.state, "doutrina_hash": "outro"})

    def test_dba_grava_so_o_que_o_modelo_entregou_dentro_da_area(self):
        (self.ws / "docs/arquitetura").mkdir(parents=True)
        (self.ws / "docs/arquitetura/PRD_TECNICO.md").write_text("prd", encoding="utf-8")
        _LlmFalso.resposta = ("### ARQUIVO: docs/dados/DICIONARIO.md\n```md\ntab\n```\n"
                              "### ARQUIVO: src/Infra/ClienteConfig.cs\n```cs\nclass C{}\n```\n")
        r = self.n.node_dba({**self.state, "technical_prd_file": "docs/arquitetura/PRD_TECNICO.md"})
        self.assertEqual(sorted(r["arquivos_gerados"]), ["docs/dados/DICIONARIO.md", "src/Infra/ClienteConfig.cs"])
        self.assertIn("ARQ-DOM-05", _LlmFalso.chamadas[0][0].content)

    def test_dba_recusa_escrita_fora_da_area(self):
        (self.ws / "docs/arquitetura").mkdir(parents=True)
        (self.ws / "docs/arquitetura/PRD_TECNICO.md").write_text("prd", encoding="utf-8")
        _LlmFalso.resposta = "### ARQUIVO: ../../fora.txt\n```\nx\n```\n"
        with self.assertRaises(RuntimeError):
            self.n.node_dba({**self.state, "technical_prd_file": "docs/arquitetura/PRD_TECNICO.md"})
        self.assertFalse((Path(self.tmp.name) / "fora.txt").exists())

    def test_prompt_manda_citar_id_no_relatorio_nao_no_codigo(self):
        self.assertIn("NÃO escreva IDs em comentários", self.n.FORMATO_ARQUIVOS)


if __name__ == "__main__":
    unittest.main()

"""Testes das fronteiras da Squad. Rodar em orquestrador/: python -m unittest discover -s tests -v"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import doutrina_tec as dout  # noqa: E402
from execucao import caminho_seguro, escrever_arquivos, executar  # noqa: E402


DOUTRINA_REAL = os.getenv("DOUTRINA_TEC")  # capturada antes do setUp limpar o ambiente


def doutrina_falsa(raiz: Path, hash_: str = "aaaa", versao: str = "9.9.9") -> None:
    g = raiz / "gerado"
    g.mkdir(parents=True)
    (g / "manifesto.json").write_text(json.dumps({"versao": versao, "hash": hash_}), encoding="utf-8")
    (g / "arquitetura-nucleo.md").write_text("NUCLEO", encoding="utf-8")
    (g / "ia-nucleo.md").write_text("NUCLEO-IA", encoding="utf-8")
    (g / "ecossistema-nucleo.md").write_text("NUCLEO-ECO", encoding="utf-8")
    (g / "ia.json").write_text(json.dumps({
        "por_papel": {"chefe": ["06.md"], "qa": ["05.md"], "frontend": ["05.md"], "documentacao": ["07.md"],
                      "requisitos": ["07.md"], "arquiteto": ["07.md"]},
        "regras": [
            {"id": "IA-DOC-01", "nivel": "MUST", "nucleo": False, "padrao": "07.md", "texto": "documentar",
             "verif": ["revisao"], "evidencia": []},
            {"id": "IA-ORQ-01", "nivel": "MUST", "nucleo": False, "padrao": "06.md", "texto": "orquestrar",
             "verif": ["teste"], "evidencia": ["squadti:orquestrador/tests/test_fronteiras.py#x"]},
            {"id": "IA-VER-01", "nivel": "MUST", "nucleo": False, "padrao": "05.md", "texto": "verificar",
             "verif": ["revisao"], "evidencia": []},
        ]}), encoding="utf-8")
    (g / "ecossistema.json").write_text(json.dumps({"por_papel": {"chefe": ["01.md"]}, "regras": [
        {"id": "ECO-MAP-01", "nivel": "MUST", "nucleo": False, "padrao": "01.md", "texto": "mapa",
         "verif": ["revisao"], "evidencia": []}]}), encoding="utf-8")
    (g / "seguranca-nucleo.md").write_text("NUCLEO-SEC", encoding="utf-8")
    (g / "seguranca.json").write_text(json.dumps({"por_papel": {"appsec": ["01.md"]}, "regras": [
        {"id": "SEC-AUT-01", "nivel": "MUST", "nucleo": True, "padrao": "01.md", "texto": "AUTORIZAR-SEGREDO-DO-TEXTO",
         "verif": ["revisao"], "evidencia": []},
        {"id": "SEC-INP-02", "nivel": "SHOULD", "nucleo": False, "padrao": "01.md", "texto": "validar",
         "verif": ["revisao"], "evidencia": []},
        {"id": "SEC-OPC-03", "nivel": "MAY", "nucleo": False, "padrao": "01.md", "texto": "opcional",
         "verif": ["revisao"], "evidencia": []}]}), encoding="utf-8")
    (g / "perfis").mkdir()
    for papel, nucleo in {"chefe": ["ia", "ecossistema"], "qa": ["ia", "ecossistema", "arquitetura"],
                          "appsec": ["ia", "ecossistema", "seguranca"], "documentacao": ["ia", "ecossistema"],
                          "frontend": ["ia", "ecossistema"], "requisitos": ["ia", "ecossistema"],
                          "arquiteto": ["ia", "ecossistema", "arquitetura"],
                          "backend": ["ia", "ecossistema", "arquitetura"], "dba": ["ia", "ecossistema", "arquitetura"]}.items():
        (g / "perfis" / f"{papel}.json").write_text(json.dumps({
            "papel": papel, "nucleo_sugerido": nucleo, "nucleo_tokens": 10, "consulta_sob_demanda": [],
            "familias": [{"nome": n} for n in nucleo]}), encoding="utf-8")
    (g / "arquitetura.json").write_text(json.dumps({
        "por_papel": {"backend": ["03.md"], "dba": ["03.md"], "qa": ["10.md"]},
        "regras": [
            {"id": "ARQ-DOM-02", "nivel": "MUST", "nucleo": True, "padrao": "03.md", "texto": "fabrica",
             "verif": ["teste-arq"], "evidencia": ["ConvencoesTests.Entidades_SemSetterPublico"]},
            {"id": "ARQ-DOM-05", "nivel": "MUST", "nucleo": False, "padrao": "03.md", "texto": "catalogo",
             "verif": ["revisao"], "evidencia": []},
            {"id": "ARQ-TST-01", "nivel": "MUST", "nucleo": False, "padrao": "10.md", "texto": "testar",
             "verif": ["teste"], "evidencia": []},
        ]}), encoding="utf-8")


class DoutrinaTec(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self.tmp.name)
        doutrina_falsa(self.raiz)
        self.state = {"architecture_source_path": str(self.raiz)}
        self.env = mock.patch.dict(os.environ, {}, clear=False)
        self.env.start()
        os.environ.pop("DOUTRINA_TEC", None)

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_regras_do_papel_exclui_nucleo_e_outros_papeis(self):
        r = dout.regras_do_papel("backend", self.state)
        self.assertIn("ARQ-DOM-05", r)
        self.assertNotIn("ARQ-DOM-02", r)  # núcleo já vai no contexto fixo
        self.assertNotIn("ARQ-TST-01", r)  # é do papel qa

    def test_incluir_nucleo_traz_evidencia(self):
        self.assertIn("prova: ConvencoesTests.Entidades_SemSetterPublico",
                      dout.regras_do_papel("backend", self.state, incluir_nucleo=True))

    def test_papel_desconhecido_falha_fechado(self):
        with self.assertRaises(dout.DoutrinaIndisponivel):
            dout.regras_do_papel("estagiario", self.state)

    def test_sem_caminho_falha_fechado(self):
        with self.assertRaises(dout.DoutrinaIndisponivel):
            dout.nucleo({})

    def test_pasta_que_nao_e_doutrina_falha_fechado(self):
        with tempfile.TemporaryDirectory() as vazia, self.assertRaises(dout.DoutrinaIndisponivel):
            dout.nucleo({"architecture_source_path": vazia})

    def test_variavel_de_ambiente_tem_precedencia(self):
        with tempfile.TemporaryDirectory() as outra:
            doutrina_falsa(Path(outra), versao="1.0.0")
            with mock.patch.dict(os.environ, {"DOUTRINA_TEC": outra}):
                self.assertEqual(dout.manifesto(self.state)["versao"], "1.0.0")

    def test_versao_gravada_na_primeira_chamada(self):
        self.assertEqual(dout.verificar_versao(self.state), {"doutrina_versao": "9.9.9", "doutrina_hash": "aaaa"})

    def test_mudanca_de_doutrina_no_meio_da_tarefa_aborta(self):
        estado = {**self.state, "doutrina_versao": "9.9.8", "doutrina_hash": "bbbb"}
        with self.assertRaises(dout.DoutrinaIndisponivel):
            dout.verificar_versao(estado)

    def test_json_corrompido_falha_fechado(self):
        (self.raiz / "gerado" / "arquitetura.json").write_text("{nao e json", encoding="utf-8")
        with self.assertRaises(dout.DoutrinaIndisponivel):
            dout.regras_do_papel("backend", self.state)

    def test_evidencias(self):
        self.assertEqual(list(dout.evidencias(self.state)), ["ARQ-DOM-02"])  # prova de outro repo não é teste do template

    def test_nucleo_junta_as_familias_na_ordem(self):
        self.assertEqual(dout.nucleo(self.state), "NUCLEO\n\nNUCLEO-IA\n\nNUCLEO-ECO")

    def test_regras_do_papel_juntam_familias(self):
        r = dout.regras_do_papel("chefe", self.state)
        self.assertIn("IA-ORQ-01", r)
        self.assertIn("ECO-MAP-01", r)
        self.assertIn("prova: squadti:", r)
        self.assertNotIn("IA-VER-01", r)  # é do papel qa
        self.assertIn("IA-VER-01", dout.regras_do_papel("qa", self.state))

    def test_papel_so_existe_em_uma_familia_nao_e_erro(self):
        self.assertIn("ARQ-DOM-05", dout.regras_do_papel("dba", self.state))  # dba só na arquitetura

    def test_familias_configuraveis_por_ambiente_e_estado(self):
        with mock.patch.dict(os.environ, {"DOUTRINA_FAMILIAS": "arquitetura"}):
            self.assertEqual(dout.nucleo(self.state), "NUCLEO")
        self.assertEqual(dout.nucleo({**self.state, "doutrina_familias": ["ia"]}), "NUCLEO-IA")

    def test_familia_inexistente_falha_fechado(self):
        with self.assertRaises(dout.DoutrinaIndisponivel):
            dout.nucleo({**self.state, "doutrina_familias": ["componentes"]})

    def test_nome_de_familia_hostil_e_recusado(self):
        for ruim in ["../x", "a/b", "A", "", "ia,../../etc", "x" * 41, "ia;rm"]:
            with mock.patch.dict(os.environ, {"DOUTRINA_FAMILIAS": ruim}):
                if ruim == "":
                    self.assertEqual(dout.familias(self.state), dout.FAMILIAS_PADRAO)  # vazio = padrão
                else:
                    with self.assertRaises(dout.DoutrinaIndisponivel, msg=ruim):
                        dout.nucleo(self.state)

    def test_perfil_define_o_nucleo_do_papel(self):
        self.assertEqual(dout.nucleo(self.state, "backend"), "NUCLEO-IA\n\nNUCLEO-ECO\n\nNUCLEO")
        self.assertEqual(dout.nucleo(self.state, "chefe"), "NUCLEO-IA\n\nNUCLEO-ECO")
        self.assertIn("NUCLEO-ECO", dout.contexto("chefe", self.state))
        self.assertNotIn("NUCLEO\n", dout.contexto("chefe", self.state) + "\n")  # arquitetura não é do perfil do chefe

    def test_familias_forcadas_valem_para_todos_os_papeis(self):
        with mock.patch.dict(os.environ, {"DOUTRINA_FAMILIAS": "ia"}):
            self.assertEqual(dout.nucleo(self.state, "backend"), "NUCLEO-IA")

    def test_perfil_ausente_corrompido_ou_hostil_falha_fechado(self):
        for papel in ("estagiario", "../x", "a/b", "x" * 21):
            with self.assertRaises(dout.DoutrinaIndisponivel, msg=papel):
                dout.nucleo(self.state, papel)
        (self.raiz / "gerado" / "perfis" / "qa.json").write_text("{nao e json", encoding="utf-8")
        with self.assertRaises(dout.DoutrinaIndisponivel):
            dout.nucleo(self.state, "qa")
        (self.raiz / "gerado" / "perfis" / "qa.json").write_text(json.dumps({"nucleo_sugerido": "ia"}), encoding="utf-8")
        with self.assertRaises(dout.DoutrinaIndisponivel):
            dout.nucleo(self.state, "qa")
        (self.raiz / "gerado" / "perfis" / "qa.json").write_text(
            json.dumps({"nucleo_sugerido": ["../x"], "familias": []}), encoding="utf-8")
        with self.assertRaises(dout.DoutrinaIndisponivel):
            dout.nucleo(self.state, "qa")

    def test_regras_cabem_no_orcamento_must_primeiro_may_fora_e_omissao_declarada(self):
        regras = [{"id": f"ARQ-X-{i:02d}", "nivel": n, "nucleo": False, "padrao": "03.md", "texto": "t" * 200,
                   "verif": ["revisao"], "evidencia": []}
                  for i, n in enumerate(["SHOULD"] * 5 + ["MAY"] * 2 + ["MUST"] * 2)]
        (self.raiz / "gerado" / "arquitetura.json").write_text(json.dumps({
            "por_papel": {"backend": ["03.md"]}, "regras": regras}), encoding="utf-8")
        r = dout.regras_do_papel("backend", self.state, orcamento_tokens=130)
        linhas = r.splitlines()
        self.assertEqual([l.split("**")[1] for l in linhas[:2]], ["ARQ-X-07", "ARQ-X-08"])  # MUST primeiro
        self.assertNotIn("MAY", "".join(linhas[:-1]))
        self.assertIn("omitida(s) por orçamento", linhas[-1])
        completo = dout.regras_do_papel("backend", self.state, orcamento_tokens=10_000)
        self.assertEqual(sum(1 for l in completo.splitlines() if "** SHOULD" in l), 5)
        self.assertIn("2 regra(s) SHOULD/MAY omitida(s)", completo)  # os 2 MAY continuam fora, e isso é dito

    def test_contexto_de_varios_papeis_nao_repete_o_nucleo_e_traz_as_regras_de_cada_um(self):
        c = dout.contexto(("backend", "frontend"), self.state)
        self.assertEqual(c.count("NUCLEO-IA"), 1)
        self.assertEqual(c.count("NUCLEO-ECO"), 1)
        self.assertIn("ARQ-DOM-05", c)   # regra de backend
        self.assertIn("IA-VER-01", c)    # regra de frontend
        self.assertIn("REGRAS DO PAPEL (backend)", c)
        self.assertIn("REGRAS DO PAPEL (frontend)", c)
        self.assertEqual(dout.contexto("backend", self.state), dout.contexto(("backend",), self.state))

    def test_contexto_sem_papel_ou_com_papel_desconhecido_falha_fechado(self):
        for ruim in ((), [], "", ("backend", "estagiario")):
            with self.assertRaises(dout.DoutrinaIndisponivel, msg=repr(ruim)):
                dout.contexto(ruim, self.state)

    def test_ids_do_papel_so_ids_e_niveis_com_nucleo_e_may_e_sem_texto(self):
        ids = dout.ids_do_papel("appsec", self.state, "SEC-")
        self.assertEqual(ids, [{"id": "SEC-AUT-01", "nivel": "MUST"}, {"id": "SEC-INP-02", "nivel": "SHOULD"},
                               {"id": "SEC-OPC-03", "nivel": "MAY"}])
        self.assertNotIn("AUTORIZAR", json.dumps(ids))
        self.assertEqual(dout.ids_do_papel("appsec", self.state, "XYZ-"), [])
        with self.assertRaises(dout.DoutrinaIndisponivel):
            dout.ids_do_papel("estagiario", self.state)

    def test_orcamento_de_regras_por_ambiente_valido_e_nunca_ilimitado(self):
        for ruim in ("abc", "", "0", "499", "-1", "999999999"):
            with mock.patch.dict(os.environ, {"DOUTRINA_REGRAS_MAX_TOKENS": ruim}):
                self.assertEqual(dout.orcamento_de_regras(), dout.ORCAMENTO_REGRAS_TOKENS, ruim)
        with mock.patch.dict(os.environ, {"DOUTRINA_REGRAS_MAX_TOKENS": "4000"}):
            self.assertEqual(dout.orcamento_de_regras(), 4000)

    def test_variavel_de_orcamento_reduz_as_regras_do_papel(self):
        regras = [{"id": f"ARQ-X-{i:02d}", "nivel": "SHOULD", "nucleo": False, "padrao": "03.md", "texto": "t" * 400,
                   "verif": ["revisao"], "evidencia": []} for i in range(40)]
        (self.raiz / "gerado" / "arquitetura.json").write_text(json.dumps({
            "por_papel": {"backend": ["03.md"]}, "regras": regras}), encoding="utf-8")
        cheio = dout.regras_do_papel("backend", self.state)
        with mock.patch.dict(os.environ, {"DOUTRINA_REGRAS_MAX_TOKENS": "1000"}):
            curto = dout.regras_do_papel("backend", self.state)
        self.assertLess(len(curto), len(cheio))
        self.assertIn("omitida(s) por orçamento", curto)

    @unittest.skipUnless(DOUTRINA_REAL, "defina DOUTRINA_TEC para testar contra a doutrina real")
    def test_doutrina_real_todos_os_papeis_resolvem(self):
        with mock.patch.dict(os.environ, {"DOUTRINA_TEC": DOUTRINA_REAL}):
            for papel in ["chefe", "requisitos", "arquiteto", "dba", "backend", "frontend", "qa", "appsec", "devops",
                          "documentacao"]:
                self.assertTrue(dout.regras_do_papel(papel, {}).strip(), f"papel sem regras: {papel}")
                self.assertTrue(dout.nucleo({}, papel).strip(), f"papel sem núcleo: {papel}")
                self.assertLessEqual(len(dout.contexto(papel, {})) // 4, 7000 + 12000 + 400, f"contexto grande: {papel}")
            self.assertTrue(dout.evidencias({}))
            self.assertRegex(dout.manifesto({})["versao"], r"^\d+\.\d+\.\d+$")
            # revisor: núcleo de backend+frontend sem repetir, regras dos dois papéis
            self.assertLessEqual(len(dout.contexto(("backend", "frontend"), {})) // 4, 7000 + 2 * 12000 + 800)
            ids = dout.ids_do_papel("appsec", {}, "SEC-")
            self.assertTrue(ids and all(i["id"].startswith("SEC-") for i in ids))


class Execucao(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self.tmp.name) / "ws"
        self.raiz.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def bloco(self, caminho, corpo="x"):
        return f"### ARQUIVO: {caminho}\n```csharp\n{corpo}\n```\n"

    def test_grava_arquivo_valido(self):
        ok, rec = escrever_arquivos(self.bloco("src/A.cs", "class A {}"), self.raiz, ("src/",))
        self.assertEqual((ok, rec), (["src/A.cs"], []))
        self.assertEqual((self.raiz / "src" / "A.cs").read_text(encoding="utf-8"), "class A {}\n")

    def test_recusa_travessia_absoluto_e_unidade(self):
        for ruim in ["../fora.cs", "src/../../fora.cs", "/etc/passwd", "C:/Windows/x.cs", "C:\\x.cs", "..\\x.cs"]:
            ok, rec = escrever_arquivos(self.bloco(ruim), self.raiz)
            self.assertEqual(ok, [], ruim)
            self.assertEqual(len(rec), 1, ruim)
        self.assertFalse((Path(self.tmp.name) / "fora.cs").exists())

    def test_arquivo_exato_da_raiz_nao_abre_a_raiz_inteira(self):
        permitidos = ("docs/", "README.md")
        ok, rec = escrever_arquivos(self.bloco("README.md", "# x"), self.raiz, permitidos)
        self.assertEqual((ok, rec), (["README.md"], []))
        for ruim in ["Outro.md", "README.mdx", "README.md.exe", "readme.md", "./README.md", "docs2/a.md", "sub/README.md"]:
            ok, rec = escrever_arquivos(self.bloco(ruim), self.raiz, permitidos)
            self.assertEqual(ok, [], ruim)
            self.assertEqual(len(rec), 1, ruim)
        self.assertEqual(sorted(p.name for p in self.raiz.iterdir()), ["README.md"])

    def test_recusa_fluxo_alternativo_e_ponto_ou_espaco_no_fim(self):
        for ruim in ["docs/a.md:evil", "docs/negocio./x.md", "docs/negocio /x.md", "docs/a.md."]:
            ok, rec = escrever_arquivos(self.bloco(ruim), self.raiz, ("docs/",))
            self.assertEqual(ok, [], ruim)
            self.assertEqual(len(rec), 1, ruim)

    def test_recusa_fora_da_area_permitida(self):
        ok, rec = escrever_arquivos(self.bloco("docs/A.md"), self.raiz, ("src/",))
        self.assertEqual(ok, [])
        self.assertEqual(len(rec), 1)

    def test_recusa_arquivo_gigante(self):
        ok, rec = escrever_arquivos(self.bloco("src/G.cs", "x" * 300_000), self.raiz, ("src/",))
        self.assertEqual(ok, [])
        self.assertEqual(len(rec), 1)

    def test_limite_de_arquivos(self):
        resp = "".join(self.bloco(f"src/F{i}.cs") for i in range(55))
        ok, rec = escrever_arquivos(resp, self.raiz, ("src/",))
        self.assertEqual(len(ok), 50)
        self.assertEqual(len(rec), 5)

    def test_resposta_sem_blocos_nao_grava_nada(self):
        self.assertEqual(escrever_arquivos("só texto", self.raiz), ([], []))
        self.assertEqual(escrever_arquivos("", self.raiz), ([], []))

    def test_caminho_seguro_aceita_subpasta(self):
        self.assertEqual(caminho_seguro(self.raiz, "a/b/c.txt"), (self.raiz / "a" / "b" / "c.txt").resolve())

    def test_executavel_fora_da_lista_nao_roda(self):
        codigo, saida = executar("powershell -c echo oi", self.raiz)
        self.assertEqual(codigo, 126)
        self.assertIn("não permitido", saida)

    def test_comando_vazio(self):
        self.assertEqual(executar("", self.raiz)[0], 126)

    def test_dotnet_roda_sem_shell(self):
        codigo, saida = executar("dotnet --version", self.raiz, timeout_s=60)
        self.assertIn(codigo, (0, 127))  # 127 = dotnet ausente nesta máquina
        if codigo == 0:
            self.assertRegex(saida.strip().splitlines()[0], r"^\d+\.")


if __name__ == "__main__":
    unittest.main()

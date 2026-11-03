"""Módulos novos da Squad v2 (entrada, auditoria, aprovação por hash, stacks, config dos agentes, achados verificados, proveniência).

Cada controle é testado no caminho feliz E no adversarial (entrada hostil, valor fora da faixa, conteúdo trocado depois do sim)."""
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import agentes  # noqa: E402
import aprovacao  # noqa: E402
import auditoria  # noqa: E402
import entrada  # noqa: E402
import proveniencia  # noqa: E402
import revisao  # noqa: E402
import stacks  # noqa: E402


# ------------------------------------------------------------------------------------------------ entrada
class Sanitizacao(unittest.TestCase):
    def test_remove_invisiveis_direcao_e_controle_e_conta(self):
        sujo = "ola\u200b mun\u202edo\x00\x07 \ufeffok\U000e0041"
        limpo, n = entrada.sanitizar(sujo)
        self.assertEqual(limpo, "ola mundo ok")
        self.assertEqual(n, 6)

    def test_preserva_quebra_de_linha_tabulacao_e_acentos(self):
        limpo, n = entrada.sanitizar("linha1\n\tlinha2 ação\r\n")
        self.assertEqual((limpo, n), ("linha1\n\tlinha2 ação\r\n", 0))

    def test_homoglifo_cirilico_dentro_de_palavra_latina_e_detectado(self):
        self.assertTrue(entrada.tem_homoglifos("admin\u0430"))      # 'а' cirílico no fim de 'admin'
        self.assertFalse(entrada.tem_homoglifos("administrador cadastro"))
        self.assertFalse(entrada.tem_homoglifos("Привет мир"))      # só cirílico: é outra língua, não homóglifo

    def test_limpar_entrada_corta_no_limite_e_avisa(self):
        texto, avisos = entrada.limpar_entrada("a\u200b" * 50, 10)
        self.assertEqual(len(texto), 10)
        self.assertTrue(any("invisível" in a for a in avisos) and any("cortado" in a for a in avisos))

    def test_none_vira_texto_vazio(self):
        self.assertEqual(entrada.sanitizar(None), ("", 0))

    def test_defesa_padrao_diz_que_a_entrada_e_dado(self):
        self.assertIn("DADO", entrada.DEFESA_PADRAO)
        self.assertIn("segredos", entrada.DEFESA_PADRAO)


# ------------------------------------------------------------------------------------------------ auditoria
class Orcamento(unittest.TestCase):
    def estado(self, tokens=0, tempo=0.0, chamadas=0, teto=None):
        return {"auditoria": [{"tokens_entrada": tokens, "tokens_saida": 0, "duracao_s": tempo, "chamadas": chamadas}],
                "orcamento": teto or {}}

    def test_sem_teto_nao_limita(self):
        auditoria.verificar_orcamento(self.estado(10**9, 10**6, 10**6))

    def test_cada_eixo_escala_ao_estourar(self):
        for eixo, kw in (("tokens", {"tokens": 1000}), ("tempo_s", {"tempo": 100.0}), ("chamadas", {"chamadas": 5})):
            with self.assertRaises(auditoria.EscaladaHumana) as cm:
                auditoria.verificar_orcamento(self.estado(teto={eixo: 5 if eixo == "chamadas" else 100 if eixo == "tempo_s" else 1000}, **kw))
            self.assertEqual(cm.exception.codigo, "orcamento")

    def test_abaixo_do_teto_passa(self):
        auditoria.verificar_orcamento(self.estado(tokens=10, teto={"tokens": 1000}))

    def test_totais_somam_tokens_tempo_e_chamadas(self):
        estado = {"auditoria": [{"tokens_entrada": 10, "tokens_saida": 5, "duracao_s": 1.5, "chamadas": 1},
                                {"tokens_entrada": 20, "tokens_saida": 5, "duracao_s": 2.0, "chamadas": 2}]}
        t = auditoria.totais(estado)
        self.assertEqual((t["tokens"], t["chamadas"], t["tempo_s"], t["nos"]), (40, 3, 3.5, 2))


class Estagnacao(unittest.TestCase):
    def test_numeros_e_caminhos_nao_mudam_a_assinatura(self):
        a = auditoria.assinatura_do_erro("error CS1002 at C:\\x\\Foo.cs:12 in 3.4s\nProgram.cs(10,5): falhou")
        b = auditoria.assinatura_do_erro("error CS9999 at D:\\y\\Foo.cs:99 in 7.1s\nProgram.cs(77,1): falhou")
        self.assertEqual(a, b)

    def test_erros_diferentes_tem_assinaturas_diferentes(self):
        self.assertNotEqual(auditoria.assinatura_do_erro("tipo X não encontrado"), auditoria.assinatura_do_erro("coluna Y ausente"))

    def test_vazio_nao_tem_assinatura_e_nunca_estagna(self):
        self.assertEqual(auditoria.assinatura_do_erro(None), "")
        self.assertFalse(auditoria.estagnou({"assinaturas_erro": ["a"]}, ""))

    def test_mesma_assinatura_em_sequencia_estagna_e_diferente_nao(self):
        self.assertTrue(auditoria.estagnou({"assinaturas_erro": ["a"]}, "a"))
        self.assertFalse(auditoria.estagnou({"assinaturas_erro": ["b"]}, "a"))
        self.assertFalse(auditoria.estagnou({"assinaturas_erro": []}, "a"))

    def test_reset_da_trilha_pelo_continuar(self):
        from state import RESET, somar_listas
        self.assertEqual(somar_listas(["a", "b"], [RESET]), [])
        self.assertEqual(somar_listas(["a"], ["b"]), ["a", "b"])


class Calibracao(unittest.TestCase):
    def setUp(self):
        auditoria.reiniciar_calibracao()
        self.addCleanup(auditoria.reiniciar_calibracao)

    def test_razao_vem_do_que_o_gateway_reportou(self):
        auditoria.calibrar(3000, 1000)
        self.assertAlmostEqual(auditoria.razao_chars_por_token(), 3.0)

    def test_valor_absurdo_e_limitado_e_nunca_desliga_a_guarda(self):
        auditoria.calibrar(10**9, 1)
        self.assertEqual(auditoria.razao_chars_por_token(), auditoria.RAZAO_MAX)
        auditoria.reiniciar_calibracao()
        auditoria.calibrar(1, 10**9)
        self.assertEqual(auditoria.razao_chars_por_token(), auditoria.RAZAO_MIN)

    def test_zero_ou_negativo_e_ignorado(self):
        auditoria.calibrar(0, 100)
        auditoria.calibrar(100, 0)
        self.assertEqual(auditoria.razao_chars_por_token(), 4.0)


class DecoradorAuditar(unittest.TestCase):
    def test_registra_no_duracao_chamadas_e_tokens_no_retorno(self):
        @auditoria.auditar("meu_no", "meu_papel")
        def no(state):
            auditoria.registrar_chamada({"agente": "x", "modelo": "m", "tokens_entrada": 7, "tokens_saida": 3})
            return {"campo": 1}
        r = no({"task_id": "T"})
        self.assertEqual(r["campo"], 1)
        (reg,) = r["auditoria"]
        self.assertEqual((reg["no"], reg["papel"], reg["chamadas"], reg["tokens_entrada"], reg["tokens_saida"]),
                         ("meu_no", "meu_papel", 1, 7, 3))
        self.assertEqual(reg["modelos"], ["m"])

    def test_orcamento_estourado_para_ANTES_de_gastar(self):
        executou = []

        @auditoria.auditar("n")
        def no(state):
            executou.append(1)
            return {}
        estado = {"task_id": "T", "orcamento": {"tokens": 10},
                  "auditoria": [{"tokens_entrada": 10, "tokens_saida": 0, "duracao_s": 0, "chamadas": 1}]}
        with self.assertRaises(auditoria.EscaladaHumana):
            no(estado)
        self.assertEqual(executou, [])

    def test_falha_do_no_propaga_e_o_evento_ao_vivo_registra(self):
        eventos = []
        auditoria.registrar_sink("T9", eventos.append)
        self.addCleanup(auditoria.registrar_sink, "T9", None)

        @auditoria.auditar("quebra")
        def no(state):
            raise ValueError("boom")
        with self.assertRaises(ValueError):
            no({"task_id": "T9"})
        self.assertTrue(any("iniciou" in e for e in eventos) and any("falhou (ValueError)" in e for e in eventos))

    def test_nos_paralelos_nao_misturam_as_chamadas(self):
        resultados = {}

        def fabricar(nome, tokens):
            @auditoria.auditar(nome)
            def no(state):
                auditoria.registrar_chamada({"agente": nome, "tokens_entrada": tokens, "tokens_saida": 0})
                return {}
            return no
        def rodar(nome, tokens):
            resultados[nome] = fabricar(nome, tokens)({"task_id": "T"})["auditoria"][0]["tokens_entrada"]
        ts = [threading.Thread(target=rodar, args=(f"n{i}", i + 1)) for i in range(8)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(resultados, {f"n{i}": i + 1 for i in range(8)})

    def test_sink_que_levanta_nao_derruba_a_execucao(self):
        auditoria.registrar_sink("T8", lambda t: 1 / 0)
        self.addCleanup(auditoria.registrar_sink, "T8", None)

        @auditoria.auditar("n")
        def no(state):
            return {"ok": True}
        self.assertTrue(no({"task_id": "T8"})["ok"])


# ------------------------------------------------------------------------------------------------ aprovação por hash
class AprovacaoPorHash(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws = Path(self.tmp.name)
        (self.ws / "spec.md").write_bytes(b"linha1\r\nlinha2\r\n")

    def test_mesmo_texto_com_outro_fim_de_linha_tem_o_mesmo_hash(self):
        a = aprovacao.hash_arquivo(self.ws, "spec.md")
        (self.ws / "spec.md").write_bytes(b"linha1\nlinha2\n")
        self.assertEqual(a, aprovacao.hash_arquivo(self.ws, "spec.md"))

    def test_texto_diferente_muda_o_hash_e_a_conferencia_recusa(self):
        aprovado = aprovacao.hash_arquivo(self.ws, "spec.md")
        (self.ws / "spec.md").write_text("reescrita depois do sim", encoding="utf-8")
        with self.assertRaises(aprovacao.AprovacaoInvalida) as cm:
            aprovacao.conferir(aprovacao.hash_arquivo(self.ws, "spec.md"), aprovado, "BUSINESS_SPEC")
        self.assertIn("mudou depois da aprovação", str(cm.exception))

    def test_aprovacao_sem_hash_e_recusada(self):
        with self.assertRaises(aprovacao.AprovacaoInvalida):
            aprovacao.conferir("abc", None, "x")

    def test_arquivo_inexistente_ou_fora_do_workspace_e_erro(self):
        with self.assertRaises(aprovacao.AprovacaoInvalida):
            aprovacao.hash_arquivo(self.ws, "nao-existe.md")
        with self.assertRaises(ValueError):
            aprovacao.hash_arquivo(self.ws, "../fora.md")

    def test_hash_do_pacote_muda_se_qualquer_arquivo_do_pacote_muda_ou_some(self):
        (self.ws / "qa.json").write_text("{}", encoding="utf-8")
        estado = {"business_spec_file": "spec.md", "qa_report_file": "qa.json"}
        h1 = aprovacao.hash_do_pacote(self.ws, estado)
        self.assertEqual(h1, aprovacao.hash_do_pacote(self.ws, estado))
        (self.ws / "qa.json").write_text('{"aprovado": false}', encoding="utf-8")
        h2 = aprovacao.hash_do_pacote(self.ws, estado)
        self.assertNotEqual(h1, h2)
        (self.ws / "qa.json").unlink()
        self.assertNotEqual(h2, aprovacao.hash_do_pacote(self.ws, estado))


# ------------------------------------------------------------------------------------------------ stacks
class AdaptadoresDeStack(unittest.TestCase):
    def test_padrao_e_dotnet_e_o_estado_decide(self):
        self.assertEqual(stacks.resolver({}), "dotnet")
        self.assertEqual(stacks.resolver({"stack_id": "python"}), "python")
        self.assertEqual(stacks.resolver({"target_stack": {"backend": {"language": "csharp"}}}), "dotnet")
        self.assertEqual(stacks.resolver({"target_stack": {"backend": {"language": "FastAPI"}}}), "python")

    def test_stack_desconhecida_falha_alto(self):
        with self.assertRaises(stacks.StackDesconhecida):
            stacks.resolver({"stack_id": "cobol"})

    def test_comando_declarado_vence_o_padrao_do_adaptador(self):
        estado = {"stack_id": "python", "target_stack": {"backend": {"test_command": "uv run pytest -x"}}}
        self.assertEqual(stacks.comando(estado, "test_command"), "uv run pytest -x")
        self.assertEqual(stacks.comando(estado, "build_command"), "uv sync")

    def test_comandos_padrao_so_usam_executaveis_permitidos(self):
        from execucao import EXECUTAVEIS_PERMITIDOS
        for sid, a in stacks.STACKS.items():
            for chave in ("build_command", "test_command", "audit_command"):
                primeiro = a[chave].split()[0]
                self.assertIn(primeiro, EXECUTAVEIS_PERMITIDOS, f"{sid}.{chave}: {primeiro}")

    def test_python_nao_usa_as_familias_dotnet_e_dotnet_usa_todas(self):
        self.assertEqual(set(stacks.familias_excluidas({"stack_id": "python"})), {"arquitetura", "componentes"})
        self.assertEqual(stacks.familias_excluidas({"stack_id": "dotnet"}), ())

    def test_detecta_projeto_gerado(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d)
            self.assertFalse(stacks.projeto_gerado({"stack_id": "python"}, raiz))
            (raiz / "pyproject.toml").write_text("[project]", encoding="utf-8")
            self.assertTrue(stacks.projeto_gerado({"stack_id": "python"}, raiz))
            self.assertFalse(stacks.projeto_gerado({"stack_id": "dotnet"}, raiz))
            (raiz / "A.csproj").write_text("<Project/>", encoding="utf-8")
            self.assertTrue(stacks.projeto_gerado({"stack_id": "dotnet"}, raiz))

    def test_areas_de_escrita_python_incluem_a_higiene_de_entrega(self):
        areas = stacks.areas({"stack_id": "python"}, "backend")
        for esperado in ("app/", "tests/", "Dockerfile", ".gitignore", ".github/workflows/", "pyproject.toml"):
            self.assertIn(esperado, areas)

    def test_cobertura_le_o_coverage_xml_do_pytest_cov(self):
        import cobertura
        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d)
            (raiz / "coverage.xml").write_text(
                '<coverage><packages><package><classes><class filename="app/a.py"><lines>'
                '<line number="1" hits="1"/><line number="2" hits="1"/></lines></class></classes></package></packages></coverage>',
                encoding="utf-8")
            ok, det = cobertura.avaliar(raiz, 90)
            self.assertTrue(ok, det)
            (raiz / ".venv").mkdir()
            (raiz / ".venv" / "coverage.xml").write_text("lixo", encoding="utf-8")  # ambiente virtual é ignorado
            self.assertEqual([p.name for p in cobertura.achar_relatorios(raiz)], ["coverage.xml"])


# ------------------------------------------------------------------------------------------------ configuração dos agentes
class ConfigDosAgentes(unittest.TestCase):
    def test_padrao_completo_e_valido(self):
        cfg = agentes.validar(None)
        self.assertEqual(set(cfg["agentes"]), set(agentes.AGENTES))
        self.assertEqual(cfg["revisao"]["modo"], "simples")
        self.assertIn("tokens", cfg["orcamento"])

    def test_aceita_perfil_temperatura_max_tokens_modo_e_orcamento(self):
        cfg = agentes.validar({"agentes": {"backend": {"perfil": "auto", "temperatura": 0.7, "max_tokens": 4000}},
                               "revisao": {"modo": "dupla"}, "orcamento": {"tokens": 500_000, "tempo_s": None}})
        self.assertEqual(cfg["agentes"]["backend"], {"perfil": "auto", "temperatura": 0.7, "max_tokens": 4000})
        self.assertEqual((cfg["revisao"]["modo"], cfg["orcamento"]["tokens"], cfg["orcamento"]["tempo_s"]), ("dupla", 500_000, None))

    def test_valores_fora_da_faixa_sao_recusados_e_nunca_ajustados(self):
        ruins = [
            {"agentes": {"backend": {"temperatura": 9}}}, {"agentes": {"backend": {"temperatura": True}}},
            {"agentes": {"backend": {"max_tokens": 10}}}, {"agentes": {"backend": {"max_tokens": "muito"}}},
            {"agentes": {"backend": {"perfil": "gpt-5"}}}, {"agentes": {"inexistente": {}}}, {"agentes": {"backend": {"modelo": "x"}}},
            {"revisao": {"modo": "tripla"}}, {"orcamento": {"tokens": 1}}, {"orcamento": {"dinheiro": 5}}, {"extra": 1},
        ]
        for cfg in ruins:
            with self.assertRaises(agentes.ConfigInvalida, msg=str(cfg)):
                agentes.validar(cfg)

    def test_perfil_de_nuvem_e_listado_como_saindo_da_maquina(self):
        cfg = agentes.validar({"agentes": {"chefe": {"perfil": "auto"}, "dba": {"perfil": "local-estrito"}}})
        self.assertEqual(agentes.modelos_que_saem_da_maquina(cfg), ["chefe"])
        self.assertEqual(agentes.modelos_que_saem_da_maquina(agentes.validar(None)), [])

    def test_salvar_e_carregar_ida_e_volta_e_arquivo_corrompido_e_erro_visivel(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"SQUADTI_AGENTES_ARQUIVO": str(Path(d) / "a.json")}):
            self.assertEqual(agentes.carregar(), agentes.validar(None))   # sem arquivo: padrão
            agentes.salvar({"revisao": {"modo": "dupla"}})
            self.assertEqual(agentes.carregar()["revisao"]["modo"], "dupla")
            Path(d, "a.json").write_text("{nao-json", encoding="utf-8")
            with self.assertRaises(agentes.ConfigInvalida):               # nunca cai em silêncio no padrão
                agentes.carregar()

    def test_tarefa_antiga_sem_config_usa_o_padrao(self):
        self.assertEqual(agentes.do_estado({}), agentes.validar(None))


# ------------------------------------------------------------------------------------------------ achados verificados
class AchadosVerificados(unittest.TestCase):
    IDS = frozenset({"ARQ-DOM-05", "SEC-AUT-01"})

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws = Path(self.tmp.name)
        (self.ws / "src").mkdir()
        (self.ws / "src" / "A.cs").write_text("a\nb\nc\nd\n", encoding="utf-8")
        (self.ws / ".gitignore").write_text("x\n", encoding="utf-8")

    def achado(self, regra="ARQ-DOM-05", arquivo="src/A.cs", linha=2, sev="ALTO"):
        return {"severidade": sev, "regra": regra, "arquivo": arquivo, "linha": linha}

    def test_achado_conferivel_e_verificado(self):
        ok, nao = revisao.verificar_achados([self.achado()], self.ws, self.IDS)
        self.assertEqual((len(ok), len(nao)), (1, 0))

    def test_regra_inexistente_arquivo_inexistente_linha_fora_e_caminho_hostil_nao_verificam(self):
        casos = {"regra": self.achado(regra="ZZZ-1-9"), "arquivo": self.achado(arquivo="src/Nao.cs"),
                 "linha": self.achado(linha=99), "travessia": self.achado(arquivo="../../etc/passwd")}
        for nome, a in casos.items():
            ok, nao = revisao.verificar_achados([a], self.ws, self.IDS)
            self.assertEqual((len(ok), len(nao)), (0, 1), nome)
            self.assertIn("motivo", nao[0])

    def test_linha_zero_e_achado_de_arquivo_inteiro_e_vale(self):
        ok, _ = revisao.verificar_achados([self.achado(linha=0)], self.ws, self.IDS)
        self.assertEqual(len(ok), 1)

    def test_arquivo_oculto_nao_perde_o_ponto(self):
        self.assertEqual(revisao._normalizar_arquivo("./.gitignore"), ".gitignore")
        self.assertEqual(revisao._normalizar_arquivo("`src/A.cs`"), "src/A.cs")
        ok, _ = revisao.verificar_achados([self.achado(arquivo="./.gitignore", linha=1)], self.ws, self.IDS)
        self.assertEqual(len(ok), 1)

    def md(self, veredito, *achados):
        return "\n".join([f"VEREDITO: {veredito}", *achados])

    def test_decidir_so_achado_verificado_bloqueia(self):
        # CRITICO com regra que não existe: não bloqueia a aprovação do modelo, mas fica na trilha
        d = revisao.decidir(self.md("APROVADO", "- [CRITICO] ZZZ-9-9 src/A.cs:1 inventado"), self.ws, self.IDS)
        self.assertTrue(d["aprovado"])
        self.assertEqual(len(d["nao_verificados"]), 1)
        # CRITICO verificado reprova mesmo com APROVADO do modelo
        d = revisao.decidir(self.md("APROVADO", "- [CRITICO] SEC-AUT-01 src/A.cs:1 sem autorização"), self.ws, self.IDS)
        self.assertFalse(d["aprovado"])
        self.assertIn("CRITICO verificado", d["motivo"])

    def test_decidir_reprovado_sem_achado_verificavel_explica(self):
        d = revisao.decidir(self.md("REPROVADO", "- [ALTO] ZZZ-9-9 src/A.cs:1 x"), self.ws, self.IDS)
        self.assertFalse(d["aprovado"])
        self.assertIn("sem achado verificável", d["motivo"])

    def test_decidir_veredito_ausente_ou_repetido_continua_reprovando(self):
        for texto in (None, "", "sem veredito", "VEREDITO: APROVADO\nVEREDITO: APROVADO"):
            self.assertFalse(revisao.decidir(texto, self.ws, self.IDS)["aprovado"], texto)

    def test_mesclar_achados_soma_revisores_e_fica_com_a_maior_severidade(self):
        a = [self.achado(sev="MEDIO")]
        b = [self.achado(sev="CRITICO"), self.achado(arquivo="src/A.cs", linha=3)]
        juntos = {(x["linha"]): x for x in revisao.mesclar_achados([a, b])}
        self.assertEqual((juntos[2]["revisores"], juntos[2]["severidade"]), (2, "CRITICO"))
        self.assertEqual(juntos[3]["revisores"], 1)

    def test_so_critico_ou_alto_de_um_revisor_so_vai_ao_verificador(self):
        self.assertTrue(revisao.precisa_verificador({"severidade": "CRITICO", "revisores": 1}, 2))
        self.assertFalse(revisao.precisa_verificador({"severidade": "CRITICO", "revisores": 2}, 2))
        self.assertFalse(revisao.precisa_verificador({"severidade": "MEDIO", "revisores": 1}, 2))
        self.assertFalse(revisao.precisa_verificador({"severidade": "CRITICO", "revisores": 1}, 1))

    def test_verificador_na_duvida_refuta(self):
        self.assertTrue(revisao.ler_verificador("VERIFICADOR: CONFIRMADO\nporque sim"))
        for texto in (None, "", "talvez", "VERIFICADOR: REFUTADO", "VERIFICADOR: CONFIRMADO\nVERIFICADOR: CONFIRMADO",
                      "verificador: confirmado", "VERIFICADOR:CONFIRMADO"):
            self.assertFalse(revisao.ler_verificador(texto), texto)

    def test_trecho_numera_as_linhas_e_oculta_segredo(self):
        (self.ws / "src" / "S.cs").write_text('x\npassword = "SenhaSecreta12345"\ny\n', encoding="utf-8")
        t = revisao.trecho(self.ws, "src/S.cs", 2, contexto=1)
        self.assertIn("1|", t)
        self.assertIn("3|", t)
        self.assertNotIn("SenhaSecreta12345", t)
        self.assertIn("possível segredo", t)  # a linha inteira sai: o marcador não traz o valor


# ------------------------------------------------------------------------------------------------ proveniência
class Proveniencia(unittest.TestCase):
    def test_manifesto_tem_doutrina_modelos_tokens_aprovacoes_e_hash_dos_arquivos_sem_prompt(self):
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d)
            (ws / "a.txt").write_text("conteudo", encoding="utf-8")
            estado = {"task_id": "T", "project_name": "P", "doutrina_versao": "1", "doutrina_hash": "h", "stack_id": "python",
                      "modelo": "tudoia-auto", "consentimento_nuvem": True, "business_spec_hash": "bs", "release_gate_hash": "rg",
                      "arquivos_gerados": ["a.txt", "../fora.txt", "nao-existe.txt"],
                      "auditoria": [{"no": "arq", "duracao_s": 2, "chamadas": 1, "tokens_entrada": 10, "tokens_saida": 5,
                                     "detalhe": [{"agente": "arquiteto", "modelo": "tudoia-auto", "tentativa": 1,
                                                  "tokens_entrada": 10, "tokens_saida": 5, "duracao_s": 2, "prompt_sha": "abc",
                                                  "resposta_chars": 99}]}]}
            m = proveniencia.gerar(estado, ws)
            self.assertEqual(m["doutrina"]["hash"], "h")
            self.assertEqual(m["modelos_por_agente"], {"arquiteto": ["tudoia-auto"]})
            self.assertEqual(m["totais"]["tokens"], 15)
            self.assertEqual(m["aprovacoes"], {"business_spec_hash": "bs", "release_gate_hash": "rg"})
            self.assertEqual([a["caminho"] for a in m["arquivos"]], ["a.txt"])  # fora do workspace e inexistente não entram
            self.assertEqual(len(m["arquivos"][0]["sha256"]), 64)
            texto = json.dumps(m)
            self.assertNotIn("resposta_chars", texto)  # só o hash do prompt: nunca prompt nem resposta


if __name__ == "__main__":
    unittest.main()

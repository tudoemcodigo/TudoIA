"""Sandbox, carga e validação em execução (hacker, macaco, carga) com um Docker FALSO que registra cada comando.

O que se prova aqui: o isolamento (rede interna, sem porta publicada, sem capabilities, limites), a desmontagem sempre, o veredito, o retorno
ao desenvolvimento com relatório e as falhas fechadas. A execução real contra containers é verificada à parte (ver docs)."""
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_entrega import Base  # noqa: E402
from test_nos import _LlmFalso  # noqa: E402

import auditoria  # noqa: E402
import carga  # noqa: E402
import sandbox as sb  # noqa: E402

OPENAPI = "openapi: 3.1.0\ninfo: {title: t, version: '1'}\npaths:\n  /tarefas:\n    get: {responses: {'200': {description: ok}}}\n"
RELATORIO_VAZIO = {"achados": [], "requisicoes": 10, "incompleto": False}
ACHADO_ALTO = {"id": "AUTH-01", "severidade": "ALTO", "categoria": "autenticação", "endpoint": "/tarefas", "metodo": "GET",
               "evidencia": "respondeu 200 sem credencial", "reproducao": "curl -i -X GET '<ALVO>/tarefas'"}
ACHADO_CRITICO = {"id": "MAC-03", "severidade": "CRITICO", "categoria": "disponibilidade", "endpoint": "/tarefas", "metodo": "POST",
                  "evidencia": "o servidor caiu", "reproducao": "curl -i -X POST '<ALVO>/tarefas' -d '{nao-json'"}
RESUMO_K6_OK = {"metrics": {"http_req_duration": {"p(95)": 120.0, "p(99)": 300.0}, "http_req_failed": {"value": 0.0},
                            "http_reqs": {"count": 5000, "rate": 120.0}, "checks": {"value": 1.0}}}
RESUMO_K6_LENTO = {"metrics": {"http_req_duration": {"p(95)": 4000.0, "p(99)": 9000.0}, "http_req_failed": {"value": 0.0},
                               "http_reqs": {"count": 900, "rate": 20.0}, "checks": {"value": 1.0}}}


class DockerFalso:
    """Imita o docker: guarda os argv, responde por subcomando e devolve os relatórios combinados nos `cp` de saída."""

    def __init__(self):
        self.comandos = []
        self.disponivel = True
        self.falhar = set()          # subcomandos que devolvem erro
        self.kit = {"ataque": RELATORIO_VAZIO, "macaco": RELATORIO_VAZIO, "ui": RELATORIO_VAZIO}
        self.k6 = [RESUMO_K6_OK]
        self.respondendo = True
        self.criados = {}            # nome do container -> (imagem, comando)
        self.k6_chamadas = 0
        self.estatisticas = "30%|200MiB / 1GiB|20%"

    def __call__(self, argv, timeout):
        self.comandos.append(list(argv))
        sub = argv[1]
        chave = " ".join(argv[1:3])
        if sub in self.falhar or chave in self.falhar:
            return 1, f"{sub} falhou (falso)"
        if sub == "info":
            return (0, "27.0") if self.disponivel else (1, "Cannot connect")
        if sub == "create":
            nome = argv[argv.index("--name") + 1]
            resto = argv[argv.index("--name") + 2:]
            # imagem = primeiro argumento que parece imagem (tem ':' ou '@sha256' ou '/') depois das flags conhecidas
            i = 0
            while i < len(resto) and resto[i].startswith("-"):
                i += 2
            self.criados[nome] = (resto[i], resto[i + 1:])
            return 0, nome
        if sub == "cp":
            origem, destino = argv[2], argv[3]
            if ":" in origem and not origem.startswith(("C:", "D:", "/")) or origem.split(":")[0] in self.criados:
                nome, caminho = origem.split(":", 1)
                imagem, cmd = self.criados.get(nome, ("", []))
                conteudo = self._saida_do_container(imagem, cmd, caminho)
                if conteudo is None:
                    return 1, "sem arquivo"
                Path(destino).write_text(json.dumps(conteudo), encoding="utf-8")
            return 0, ""
        if sub == "start":
            nome = argv[-1]
            imagem, cmd = self.criados.get(nome, ("", []))
            if "python" in imagem and "-c" in cmd and "urlopen" in " ".join(cmd):
                return 0, "200\n" if self.respondendo else "0\n"
            if "k6" in imagem:
                self.k6_chamadas += 1
            return 0, "ok"
        if sub == "stats":
            return 0, self.estatisticas
        if sub == "inspect":
            return 0, "false"
        return 0, "ok"

    def _saida_do_container(self, imagem, cmd, caminho):
        if "k6" in imagem:
            return self.k6[min(self.k6_chamadas - 1, len(self.k6) - 1)]
        if "kit_api.py" in " ".join(cmd):
            return self.kit["ataque" if "ataque" in cmd else "macaco"]
        if "kit_ui.py" in " ".join(cmd):
            return self.kit["ui"]
        return None

    def argv(self, *trechos):
        return [c for c in self.comandos if all(t in " ".join(c) for t in trechos)]


def fabrica(falso):
    return lambda: sb.Docker(executor=falso)


# --------------------------------------------------------------------------------------------------- validador de argumentos
class ValidadorDeArgumentos(unittest.TestCase):
    def test_recusa_as_flags_que_quebram_o_isolamento(self):
        ruins = [["docker", "run", "--privileged", "x"], ["docker", "run", "-v", "/:/host", "x"], ["docker", "run", "--volume=/a:/b", "x"],
                 ["docker", "run", "--network", "host", "x"], ["docker", "run", "--network=host", "x"], ["docker", "run", "--cap-add", "SYS_ADMIN", "x"],
                 ["docker", "run", "--pid", "host", "x"], ["docker", "run", "--device", "/dev/sda", "x"], ["docker", "run", "--mount", "type=bind", "x"],
                 ["docker", "run", "--network", "container", "x"], ["docker", "run", "--add-host=a:1.1.1.1", "x"]]
        for argv in ruins:
            with self.assertRaises(sb.ArgumentoProibido, msg=str(argv)):
                sb.validar_argv(argv)

    def test_recusa_subcomando_fora_da_lista(self):
        for sub in ("system", "volume", "swarm", "login", "push", "commit"):
            with self.assertRaises(sb.ArgumentoProibido):
                sb.validar_argv(["docker", sub])
        with self.assertRaises(sb.ArgumentoProibido):
            sb.validar_argv(["docker"])

    def test_aceita_o_uso_normal(self):
        sb.validar_argv(["docker", "run", "-d", "--network", "squadti-net-t1", "--memory", "1g", "--cap-drop", "ALL", "img"])

    def test_docker_executar_valida_antes_de_executar(self):
        chamadas = []
        d = sb.Docker(executor=lambda argv, t: chamadas.append(argv) or (0, ""))
        with self.assertRaises(sb.ArgumentoProibido):
            d.executar("run", "--privileged", "x")
        self.assertEqual(chamadas, [])

    def test_nome_seguro_so_gera_nome_valido(self):
        self.assertEqual(sb.nome_seguro("sut", "TASK-001"), "sut-task-001")
        self.assertTrue(sb.RE_NOME.match(sb.nome_seguro("sut", "A B/C..;rm -rf")))
        self.assertLessEqual(len(sb.nome_seguro("sut", "x" * 200)), 60)


# --------------------------------------------------------------------------------------------------- ciclo do sandbox
class CicloDoSandbox(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws = Path(self.tmp.name)
        (self.ws / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
        self.falso = DockerFalso()
        self.box = sb.Sandbox("T1", self.ws, docker=sb.Docker(executor=self.falso))

    def test_sem_dockerfile_falha_fechado_com_mensagem_clara(self):
        (self.ws / "Dockerfile").unlink()
        with self.assertRaises(sb.SandboxFalhou) as cm:
            self.box.construir()
        self.assertEqual(cm.exception.etapa, "build")
        self.assertEqual(self.falso.argv("build"), [])

    def test_build_que_falha_vira_sandbox_falhou_com_o_final_do_log(self):
        self.falso.falhar.add("build")
        with self.assertRaises(sb.SandboxFalhou) as cm:
            self.box.construir()
        self.assertIn("docker build falhou", cm.exception.detalhe)

    def test_rede_interna_sem_porta_publicada_e_container_sem_privilegio(self):
        self.box.construir()
        self.box.subir(porta=8080, saude="/saude", tentativas=2, esperar_s=0)
        (rede,) = self.falso.argv("network create")
        self.assertIn("--internal", rede)                                   # sem rota para a internet
        run_sut = self.falso.argv("run -d --name sut-t1")[0]
        texto = " ".join(run_sut)
        self.assertIn("--cap-drop ALL", texto)
        self.assertIn("no-new-privileges:true", texto)
        self.assertIn("--memory 1g", texto)
        self.assertIn("--pids-limit 512", texto)
        self.assertNotIn("--publish", run_sut)
        self.assertNotIn("-p", run_sut)                                      # nenhuma porta vai ao host
        self.assertIn("--network-alias sut", texto)
        for comando in self.falso.comandos:                                  # nada perigoso em NENHUM comando do ciclo
            sb.validar_argv(comando)
        self.assertEqual(self.box.alvo, "http://sut:8080")

    def test_sobe_o_banco_postgres_com_imagem_fixada_e_injeta_database_url(self):
        self.box.construir()
        self.box.subir(motor_banco="postgres", tentativas=2, esperar_s=0)
        db = " ".join(self.falso.argv("run -d --name sut-db-t1")[0])
        self.assertIn("postgres:17-alpine@sha256:", db)
        self.assertIn("--network-alias banco", db)
        sut = " ".join(self.falso.argv("run -d --name sut-t1")[0])
        self.assertIn("DATABASE_URL=postgresql://postgres:", sut)
        self.assertIn("@banco:5432/app", sut)

    def test_sistema_que_nao_responde_levanta_com_os_logs(self):
        self.falso.respondendo = False
        self.box.construir()
        with self.assertRaises(sb.SandboxFalhou) as cm:
            self.box.subir(tentativas=2, esperar_s=0)
        self.assertEqual(cm.exception.etapa, "sut")
        self.assertTrue(self.falso.argv("logs"))

    def test_limpar_remove_containers_rede_e_imagem_e_e_idempotente(self):
        self.box.construir()
        self.box.subir(motor_banco="postgres", tentativas=2, esperar_s=0)
        self.box.limpar()
        self.assertTrue(self.falso.argv("rm -f sut-t1") and self.falso.argv("rm -f sut-db-t1"))
        self.assertTrue(self.falso.argv("network rm squadti-net-t1"))
        self.assertTrue(self.falso.argv("image rm -f squadti-sut-t1"))
        antes = len(self.falso.comandos)
        self.box.limpar()
        self.assertEqual(len(self.falso.comandos), antes)

    def test_context_manager_desmonta_mesmo_com_excecao(self):
        with self.assertRaises(ValueError):
            with sb.Sandbox("T2", self.ws, docker=sb.Docker(executor=self.falso)) as box:
                box.construir()
                box.subir(tentativas=2, esperar_s=0)
                raise ValueError("boom")
        self.assertTrue(self.falso.argv("network rm squadti-net-t2"))

    def test_ferramenta_roda_na_rede_do_sandbox_copia_entrada_coleta_saida_e_remove(self):
        self.box.construir()
        self.box.subir(tentativas=2, esperar_s=0)
        self.falso.kit["macaco"] = {"achados": [ACHADO_ALTO]}
        codigo, _, arquivos = self.box.rodar_ferramenta(
            sb.IMAGEM_PYTHON, ["python", "/tmp/kit_api.py", "macaco", "http://sut:8080", "/tmp/o.json", "/tmp/saida.json"],
            arquivos={"/tmp/kit_api.py": b"print(1)"}, coletar=["/tmp/saida.json"])
        self.assertEqual(codigo, 0)
        self.assertEqual(json.loads(arquivos["/tmp/saida.json"])["achados"][0]["id"], "AUTH-01")
        criacao = [c for c in self.falso.argv("create") if "kit_api.py" in " ".join(c)][0]
        self.assertIn(self.box.rede, criacao)                                # só alcança a rede do sandbox
        self.assertIn("--cap-drop", criacao)
        nome = criacao[criacao.index("--name") + 1]
        self.assertTrue(self.falso.argv(f"rm -f {nome}"))                    # container da ferramenta removido sempre

    def test_estatisticas_do_alvo(self):
        self.box.construir()
        self.box.subir(tentativas=2, esperar_s=0)
        self.assertEqual(self.box.estatisticas(), {"cpu": "30%", "memoria": "200MiB / 1GiB", "memoria_perc": "20%"})

    def test_docker_disponivel_olha_o_daemon(self):
        self.assertTrue(sb.docker_disponivel(sb.Docker(executor=self.falso)))
        self.falso.disponivel = False
        self.assertFalse(sb.docker_disponivel(sb.Docker(executor=self.falso)))


# --------------------------------------------------------------------------------------------------- carga
class Carga(unittest.TestCase):
    def test_script_k6_tem_rampa_ate_os_vus_e_so_os_caminhos_dados(self):
        s = carga.gerar_script_k6("http://sut:8080", ["/", "/tarefas"], 100)
        self.assertIn("target: 100", s)
        self.assertIn('["/", "/tarefas"]', s)
        self.assertIn("sleep(", s)       # usuário "pensa" entre requisições

    def test_alvos_seguros_so_get_sem_parametro_obrigatorio(self):
        spec = {"paths": {"/a": {"get": {}}, "/b/{id}": {"get": {}}, "/c": {"post": {}},
                          "/d": {"get": {"parameters": [{"name": "q", "in": "query", "required": True}]}},
                          "/e": {"get": {"parameters": [{"name": "q", "in": "query"}]}}}}
        self.assertEqual(carga.alvos_seguros(spec), ["/", "/a", "/e"])

    def test_interpretar_aprova_e_reprova_por_cada_eixo_do_slo(self):
        self.assertTrue(carga.interpretar(RESUMO_K6_OK, 50)["passou"])
        lento = carga.interpretar(RESUMO_K6_LENTO, 50)
        self.assertFalse(lento["passou"])
        self.assertTrue(any("p95" in m for m in lento["motivos"]) and any("p99" in m for m in lento["motivos"]))
        erro = carga.interpretar({"metrics": {**RESUMO_K6_OK["metrics"], "checks": {"value": 0.8}}}, 50)
        self.assertTrue(any("erro" in m for m in erro["motivos"]))

    def test_metrica_ausente_ou_resumo_vazio_reprova_falha_fechado(self):
        for resumo in ({}, {"metrics": {}}, {"metrics": {"http_req_duration": {"p(95)": 1}}}):
            d = carga.interpretar(resumo, 50)
            self.assertFalse(d["passou"])
            self.assertIn("não devolveu as métricas", d["motivos"][0])

    def test_aceita_os_dois_formatos_de_resumo_do_k6(self):
        aninhado = {"metrics": {"http_req_duration": {"values": {"p(95)": 100.0, "p(99)": 200.0}}, "http_req_failed": {"values": {"rate": 0.0}},
                                "checks": {"values": {"rate": 1.0}}, "http_reqs": {"values": {"count": 10, "rate": 5.0}}}}
        self.assertTrue(carga.interpretar(aninhado, 10)["passou"])

    def test_slo_configurado_vale(self):
        d = carga.interpretar(RESUMO_K6_OK, 10, {"p95_ms": 50})
        self.assertFalse(d["passou"])

    def test_diagnostico_aponta_o_recurso_saturado(self):
        self.assertIn("OOM", carga.diagnosticar({}, None, True))
        self.assertIn("CPU", carga.diagnosticar({"erro": 0}, {"cpu": "97%", "memoria_perc": "10%"}, False))
        self.assertIn("memória", carga.diagnosticar({"erro": 0}, {"cpu": "10%", "memoria_perc": "95%"}, False))
        self.assertIn("pool", carga.diagnosticar({"erro": 0.2}, {"cpu": "10%", "memoria_perc": "10%"}, False))
        self.assertIn("banco", carga.diagnosticar({"erro": 0}, {"cpu": "10%", "memoria_perc": "10%"}, False))

    def caixa(self, falso):
        import tempfile
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        (Path(tmp.name) / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
        box = sb.Sandbox("T1", Path(tmp.name), docker=sb.Docker(executor=falso))
        box.construir()
        box.subir(tentativas=2, esperar_s=0)
        return box

    def test_degraus_sobem_ate_saturar_e_a_subida_para(self):
        falso = DockerFalso()
        falso.k6 = [RESUMO_K6_OK, RESUMO_K6_OK, RESUMO_K6_LENTO]
        box = self.caixa(falso)
        with mock.patch.object(carga, "RAMPA_S", 0), mock.patch.object(carga.time, "sleep", lambda s: None):
            r = carga.executar(box, {"paths": {"/a": {"get": {}}}}, passos=[25, 50, 100, 200], minimo_vus=50)
        self.assertEqual([d["vus"] for d in r["degraus"]], [25, 50, 100])   # parou no 1º que violou o SLO
        self.assertEqual((r["estavel_ate_vus"], r["saturou_em_vus"], r["aprovado"]), (50, 100, True))
        self.assertTrue(r["gargalo"])
        self.assertIn("capacidade relativa", r["nota"])

    def test_nao_sustentar_o_minimo_reprova(self):
        falso = DockerFalso()
        falso.k6 = [RESUMO_K6_OK, RESUMO_K6_LENTO]
        box = self.caixa(falso)
        with mock.patch.object(carga, "RAMPA_S", 0), mock.patch.object(carga.time, "sleep", lambda s: None):
            r = carga.executar(box, {"paths": {}}, passos=[25, 50], minimo_vus=100)
        self.assertFalse(r["aprovado"])

    def test_k6_com_saida_de_erro_reprova_o_degrau(self):
        falso = DockerFalso()
        box = self.caixa(falso)
        falso.falhar.add("start")      # a ferramenta não rodou
        with mock.patch.object(carga, "RAMPA_S", 0), mock.patch.object(carga.time, "sleep", lambda s: None):
            r = carga.executar(box, {"paths": {}}, passos=[25], minimo_vus=25)
        self.assertFalse(r["degraus"][0]["passou"])
        self.assertTrue(any("k6 saiu com código" in m for m in r["degraus"][0]["motivos"]))

    def test_perfil_desconhecido_e_erro_e_o_completo_vai_a_10_mil(self):
        self.assertEqual(carga.PERFIS_CARGA["completo"][-1], 10000)
        with self.assertRaises(ValueError):
            carga.executar(mock.Mock(), {}, perfil="infinito")


# --------------------------------------------------------------------------------------------------- nó de validação em execução
class ValidacaoEmExecucao(Base):
    def setUp(self):
        super().setUp()
        sys.modules["nodes"] = self.n
        for m in ("validacao",):
            sys.modules.pop(m, None)
        import validacao
        self.v = validacao
        self.addCleanup(sys.modules.pop, "validacao", None)
        self.falso = DockerFalso()
        patcher = mock.patch.object(validacao, "FABRICA_DOCKER", fabrica(self.falso))
        patcher.start()
        self.addCleanup(patcher.stop)
        sleep = mock.patch.object(sb.time, "sleep", lambda s: None)
        sleep.start()
        self.addCleanup(sleep.stop)
        (self.ws / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
        (self.ws / "contracts").mkdir()
        (self.ws / "contracts" / "openapi.yaml").write_text(OPENAPI, encoding="utf-8")
        (self.ws / "docs" / "negocio").mkdir(parents=True)
        (self.ws / "docs" / "negocio" / "BUSINESS_SPEC.md").write_text("spec", encoding="utf-8")
        self.state.update({"openapi_file": "contracts/openapi.yaml", "business_spec_file": "docs/negocio/BUSINESS_SPEC.md",
                           "plano": {"tamanho": "padrao", "precisa_banco": False, "precisa_frontend": False, "precisa_api": True},
                           "agentes_cfg": {"validacao": {"modo": "auto", "carga": "escalado"}}, "stack_id": "python"})
        _LlmFalso.resposta = "### ARQUIVO: docs/seguranca/MODELO_DE_AMEACAS.md\n```md\n# Modelo de ameaças\nativos e fronteiras de confiança\n```\n"
        self.falso.k6 = [RESUMO_K6_OK]

    def rodar(self, **estado):
        with mock.patch.object(carga, "RAMPA_S", 0), mock.patch.object(carga.time, "sleep", lambda s: None), \
                mock.patch.object(carga, "PERFIS_CARGA", {"escalado": [25, 50, 100], "completo": [100]}):
            return self.v.node_validacao_runtime({**self.state, **estado})

    def test_tudo_limpo_aprova_grava_os_tres_relatorios_e_o_modelo_de_ameacas(self):
        r = self.rodar()
        self.assertTrue(r["hacker_passed"] and r["macaco_passed"] and r["carga_passed"])
        self.assertEqual(r["current_phase"], "VALIDACAO_RUNTIME_APROVADA")
        for rel in ("tests/reports/hacker_report.json", "tests/reports/macaco_report.json", "tests/reports/carga_report.json"):
            self.assertTrue((self.ws / rel).is_file(), rel)
        self.assertTrue((self.ws / "docs/seguranca/MODELO_DE_AMEACAS.md").is_file())
        self.assertEqual(r["rodadas_runtime"], 0)
        self.assertEqual({x["no"] for x in r["auditoria"] if x["no"] != "validacao_runtime"}, {"qa_macaco", "hacker", "carga_devops"})

    def test_sandbox_e_sempre_desmontado(self):
        self.rodar()
        self.assertTrue(self.falso.argv("network rm"))
        self.assertTrue(self.falso.argv("image rm -f"))
        for c in self.falso.comandos:
            sb.validar_argv(c)

    def test_hacker_que_invade_bloqueia_e_devolve_o_relatorio_ao_desenvolvimento(self):
        self.falso.kit["ataque"] = {"achados": [ACHADO_ALTO, {**ACHADO_ALTO, "id": "HDR-02", "severidade": "BAIXO"}]}
        r = self.rodar()
        self.assertFalse(r["hacker_passed"])
        self.assertEqual((r["falha_origem"], r["rodadas_runtime"]), ("backend", 1))
        self.assertIn("HACKER", r["last_error_log"])
        self.assertIn("AUTH-01", r["last_error_log"])
        self.assertIn("curl", r["last_error_log"])
        self.assertNotIn("HDR-02", r["last_error_log"])            # BAIXO não bloqueia nem entra no retorno
        self.assertEqual([a["id"] for a in r["achados_agentes"]], ["AUTH-01", "HDR-02"])   # mas vai ao livro de lições
        self.assertEqual(r["achados_agentes"][0]["agente"], "hacker")

    def test_macaco_que_derruba_o_servidor_bloqueia(self):
        self.falso.kit["macaco"] = {"achados": [ACHADO_CRITICO]}
        r = self.rodar()
        self.assertFalse(r["macaco_passed"])
        self.assertTrue(r["hacker_passed"])
        self.assertIn("MACACO", r["last_error_log"])
        self.assertEqual(r["current_phase"], "VALIDACAO_RUNTIME_REPROVADA")

    def test_carga_que_nao_sustenta_o_minimo_bloqueia_com_o_gargalo(self):
        self.falso.k6 = [RESUMO_K6_LENTO]
        r = self.rodar()
        self.assertFalse(r["carga_passed"])
        self.assertIn("CARGA", r["last_error_log"])
        self.assertIn("Gargalo provável", r["last_error_log"])

    def test_sistema_trivial_nao_faz_carga(self):
        r = self.rodar(plano={**self.state["plano"], "tamanho": "trivial"})
        self.assertIsNone(r["carga_passed"])
        self.assertEqual(self.falso.k6_chamadas, 0)

    def test_carga_desligada_na_configuracao(self):
        r = self.rodar(agentes_cfg={"validacao": {"carga": "nunca"}})
        self.assertIsNone(r["carga_passed"])

    def test_docker_ausente_em_modo_auto_pula_e_registra_o_motivo(self):
        self.falso.disponivel = False
        r = self.rodar()
        self.assertFalse(r["validacao_executada"])
        self.assertIn("NÃO foi validado", r["validacao_motivo"])
        self.assertIsNone(r["hacker_passed"])
        self.assertEqual(self.falso.argv("build"), [])

    def test_docker_ausente_em_modo_sempre_escala(self):
        self.falso.disponivel = False
        with self.assertRaises(auditoria.EscaladaHumana) as cm:
            self.rodar(agentes_cfg={"validacao": {"modo": "sempre"}})
        self.assertEqual(cm.exception.codigo, "docker")

    def test_modo_nunca_pula_sem_tocar_no_docker(self):
        r = self.rodar(agentes_cfg={"validacao": {"modo": "nunca"}})
        self.assertFalse(r["validacao_executada"])
        self.assertEqual(self.falso.comandos, [])

    def test_sistema_que_nao_constroi_volta_ao_desenvolvimento_com_o_log_e_o_sandbox_e_limpo(self):
        self.falso.falhar.add("build")
        r = self.rodar()
        self.assertFalse(r["hacker_passed"])
        self.assertIn("build", r["last_error_log"])
        self.assertEqual((r["falha_origem"], r["rodadas_runtime"]), ("backend", 1))

    def test_mesmo_erro_de_sandbox_duas_vezes_escala_por_estagnacao(self):
        self.falso.falhar.add("build")
        primeiro = self.rodar()
        segundo = self.rodar(assinaturas_erro=primeiro["assinaturas_erro"], rodadas_runtime=1)
        self.assertIn("estagnacao", segundo["escalada"])

    def test_terceira_reprovacao_escala_ao_humano(self):
        self.falso.kit["ataque"] = {"achados": [ACHADO_ALTO]}
        r = self.rodar(rodadas_runtime=2)
        self.assertIn("reprovou 3 vezes", r["escalada"])

    def test_mesmos_achados_voltando_escalam_por_estagnacao(self):
        self.falso.kit["ataque"] = {"achados": [ACHADO_ALTO]}
        primeiro = self.rodar()
        segundo = self.rodar(assinaturas_erro=primeiro["assinaturas_erro"], rodadas_runtime=1)
        self.assertIn("estagnacao", segundo["escalada"])

    def test_falha_do_modelo_de_ameacas_nao_bloqueia(self):
        _LlmFalso.resposta = "x"        # resposta minúscula duas vezes: o modelo não entrega, a validação segue
        r = self.rodar()
        self.assertTrue(r["hacker_passed"])
        self.assertIsNone(json.loads((self.ws / "tests/reports/hacker_report.json").read_text(encoding="utf-8"))["modelo_de_ameacas"])

    def test_sem_contrato_openapi_so_ha_o_modelo_de_ameacas(self):
        r = self.rodar(openapi_file=None, plano={**self.state["plano"], "precisa_api": False})
        self.assertTrue(r["hacker_passed"] and r["macaco_passed"])
        self.assertEqual(self.falso.argv("kit_api.py"), [])

    def test_macaco_de_interface_so_com_frontend_servindo_html(self):
        self.falso.kit["ui"] = {"achados": [{**ACHADO_ALTO, "id": "UI-01", "categoria": "interface"}]}
        # o sistema responde 200 mas NÃO é HTML: o macaco de UI não roda
        r = self.rodar(plano={**self.state["plano"], "precisa_frontend": True})
        self.assertTrue(r["macaco_passed"])
        self.assertEqual(self.falso.argv("kit_ui.py"), [])

    def test_resumo_para_dev_redige_segredo(self):
        achado = {**ACHADO_ALTO, "evidencia": 'vazou password = "SenhaMuitoSecreta999"'}
        texto = self.v.resumo_para_dev([achado], "O HACKER invadiu")
        self.assertNotIn("SenhaMuitoSecreta999", texto)

    def test_so_achado_grave_entra_no_resumo_de_retorno(self):
        texto = self.v.resumo_para_dev([ACHADO_ALTO, {**ACHADO_ALTO, "id": "RATE-01", "severidade": "BAIXO"}], "x")
        self.assertIn("AUTH-01", texto)
        self.assertNotIn("RATE-01", texto)


if __name__ == "__main__":
    unittest.main()

"""
Evals da SquadTI: verificadores contra workspaces falsos (passa e falha para cada um, com entrada hostil), driver contra uma API
simulada em processo (transições, escalada, timeout, 5xx), pass@k/pass^k, comparação entre rodadas e ausência de vazamento
do token e de valores de segredo nos relatórios.
"""
import copy
import json
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import pytest

from evals import driver, relatorio, run, verificadores

TOKEN = "tok-" + "Zq7" * 14                        # sintético, 46 caracteres
SEGREDO = "AKIA" + "ABCDEFGHIJKLMNOP"               # valor sintético com formato de chave AWS (16 após AKIA)
DOUTRINA = {"versao": "9.9.9", "hash": "d0c7" * 16}


# ------------------------------------------------------------------ workspace e API falsos
def _json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def arquivos_validos() -> dict:
    """Workspace que passa em todos os verificadores gerais (caminho relativo -> texto)."""
    qa = {"aprovado": True, "etapas": [
        {"etapa": "backend-build", "codigo": 0}, {"etapa": "backend-testes", "codigo": 0},
        {"etapa": "cobertura", "codigo": 0, "detalhe": {"minimo": 90, "linha": 96.5, "ramo": 92.0, "motivo": ""}}]}
    limpo = {"aprovado": True, "achados": [{"id": "X1", "severidade": "BAIXO"}, {"id": "X2", "severidade": "MEDIO"}]}
    return {
        "tests/reports/qa_report.json": _json(qa),
        "tests/reports/security_report.json": _json({"aprovado": True, "etapas": []}),
        "tests/reports/devops_report.json": _json({"aprovado": True, "etapas": []}),
        "tests/reports/hacker_report.json": _json(limpo),
        "tests/reports/macaco_report.json": _json({"aprovado": True, "resumo": {"CRITICO": 0, "ALTO": 0, "MEDIO": 1}}),
        "tests/reports/carga_report.json": _json({"aprovado": True, "p95_ms": 120}),
        "README.md": "# Projeto\nComo rodar.\n",
        "docs/arquitetura/PRD_TECNICO.md": "# PRD\n",
        "contracts/openapi.yaml": "openapi: 3.1.0\npaths:\n  /pedidos:\n    post:\n      parameters:\n        - name: Idempotency-Key\n"
                                  "      responses:\n        '201': {}\n        '409': {}\n",
        "Dockerfile": "FROM python:3.12-slim\n",
        ".gitignore": ".venv/\n.env\n",
        "docs/proveniencia.json": _json({"doutrina": DOUTRINA}),
        "tests/test_api.py": "def test_ok():\n    assert 409 and 'idempotency'\n",
        "app/main.py": "print('ola')\n",
    }


def api_valida() -> dict:
    return {"detalhe": {"situacao": {"estado": "concluida"}, "doutrina": dict(DOUTRINA),
                        "verificacoes": {"tests_passed": True, "review_passed": True, "security_passed": True, "devops_passed": True}},
            "auditoria": {"totais": {"tokens": 1000, "tempo_s": 50.0}, "nos": []},
            "mensagens": {"mensagens": [{"de": "usuario", "para": "chefe", "texto": "briefing"},
                                        {"de": "chefe", "para": "usuario", "texto": "plano pronto"}]},
            "duracao_s": 120}


def caso_base() -> dict:
    return {"id": "x", "limites": {"tokens": 2000, "tempo_s": 300}, "cobertura_minima": 90}


def escrever(raiz: Path, arquivos: dict) -> Path:
    for rel, texto in arquivos.items():
        alvo = raiz / rel
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_text(texto, encoding="utf-8")
    return raiz


def por_nome(resultados: list) -> dict:
    return {r["nome"]: r for r in resultados}


def caso_de_teste(cid: str) -> dict:
    return {"id": cid, "titulo": "t", "stack": "python", "perfil": "auto", "briefing": "Briefing sintético.",
            "respostas_da_entrevista": ["Resposta um.", "Resposta dois."], "limites": {"tokens": 5000, "tempo_s": 600},
            "orcamento": {"tokens": 10000, "tempo_s": 900, "chamadas": 50}, "timeout_s": 20, "verificadores_extra": []}


# ------------------------------------------------------------------ verificadores: passa e falha de CADA um
def _mod_json(arquivos, rel, fn):
    dado = json.loads(arquivos[rel])
    fn(dado)
    arquivos[rel] = _json(dado)


def _qa(fn):
    return lambda a, api, caso: _mod_json(a, "tests/reports/qa_report.json", fn)


def _ausente(rel):
    return lambda a, api, caso: a.pop(rel)


def _corrompido(rel):
    return lambda a, api, caso: a.__setitem__(rel, '{"aprovado": tru')


FALHAS = [
    ("desfecho_concluida", lambda a, api, c: api["detalhe"]["situacao"].update(estado="aguardando_aprovacao_release")),
    ("desfecho_concluida", lambda a, api, c: api.update(detalhe={})),
    ("build_e_testes", _qa(lambda d: d["etapas"][1].update(codigo=1))),
    ("build_e_testes", _qa(lambda d: d["etapas"][0].update(codigo=2))),
    ("build_e_testes", _qa(lambda d: d.update(etapas="nada"))),
    ("build_e_testes", _ausente("tests/reports/qa_report.json")),
    ("build_e_testes", _corrompido("tests/reports/qa_report.json")),
    ("build_e_testes", lambda a, api, c: a.__setitem__("tests/reports/qa_report.json", " " * 2_100_000)),  # JSON grande demais
    ("cobertura", _qa(lambda d: d["etapas"][2]["detalhe"].update(linha=89.9))),
    ("cobertura", _qa(lambda d: d["etapas"][2]["detalhe"].update(ramo=70))),
    ("cobertura", _qa(lambda d: d["etapas"][2]["detalhe"].update(minimo=0))),
    ("cobertura", _qa(lambda d: d["etapas"].pop())),
    ("cobertura", lambda a, api, c: c.update(cobertura_minima=99)),
    ("cobertura", _corrompido("tests/reports/qa_report.json")),
    ("sem_achados_graves", lambda a, api, c: _mod_json(a, "tests/reports/hacker_report.json",
                                                        lambda d: d["achados"].append({"severidade": "ALTO"}))),
    ("sem_achados_graves", lambda a, api, c: _mod_json(a, "tests/reports/hacker_report.json",
                                                        lambda d: d["achados"].append({"severity": "critical"}))),
    ("sem_achados_graves", lambda a, api, c: _mod_json(a, "tests/reports/macaco_report.json",
                                                        lambda d: d["resumo"].update(CRITICO=2))),
    ("sem_achados_graves", lambda a, api, c: _mod_json(a, "tests/reports/macaco_report.json",
                                                        lambda d: d["achados"].append({"severidade": "CRÍTICO"}) if "achados" in d
                                                        else d.update(achados=[{"severidade": "CRÍTICO"}]))),
    ("sem_achados_graves", _ausente("tests/reports/macaco_report.json")),
    ("sem_achados_graves", _corrompido("tests/reports/hacker_report.json")),
    ("portoes_verdes", lambda a, api, c: api["detalhe"]["verificacoes"].update(review_passed=False)),
    ("portoes_verdes", lambda a, api, c: api["detalhe"].pop("verificacoes")),
    ("portoes_verdes", lambda a, api, c: _mod_json(a, "tests/reports/security_report.json", lambda d: d.update(aprovado=False))),
    ("portoes_verdes", lambda a, api, c: _mod_json(a, "tests/reports/qa_report.json", lambda d: d.pop("aprovado"))),
    ("portoes_verdes", lambda a, api, c: _mod_json(a, "tests/reports/carga_report.json", lambda d: d.update(aprovado=False))),
    ("portoes_verdes", _ausente("tests/reports/carga_report.json")),
    ("portoes_verdes", _corrompido("tests/reports/devops_report.json")),
    ("arquivos_obrigatorios", _ausente("Dockerfile")),
    ("arquivos_obrigatorios", _ausente(".gitignore")),
    ("arquivos_obrigatorios", _ausente("contracts/openapi.yaml")),
    ("arquivos_obrigatorios", _ausente("docs/proveniencia.json")),
    ("arquivos_obrigatorios", lambda a, api, c: a.__setitem__("README.md", "")),
    ("sem_segredos", lambda a, api, c: a.__setitem__("app/config.py", f'CHAVE = "{SEGREDO}"\n')),
    ("sem_segredos", lambda a, api, c: a.__setitem__("app/cfg.py", "senha = '[linha omitida: possível segredo]'\n"
                                                                    "x = '[linha omitida: possível segredo]'\n")),
    ("proveniencia_doutrina", lambda a, api, c: _mod_json(a, "docs/proveniencia.json", lambda d: d["doutrina"].update(hash="outro"))),
    ("proveniencia_doutrina", lambda a, api, c: _mod_json(a, "docs/proveniencia.json", lambda d: d["doutrina"].update(versao="0.0.1"))),
    ("proveniencia_doutrina", lambda a, api, c: api["detalhe"].pop("doutrina")),
    ("proveniencia_doutrina", _corrompido("docs/proveniencia.json")),
    ("limites_tokens_tempo", lambda a, api, c: api["auditoria"]["totais"].update(tokens=2001)),
    ("limites_tokens_tempo", lambda a, api, c: api.update(duracao_s=301)),
    ("limites_tokens_tempo", lambda a, api, c: api.update(auditoria={})),
    ("limites_tokens_tempo", lambda a, api, c: c.pop("limites")),
    ("conversa_com_chefe", lambda a, api, c: api["mensagens"]["mensagens"].pop()),
    ("conversa_com_chefe", lambda a, api, c: api.update(mensagens={})),
]


def test_base_passa_em_todos_os_verificadores_gerais(tmp_path):
    ws = escrever(tmp_path, arquivos_validos())
    res = verificadores.executar(ws, api_valida(), caso_base())
    assert len(res) == len(verificadores.GERAIS) == 10
    assert [r["nome"] for r in res if not r["passou"]] == []
    assert all(set(r) == {"nome", "passou", "detalhe"} for r in res)


@pytest.mark.parametrize("nome,mutacao", FALHAS, ids=[f"{n}-{i}" for i, (n, _) in enumerate(FALHAS)])
def test_cada_verificador_reprova_o_defeito_e_so_ele(tmp_path, nome, mutacao):
    arquivos, api, caso = arquivos_validos(), api_valida(), caso_base()
    mutacao(arquivos, api, caso)
    res = por_nome(verificadores.executar(escrever(tmp_path, arquivos), api, caso))
    assert res[nome]["passou"] is False
    assert res[nome]["detalhe"]


def test_todo_verificador_geral_tem_um_caso_de_falha():
    assert {v.nome for v in verificadores.GERAIS} == {n for n, _ in FALHAS}


def test_segredo_aparece_so_como_tipo_e_local_nunca_o_valor(tmp_path):
    arquivos = arquivos_validos()
    arquivos["app/config.py"] = f'x = 1\nCHAVE = "{SEGREDO}"\n'
    res = por_nome(verificadores.executar(escrever(tmp_path, arquivos), api_valida(), caso_base()))
    texto = json.dumps(res, ensure_ascii=False)
    assert "chave-aws em app/config.py:2" in res["sem_segredos"]["detalhe"]
    assert SEGREDO not in texto


def test_verificadores_nao_levantam_com_entrada_totalmente_invalida(tmp_path):
    for ws, api, caso in ((tmp_path / "nao_existe", None, None), (tmp_path, "lixo", []), (tmp_path, {"detalhe": 3}, {"limites": 7})):
        res = verificadores.executar(ws, api, caso)
        assert len(res) == 10 and not any(r["passou"] for r in res if r["nome"] != "sem_segredos")  # pasta vazia não tem segredo


# ---- entrada hostil: caminhos, links, glob
@pytest.mark.parametrize("rel", ["../fora.txt", "a/../../fora.txt", "/etc/passwd", "C:/Windows/win.ini", "", "..", "a\\..\\..\\x"])
def test_caminho_hostil_e_recusado(tmp_path, rel):
    with pytest.raises(verificadores.EntradaInvalida):
        verificadores._seguro(tmp_path, rel)


def test_link_simbolico_para_fora_e_recusado_e_nao_e_lido(tmp_path):
    fora = tmp_path / "fora"
    fora.mkdir()
    (fora / "segredo.txt").write_text("conteudo externo", encoding="utf-8")
    ws = tmp_path / "ws"
    ws.mkdir()
    try:
        os.symlink(fora, ws / "link", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("sem permissão para criar link simbólico neste ambiente")
    with pytest.raises(verificadores.EntradaInvalida):
        verificadores._ler_texto(ws, "link/segredo.txt")


def test_glob_com_ponto_ponto_e_recusado_e_nada_fora_do_workspace_e_lido(tmp_path):
    (tmp_path / "fora.txt").write_text("PALAVRA-SECRETA", encoding="utf-8")
    ws = tmp_path / "ws"
    ws.mkdir()
    r = verificadores.conteudo_contem(ws, {}, {}, {"nome": "n", "glob": ["../*.txt"], "termos_todos": ["PALAVRA-SECRETA"]})
    assert r["passou"] is False and "recusado" in r["detalhe"]
    r = verificadores.conteudo_contem(ws, {}, {}, {"nome": "n", "glob": ["/tmp/*"], "termos_todos": ["x"]})
    assert r["passou"] is False


# ---- verificadores por caso
def test_conteudo_contem_passa_e_falha(tmp_path):
    ws = escrever(tmp_path, arquivos_validos())
    ok = verificadores.conteudo_contem(ws, {}, {}, {"nome": "idem", "glob": ["contracts/openapi.*"], "termos_todos": ["idempotency-key"]})
    assert ok == {"nome": "idem", "passou": True, "detalhe": "1 arquivo(s) conferidos"}
    ausente = verificadores.conteudo_contem(ws, {}, {}, {"nome": "idem", "glob": ["contracts/openapi.*"], "termos_todos": ["x-nao-existe"]})
    assert ausente["passou"] is False and "x-nao-existe" in ausente["detalhe"]
    algum = verificadores.conteudo_contem(ws, {}, {}, {"nome": "q", "glob": ["tests/**/*.py"], "termos_qualquer": ["zzz", "409"]})
    assert algum["passou"] is True
    nenhum = verificadores.conteudo_contem(ws, {}, {}, {"nome": "q", "glob": ["tests/**/*.py"], "termos_qualquer": ["zzz"]})
    assert nenhum["passou"] is False
    sem_arquivo = verificadores.conteudo_contem(ws, {}, {}, {"nome": "q", "glob": ["nada/*.py"], "termos_todos": ["a"]})
    assert sem_arquivo["passou"] is False


def test_executar_inclui_verificadores_do_caso_e_trata_tipo_desconhecido(tmp_path):
    ws = escrever(tmp_path, arquivos_validos())
    caso = {**caso_base(), "verificadores_extra": [
        {"tipo": "conteudo_contem", "nome": "k", "glob": "contracts/openapi.*", "termos_todos": ["Idempotency-Key"]},
        {"tipo": "inexistente"}, "lixo"]}
    res = verificadores.executar(ws, api_valida(), caso)
    assert por_nome(res)["k"]["passou"] is True
    assert sum(1 for r in res if r["nome"] == "verificador_do_caso" and not r["passou"]) == 2


def test_casos_dourados_carregam_e_o_do_pedido_exige_idempotency_key(tmp_path):
    casos = driver.carregar_casos(run.PASTA_CASOS)
    ids = [c["id"] for c in casos]
    assert ids == ["a-crud-tarefas", "b-catalogo", "c-autenticada", "d-pedidos"]
    assert all(c["stack"] == "python" and c["perfil"] == "auto" and c["respostas_da_entrevista"] for c in casos)
    d = next(c for c in casos if c["id"] == "d-pedidos")
    arquivos = arquivos_validos()
    ws_ok = escrever(tmp_path / "ok", arquivos)
    assert por_nome(verificadores.executar(ws_ok, api_valida(), d))["openapi_declara_idempotency_key"]["passou"] is True
    arquivos["contracts/openapi.yaml"] = "openapi: 3.1.0\npaths:\n  /pedidos: {}\n"
    ws_ruim = escrever(tmp_path / "ruim", arquivos)
    assert por_nome(verificadores.executar(ws_ruim, api_valida(), d))["openapi_declara_idempotency_key"]["passou"] is False


@pytest.mark.parametrize("mut", [lambda c: c.update(id="Maiusculo"), lambda c: c.update(briefing=" "), lambda c: c.update(stack="dotnet"),
                                 lambda c: c.update(respostas_da_entrevista=[]), lambda c: c.update(limites={"tokens": 0, "tempo_s": 5}),
                                 lambda c: c.update(verificadores_extra=[{"tipo": "x"}]), lambda c: c.update(timeout_s=-1)])
def test_caso_malformado_e_recusado(mut):
    caso = caso_de_teste("ok")
    driver.validar_caso(copy.deepcopy(caso))
    mut(caso)
    with pytest.raises(driver.ErroCaso):
        driver.validar_caso(caso)


# ------------------------------------------------------------------ pass@k / pass^k
@pytest.mark.parametrize("n,c,k,esp_at,esp_hat", [
    (4, 0, 4, 0.0, 0.0), (4, 4, 4, 1.0, 1.0), (4, 3, 4, 1.0, 0.0), (1, 1, 1, 1.0, 1.0), (1, 0, 1, 0.0, 0.0),
    (3, 2, 1, 2 / 3, 2 / 3), (3, 2, 2, 1.0, 1 / 3), (5, 1, 2, 1 - 6 / 10, 0.0)])
def test_pass_at_k_e_pass_hat_k(n, c, k, esp_at, esp_hat):
    assert relatorio.pass_at_k(n, c, k) == pytest.approx(esp_at)
    assert relatorio.pass_hat_k(n, c, k) == pytest.approx(esp_hat)


@pytest.mark.parametrize("n,c,k", [(0, 0, 1), (3, 4, 1), (3, -1, 1), (3, 1, 0), (3, 1, 4)])
def test_pass_k_recusa_parametros_invalidos(n, c, k):
    with pytest.raises(ValueError):
        relatorio.pass_at_k(n, c, k)
    with pytest.raises(ValueError):
        relatorio.pass_hat_k(n, c, k)


def _res(caso, passou, tokens=1000, dur=600.0, falhas=(), desfecho="concluida", nos=()):
    return {"caso": caso, "n": 1, "passou": passou, "tokens": tokens, "duracao_s": dur, "desfecho": desfecho,
            "verificadores": [{"nome": f, "passou": False, "detalhe": "d"} for f in falhas] + [{"nome": "ok", "passou": True, "detalhe": ""}],
            "nos_lentos": [{"no": n, "duracao_s": d} for n, d in nos]}


def test_agregar_calcula_k_igual_ao_numero_de_execucoes_e_lista_falhas():
    rs = [_res("a", True), _res("a", False, falhas=["cobertura"], desfecho="concluida"), _res("a", True),
          _res("b", False, falhas=["cobertura", "sem_segredos"], nos=[("qa", 30), ("dev", 90)], desfecho="escalada")]
    s = relatorio.agregar(rs)
    assert (s["a"]["execucoes"], s["a"]["aprovadas"], s["a"]["k"]) == (3, 2, 3)
    assert s["a"]["pass_at_k"] == 1.0 and s["a"]["pass_hat_k"] == 0.0
    assert s["a"]["verificadores_que_falharam"] == {"cobertura": 1}
    assert s["b"]["pass_at_k"] == 0.0 and s["b"]["desfechos"] == ["escalada"]
    assert [x["no"] for x in s["b"]["nos_mais_lentos"]] == ["dev", "qa"]


# ------------------------------------------------------------------ comparação entre rodadas
def _resumo(passou=True, tokens=1000.0, dur=600.0, falhas=None):
    return relatorio.agregar([_res("c1", passou, tokens, dur, falhas or [])])


def test_comparacao_detecta_regressao_de_caso_tokens_e_tempo():
    ant = _resumo(True)
    r = relatorio.comparar(_resumo(False, falhas=["cobertura"]), ant)
    assert [x["tipo"] for x in r["regressoes"]] == ["passava_e_agora_falha"] and "cobertura" in r["regressoes"][0]["detalhe"]
    r = relatorio.comparar(_resumo(True, tokens=1301), ant)
    assert [x["tipo"] for x in r["regressoes"]] == ["tokens_acima_do_limiar"]
    r = relatorio.comparar(_resumo(True, tokens=1299, dur=779), ant)
    assert r["regressoes"] == []
    r = relatorio.comparar(_resumo(True, dur=781), ant)
    assert [x["tipo"] for x in r["regressoes"]] == ["duração_acima_do_limiar"]


def test_comparacao_melhoria_caso_novo_e_sem_anterior():
    r = relatorio.comparar(_resumo(True), _resumo(False))
    assert r["melhorias"] == [{"caso": "c1", "tipo": "falhava_e_agora_passa"}] and r["regressoes"] == []
    r = relatorio.comparar({**_resumo(True), **relatorio.agregar([_res("novo", True)])}, _resumo(True))
    assert r["novos_casos"] == ["novo"]
    assert relatorio.comparar(_resumo(True), None) == {"anterior": False, "regressoes": [], "melhorias": [], "novos_casos": ["c1"]}


def test_rodada_anterior_pega_a_mais_recente_anterior_e_ignora_lixo(tmp_path):
    def rodada(nome, conteudo):
        (tmp_path / nome).mkdir()
        if conteudo is not None:
            (tmp_path / nome / "resumo.json").write_text(conteudo, encoding="utf-8")
    rodada("2026-01-01_000000", _json({"casos": {"c1": {"x": 1}}}))
    rodada("2026-01-02_000000", _json({"casos": {"c1": {"x": 2}}}))
    rodada("2026-01-03_000000", "{corrompido")
    rodada("2026-01-04_000000", None)
    rodada("2026-01-06_000000", _json({"casos": {"c1": {"x": 6}}}))
    assert relatorio.rodada_anterior(tmp_path, "2026-01-05_000000")["casos"]["c1"]["x"] == 2   # pula a corrompida e a sem resumo
    assert relatorio.rodada_anterior(tmp_path, "2026-01-01_000000") is None
    assert relatorio.rodada_anterior(tmp_path / "nao_existe", "z") is None


# ------------------------------------------------------------------ API simulada
class ApiFalsa:
    """Imita as transições da API real em processo. `cenario` escolhe o defeito; `chamadas` registra (método, rota, corpo)."""
    FASES = ["aguardando_respostas", "aguardando_aprovacao_spec", "aguardando_aprovacao_release", "concluida"]

    def __init__(self, cenario="feliz", arquivos=None):
        self.cenario, self.arquivos = cenario, arquivos if arquivos is not None else arquivos_validos()
        self.chamadas, self.tarefas, self.travas = [], {}, threading.Lock()
        self.get_5xx_restantes = 2 if cenario == "get_5xx_transitorio" else 0
        self.ocupado_restante = 1 if cenario == "ocupado" else 0
        api = self
        self.arquivos_extra = ["../fora.txt", "/etc/passwd"] if cenario == "arquivos_hostis" else []
        if cenario == "arquivos_hostis":
            self.arquivos["../fora.txt"] = "FORA"
            self.arquivos["/etc/passwd"] = "root"

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _enviar(self, status, corpo):
                dados = _json(corpo).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(dados)))
                self.end_headers()
                self.wfile.write(dados)

            def _tratar(self, metodo):
                url = urlparse(self.path)
                if url.path == "/saude":
                    return self._enviar(200, {"ok": True})
                if self.headers.get("Authorization") != f"Bearer {TOKEN}":
                    return self._enviar(401, {"erro": {"codigo": "nao_autenticado", "mensagem": "token ausente ou inválido"}})
                corpo = {}
                if metodo == "POST":
                    corpo = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}")
                with api.travas:
                    status, dado = api.rotear(metodo, url.path, parse_qs(url.query), corpo)
                self._enviar(status, dado)

            def do_GET(self):
                self._tratar("GET")

            def do_POST(self):
                self._tratar("POST")

        self.servidor = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.servidor.server_address[1]}"
        self.thread = threading.Thread(target=self.servidor.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *a):
        self.servidor.shutdown()
        self.servidor.server_close()
        self.thread.join(5)

    # -- lógica
    def erro(self, status, codigo, msg="x"):
        return status, {"erro": {"codigo": codigo, "mensagem": msg}}

    def rotear(self, metodo, caminho, q, corpo):
        self.chamadas.append((metodo, re.sub(r"ev-[^/]+", "TAREFA", caminho), corpo))
        if metodo == "POST" and caminho == "/api/tarefas":
            if self.ocupado_restante:
                self.ocupado_restante -= 1
                return self.erro(409, "ocupado", "já há uma execução em andamento")
            tid = corpo["tarefa"]
            self.tarefas[tid] = {"estado": None, "alvo": "aguardando_respostas", "rodando": 2, "invisivel": 1 if self.cenario != "nunca_aparece" else 10 ** 9,
                                 "respostas": 0, "exec_final": "ok"}
            return 202, {"tarefa": tid}
        m = re.match(r"^/api/tarefas/([^/]+)(?:/([a-z-]+))?$", caminho)
        if not m or m.group(1) not in self.tarefas:
            return self.erro(404, "nao_encontrado", "tarefa inexistente")
        t, sub = self.tarefas[m.group(1)], m.group(2)
        if metodo == "POST":
            return self.acao(t, sub, corpo)
        if sub is None:
            return self.detalhe(t)
        if sub == "auditoria":
            return 200, {"totais": {"tokens": 4200, "tempo_s": 80.0}, "orcamento": {},
                         "nos": [{"no": "qa", "duracao_s": 30.0}, {"no": "dev", "duracao_s": 55.5}, {"no": "chefe", "duracao_s": 2.0}]}
        if sub == "mensagens":
            return 200, {"mensagens": [{"de": "usuario", "para": "chefe", "texto": "b"}, {"de": "chefe", "para": "usuario", "texto": "ok"}]}
        if sub == "arquivo":
            rel = unquote((q.get("caminho") or [""])[0])
            if rel in self.arquivos:
                return 200, {"caminho": rel, "conteudo": self.arquivos[rel], "truncado": False, "linhas_omitidas": 0}
            return self.erro(404, "nao_encontrado", "arquivo inexistente")
        return self.erro(404, "nao_encontrado")

    def acao(self, t, sub, corpo):
        if t["rodando"] > 0:
            return self.erro(409, "ocupado", "execução em andamento")
        seq = {"responder": ("aguardando_respostas", "aguardando_aprovacao_spec"),
               "aprovar": ("aguardando_aprovacao_spec", "aguardando_aprovacao_release"),
               "aprovar-release": ("aguardando_aprovacao_release", "concluida")}
        if sub not in seq or t["estado"] != seq[sub][0]:
            return self.erro(409, "estado_invalido", "nada a fazer")
        if sub == "responder":
            t["respostas"] += 1
            if self.cenario == "post_5xx":
                return self.erro(500, "falha_interna", "falha interna: RuntimeError")
        t["alvo"], t["rodando"], t["exec_final"] = seq[sub][1], 2, "ok"
        if self.cenario == "entrevista_infinita" and sub == "responder":
            t["alvo"] = "aguardando_respostas"
        if self.cenario == "escalada" and sub == "aprovar":
            t["alvo"] = "escalada"
        if self.cenario == "erro_execucao" and sub == "responder":
            t["exec_final"] = "erro"
        if self.cenario == "timeout" and sub == "responder":
            t["rodando"] = 10 ** 9
        return 202, {"tarefa": "x"}

    def detalhe(self, t):
        if self.cenario == "get_5xx_sempre":
            return self.erro(500, "falha_interna")
        if self.get_5xx_restantes:
            self.get_5xx_restantes -= 1
            return self.erro(500, "falha_interna")
        if t["invisivel"] > 0:
            t["invisivel"] -= 1
            return self.erro(404, "nao_encontrado", "tarefa inexistente")
        if t["rodando"] > 0:
            t["rodando"] -= 1
            if t["rodando"] == 0:
                t["estado"] = t["alvo"]
        rodando = t["rodando"] > 0 or t["estado"] is None
        exe = {"estado": "rodando" if rodando else t["exec_final"], "acao": "x", "nos": [],
               "erro": f"modelo indisponível (chave {TOKEN})" if t["exec_final"] == "erro" and not rodando else None}
        msg = {"escalada": "orçamento da tarefa esgotado: 100 de 100 tokens"}.get(t["estado"], "")
        return 200, {"tarefa": "x", "situacao": {"estado": t["estado"] or "em_fase", "fase": "F", "aguardando": [], "mensagem": msg},
                     "execucao": exe, "doutrina": dict(DOUTRINA),
                     "verificacoes": {k: True for k in ("tests_passed", "review_passed", "security_passed", "devops_passed")},
                     "arquivos": [*sorted(self.arquivos), *self.arquivos_extra][:50]}

    def metodos(self, metodo, sufixo=None):
        return [c for c in self.chamadas if c[0] == metodo and (sufixo is None or c[1].endswith(sufixo))]


def executar(api, tmp_path, caso=None, **kw):
    cliente = driver.Cliente(api.url, TOKEN, timeout_s=5, espera_s=0.01)
    kw.setdefault("intervalo_s", 0.01)
    return driver.executar_caso(cliente, caso or caso_de_teste("c1"), 1, "2026-01-01_000000", tmp_path / "saida", **kw)


def test_driver_fluxo_feliz_ponta_a_ponta_passa_em_todos_os_verificadores(tmp_path):
    with ApiFalsa() as api:
        r = executar(api, tmp_path)
    assert r["desfecho"] == "concluida"
    assert [v["nome"] for v in r["verificadores"] if not v["passou"]] == []
    assert r["passou"] is True and r["modo_eval"] is True
    assert [a["etapa"] for a in r["aprovacoes_automaticas"]] == ["aguardando_aprovacao_spec", "aguardando_aprovacao_release"]
    assert all(a["automatica_de_teste"] for a in r["aprovacoes_automaticas"])
    assert r["tokens"] == 4200 and [n["no"] for n in r["nos_lentos"]] == ["dev", "qa", "chefe"]
    # cada ação exatamente uma vez, na ordem do fluxo, com o corpo esperado
    posts = [c[1] for c in api.metodos("POST")]
    assert posts == ["/api/tarefas", "/api/tarefas/TAREFA/responder", "/api/tarefas/TAREFA/aprovar",
                     "/api/tarefas/TAREFA/aprovar-release"]
    inicio = api.metodos("POST")[0][2]
    assert inicio["perfil"] == "auto" and inicio["consentimento_nuvem"] is True and inicio["stack"] == "python"
    assert inicio["orcamento"] == caso_de_teste("c1")["orcamento"]
    resposta = api.metodos("POST", "/responder")[0][2]["resposta"]
    assert "Resposta um." in resposta and "Resposta dois." in resposta
    assert (tmp_path / "saida" / "workspace" / "README.md").is_file()


def test_driver_nao_repete_a_resposta_enquanto_a_execucao_ainda_roda(tmp_path):
    with ApiFalsa() as api:
        executar(api, tmp_path)
    assert len(api.metodos("POST", "/responder")) == len(api.metodos("POST", "/aprovar")) == len(api.metodos("POST", "/aprovar-release")) == 1


def test_driver_escalada_encerra_reprovado_com_o_motivo_e_nao_aprova_o_release(tmp_path):
    with ApiFalsa("escalada") as api:
        r = executar(api, tmp_path)
    assert r["desfecho"] == "escalada" and r["passou"] is False
    assert "orçamento da tarefa esgotado" in r["motivo"]
    assert api.metodos("POST", "/aprovar-release") == []
    assert por_nome(r["verificadores"])["desfecho_concluida"]["passou"] is False


def test_driver_erro_de_execucao_vira_reprovacao_e_nao_vaza_o_token(tmp_path):
    with ApiFalsa("erro_execucao") as api:
        r = executar(api, tmp_path)
    assert r["desfecho"] == "erro_de_execucao" and r["passou"] is False
    assert "modelo indisponível" in r["motivo"]
    assert TOKEN not in json.dumps(r)


def test_driver_timeout_global_encerra_o_caso(tmp_path):
    with ApiFalsa("timeout") as api:
        r = executar(api, tmp_path, timeout_s=0.4)
    assert r["desfecho"] == "timeout" and r["passou"] is False and "prazo" in r["motivo"]
    assert r["duracao_s"] < 5


def test_driver_get_5xx_transitorio_e_repetido_e_o_caso_passa(tmp_path):
    with ApiFalsa("get_5xx_transitorio") as api:
        r = executar(api, tmp_path)
    assert r["passou"] is True


def test_driver_get_5xx_persistente_vira_erro_de_api(tmp_path):
    with ApiFalsa("get_5xx_sempre") as api:
        r = executar(api, tmp_path)
    assert r["desfecho"] == "erro_de_api" and r["passou"] is False and "500" in r["motivo"]
    assert por_nome(r["verificadores"])["execucao"]["passou"] is False


def test_driver_post_5xx_nao_e_repetido(tmp_path):
    with ApiFalsa("post_5xx") as api:
        r = executar(api, tmp_path)
    assert r["desfecho"] == "erro_de_api" and "500" in r["motivo"]
    assert len(api.metodos("POST", "/responder")) == 1


def test_driver_espera_a_vez_quando_a_squad_esta_ocupada(tmp_path):
    with ApiFalsa("ocupado") as api:
        r = executar(api, tmp_path)
    assert r["passou"] is True and len(api.metodos("POST", "/api/tarefas")) == 2


def test_driver_entrevista_que_nao_converge_para_depois_do_limite(tmp_path):
    with ApiFalsa("entrevista_infinita") as api:
        r = executar(api, tmp_path, max_rodadas_entrevista=2)
    assert r["desfecho"] == "entrevista_nao_convergiu" and len(api.metodos("POST", "/responder")) == 2
    assert api.metodos("POST", "/responder")[1][2]["resposta"] == driver.RESPOSTA_DE_REFORCO


def test_driver_tarefa_que_nunca_aparece_vira_erro_apos_a_espera_inicial(tmp_path):
    with ApiFalsa("nunca_aparece") as api:
        r = executar(api, tmp_path, espera_inicial_s=0.2)
    assert r["desfecho"] == "erro_de_api" and "404" in r["motivo"]


def test_coleta_recusa_caminhos_hostis_listados_pela_api(tmp_path):
    with ApiFalsa("arquivos_hostis") as api:
        r = executar(api, tmp_path)
    assert r["coleta"]["recusados"] >= 2
    assert not (tmp_path / "fora.txt").exists() and not (tmp_path / "saida" / "fora.txt").exists()
    assert not any(p.name in ("fora.txt", "passwd") for p in tmp_path.rglob("*"))


def test_cliente_recusa_url_fora_do_loopback_e_token_vazio():
    for url in ("http://exemplo.com:8790", "https://127.0.0.1:8790", "http://127.0.0.1", "http://10.0.0.5:8790", "http://127.0.0.1:8790/x"):
        with pytest.raises(driver.ErroCaso):
            driver.Cliente(url, TOKEN)
    with pytest.raises(driver.ErroCaso):
        driver.Cliente("http://127.0.0.1:8790", "")


def test_token_errado_da_401_sem_ecoar_o_token():
    with ApiFalsa() as api:
        cliente = driver.Cliente(api.url, "outro-token-" + "q" * 30, espera_s=0.01)
        with pytest.raises(driver.ErroApi) as e:
            cliente.requisitar("GET", "/api/tarefas")
    assert e.value.status == 401 and "outro-token" not in e.value.mensagem


def test_conexao_recusada_vira_erro_de_api_status_zero():
    with ApiFalsa() as api:
        url = api.url
    cliente = driver.Cliente(url, TOKEN, timeout_s=1, tentativas=2, espera_s=0.01)
    with pytest.raises(driver.ErroApi) as e:
        cliente.requisitar("GET", "/api/tarefas")
    assert e.value.status == 0 and TOKEN not in e.value.mensagem


# ------------------------------------------------------------------ rodada completa, relatório e vazamento
def _gravar_casos(pasta: Path, ids) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    for cid in ids:
        (pasta / f"{cid}.json").write_text(_json(caso_de_teste(cid)), encoding="utf-8")
    return pasta


def test_rodada_com_k2_grava_resultados_relatorio_e_compara_com_a_anterior(tmp_path):
    casos = driver.carregar_casos(_gravar_casos(tmp_path / "casos", ["c1", "c2"]))
    saida = tmp_path / "res"
    with ApiFalsa() as api:
        cliente = driver.Cliente(api.url, TOKEN, timeout_s=5, espera_s=0.01)
        r1 = run.rodar_rodada(cliente, casos, 2, saida, rodada="2026-01-01_000000", intervalo_s=0.01)
    pasta = saida / "2026-01-01_000000"
    assert sorted(p.name for p in pasta.glob("*.json")) == ["c1-1.json", "c1-2.json", "c2-1.json", "c2-2.json", "resumo.json"]
    assert r1["resumo"]["c1"]["pass_hat_k"] == 1.0 and r1["comparacao"]["anterior"] is False
    md = (pasta / "RELATORIO.md").read_text(encoding="utf-8")
    assert "MODO EVAL" in md and "| c1 | 2/2 SIM |" in md and "dev 55.5s" in md and "Não há rodada anterior" in md

    with ApiFalsa("escalada") as api:  # segunda rodada: o fluxo escala -> regressão contra a primeira
        cliente = driver.Cliente(api.url, TOKEN, timeout_s=5, espera_s=0.01)
        r2 = run.rodar_rodada(cliente, casos[:1], 2, saida, rodada="2026-01-02_000000", intervalo_s=0.01)
    assert [x["caso"] for x in r2["comparacao"]["regressoes"]] == ["c1"]
    md2 = (saida / "2026-01-02_000000" / "RELATORIO.md").read_text(encoding="utf-8")
    assert "REGRESSÃO `c1`" in md2 and "2026-01-01_000000" in md2 and "escalada" in md2


def test_nenhum_relatorio_imprime_o_token_nem_valor_de_segredo(tmp_path):
    arquivos = arquivos_validos()
    arquivos["app/config.py"] = f'CHAVE = "{SEGREDO}"\nTOKEN_API = "{TOKEN}"\n'
    casos = driver.carregar_casos(_gravar_casos(tmp_path / "casos", ["c1"]))
    saida = tmp_path / "res"
    with ApiFalsa("erro_execucao", arquivos) as api:
        cliente = driver.Cliente(api.url, TOKEN, timeout_s=5, espera_s=0.01)
        run.rodar_rodada(cliente, casos, 1, saida, rodada="2026-01-01_000000", intervalo_s=0.01)
    with ApiFalsa("feliz", arquivos) as api:
        cliente = driver.Cliente(api.url, TOKEN, timeout_s=5, espera_s=0.01)
        r = run.rodar_rodada(cliente, casos, 1, saida, rodada="2026-01-02_000000", intervalo_s=0.01)
    assert por_nome(r["resultados"][0]["verificadores"])["sem_segredos"]["passou"] is False   # o verificador viu o segredo...
    relatorios = [p for p in saida.rglob("*") if p.is_file() and "workspace" not in p.relative_to(saida).parts]
    assert len(relatorios) >= 6
    for p in relatorios:
        texto = p.read_text(encoding="utf-8")
        assert TOKEN not in texto and SEGREDO not in texto, p.name       # ...mas nenhum relatório traz o valor
    # nem a cópia do workspace guarda o token da API
    assert all(TOKEN not in p.read_text(encoding="utf-8") for p in saida.rglob("*") if p.is_file())


def test_cli_codigos_de_saida_e_nada_de_token_na_saida(tmp_path, capsys, monkeypatch):
    casos = _gravar_casos(tmp_path / "casos", ["c1"])
    base = ["--casos-dir", str(casos), "--saida", str(tmp_path / "res"), "--intervalo-s", "0.01"]
    monkeypatch.delenv("TUDOIA_SQUADTI_TOKEN", raising=False)
    with ApiFalsa() as api:
        assert run.main([*base, "--url", api.url]) == 2                       # sem token
        monkeypatch.setenv("TUDOIA_SQUADTI_TOKEN", TOKEN)
        assert run.main([*base, "--url", api.url, "--k", "0"]) == 2
        assert run.main([*base, "--url", api.url, "--caso", "nao-existe"]) == 2
        assert run.main([*base, "--url", "http://exemplo.com:1"]) == 2
        assert run.main([*base, "--url", api.url, "--k", "2"]) == 0
    with ApiFalsa("escalada") as api:
        assert run.main([*base, "--url", api.url]) == 1
    saida = capsys.readouterr()
    assert TOKEN not in saida.out and TOKEN not in saida.err
    assert "MODO EVAL" in saida.out and "pass@k=1.0 pass^k=1.0" in saida.out

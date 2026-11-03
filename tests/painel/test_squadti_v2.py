# ruff: noqa: F401, F811  (fixtures importadas de test_squadti.py: o pytest as resolve pelo nome)
"""Rotas /api/squadti da v2 (agentes, CHEFE, auditoria, proveniência, log, continuar). Mesmo seam de test_squadti.py:
API da Squad falsa por httpx.MockTransport e cookies de sessão assinados; nada de métodos privados."""
import httpx
import pytest

from tudoia_painel.rotas import squadti

# as fixtures vêm do módulo irmão (o pytest as resolve pelo nome no namespace deste arquivo)
from test_squadti import TOKEN, admin, api_falsa, leitor, montar, operador  # noqa: F401

CFG_OK = {
    "agentes": {"chefe": {"perfil": "local", "temperatura": 0.2, "max_tokens": 4000}, "backend": {"temperatura": 0.0}},
    "revisao": {"modo": "dupla"},
    "validacao": {"modo": "auto", "carga": "escalado", "slo": {"p95_ms": 800, "p99_ms": 1500, "erro_max": 0.01}, "ui_segundos": 30},
    "orcamento": {"tokens": 3_000_000, "tempo_s": None, "chamadas": 400},
}


# ---------------------------------------------------------------- leituras repassam certo
@pytest.mark.parametrize("rota,destino", [
    ("/api/squadti/agentes", "/api/agentes"),
    ("/api/squadti/tarefas/T1/mensagens", "/api/tarefas/T1/mensagens"),
    ("/api/squadti/tarefas/T1/auditoria", "/api/tarefas/T1/auditoria"),
    ("/api/squadti/tarefas/T1/proveniencia", "/api/tarefas/T1/proveniencia"),
])
def test_leituras_repassam_com_token_e_leitor_pode(leitor, api_falsa, rota, destino):
    api_falsa.resposta = (200, {"qualquer": "coisa"})
    r = leitor.get(rota)
    assert r.status_code == 200 and r.json() == {"qualquer": "coisa"}
    assert api_falsa.pedidos == [{"metodo": "GET", "caminho": destino, "auth": f"Bearer {TOKEN}", "corpo": None}]


def test_log_repassa_o_cursor_e_o_valida(leitor, api_falsa):
    api_falsa.resposta = (200, {"eventos": [], "proximo": 7})
    assert leitor.get("/api/squadti/tarefas/T1/log", params={"desde": 7}).json()["proximo"] == 7
    assert api_falsa.pedidos[0]["caminho"] == "/api/tarefas/T1/log?desde=7"
    leitor.get("/api/squadti/tarefas/T1/log")
    assert api_falsa.pedidos[1]["caminho"] == "/api/tarefas/T1/log?desde=0"
    antes = len(api_falsa.pedidos)
    for desde in ("-1", "abc", "99999999999"):
        assert leitor.get("/api/squadti/tarefas/T1/log", params={"desde": desde}).status_code == 422
    assert len(api_falsa.pedidos) == antes


# ---------------------------------------------------------------- papéis
def test_leitor_nao_escreve_nada_da_v2(leitor, api_falsa):
    for rota, corpo in [("/api/squadti/tarefas/T1/mensagem", {"texto": "oi"}),
                        ("/api/squadti/tarefas/T1/continuar", {}),
                        ("/api/squadti/agentes", CFG_OK)]:
        assert leitor.post(rota, json=corpo).status_code == 403, rota
    assert api_falsa.pedidos == []


def test_operador_fala_com_o_chefe_e_continua_mas_nao_salva_agentes(operador, api_falsa):
    api_falsa.resposta = (202, {"mensagens": []})
    assert operador.post("/api/squadti/tarefas/T1/mensagem", json={"texto": "/ajuste use Dapper"}).status_code == 202
    assert operador.post("/api/squadti/tarefas/T1/continuar", json={}).status_code == 202
    assert [p["caminho"] for p in api_falsa.pedidos] == ["/api/tarefas/T1/mensagem", "/api/tarefas/T1/continuar"]
    assert api_falsa.pedidos[0]["corpo"] == {"texto": "/ajuste use Dapper"}
    assert api_falsa.pedidos[1]["corpo"] == {}
    antes = len(api_falsa.pedidos)
    r = operador.post("/api/squadti/agentes", json=CFG_OK)
    assert r.status_code == 403 and r.json()["erro"]["codigo"] == "papel_insuficiente"
    assert len(api_falsa.pedidos) == antes


def test_admin_salva_agentes_e_o_corpo_chega_integro(admin, api_falsa):
    api_falsa.resposta = (200, CFG_OK)
    r = admin.post("/api/squadti/agentes", json=CFG_OK)
    assert r.status_code == 200
    enviado = api_falsa.pedidos[0]["corpo"]
    assert api_falsa.pedidos[0]["metodo"] == "POST" and api_falsa.pedidos[0]["caminho"] == "/api/agentes"
    assert enviado["revisao"] == {"modo": "dupla"} and enviado["validacao"] == CFG_OK["validacao"]
    assert enviado["orcamento"] == {"tokens": 3_000_000, "tempo_s": None, "chamadas": 400}  # null = sem limite sobrevive
    assert enviado["agentes"]["backend"] == {"temperatura": 0.0}  # o que o usuário não enviou não é inventado


def test_admin_tambem_le_e_o_prefixo_de_escrita_nao_vaza_para_outras_rotas(operador, api_falsa):
    assert operador.get("/api/squadti/agentes").status_code == 200
    # só `/api/squadti/agentes` é admin: o resto da Squad segue com o operador
    assert operador.post("/api/squadti/tarefas/T1/aprovar", json={}).status_code == 202


# ---------------------------------------------------------------- entrada hostil
@pytest.mark.parametrize("rota", ["mensagens", "auditoria", "proveniencia", "log"])
def test_id_com_ponto_ponto_nunca_chega_a_api(operador, api_falsa, rota):
    for tarefa in ("..", "a%2f..", "-x", "x" * 65, "a b"):
        assert operador.get(f"/api/squadti/tarefas/{tarefa}/{rota}").status_code in (404, 422), tarefa
    assert api_falsa.pedidos == []


@pytest.mark.parametrize("rota", ["mensagem", "continuar"])
def test_id_hostil_nos_posts_nunca_chega_a_api(operador, api_falsa, rota):
    for tarefa in ("..", "-x", "x" * 65):
        assert operador.post(f"/api/squadti/tarefas/{tarefa}/{rota}", json={"texto": "x"}).status_code in (404, 422), tarefa
    assert api_falsa.pedidos == []


def test_mensagem_vazia_gigante_ou_com_campo_extra_e_recusada(operador, api_falsa):
    url = "/api/squadti/tarefas/T1/mensagem"
    assert operador.post(url, json={"texto": ""}).status_code == 422
    assert operador.post(url, json={"texto": "x" * 4001}).status_code == 422
    assert operador.post(url, json={"texto": "x", "papel": "chefe"}).status_code == 422
    assert operador.post(url, json={}).status_code == 422
    assert operador.post(url, json={"texto": "x" * 4000}).status_code == 202
    assert len(api_falsa.pedidos) == 1


@pytest.mark.parametrize("corpo", [
    {"orcamento": {"tokens": 10}},                    # abaixo da faixa
    {"orcamento": {"tokens": 10**12}},
    {"orcamento": {"dinheiro": 5}},                   # eixo desconhecido
    {"orcamento": {"tokens": "muitos"}},
    {"extra": 1},
])
def test_continuar_valida_o_orcamento(operador, api_falsa, corpo):
    assert operador.post("/api/squadti/tarefas/T1/continuar", json=corpo).status_code == 422
    assert api_falsa.pedidos == []


def test_continuar_com_orcamento_novo_repassa_so_o_enviado(operador, api_falsa):
    operador.post("/api/squadti/tarefas/T1/continuar", json={"orcamento": {"tokens": 5_000_000}})
    assert api_falsa.pedidos[0]["corpo"] == {"orcamento": {"tokens": 5_000_000}}


@pytest.mark.parametrize("corpo", [
    {"agentes": {"../x": {}}},
    {"agentes": {"Chefe": {}}},
    {"agentes": {"chefe": {"modelo": "gpt"}}},         # campo extra do agente
    {"agentes": {"chefe": {"perfil": "max"}}},         # perfil pago não é oferecido
    {"agentes": {"chefe": {"temperatura": 9}}},
    {"agentes": {"chefe": {"max_tokens": 10}}},
    {"agentes": {"chefe": {"max_tokens": "x"}}},
    {"agentes": {f"a{i}": {} for i in range(40)}},     # agentes demais
    {"revisao": {"modo": "tripla"}},
    {"revisao": {"modo": "dupla", "x": 1}},
    {"orcamento": {"tempo_s": 1}},
    {"validacao": {"modo": {"a": {"b": 1}}}},          # profundidade
    {"validacao": {"modo": "x" * 200}},                # texto longo
    {"validacao": {"../x": 1}},
    {"validacao": {f"k{i}": 1 for i in range(20)}},
    {"validacao": [1, 2]},
    {"desconhecido": 1},
])
def test_salvar_agentes_recusa_corpo_hostil_antes_de_chamar_a_squad(admin, api_falsa, corpo):
    assert admin.post("/api/squadti/agentes", json=corpo).status_code == 422
    assert api_falsa.pedidos == []


def test_nova_tarefa_com_stack_e_orcamento(operador, api_falsa):
    api_falsa.resposta = (202, {"tarefa": "T1"})
    r = operador.post("/api/squadti/tarefas", json={"tarefa": "T1", "briefing": "x", "stack": "python",
                                                    "orcamento": {"tokens": 500_000, "chamadas": 50}})
    assert r.status_code == 202
    assert api_falsa.pedidos[0]["corpo"] == {"tarefa": "T1", "briefing": "x", "perfil": "local-estrito",
                                              "consentimento_nuvem": False, "stack": "python",
                                              "orcamento": {"tokens": 500_000, "chamadas": 50}}


def test_nova_tarefa_sem_stack_deixa_o_chefe_decidir(operador, api_falsa):
    operador.post("/api/squadti/tarefas", json={"tarefa": "T1", "briefing": "x"})
    assert "stack" not in api_falsa.pedidos[0]["corpo"] and "orcamento" not in api_falsa.pedidos[0]["corpo"]


@pytest.mark.parametrize("extra", [{"stack": "java"}, {"stack": ""}, {"orcamento": {"tokens": 1}}, {"orcamento": 5}])
def test_nova_tarefa_recusa_stack_e_orcamento_invalidos(operador, api_falsa, extra):
    assert operador.post("/api/squadti/tarefas", json={"tarefa": "T1", "briefing": "x", **extra}).status_code == 422
    assert api_falsa.pedidos == []


def test_nova_tarefa_perfil_auto_segue_exigindo_consentimento(operador, api_falsa):
    r = operador.post("/api/squadti/tarefas", json={"tarefa": "T1", "briefing": "x", "perfil": "auto", "stack": "dotnet"})
    assert r.status_code == 422 and r.json()["erro"]["codigo"] == "consentimento_nuvem"
    assert api_falsa.pedidos == []


# ---------------------------------------------------------------- erros da Squad
@pytest.mark.parametrize("metodo,rota,corpo", [
    ("post", "/api/squadti/tarefas/T1/mensagem", {"texto": "oi"}),
    ("post", "/api/squadti/tarefas/T1/continuar", {}),
    ("post", "/api/squadti/agentes", CFG_OK),
    ("get", "/api/squadti/tarefas/T1/auditoria", None),
    ("get", "/api/squadti/tarefas/T1/log", None),
])
def test_erro_4xx_da_squad_passa_com_codigo_e_mensagem(admin, api_falsa, metodo, rota, corpo):
    api_falsa.resposta = (409, {"erro": {"codigo": "estado_invalido", "mensagem": "a tarefa não está escalada"}})
    r = admin.post(rota, json=corpo) if metodo == "post" else admin.get(rota)
    assert r.status_code == 409
    assert r.json()["erro"] == {"codigo": "estado_invalido", "mensagem": "a tarefa não está escalada"} or \
        (r.json()["erro"]["codigo"] == "estado_invalido" and "escalada" in r.json()["erro"]["mensagem"])


@pytest.mark.parametrize("metodo,rota,corpo", [
    ("post", "/api/squadti/tarefas/T1/mensagem", {"texto": "oi"}),
    ("post", "/api/squadti/tarefas/T1/continuar", {}),
    ("post", "/api/squadti/agentes", CFG_OK),
    ("get", "/api/squadti/agentes", None),
    ("get", "/api/squadti/tarefas/T1/proveniencia", None),
])
@pytest.mark.parametrize("status", [401, 500, 503])
def test_5xx_e_401_viram_503_sem_vazar_o_corpo(admin, api_falsa, metodo, rota, corpo, status):
    api_falsa.resposta = (status, {"erro": {"codigo": "x", "mensagem": "segredo-interno-123 C:/caminho/interno"}})
    r = admin.post(rota, json=corpo) if metodo == "post" else admin.get(rota)
    assert r.status_code == 503 and "segredo-interno-123" not in r.text and "caminho" not in r.text


def test_mensagem_ao_chefe_que_demora_e_cortada_pelo_timeout_e_vira_503(tmp_path, monkeypatch):
    def demora(request):
        raise httpx.ReadTimeout("lento", request=request)
    monkeypatch.setattr(squadti, "TRANSPORTE", httpx.MockTransport(demora))
    from tudoia_painel.autenticacao import PAPEL_OPERADOR
    with montar(tmp_path, [f"TUDOIA_SQUADTI_TOKEN={TOKEN}"], PAPEL_OPERADOR) as c:
        r = c.post("/api/squadti/tarefas/T1/mensagem", json={"texto": "oi"})
        assert r.status_code == 503 and r.json()["erro"]["codigo"] == "indisponivel" and "lento" not in r.text


def test_timeout_maior_so_na_mensagem(operador, api_falsa):
    operador.get("/api/squadti/tarefas")
    operador.post("/api/squadti/tarefas/T1/aprovar", json={})
    operador.post("/api/squadti/tarefas/T1/continuar", json={})
    operador.get("/api/squadti/tarefas/T1/log")
    operador.post("/api/squadti/tarefas/T1/mensagem", json={"texto": "oi"})
    assert api_falsa.timeouts[:-1] == [squadti.TIMEOUT_S] * 4
    assert api_falsa.timeouts[-1] == squadti.TIMEOUT_MENSAGEM_S == 120.0


# ---------------------------------------------------------------- falha fechado e interface
def test_sem_token_as_rotas_v2_respondem_503(tmp_path):
    from tudoia_painel.autenticacao import PAPEL_ADMIN
    with montar(tmp_path, ["TZ=UTC"], PAPEL_ADMIN) as c:
        for r in (c.get("/api/squadti/agentes"), c.get("/api/squadti/tarefas/T1/log"),
                  c.post("/api/squadti/agentes", json=CFG_OK), c.post("/api/squadti/tarefas/T1/mensagem", json={"texto": "x"})):
            assert r.status_code == 503


def test_interface_tem_as_abas_e_o_cockpit(operador):
    js = operador.get("/app/squadti.js").text
    for marca in ("/api/squadti/agentes", "/auditoria", "/proveniencia", "/log?desde=", "/mensagem", "/continuar"):
        assert marca in js, marca
    assert "innerHTML" not in js  # texto vindo da API entra só por textContent

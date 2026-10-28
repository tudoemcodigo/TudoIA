import pytest

from tudoia_painel import caminhos
from tudoia_painel.catalogo import carregar_roteamento
from tudoia_painel.regras import carregar_modulo_regras

R = carregar_modulo_regras()
CODIGO = "```python\n" + "\n".join(f"def f{i}(x):\n    return x + {i}" for i in range(15)) + "\n```"
TRACE = 'Traceback (most recent call last):\n  File "a.py", line 3, in <module>\n    1/0\nZeroDivisionError: division by zero'


@pytest.fixture(scope="module")
def regras():
    return carregar_roteamento(caminhos.raiz() / "config" / "roteamento.yaml")


def u(texto):
    return {"model": "tudoia-auto", "messages": [{"role": "user", "content": texto}]}


CASOS = [
    ("saudacao", u("oi, tudo bem?"), "tudoia-local"),
    ("traducao curta", u("traduza 'bom dia' para inglês"), "tudoia-local"),
    ("fato simples", u("qual a capital da Austrália?"), "tudoia-local"),
    ("resumo curto", u("resuma em uma frase: " + "O projeto avançou bem nesta semana. " * 9), "tudoia-local"),
    ("refatorar codigo", u("refatore este módulo:\n" + CODIGO), "tudoia-nuvem"),
    ("stack trace", u(TRACE + "\npor que isso acontece?"), "tudoia-nuvem"),
    ("comparacao", u("compare a arquitetura de microserviços e monólito passo a passo"), "tudoia-nuvem"),
    ("saudacao + dificil", u("oi! compare a arquitetura de microserviços e monólito passo a passo"), "tudoia-nuvem"),
    ("texto longo", u("palavra " * 320), "tudoia-nuvem"),
    ("nuvem forcada", u("#nuvem oi"), "tudoia-nuvem"),
    ("ferramentas", dict(u("liste os arquivos"), tools=[{"type": "function", "function": {"name": "ls"}}]), "tudoia-codigo"),
    ("system gigante", {"model": "tudoia-auto", "system": "x" * 15000, "messages": [{"role": "user", "content": "oi"}]}, "tudoia-local"),
    ("imagem", {"model": "tudoia-auto", "messages": [{"role": "user", "content": [
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "AAAA"}},
        {"type": "text", "text": "o que tem na imagem?"}]}]}, "tudoia-local"),
    ("muitos turnos curtos", {"model": "tudoia-auto", "messages": [
        m for _ in range(10) for m in ({"role": "user", "content": "ok"}, {"role": "assistant", "content": "certo"})]}, "tudoia-local"),
    ("sql", u("planeje e otimize a consulta SQL abaixo\n```sql\nSELECT * FROM a JOIN b ON a.id = b.id WHERE b.x > 1\n```"), "tudoia-nuvem"),
    ("diff", u("diff --git a/x.py b/x.py\n@@ -1,2 +1,2 @@\n-a = 1\n+a = 2\nrevise"), "tudoia-nuvem"),
    ("agradecimento", u("obrigado!"), "tudoia-local"),
    ("palavra noite nao e oi", u("qual o melhor horário da noite para correr?"), "tudoia-local"),
]


@pytest.mark.parametrize("nome,dados,esperado", CASOS, ids=[c[0] for c in CASOS])
def test_destino(nome, dados, esperado, regras):
    assert R.decidir(dados, regras).grupo == esperado


def test_marcador_local_vence_e_sai_do_texto(regras):
    dados = u("#local refatore este módulo:\n" + CODIGO)
    d = R.decidir(dados, regras)
    assert (d.grupo, d.marcador) == ("tudoia-local", "local")
    assert "#local" not in dados["messages"][0]["content"]


def test_marcador_em_bloco_de_texto_anthropic(regras):
    dados = {"messages": [{"role": "user", "content": [{"type": "text", "text": "#nuvem oi"}]}]}
    assert R.decidir(dados, regras).grupo == "tudoia-nuvem"
    assert dados["messages"][0]["content"][0]["text"].strip() == "oi"


def test_limiar_editado(regras):
    assert R.decidir(u("analise isto"), regras).grupo == "tudoia-local"
    assert R.decidir(u("analise isto"), dict(regras, limiar=2)).grupo == "tudoia-nuvem"


def test_motivos_e_pontos(regras):
    d = R.decidir(u("refatore este módulo:\n" + CODIGO), regras)
    assert d.pontos == 4 and "codigo" in d.motivos and any(m.startswith("palavras") for m in d.motivos)


def test_nuvem_esgotada_vai_para_local(regras):
    membros = {"tudoia-nuvem": ["nim/a", "nim/b"], "tudoia-codigo": ["nim/c"]}
    d = R.decidir(u("refatore este módulo:\n" + CODIGO), regras, esgotados={"nim/a", "nim/b"}, membros=membros)
    assert d.grupo == "tudoia-local" and "provedores esgotados" in d.motivos


def test_codigo_esgotado_vai_para_local_agente(regras):
    membros = {"tudoia-nuvem": ["nim/a"], "tudoia-codigo": ["nim/c"]}
    dados = dict(u("ls"), tools=[{"name": "ls"}])
    assert R.decidir(dados, regras, esgotados={"nim/c"}, membros=membros).grupo == "tudoia-local-agente"


def test_esgotado_parcial_nao_muda(regras):
    membros = {"tudoia-nuvem": ["nim/a", "nim/b"]}
    assert R.decidir(u(TRACE + "\npor que?"), regras, esgotados={"nim/a"}, membros=membros).grupo == "tudoia-nuvem"


def test_sem_mensagens_nao_quebra(regras):
    assert R.decidir({"model": "tudoia-auto"}, regras).grupo == "tudoia-local"


def test_bloco_de_texto_nulo_nao_quebra(regras):
    dados = {"messages": [{"role": "user", "content": [{"type": "text", "text": None}, {"type": "text", "text": "oi"}]}]}
    assert R.decidir(dados, regras).grupo == "tudoia-local"


def test_limites_json_antigo_e_ignorado():
    from datetime import datetime, timedelta, timezone
    agora = datetime(2026, 10, 19, 23, 0, tzinfo=timezone.utc)
    velho = {"ts": (agora - timedelta(minutes=5)).isoformat(), "esgotados": ["nim/a"], "membros": {"tudoia-nuvem": ["nim/a"]}}
    novo = dict(velho, ts=(agora - timedelta(seconds=30)).isoformat())
    assert R.limites_validos(velho, agora) == (set(), None)
    assert R.limites_validos(novo, agora) == ({"nim/a"}, {"tudoia-nuvem": ["nim/a"]})
    assert R.limites_validos({"esgotados": ["x"]}, agora) == (set(), None)


GRUPOS = {"tudoia-local", "tudoia-nuvem", "tudoia-codigo", "tudoia-visao", "tudoia-max"}
IMG = {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}


def com_imagem(texto="o que é isto?", **extra):
    return dict({"model": "tudoia-auto", "messages": [{"role": "user", "content": [IMG, {"type": "text", "text": texto}]}]}, **extra)


def test_max_sem_grupo_segue_regra_normal(regras):
    dados = u("#max oi")
    d = R.decidir(dados, regras, grupos_existentes={"tudoia-local", "tudoia-nuvem"})
    assert d.grupo != "tudoia-max" and d.grupo == "tudoia-local"
    assert "#max sem grupo" in d.motivos
    assert dados["messages"][0]["content"] == "oi"


def test_max_com_grupo(regras):
    d = R.decidir(u("#max oi"), regras, grupos_existentes=GRUPOS)
    assert d.grupo == "tudoia-max" and d.marcador == "max"


def test_max_ignorado_se_grupos_desconhecidos(regras):
    d = R.decidir(u("#max oi"), regras)
    assert d.grupo != "tudoia-max" and "#max sem grupo" in d.motivos


def test_tem_imagem():
    assert R.tem_imagem(com_imagem())
    assert R.tem_imagem({"messages": [{"role": "user", "content": [{"type": "image", "source": {}}]}]})
    assert not R.tem_imagem(u("oi"))


def test_imagem_vai_para_visao(regras):
    d = R.decidir(com_imagem(), regras, grupos_existentes=GRUPOS)
    assert d.grupo == "tudoia-visao" and "imagem" in d.motivos


def test_imagem_sem_grupo_visao_segue_normal(regras):
    d = R.decidir(com_imagem(), regras, grupos_existentes={"tudoia-local", "tudoia-nuvem"})
    assert d.grupo == "tudoia-local" and "imagem sem grupo visao" in d.motivos
    d2 = R.decidir(com_imagem(), regras)
    assert d2.grupo == "tudoia-local" and "imagem sem grupo visao" in d2.motivos


def test_tools_com_imagem_fica_no_codigo(regras):
    # sessão de agente não vai para a visão (membros podem não aceitar ferramentas); o hook troca a imagem por texto
    dados = com_imagem(tools=[{"type": "function", "function": {"name": "ls"}}])
    d = R.decidir(dados, regras, grupos_existentes=GRUPOS)
    assert d.grupo == "tudoia-codigo" and "imagem com ferramentas" in d.motivos


def test_screenshot_em_tool_result_nao_desvia_o_agente(regras):
    dados = {"model": "tudoia-auto", "tools": [{"name": "screenshot"}], "messages": [
        {"role": "user", "content": "abra a página"},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "screenshot", "input": {}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": [IMG]}]}]}
    assert R.decidir(dados, regras, grupos_existentes=GRUPOS).grupo == "tudoia-codigo"
    assert R.decidir(com_imagem("#max veja"), regras, grupos_existentes=GRUPOS).grupo == "tudoia-max"


def test_local_e_nuvem_vencem_imagem(regras):
    assert R.decidir(com_imagem("#local oi"), regras, grupos_existentes=GRUPOS).grupo == "tudoia-local"
    assert R.decidir(com_imagem("#nuvem oi"), regras, grupos_existentes=GRUPOS).grupo == "tudoia-nuvem"


def test_decidir_aceita_vetor_e_exemplos(regras):
    assert R.decidir(u("oi"), regras, vetor=[0.0], exemplos={}).grupo == "tudoia-local"


# ── classificador semântico (T6) ─────────────────────────────────────────────
EX = [([1.0, 0.0], "nuvem")] * 5 + [([0.0, 1.0], "local")] * 5


def test_votar_knn_maioria_e_margem():
    ex = [([1.0, 0.0], "nuvem"), ([0.9, 0.1], "nuvem"), ([0.8, 0.2], "nuvem"), ([0.0, 1.0], "local"),
          ([0.1, 0.9], "local"), ([0.2, 0.8], "local"), ([0.3, 0.7], "local")]
    assert R.votar_knn([1.0, 0.0], ex, k=3) == ("nuvem", 3)
    assert R.votar_knn([1.0, 0.0], ex, k=5) == ("nuvem", 1)   # 3 nuvem x 2 local
    assert R.votar_knn([0.0, 1.0], ex, k=3) == ("local", 3)


def test_votar_knn_vazio():
    assert R.votar_knn([1.0, 0.0], []) == (None, 0)


def test_peso_semantico_margem_pequena_nao_pesa(regras):
    assert R.peso_semantico("nuvem", 1, regras) == (0, None)
    assert R.peso_semantico(None, 0, regras) == (0, None)
    assert R.peso_semantico("nuvem", 2, regras) == (3, "semântico: nuvem")
    assert R.peso_semantico("local", 5, regras) == (-2, "semântico: local")
    assert R.peso_semantico("local", 5, {"pesos": {"semantico_local": -1}}) == (-1, "semântico: local")


def test_decidir_curto_dificil_vai_para_nuvem_com_semantico(regras):
    dados = u("mostre que raiz de 2 é irracional")
    sem = R.decidir(u("mostre que raiz de 2 é irracional"), regras)
    assert sem.grupo == R.LOCAL
    d = R.decidir(dados, regras, vetor=[1.0, 0.0], exemplos=EX)
    assert d.grupo == R.NUVEM and "semântico: nuvem" in d.motivos


def test_decidir_sem_vetor_e_so_heuristica(regras):
    d = R.decidir(u("mostre que raiz de 2 é irracional"), regras, vetor=None, exemplos=EX)
    assert d.grupo == R.LOCAL and not any("semântico" in m for m in d.motivos)
    d = R.decidir(u("mostre que raiz de 2 é irracional"), regras, vetor=[1.0, 0.0], exemplos=None)
    assert d.grupo == R.LOCAL and not any("semântico" in m for m in d.motivos)


def test_semantico_local_desconta_e_nao_vale_com_marcador_imagem_tools(regras):
    d = R.decidir(u("explique isso"), regras, vetor=[0.0, 1.0], exemplos=EX)
    assert d.pontos == -2 and "semântico: local" in d.motivos
    d = R.decidir(u("#nuvem oi"), regras, vetor=[0.0, 1.0], exemplos=EX)
    assert d.motivos == ["marcador #nuvem"]
    d = R.decidir(dict(u("oi"), tools=[{"x": 1}]), regras, vetor=[1.0, 0.0], exemplos=EX)
    assert d.grupo == R.CODIGO and d.motivos == ["ferramentas"]


def test_precisa_pontuar_nao_altera_os_dados(regras):
    dados = u("#local oi")
    assert R.precisa_pontuar(dados) is False
    assert dados["messages"][-1]["content"] == "#local oi"
    assert R.precisa_pontuar(u("#nuvem oi")) is False
    assert R.precisa_pontuar(dict(u("oi"), tools=[{"x": 1}])) is False
    assert R.precisa_pontuar(u("oi")) is True
    assert R.precisa_pontuar(u("#max oi"), {R.LOCAL}) is True          # #max sem grupo segue a regra normal
    assert R.precisa_pontuar(u("#max oi"), {R.MAXIMO}) is False
    assert R.precisa_pontuar(com_imagem(), {R.VISAO}) is False
    assert R.precisa_pontuar(com_imagem(), set()) is True


def test_carregar_exemplos_junta_e_deduplica():
    dados = {"local": ["Oi, tudo bem?", "quanto é 2+2?"], "nuvem": ["mostre a prova"],
             "aprendidos": {"nuvem": ["OI tudo bem", "outra coisa"], "local": ["mostre a prova!"]}}
    r = R.carregar_exemplos(dados)
    assert ("Oi, tudo bem?", "local") in r and ("mostre a prova", "nuvem") in r and ("outra coisa", "nuvem") in r
    assert len(r) == 4 and R.carregar_exemplos({}) == []


def test_imagem_so_na_ultima_mensagem_do_usuario(regras):
    tools = [{"type": "function", "function": {"name": "ls"}}]
    antiga = {"model": "tudoia-auto", "tools": tools, "messages": [
        {"role": "user", "content": [IMG, {"type": "text", "text": "veja"}]},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": "agora rode os testes"}]}
    assert not R.tem_imagem(antiga)
    assert R.decidir(antiga, regras, grupos_existentes=GRUPOS).grupo == "tudoia-codigo"
    atual = {"model": "tudoia-auto", "tools": tools, "messages": [
        {"role": "user", "content": "oi"}, {"role": "assistant", "content": "ok"},
        {"role": "user", "content": [{"type": "image", "source": {}}, {"type": "text", "text": "e isto?"}]}]}
    assert R.tem_imagem(atual)
    assert R.decidir(atual, regras, grupos_existentes=GRUPOS).grupo == "tudoia-codigo"   # tools vence imagem
    del atual["tools"]
    assert R.decidir(atual, regras, grupos_existentes=GRUPOS).grupo == "tudoia-visao"


def test_quarentena_valida_ignora_vencidos():
    from datetime import datetime, timedelta, timezone
    agora = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)
    dados = {"ts": agora.isoformat(), "modelos": {
        "nim/passado": {"motivo": "x", "ate": (agora - timedelta(minutes=1)).isoformat()},
        "nim/futuro": {"motivo": "x", "ate": (agora + timedelta(hours=1)).isoformat()},
    }}
    assert R.quarentena_valida(dados, agora) == {"nim/futuro"}


def test_quarentena_valida_ignora_lixo():
    from datetime import datetime, timezone
    agora = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)
    assert R.quarentena_valida({}, agora) == set()
    assert R.quarentena_valida({"modelos": {"x": {}}}, agora) == set()
    assert R.quarentena_valida({"modelos": {"x": {"ate": "lixo"}}}, agora) == set()
    assert R.quarentena_valida({"modelos": {"x": {"ate": None}, "y": "z"}}, agora) == set()
    assert R.quarentena_valida({"modelos": []}, agora) == set()
    assert R.quarentena_valida(None, agora) == set()

# ── M1: entradas patológicas nunca derrubam o roteamento ──────────────────────────

class _Ruim:
    def __str__(self):
        raise RuntimeError("str quebrado")


def test_quarentena_valida_entradas_patologicas():
    from datetime import datetime, timedelta, timezone
    agora = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)
    futuro = (agora + timedelta(hours=1)).isoformat()
    assert R.quarentena_valida({"modelos": {"x": {"ate": _Ruim()}, "y": {"ate": futuro}}}, agora) == {"y"}
    assert R.quarentena_valida({"modelos": {"x": {"ate": "2026-10-22T13:00:00"}}}, agora) == set()   # sem fuso
    assert R.quarentena_valida({"modelos": {"x": ["ate"], "y": 5}}, agora) == set()
    assert R.quarentena_valida({"modelos": {("tupla",): {"ate": futuro}}}, agora) == set()   # chave não-texto


def test_limites_validos_entradas_patologicas():
    from datetime import datetime, timezone
    agora = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)
    ts = agora.isoformat()
    assert R.limites_validos({"ts": ts, "esgotados": 5}, agora) == (set(), None)
    assert R.limites_validos({"ts": ts, "esgotados": [["x"], "nim/a", 3]}, agora) == ({"nim/a"}, None)
    assert R.limites_validos({"ts": ts, "esgotados": "nim/a"}, agora) == (set(), None)
    assert R.limites_validos({"ts": ts, "membros": ["x"]}, agora) == (set(), None)
    assert R.limites_validos({"ts": ts, "membros": {"tudoia-nuvem": 5, "tudoia-codigo": ["nim/c", 1]}}, agora) == (
        set(), {"tudoia-codigo": ["nim/c"]})
    assert R.limites_validos([1, 2], agora) == (set(), None)
    assert R.limites_validos("lixo", agora) == (set(), None)
    assert R.limites_validos({"ts": _Ruim()}, agora) == (set(), None)


# ── M7: quarentena do verificador + decidir (efeito de grupo) ─────────────────────

def _quarentena(agora, nomes):
    from datetime import timedelta
    return {"ts": agora.isoformat(), "modelos": {n: {"motivo": "404", "ate": (agora + timedelta(minutes=20)).isoformat()}
                                                 for n in nomes}}


def test_quarentena_de_todos_os_membros_manda_para_o_local(regras):
    from datetime import datetime, timezone
    agora = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)
    membros = {"tudoia-nuvem": ["nim/a", "nim/b"], "tudoia-codigo": ["nim/c"]}
    esgotados = R.quarentena_valida(_quarentena(agora, ["nim/a", "nim/b"]), agora)
    d = R.decidir(u("refatore este módulo:\n" + CODIGO), regras, esgotados=esgotados, membros=membros)
    assert d.grupo == "tudoia-local" and "provedores esgotados" in d.motivos


def test_quarentena_de_um_so_membro_continua_no_grupo(regras):
    from datetime import datetime, timezone
    agora = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)
    membros = {"tudoia-nuvem": ["nim/a", "nim/b"], "tudoia-codigo": ["nim/c"]}
    esgotados = R.quarentena_valida(_quarentena(agora, ["nim/a"]), agora)
    d = R.decidir(u("refatore este módulo:\n" + CODIGO), regras, esgotados=esgotados, membros=membros)
    assert d.grupo == "tudoia-nuvem" and "provedores esgotados" not in d.motivos


def test_gpu_ocupada_desvia_local_para_nuvem_salvo_marcador_local(regras):
    from datetime import datetime, timedelta, timezone
    agora = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)
    ativo = {"dono": "video:123", "expira_em": (agora + timedelta(minutes=30)).isoformat().replace("+00:00", "Z")}
    vencido = {"dono": "video:123", "expira_em": (agora - timedelta(minutes=1)).isoformat()}
    assert R.gpu_ocupada_valida(ativo, agora) is True
    assert R.gpu_ocupada_valida(vencido, agora) is False
    assert R.gpu_ocupada_valida({}, agora) is False
    assert R.gpu_ocupada_valida(None, agora) is False
    # Pedido trivial que iria para tudoia-local vai para tudoia-nuvem quando a GPU está ocupada
    d = R.decidir(u("oi, tudo bem?"), regras, gpu_ocupada=True)
    assert d.grupo == "tudoia-nuvem" and "gpu ocupada" in d.motivos
    # Marcador explícito #local continua vencendo
    d_forcado = R.decidir(u("#local oi, tudo bem?"), regras, gpu_ocupada=True)
    assert d_forcado.grupo == "tudoia-local" and d_forcado.marcador == "local"
    # Se a GPU está ocupada, provedores de nuvem esgotados NÃO desviam para o Ollama local
    membros = {"tudoia-nuvem": ["nim/a"], "tudoia-codigo": ["nim/c"]}
    d_esg = R.decidir(u("refatore este módulo:\n" + CODIGO), regras, esgotados={"nim/a"}, membros=membros, gpu_ocupada=True)
    assert d_esg.grupo == "tudoia-nuvem" and "provedores esgotados" not in d_esg.motivos


def test_tem_imagem_em_tool_result():
    payload = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "call_123",
                        "content": [{"type": "image", "source": {"data": "abc"}}]
                    }
                ]
            }
        ]
    }
    assert R.tem_imagem(payload)
    assert R.tem_qualquer_imagem(payload)


def test_sanitizar_imagens_historico():
    payload = {
        "messages": [
            {"role": "user", "content": [{"type": "image", "source": {}}]},
            {"role": "assistant", "content": "imagem recebida"},
            {"role": "user", "content": "agora faca o codigo"}
        ]
    }
    R.sanitizar_imagens_historico(payload)
    # A mensagem antiga teve a imagem substituida por texto
    assert payload["messages"][0]["content"][0]["type"] == "text"
    assert "Imagem anterior" in payload["messages"][0]["content"][0]["text"]
    # A mensagem atual nao foi alterada
    assert payload["messages"][2]["content"] == "agora faca o codigo"


def test_remover_cache_control():
    payload = {
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": "oi", "cache_control": {"type": "ephemeral"}}]}
        ],
        "tools": [
            {"type": "function", "cache_control": {"type": "ephemeral"}}
        ]
    }
    R.remover_cache_control(payload)
    assert "cache_control" not in payload["messages"][0]["content"][0]
    assert "cache_control" not in payload["tools"][0]


def test_remover_cache_control_tambem_no_system():
    payload = {"system": [{"type": "text", "text": "voce e o Claude Code", "cache_control": {"type": "ephemeral"}}, "lixo"],
               "messages": []}
    R.remover_cache_control(payload)
    assert payload["system"][0] == {"type": "text", "text": "voce e o Claude Code"}
    texto = {"system": "só texto", "messages": None}
    R.remover_cache_control(texto)   # system string e messages nulo não quebram
    assert texto["system"] == "só texto"


def test_destinos_com_cache_so_pago_sem_fallback():
    cfg = {"model_list": [
        {"model_name": "tudoia-max", "model_info": {"plano": "PAID"}},
        {"model_name": "claude-sonnet-5-5", "model_info": {"plano": "PAID"}},
        {"model_name": "misto", "model_info": {"plano": "PAID"}}, {"model_name": "misto", "model_info": {"plano": "FREE"}},
        {"model_name": "gemini/gemini-3.8-flash", "model_info": {"plano": "FREE"}},
        {"model_name": "sem-info"}, "lixo"]}
    assert R.destinos_com_cache(cfg, {"tudoia-max": ["tudoia-nuvem"]}) == {"claude-sonnet-5-5"}
    assert R.destinos_com_cache(None, None) == set()


def test_sanitizar_tira_tambem_a_imagem_atual_quando_pedido():
    payload = {"messages": [{"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "t1", "content": [IMG, {"type": "text", "text": "ok"}]}]}]}
    R.sanitizar_imagens_historico(payload)   # padrão: a mensagem atual fica como está
    assert R.tem_imagem(payload)
    R.sanitizar_imagens_historico(payload, manter_atual=False)
    assert not R.tem_qualquer_imagem(payload)
    assert payload["messages"][0]["content"][0]["content"][1] == {"type": "text", "text": "ok"}


@pytest.mark.parametrize("texto", ["qual a previsão do tempo amanhã?", "aprove o pedido de férias", "imprevisto no caminho",
                                   "adicione o provedor groq"])
def test_palavra_dificil_nao_casa_no_meio_da_palavra(texto, regras):
    d = R.decidir(u(texto), regras)
    assert not any(m.startswith("palavras") for m in d.motivos), d.motivos


@pytest.mark.parametrize("texto,termo", [("revisar o contrato", "revis"), ("faça a revisão", "revis"),
                                         ("REVISÃO geral", "revis"), ("prove que é par", "prove"),
                                         ("vale o trade-off?", "trade-off"), ("por que caiu?", "por que")])
def test_palavra_dificil_ainda_e_prefixo(texto, termo, regras):
    d = R.decidir(u(texto), regras)
    assert any(m.startswith("palavras") and termo in m for m in d.motivos), d.motivos



def test_knn_com_vetores_de_outro_modelo_nao_vota():
    """Cache de exemplos de outro modelo de embedding (outra dimensão): antes o zip cortava e o voto saía errado."""
    exemplos = [([1.0, 0.0, 0.0], "nuvem"), ([0.0, 1.0, 0.0], "local")]
    assert R.votar_knn([1.0, 0.0], exemplos) == (None, 0)
    assert R.votar_knn([1.0, 0.0, 0.0], exemplos, k=1)[0] == "nuvem"

"""Perfis de destino (tudoia-local-estrito, tudoia-hibrido): regras puras, config.yaml gerado e hook do LiteLLM.

Foco: o perfil sem nuvem nunca manda nada à nuvem (estouro de contexto, Ollama fora, marcador, config torta) e o
híbrido só usa nuvem gratuita. Tudo offline: nada aqui chama Ollama, LiteLLM, painel ou rede.
"""
import asyncio
import copy
import importlib.util
import json
import os
import sys
import time
import types
from pathlib import Path

import pytest
import yaml

from tudoia_painel import caminhos
from tudoia_painel.catalogo import carregar_catalogo, carregar_roteamento
from tudoia_painel.gerador import gerar_config, grupos_dos_perfis
from tudoia_painel.regras import carregar_modulo_regras

R = carregar_modulo_regras()
FIX = Path(__file__).parent / "fixtures"
LIT = caminhos.raiz() / "runtime/litellm"
ESTRITO, ESTRITO_AG, HIBRIDO = "tudoia-local-estrito", "tudoia-local-estrito-agente", "tudoia-hibrido"
FERRAMENTAS = [{"type": "function", "function": {"name": "ls"}}]
IMAGEM = {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "AAAA"}}


def perfis_reais() -> dict:
    return carregar_roteamento(caminhos.raiz() / "config" / "roteamento.yaml")["perfis"]


def rot_com_perfis(**extra) -> dict:
    return {
        "limiar": 3, "pesos": {}, "perfis": perfis_reais(),
        "ordem": {   # local/ explícito: o gerador não consulta o Ollama para descobrir o modelo
            "tudoia-local": ["local/tudoia-chat"], "tudoia-local-agente": ["local/tudoia-agente"],
            "tudoia-nuvem": ["nim/nemotron-3-super", "nim/glm-5.3-flash"], "tudoia-codigo": ["nim/glm-5.3-flash"],
            "tudoia-max": ["claude-sonnet-5-5"], "tudoia-visao": ["nim/visao-vl"], **extra,
        },
    }


def cfg_de(env=None, **extra) -> dict:
    env = {"NVIDIA_NIM_API_KEY": "x"} if env is None else env
    return gerar_config(carregar_catalogo(FIX / "catalogo-mini.yaml"), env, rot_com_perfis(**extra))


@pytest.fixture(scope="module")
def cfg():
    return cfg_de()


@pytest.fixture(scope="module")
def grupos(cfg):
    return R.info_grupos(cfg)


@pytest.fixture(scope="module")
def grupos_sem_nuvem():
    return R.info_grupos(cfg_de(env={}))


def u(texto, **extra):
    return {"model": "x", "messages": [{"role": "user", "content": texto}], **extra}


def estrito(dados, grupos, **kw):
    return R.decidir_perfil(dados, "local-estrito", perfis_reais()["local-estrito"], grupos, **kw)


def hibrido(dados, grupos, **kw):
    return R.decidir_perfil(dados, "hibrido", perfis_reais()["hibrido"], grupos, **kw)


def texto_usuario(dados):
    return R.ultima_do_usuario(dados)


# ── validação do YAML ────────────────────────────────────────────────────────────────────────────────────────────
def test_roteamento_real_e_valido_e_tem_os_dois_perfis():
    perfis = perfis_reais()
    assert {p["modelo"] for p in perfis.values()} == {ESTRITO, HIBRIDO}
    assert perfis["local-estrito"]["nuvem"] is False and "nuvem_categorias" not in perfis["local-estrito"]


def _mutar(f):
    rot = copy.deepcopy(yaml.safe_load((caminhos.raiz() / "config" / "roteamento.yaml").read_text(encoding="utf-8")))
    f(rot["perfis"])
    return rot


INVALIDOS = {
    "perfis nao e mapa": lambda p: p.__setitem__("x", "texto"),
    "sem modelo": lambda p: p["hibrido"].pop("modelo"),
    "modelo reservado": lambda p: p["hibrido"].__setitem__("modelo", "tudoia-max"),
    "modelo tudoia-auto": lambda p: p["hibrido"].__setitem__("modelo", "tudoia-auto"),
    "modelo duplicado": lambda p: p["hibrido"].__setitem__("modelo", ESTRITO),
    "nuvem nao booleana": lambda p: p["hibrido"].__setitem__("nuvem", "sim"),
    "categoria desconhecida": lambda p: p["hibrido"]["categorias"].__setitem__("magia", "tudoia-local"),
    "grupo vazio": lambda p: p["hibrido"]["categorias"].__setitem__("chat", ""),
    "max como destino": lambda p: p["hibrido"]["nuvem_categorias"].__setitem__("chat", "tudoia-max"),
    "sem chat": lambda p: p["hibrido"]["categorias"].pop("chat"),
    "estrito com nuvem_categorias": lambda p: p["local-estrito"].__setitem__("nuvem_categorias", {"chat": "tudoia-nuvem"}),
    "marcador max": lambda p: p["hibrido"].__setitem__("marcadores", ["local", "max"]),
    "marcador nao e lista": lambda p: p["hibrido"].__setitem__("marcadores", "local"),
    "marcador nuvem sem destino": lambda p: p["hibrido"].pop("nuvem_categorias"),
}


@pytest.mark.parametrize("nome", list(INVALIDOS))
def test_config_de_perfis_invalida_falha_fechado(nome):
    rot = _mutar(INVALIDOS[nome])
    with pytest.raises(ValueError):
        R.validar_regras(rot)


def test_sem_perfis_o_arquivo_continua_valido():
    rot = _mutar(lambda p: None)
    del rot["perfis"]
    R.validar_regras(rot)
    assert R.perfil_do_modelo(rot, ESTRITO) is None


def test_perfil_do_modelo(cfg):
    rot = {"perfis": perfis_reais()}
    assert R.perfil_do_modelo(rot, ESTRITO) == "local-estrito"
    assert R.perfil_do_modelo(rot, HIBRIDO) == "hibrido"
    for desconhecido in ("tudoia-auto", "tudoia-local", "tudoia-max", "tudoia-hibrido ", "", None, 3, ["x"]):
        assert R.perfil_do_modelo(rot, desconhecido) is None
    assert R.perfil_do_modelo({}, ESTRITO) is None


# ── config.yaml gerado ───────────────────────────────────────────────────────────────────────────────────────────
def test_gerador_cria_grupos_locais_sem_saida(cfg, grupos):
    for g in (ESTRITO, ESTRITO_AG):
        assert grupos[g]["destino"] == "local" and grupos[g]["saida"] is False
        assert grupos[g]["contexto"] == 30000   # enable_pre_call_checks pula o membro: pedido grande falha, não vaza
    assert grupos[HIBRIDO]["destino"] == "local"
    rs = cfg["router_settings"]
    for chave in ("fallbacks", "context_window_fallbacks"):
        origens = {o for regra in rs[chave] for o in regra}
        assert not origens & {ESTRITO, ESTRITO_AG, HIBRIDO}
    assert "default_fallbacks" not in rs and "default_fallbacks" not in cfg["litellm_settings"]
    assert rs["enable_pre_call_checks"] is True


def test_grupo_estrito_usa_o_modelo_local_certo(cfg):
    (chat,) = [m for m in cfg["model_list"] if m["model_name"] == ESTRITO]
    (ag,) = [m for m in cfg["model_list"] if m["model_name"] == ESTRITO_AG]
    assert chat["litellm_params"]["model"] == "ollama_chat/tudoia-chat"
    assert ag["litellm_params"]["model"] == "ollama_chat/tudoia-agente"


def test_membro_de_nuvem_no_grupo_estrito_e_ignorado():
    # alguém põe um modelo da nuvem na `ordem` do grupo estrito: o gerador só aceita membro local
    cfg = cfg_de(**{ESTRITO: ["nim/glm-5.3-flash", "local/tudoia-chat"]})
    membros = [m for m in cfg["model_list"] if m["model_name"] == ESTRITO]
    assert [m["model_info"]["plano"] for m in membros] == ["LOCAL"]


def test_pago_nunca_em_grupo_de_perfil(cfg, grupos):
    alvos = {g for p in perfis_reais().values() for mapa in (p["categorias"], p.get("nuvem_categorias", {})) for g in mapa.values()}
    assert alvos <= set(grupos) | {"tudoia-visao"}
    for g in alvos & set(grupos):
        assert grupos[g]["destino"] in ("local", "nuvem"), g
    for m in cfg["model_list"]:
        if m["model_name"] in alvos | {HIBRIDO}:
            assert m["model_info"]["plano"] != "PAID"
    cfg_pago = cfg_de(env={"NVIDIA_NIM_API_KEY": "x", "ANTHROPIC_API_KEY": "y"})
    assert R.info_grupos(cfg_pago)["tudoia-max"]["destino"] == "pago"
    assert all(R.info_grupos(cfg_pago)[g]["destino"] != "pago" for g in alvos & set(R.info_grupos(cfg_pago)))


def test_grupo_local_que_serve_a_duas_familias_e_erro():
    perfis = {"p": {"modelo": "tudoia-p", "nuvem": False, "categorias": {"chat": "g", "agente": "g"}}}
    with pytest.raises(ValueError, match="modelos locais diferentes"):
        grupos_dos_perfis(perfis)
    assert grupos_dos_perfis(None) == ({}, [])


def test_sem_perfis_o_config_nao_muda():
    rot = rot_com_perfis()
    sem = {k: v for k, v in rot.items() if k != "perfis"}
    cat = carregar_catalogo(FIX / "catalogo-mini.yaml")
    base = gerar_config(cat, {"NVIDIA_NIM_API_KEY": "x"}, sem)
    nomes = {m["model_name"] for m in base["model_list"]}
    assert not nomes & {ESTRITO, ESTRITO_AG, HIBRIDO}
    assert base["router_settings"]["context_window_fallbacks"] == [{"tudoia-local": ["tudoia-nuvem"]}]


def test_config_real_gera_perfis_utilizaveis():
    # roteamento.yaml e catálogo reais, sem chaves: grupos de perfil existem e o estrito passa nas verificações
    cfg = gerar_config(carregar_catalogo(caminhos.raiz() / "config" / "catalogo-modelos.yaml"), {},
                       carregar_roteamento(caminhos.raiz() / "config" / "roteamento.yaml"))
    d = estrito(u("oi"), R.info_grupos(cfg))
    assert d.recusa is None and d.grupo == ESTRITO and d.destino == "local" and d.fechado is True


def test_info_grupos_deteccao_de_saida():
    base = {"model_list": [{"model_name": "a", "model_info": {"plano": "LOCAL"}},
                           {"model_name": "b", "model_info": {"plano": "LOCAL"}}], "router_settings": {}}
    assert R.info_grupos(base)["a"]["saida"] is False
    for rs, ls in (({"fallbacks": [{"a": ["b"]}]}, {}), ({"context_window_fallbacks": [{"a": ["n"]}]}, {}),
                   ({"content_policy_fallbacks": [{"a": ["n"]}]}, {}), ({}, {"fallbacks": [{"a": ["b"]}]}),
                   ({"default_fallbacks": ["n"]}, {}), ({}, {"default_fallbacks": ["n"]}), ({"fallbacks": [{"*": ["n"]}]}, {})):
        cfg = dict(base, router_settings=rs, litellm_settings=ls)
        assert R.info_grupos(cfg)["a"]["saida"] is True, (rs, ls)
    assert R.info_grupos(dict(base, router_settings={"fallbacks": [{"zzz": []}]}))["a"]["saida"] is False
    assert R.info_grupos(None) is None and R.info_grupos("lixo") is None
    misto = {"model_list": [{"model_name": "m", "model_info": {"plano": "LOCAL"}}, {"model_name": "m", "model_info": {"plano": "FREE"}}]}
    assert R.info_grupos(misto)["m"]["destino"] == "misto"


# ── local-estrito ────────────────────────────────────────────────────────────────────────────────────────────────
def test_estrito_caminho_feliz(grupos):
    d = estrito(u("explique o que é um índice de banco"), grupos)
    assert (d.grupo, d.categoria, d.destino, d.fechado, d.recusa, d.perfil) == (ESTRITO, "chat", "local", True, None, "local-estrito")


def test_estrito_categorias(grupos):
    assert estrito(u("liste", tools=FERRAMENTAS), grupos).grupo == ESTRITO_AG
    assert estrito(u("```python\nx = 1\n```"), grupos).grupo == ESTRITO_AG
    assert estrito(u("#codigo oi"), grupos).grupo == ESTRITO_AG
    assert estrito(u("#raciocinio oi"), grupos).grupo == ESTRITO
    assert estrito(u("#rapido oi"), grupos).grupo == ESTRITO


def test_estrito_estouro_de_contexto_nao_vai_a_nuvem(grupos):
    # 200k caracteres (~50k tokens) > 30k do local. O perfil continua no grupo local, sem fallback e com
    # disable_fallbacks: o router pula o membro (enable_pre_call_checks) e devolve erro, não reenvia à nuvem.
    d = estrito(u("palavra " * 25000), grupos)
    assert d.recusa is None and d.grupo == ESTRITO and d.fechado is True and "excede contexto local" not in d.motivos
    assert grupos[ESTRITO]["saida"] is False and R.estimar_tokens(u("palavra " * 25000)) > grupos[ESTRITO]["contexto"]


def test_estrito_ollama_fora_falha_alto(grupos):
    for dados in (u("oi"), u("x", tools=FERRAMENTAS), u("#local oi")):
        d = estrito(dados, grupos, ollama_ok=False)
        assert d.recusa is not None and d.recusa[0] == 503 and "Nada foi enviado" in d.recusa[1]
        assert d.fechado is True


def test_estrito_gpu_ocupada_nao_desvia(grupos):
    d = estrito(u("oi"), grupos, gpu_ocupada=True)
    assert d.grupo == ESTRITO and d.recusa is None


def test_estrito_ignora_marcadores_de_nuvem_e_nao_os_apaga(grupos):
    for marcador in ("#nuvem", "#max", "#NUVEM"):
        dados = u(f"{marcador} oi")
        d = estrito(dados, grupos)
        assert d.grupo == ESTRITO and d.destino == "local" and d.marcador is None
        assert texto_usuario(dados) == f"{marcador} oi"


def test_estrito_marcador_local_sai_do_texto(grupos):
    dados = u("#LOCAL oi")
    d = estrito(dados, grupos)
    assert d.marcador == "local" and texto_usuario(dados) == "oi" and d.grupo == ESTRITO


def test_marcadores_malformados_nao_valem(grupos):
    for texto in ("x#local oi", "#locais oi", "#local# oi".replace("# oi", "x oi"), "a #codigos oi"):
        dados = u(texto)
        d = hibrido(dados, grupos)
        assert d.marcador is None and d.categoria == "chat" and d.grupo == "tudoia-local", texto
        assert texto_usuario(dados) == texto


def test_estrito_imagem_nao_tem_destino(grupos):
    dados = {"model": "x", "messages": [{"role": "user", "content": [IMAGEM, {"type": "text", "text": "o que é?"}]}]}
    d = estrito(dados, grupos)
    assert d.recusa is not None and d.recusa[0] == 400 and "visao" in d.recusa[1]


def test_estrito_marcador_em_bloco_de_texto(grupos):
    dados = {"model": "x", "messages": [{"role": "user", "content": [{"type": "text", "text": "#local #codigo faça"}]}]}
    d = estrito(dados, grupos)
    assert d.grupo == ESTRITO_AG and dados["messages"][0]["content"][0]["text"] == "faça"


def test_categorias_duplicadas_e_em_conflito(grupos):
    dados = u("#chat #codigo #chat oi")
    d = estrito(dados, grupos)
    assert d.categoria == "chat" and any("conflito" in m for m in d.motivos)
    assert texto_usuario(dados) == "oi"   # todos os marcadores saem, nenhum chega ao modelo
    dados = u("#codigo #codigo oi")
    d = estrito(dados, grupos)
    assert d.categoria == "codigo" and not any("conflito" in m for m in d.motivos)


def test_estrito_so_olha_a_ultima_mensagem_do_usuario(grupos):
    dados = {"model": "x", "messages": [{"role": "user", "content": "#codigo antigo"}, {"role": "assistant", "content": "ok"},
                                        {"role": "user", "content": "oi"}]}
    d = estrito(dados, grupos)
    assert d.categoria == "chat" and dados["messages"][0]["content"] == "#codigo antigo"


@pytest.mark.parametrize("mutar,trecho", [
    (lambda c: c["router_settings"]["fallbacks"].append({ESTRITO: ["tudoia-nuvem"]}), ESTRITO),
    (lambda c: c["router_settings"]["context_window_fallbacks"].append({ESTRITO_AG: ["tudoia-codigo"]}), ESTRITO_AG),
    (lambda c: c["router_settings"].__setitem__("default_fallbacks", ["tudoia-nuvem"]), ESTRITO),
    (lambda c: c["litellm_settings"].__setitem__("default_fallbacks", ["tudoia-nuvem"]), ESTRITO),
    (lambda c: c["router_settings"]["fallbacks"].append({"*": ["tudoia-nuvem"]}), ESTRITO),
    (lambda c: next(m for m in c["model_list"] if m["model_name"] == ESTRITO)["model_info"].__setitem__("plano", "FREE"), ESTRITO),
])
def test_estrito_config_com_saida_ou_nuvem_recusa(cfg, mutar, trecho):
    torta = copy.deepcopy(cfg)
    mutar(torta)
    d = estrito(u("oi"), R.info_grupos(torta))
    assert d.recusa is not None and d.recusa[0] == 500 and trecho in d.recusa[1]


def test_estrito_config_ilegivel_ou_sem_grupo_recusa(cfg):
    d = estrito(u("oi"), None)
    assert d.recusa is not None and d.recusa[0] == 503
    sem = copy.deepcopy(cfg)
    sem["model_list"] = [m for m in sem["model_list"] if m["model_name"] != ESTRITO_AG]
    d = estrito(u("oi"), R.info_grupos(sem))
    assert d.recusa is not None and d.recusa[0] == 503 and ESTRITO_AG in d.recusa[1]


# ── híbrido ──────────────────────────────────────────────────────────────────────────────────────────────────────
def test_hibrido_local_primeiro(grupos):
    d = hibrido(u("explique o que é um índice de banco"), grupos)
    assert (d.grupo, d.categoria, d.destino, d.fechado, d.recusa) == ("tudoia-local", "chat", "local", False, None)
    assert hibrido(u("liste", tools=FERRAMENTAS), grupos).grupo == "tudoia-local-agente"
    assert hibrido(u("```sql\nselect 1\n```"), grupos).grupo == "tudoia-local-agente"


def test_hibrido_imagem_vai_para_visao_gratuita(grupos):
    dados = {"model": "x", "messages": [{"role": "user", "content": [IMAGEM, {"type": "text", "text": "o que é?"}]}]}
    d = hibrido(dados, grupos)
    assert d.grupo == "tudoia-visao" and d.destino == "nuvem" and d.categoria == "visao"


def test_hibrido_sem_grupo_visao_degrada_para_chat(grupos_sem_nuvem):
    dados = {"model": "x", "messages": [{"role": "user", "content": [IMAGEM, {"type": "text", "text": "o que é?"}]}]}
    d = hibrido(dados, grupos_sem_nuvem)
    assert d.recusa is None and d.grupo == "tudoia-local" and any("sem grupo tudoia-visao" in m for m in d.motivos)


def test_hibrido_apoio_da_nuvem_gratuita(grupos):
    for kw, motivo in (({"ollama_ok": False}, "ollama fora"), ({"gpu_ocupada": True}, "gpu ocupada")):
        d = hibrido(u("oi"), grupos, **kw)
        assert d.grupo == "tudoia-nuvem" and d.destino == "nuvem" and motivo in d.motivos and d.fechado is False
        d = hibrido(u("x", tools=FERRAMENTAS), grupos, **kw)
        assert d.grupo == "tudoia-codigo" and d.destino == "nuvem"


def test_hibrido_pedido_maior_que_o_contexto_local_vai_para_nuvem_gratis(grupos):
    d = hibrido(u("palavra " * 25000), grupos)
    assert d.grupo == "tudoia-nuvem" and "excede contexto local" in d.motivos and d.destino == "nuvem"
    d = hibrido(u("palavra " * 25000, tools=FERRAMENTAS), grupos)
    assert d.grupo == "tudoia-codigo"


def test_hibrido_local_explicito_nunca_vai_a_nuvem(grupos):
    d = hibrido(u("#local " + "palavra " * 25000), grupos)
    assert d.grupo == "tudoia-local" and d.fechado is True and d.recusa is None   # disable_fallbacks: nem o router desvia
    d = hibrido(u("#local oi"), grupos, ollama_ok=False)
    assert d.recusa is not None and d.recusa[0] == 503
    d = hibrido(u("#local oi"), grupos, gpu_ocupada=True)
    assert d.grupo == "tudoia-local"


def test_hibrido_marcadores_conflitantes_vence_o_restritivo(grupos):
    for texto in ("#nuvem #local oi", "#local #nuvem oi", "#NUVEM #Local oi"):
        dados = u(texto)
        d = hibrido(dados, grupos)
        assert d.marcador == "local" and d.grupo == "tudoia-local" and d.fechado is True, texto
        assert texto_usuario(dados) == "oi"


def test_hibrido_nuvem_explicita(grupos):
    assert hibrido(u("#nuvem oi"), grupos).grupo == "tudoia-nuvem"
    assert hibrido(u("#nuvem x", tools=FERRAMENTAS), grupos).grupo == "tudoia-codigo"


def test_hibrido_nuvem_explicita_sem_provedor_recusa(grupos_sem_nuvem):
    d = hibrido(u("#nuvem oi"), grupos_sem_nuvem)
    assert d.recusa is not None and d.recusa[0] == 503


def test_hibrido_sem_nuvem_e_ollama_fora_recusa(grupos_sem_nuvem):
    d = hibrido(u("oi"), grupos_sem_nuvem, ollama_ok=False)
    assert d.recusa is not None and d.recusa[0] == 503
    d = hibrido(u("oi"), grupos_sem_nuvem, gpu_ocupada=True)   # GPU ocupada sem nuvem: segue no local, mais lento
    assert d.grupo == "tudoia-local" and d.recusa is None


def test_hibrido_max_nunca_por_marcador(cfg):
    pago = R.info_grupos(cfg_de(env={"NVIDIA_NIM_API_KEY": "x", "ANTHROPIC_API_KEY": "y"}))
    dados = u("#max oi")
    d = hibrido(dados, pago)
    assert d.grupo == "tudoia-local" and d.marcador is None and texto_usuario(dados) == "#max oi"
    for caso in (u("oi"), u("x", tools=FERRAMENTAS), u("#nuvem oi")):
        for kw in ({}, {"ollama_ok": False}, {"gpu_ocupada": True}):
            assert hibrido(caso, pago, **kw).grupo != "tudoia-max"


def test_hibrido_grupo_pago_no_perfil_recusa(cfg):
    torta = copy.deepcopy(cfg)
    for m in torta["model_list"]:
        if m["model_name"] == "tudoia-nuvem":
            m["model_info"]["plano"] = "PAID"
    d = hibrido(u("oi"), R.info_grupos(torta))
    assert d.recusa is not None and d.recusa[0] == 500


def test_tudoia_auto_continua_igual(grupos):
    # compat: tudoia-auto e seus marcadores não passam pelos perfis
    regras = carregar_roteamento(caminhos.raiz() / "config" / "roteamento.yaml")
    assert R.decidir(u("#local oi"), regras).grupo == "tudoia-local"
    assert R.decidir(u("#nuvem oi"), regras).grupo == "tudoia-nuvem"
    assert R.decidir(u("#max oi"), regras, grupos_existentes={"tudoia-max"}).grupo == "tudoia-max"
    d = R.decidir(u("#local oi"), regras)
    assert d.perfil is None and d.fechado is False and d.recusa is None


# ── cadeia de nova tentativa do /v1/messages (roteador_resiliente) ──────────────────────────────────────────────
def test_nova_tentativa_do_estrito_nao_tem_destino_de_nuvem(cfg):
    import roteador_resiliente as RS
    mapa = RS.mapa_de_grupos(cfg)
    for g in (ESTRITO, ESTRITO_AG, HIBRIDO):
        assert RS.plano(mapa, g, None) == []
    assert RS.plano(mapa, "tudoia-local", None) == []   # híbrido que caiu no local: sem destino
    assert "tudoia-nuvem" not in RS.plano(mapa, "tudoia-local-agente", None)


# ── eventos: lista branca ───────────────────────────────────────────────────────────────────────────────────────
def test_evento_inicio_leva_perfil_categoria_destino_e_descarta_o_resto():
    import roteador_eventos as EV
    ev = EV.evento_inicio({"litellm_call_id": "c1", "model": ESTRITO}, grupo=ESTRITO, perfil="local-estrito",
                          categoria="chat", destino="local", texto_do_pedido="segredo")
    assert (ev["perfil"], ev["categoria"], ev["destino"], ev["grupo"]) == ("local-estrito", "chat", "local", ESTRITO)
    assert "texto_do_pedido" not in ev and "segredo" not in json.dumps(ev)


# ── hook do LiteLLM ──────────────────────────────────────────────────────────────────────────────────────────────
def _carregar_hook():
    class CustomLogger:
        pass

    for nome in ("litellm", "litellm.integrations", "litellm.integrations.custom_logger"):
        sys.modules.setdefault(nome, types.ModuleType(nome))
    sys.modules["litellm.integrations.custom_logger"].CustomLogger = CustomLogger
    if str(LIT) not in sys.path:
        sys.path.insert(0, str(LIT))
    spec = importlib.util.spec_from_file_location("roteador_hook_perfis", LIT / "roteador.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


H = _carregar_hook()


def _linhas(caminho, minimo=1, s=5.0):
    fim = time.time() + s
    while time.time() < fim:
        if caminho.exists():
            linhas = [json.loads(x) for x in caminho.read_text(encoding="utf-8").splitlines() if x.strip()]
            if len(linhas) >= minimo:
                return linhas
        time.sleep(0.02)
    raise AssertionError(f"{caminho.name}: esperava {minimo} linha(s)")


@pytest.fixture
def criar_hook(tmp_path, monkeypatch):
    def criar(config="padrao", ollama=True, arq_regras=None):
        monkeypatch.setattr(H, "DIR_LOGS", str(tmp_path))
        monkeypatch.setattr(H, "ARQ_EVENTOS", str(tmp_path / "eventos.jsonl"))
        monkeypatch.setattr(H, "ARQ_REGRAS", str(arq_regras or caminhos.raiz() / "config/roteamento.yaml"))
        lida = cfg_de() if config == "padrao" else config
        monkeypatch.setattr(H.Roteador, "_ler_config", staticmethod(lambda: lida))
        r = H.Roteador()
        r._saude_ok, r._saude_em = ollama, float("inf")   # Ollama "no ar"/"fora" sem rede
        monkeypatch.setattr(r, "gpu_ocupada", lambda: False)
        return r
    return criar


def _pre(hook, dados):
    dados.setdefault("litellm_call_id", "c-" + str(id(dados)))
    return asyncio.run(hook.async_pre_call_hook({}, None, dados, "completion"))


def test_hook_estrito_roteia_fecha_fallbacks_e_registra(criar_hook, tmp_path):
    hook = criar_hook()
    dados = {"model": ESTRITO, "stream": False, "messages": [{"role": "user", "content": "#local resuma isto"}]}
    out = _pre(hook, dados)
    assert out["model"] == ESTRITO and out["disable_fallbacks"] is True
    assert out["messages"][0]["content"] == "resuma isto"
    (ini,) = [e for e in _linhas(tmp_path / "eventos.jsonl") if e["tipo"] == "inicio"]
    assert (ini["perfil"], ini["categoria"], ini["destino"], ini["grupo"]) == ("local-estrito", "chat", "local", ESTRITO)
    cab = asyncio.run(hook.async_post_call_response_headers_hook(dados, None, None))
    assert cab == {"x-tudoia-perfil": "local-estrito", "x-tudoia-categoria": "chat", "x-tudoia-destino": "local",
                   "x-tudoia-grupo": ESTRITO}


def test_hook_estrito_agente(criar_hook):
    hook = criar_hook()
    out = _pre(hook, {"model": ESTRITO, "tools": FERRAMENTAS, "messages": [{"role": "user", "content": "liste"}]})
    assert out["model"] == ESTRITO_AG and out["disable_fallbacks"] is True


def test_hook_estrito_ollama_fora_falha_alto_e_registra(criar_hook, tmp_path):
    hook = criar_hook(ollama=False)
    dados = {"model": ESTRITO, "messages": [{"role": "user", "content": "dado sigiloso"}]}
    with pytest.raises(Exception) as exc:
        _pre(hook, dados)
    assert getattr(exc.value, "status_code", None) == 503
    assert dados["model"] == ESTRITO   # não foi reescrito para grupo algum
    ev = [e for e in _linhas(tmp_path / "eventos.jsonl") if e["tipo"] == "erro"][0]
    assert ev["perfil"] == "local-estrito" and ev["ok"] is False and "sigiloso" not in json.dumps(ev)
    linha = _linhas(tmp_path / "roteador.jsonl")[0]
    assert linha["ok"] is False and linha["grupo"] is None and "sigiloso" not in json.dumps(linha)


def test_hook_estrito_config_ilegivel_falha_alto(criar_hook):
    hook = criar_hook(config=None)
    with pytest.raises(Exception) as exc:
        _pre(hook, {"model": ESTRITO, "messages": [{"role": "user", "content": "oi"}]})
    assert getattr(exc.value, "status_code", None) == 503


def test_hook_hibrido_ollama_fora_usa_nuvem_gratuita(criar_hook, tmp_path):
    hook = criar_hook(ollama=False)
    out = _pre(hook, {"model": HIBRIDO, "messages": [{"role": "user", "content": "oi"}]})
    assert out["model"] == "tudoia-nuvem" and "disable_fallbacks" not in out
    (ini,) = [e for e in _linhas(tmp_path / "eventos.jsonl") if e["tipo"] == "inicio"]
    assert ini["destino"] == "nuvem" and "ollama fora" in ini["motivos"]


def test_hook_hibrido_local_explicito_fecha_fallbacks(criar_hook):
    hook = criar_hook()
    out = _pre(hook, {"model": HIBRIDO, "messages": [{"role": "user", "content": "#local oi"}]})
    assert out["model"] == "tudoia-local" and out["disable_fallbacks"] is True
    out = _pre(hook, {"model": HIBRIDO, "messages": [{"role": "user", "content": "oi"}]})
    assert out["model"] == "tudoia-local" and "disable_fallbacks" not in out   # sem #local o apoio da nuvem vale


def test_hook_tudoia_auto_inalterado(criar_hook):
    hook = criar_hook()
    out = _pre(hook, {"model": "tudoia-auto", "messages": [{"role": "user", "content": "#local oi"}]})
    assert out["model"] == "tudoia-local" and out["messages"][0]["content"] == "oi" and "disable_fallbacks" not in out
    out = _pre(hook, {"model": "tudoia-auto", "messages": [{"role": "user", "content": "#nuvem oi"}]})
    assert out["model"] == "tudoia-nuvem" and "disable_fallbacks" not in out


def test_hook_grupo_comum_nao_vira_perfil(criar_hook):
    hook = criar_hook()
    out = _pre(hook, {"model": "tudoia-local", "messages": [{"role": "user", "content": "#codigo oi"}]})
    assert out["model"] == "tudoia-local" and out["messages"][0]["content"] == "#codigo oi" and "disable_fallbacks" not in out


def test_hook_roteamento_invalido_no_inicio_nao_abre_caminho_para_nuvem(criar_hook, tmp_path, cfg, grupos):
    # roteamento.yaml quebrado na partida: o hook não conhece os perfis e não toca no pedido. Isso só é seguro porque o
    # grupo do estrito, sozinho, já é local e sem saída no config.yaml: é isso que este teste prova.
    ruim = tmp_path / "ruim.yaml"
    ruim.write_text("limiar: 3,5\npesos: {}\nordem: {}\n", encoding="utf-8")
    hook = criar_hook(arq_regras=ruim)
    out = _pre(hook, {"model": ESTRITO, "messages": [{"role": "user", "content": "oi"}]})
    assert out["model"] == ESTRITO
    assert grupos[ESTRITO]["destino"] == "local" and grupos[ESTRITO]["saida"] is False


def test_hook_roteamento_invalido_depois_mantem_a_ultima_versao_valida(criar_hook, tmp_path):
    arq = tmp_path / "rot.yaml"
    arq.write_text((caminhos.raiz() / "config" / "roteamento.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    hook = criar_hook(arq_regras=arq)
    assert _pre(hook, {"model": ESTRITO, "messages": [{"role": "user", "content": "oi"}]})["disable_fallbacks"] is True
    arq.write_text("perfis: lixo\nlimiar: 3\npesos: {}\nordem: {}\n", encoding="utf-8")
    os.utime(arq, (time.time() + 5, time.time() + 5))
    out = _pre(hook, {"model": ESTRITO, "messages": [{"role": "user", "content": "oi"}]})
    assert out["disable_fallbacks"] is True   # perfis inválidos não desfazem o que já valia

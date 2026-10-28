from pathlib import Path

import pytest
import yaml

from tudoia_painel.catalogo import carregar_catalogo
from tudoia_painel.gerador import gerar_config, gravar_config

FIX = Path(__file__).parent / "fixtures"
AUTOMATICOS = {"tudoia-auto", "tudoia-visao", "tudoia-nuvem", "tudoia-codigo", "tudoia-local", "tudoia-local-agente"}


@pytest.fixture
def cat_mini():
    return carregar_catalogo(FIX / "catalogo-mini.yaml")


@pytest.fixture
def rot_mini():
    return {
        "limiar": 3,
        "pesos": {},
        "ordem": {
            "tudoia-nuvem": ["nim/nemotron-3-super", "cloudflare/gpt-oss-120b", "nim/glm-5.3-flash"],
            "tudoia-codigo": ["nim/glm-5.3-flash"],
            "tudoia-max": ["claude-sonnet-5-5"],
            "tudoia-visao": ["nim/visao-vl"],
        },
    }


def grupo(cfg, nome):
    return [m for m in cfg["model_list"] if m["model_name"] == nome]


def test_so_provedores_com_chave(cat_mini, rot_mini):
    cfg = gerar_config(cat_mini, {"NVIDIA_NIM_API_KEY": "x"}, rot_mini)
    provs = {m["model_info"]["provedor"] for m in cfg["model_list"]}
    assert provs == {"nvidia", "local"}
    nomes = {m["model_name"] for m in cfg["model_list"]}
    assert "nim/desligado" not in nomes and "nim/glm-5.3-flash" in nomes


def test_deployment_usa_referencia_a_variavel_e_nao_o_valor(cat_mini, rot_mini):
    cfg = gerar_config(cat_mini, {"NVIDIA_NIM_API_KEY": "segredo-123"}, rot_mini)
    texto = yaml.safe_dump(cfg)
    assert "segredo-123" not in texto
    (dep,) = grupo(cfg, "nim/glm-5.3-flash")
    assert dep["litellm_params"]["api_key"] == "os.environ/NVIDIA_NIM_API_KEY"
    assert dep["litellm_params"]["model"] == "nvidia_nim/z-ai/glm-5.3-flash"
    assert dep["litellm_params"]["api_base"] == "https://integrate.api.nvidia.com/v1"
    assert dep["model_info"] == {"plano": "FREE", "provedor": "nvidia", "papeis": ["chat", "codigo", "agente", "rapido"],
                                 "max_input_tokens": 131072}
    assert "additional_drop_params" not in dep["litellm_params"]


def test_contexto_do_catalogo_vira_max_input_tokens(cat_mini, rot_mini):
    # com max_input_tokens, enable_pre_call_checks pula o membro em que o pedido não cabe em vez de levar 400
    cfg = gerar_config(cat_mini, {"NVIDIA_NIM_API_KEY": "x"}, rot_mini)
    (cod,) = grupo(cfg, "tudoia-codigo")
    assert cod["model_info"]["max_input_tokens"] == 131072
    (sem,) = grupo(cfg, "nim/nemotron-3-super")
    assert "max_input_tokens" not in sem["model_info"]   # contexto desconhecido: não inventa limite


def test_gravar_config_recusa_codigo_do_gerador_desatualizado(tmp_path, monkeypatch):
    # painel aberto há horas tem o gerador antigo na memória: gravar desfaria correções feitas depois
    from tudoia_painel import gerador
    monkeypatch.setattr(gerador, "_ASSINATURA_CARREGADA", "outra")
    with pytest.raises(RuntimeError, match="reinicie o painel"):
        gravar_config({"model_list": []}, tmp_path / "config.yaml")
    assert not (tmp_path / "config.yaml").exists()


def test_paid_nunca_em_grupos_automaticos(cat_mini, rot_mini):
    cfg = gerar_config(cat_mini, {"NVIDIA_NIM_API_KEY": "x", "ANTHROPIC_API_KEY": "y"}, rot_mini)
    for m in cfg["model_list"]:
        if m["model_name"] in AUTOMATICOS:
            assert m["model_info"]["plano"] != "PAID", m
    for regra in cfg["router_settings"]["fallbacks"]:
        for origem, destinos in regra.items():
            if origem in AUTOMATICOS:
                assert "tudoia-max" not in destinos
    (mx,) = grupo(cfg, "tudoia-max")
    assert mx["litellm_params"]["model"] == "anthropic/claude-sonnet-5-5"


def test_paid_aparece_pelo_nome(cat_mini, rot_mini):
    cfg = gerar_config(cat_mini, {"ANTHROPIC_API_KEY": "y"}, rot_mini)
    assert grupo(cfg, "claude-sonnet-5-5")


def test_sem_paid_nao_existe_tudoia_max(cat_mini, rot_mini):
    cfg = gerar_config(cat_mini, {"NVIDIA_NIM_API_KEY": "x"}, rot_mini)
    assert grupo(cfg, "tudoia-max") == []
    assert all("tudoia-max" not in r for r in cfg["router_settings"]["fallbacks"])


def test_ordem_respeita_roteamento_e_ignora_ausentes(cat_mini, rot_mini):
    cfg = gerar_config(cat_mini, {"NVIDIA_NIM_API_KEY": "x"}, rot_mini)
    membros = grupo(cfg, "tudoia-nuvem")
    assert [m["litellm_params"]["model"] for m in membros] == [
        "nvidia_nim/nvidia/nemotron-3-super-120b-a12b",
        "nvidia_nim/z-ai/glm-5.3-flash",
    ]
    assert all("order" not in m["litellm_params"] for m in membros)   # order esconderia o resto do grupo da estratégia de latência


def test_codigo_vazio_aponta_para_local_agente(cat_mini, rot_mini):
    rot_mini["ordem"]["tudoia-codigo"] = ["or/inexistente"]
    cfg = gerar_config(cat_mini, {"NVIDIA_NIM_API_KEY": "x"}, rot_mini)
    (cod,) = grupo(cfg, "tudoia-codigo")
    assert cod["litellm_params"]["model"] == "ollama_chat/tudoia-agente"
    assert cod["model_info"]["provedor"] == "local"


def test_sem_nenhuma_chave_tudo_vai_para_o_local(cat_mini, rot_mini):
    cfg = gerar_config(cat_mini, {}, rot_mini)
    assert {m["model_info"]["provedor"] for m in cfg["model_list"]} == {"local"}
    (nuvem,) = grupo(cfg, "tudoia-nuvem")
    assert nuvem["litellm_params"]["model"] == "ollama_chat/tudoia-chat"


def test_grupos_locais(cat_mini, rot_mini):
    cfg = gerar_config(cat_mini, {}, rot_mini)
    for nome, modelo in [("tudoia-local", "tudoia-chat"), ("tudoia-local-agente", "tudoia-agente"), ("tudoia-auto", "tudoia-chat")]:
        (dep,) = grupo(cfg, nome)
        # nenhum local raciocina: no agente o prompt de ~64k do Claude Code já leva ~100 s só de leitura
        esperado = {"model": f"ollama_chat/{modelo}", "api_base": "os.environ/OLLAMA_URL",
                    "timeout": 300 if modelo == "tudoia-agente" else 600,
                    "input_cost_per_token": 0.0, "output_cost_per_token": 0.0, "think": False}
        assert dep["litellm_params"] == esperado
        assert dep["model_info"]["membro"] == f"local/{modelo}"
        # agente com num_ctx 32k: pedido maior é pulado pelo enable_pre_call_checks em vez de truncado
        assert dep["model_info"].get("max_input_tokens") == 30000   # todos os locais têm num_ctx 32k
        assert dep["model_info"]["plano"] == "LOCAL" and dep["model_info"]["provedor"] == "local"


def test_fallbacks_e_settings(cat_mini, rot_mini):
    cfg = gerar_config(cat_mini, {"NVIDIA_NIM_API_KEY": "x", "ANTHROPIC_API_KEY": "y"}, rot_mini)
    rs = cfg["router_settings"]
    assert rs["fallbacks"][:4] == [
        {"tudoia-nuvem": ["tudoia-local"]},
        {"tudoia-codigo": ["tudoia-local-agente"]},
        {"tudoia-max": ["tudoia-nuvem"]},
        {"tudoia-visao": ["tudoia-nuvem"]},
    ]
    assert rs["context_window_fallbacks"] == [{"tudoia-local": ["tudoia-nuvem"]}]
    assert rs["enable_pre_call_checks"] is True
    assert rs["routing_strategy"] == "latency-based-routing"
    assert (rs["allowed_fails"], rs["cooldown_time"], rs["num_retries"]) == (1, 60, 1)
    # travamento da NIM grátis é passageiro: 1 timeout não pode tirar metade do tudoia-codigo por 60 s
    assert rs["allowed_fails_policy"] == {"TimeoutErrorAllowedFails": 3, "RateLimitErrorAllowedFails": 1,
                                          "InternalServerErrorAllowedFails": 2, "BadRequestErrorAllowedFails": 5,
                                          "AuthenticationErrorAllowedFails": 0}
    assert cfg["litellm_settings"]["drop_params"] is True
    assert cfg["litellm_settings"]["callbacks"] == "roteador.proxy_handler_instance"
    assert "general_settings" in cfg


def test_gravar_config_guarda_anterior_e_cabecalho(tmp_path):
    destino = tmp_path / "config.yaml"
    destino.write_text("antigo: 1\n", encoding="utf-8")
    gravar_config({"model_list": []}, destino)
    texto = destino.read_text(encoding="utf-8")
    assert texto.startswith("# GERADO por tudoia-painel")
    assert yaml.safe_load(texto) == {"model_list": []}
    assert (tmp_path / "config.yaml.anterior").read_text(encoding="utf-8") == "antigo: 1\n"


def test_model_info_nao_usa_campo_reservado_tier(cat_mini, rot_mini):
    # o LiteLLM valida model_info.tier como 'free'|'paid' e descarta o deployment se vier outra coisa
    cfg = gerar_config(cat_mini, {"NVIDIA_NIM_API_KEY": "x", "ANTHROPIC_API_KEY": "y"}, rot_mini)
    assert all("tier" not in m["model_info"] for m in cfg["model_list"])


def test_nuvem_tem_stream_timeout_para_cair_no_proximo(cat_mini, rot_mini):
    # sem stream_timeout o LiteLLM espera o 1º token para sempre num provedor travado e nunca faz fallback
    cfg = gerar_config(cat_mini, {"NVIDIA_NIM_API_KEY": "x", "ANTHROPIC_API_KEY": "y"}, rot_mini)
    for m in cfg["model_list"]:
        p = m["litellm_params"]
        if m["model_info"]["provedor"] == "local":
            assert p.get("stream_timeout", 600) >= 300   # o local pode levar minutos para carregar o modelo
        else:
            # também é o silêncio máximo ENTRE chunks: com 15 o GLM-5.3 era cortado no meio (pausas medidas até 13,8 s)
            assert p["stream_timeout"] == 30, m["model_name"]
            assert p["timeout"] == 60, m["model_name"]   # age como espera máxima SEM receber dados (1º byte travado)


def test_latencia_e_sem_order_nos_grupos_gratis(cat_mini, rot_mini):
    # o LiteLLM aplica `order` ANTES da estratégia (router.py: get_order_filtered_deployments): com order só o 1º membro competiria
    cfg = gerar_config(cat_mini, {"NVIDIA_NIM_API_KEY": "x"}, rot_mini)
    assert cfg["router_settings"]["routing_strategy"] == "latency-based-routing"
    for g in ("tudoia-nuvem", "tudoia-codigo", "tudoia-visao"):
        membros = grupo(cfg, g)
        assert membros
        assert all("order" not in m["litellm_params"] for m in membros), g


def test_max_mantem_order(cat_mini, rot_mini):
    rot_mini["ordem"]["tudoia-max"] = ["claude-sonnet-5-5", "claude-sonnet-5-5"]
    cfg = gerar_config(cat_mini, {"ANTHROPIC_API_KEY": "y"}, rot_mini)
    assert [m["litellm_params"]["order"] for m in grupo(cfg, "tudoia-max")] == [1, 2]


def test_grupo_visao_so_com_membros(cat_mini, rot_mini):
    cfg = gerar_config(cat_mini, {"NVIDIA_NIM_API_KEY": "x"}, rot_mini)
    (vis,) = grupo(cfg, "tudoia-visao")
    assert vis["litellm_params"]["model"] == "nvidia_nim/nvidia/vl-teste"
    assert {"tudoia-visao": ["tudoia-nuvem"]} in cfg["router_settings"]["fallbacks"]   # nuvem pode ignorar a imagem, mas responde
    sem = gerar_config(cat_mini, {}, rot_mini)   # sem chave não há membro: o grupo nem existe (nada de cair no local)
    assert grupo(sem, "tudoia-visao") == []
    assert all("tudoia-visao" not in r for r in sem["router_settings"]["fallbacks"])
    rot_mini["ordem"].pop("tudoia-visao")
    assert grupo(gerar_config(cat_mini, {"NVIDIA_NIM_API_KEY": "x"}, rot_mini), "tudoia-visao") == []


def test_modelo_gratis_chamado_pelo_nome_tem_fallback(cat_mini, rot_mini):
    # pedido direto a um membro (ex.: groq/gpt-oss-120b) que falhava não tinha para onde ir
    cfg = gerar_config(cat_mini, {"NVIDIA_NIM_API_KEY": "x", "ANTHROPIC_API_KEY": "y"}, rot_mini)
    fb = cfg["router_settings"]["fallbacks"]
    assert {"nim/glm-5.3-flash": ["tudoia-nuvem"]} in fb
    assert {"nim/visao-vl": ["tudoia-nuvem"]} in fb
    assert all("claude-sonnet-5-5" not in r for r in fb)   # PAID pelo nome nunca cai em outro lugar sozinho


def test_custo_zero_em_gratis_e_local(cat_mini, rot_mini):
    # sem custo declarado o LiteLLM loga ModelNotMappedError para ollama_chat/* e openrouter/free a cada pedido
    cfg = gerar_config(cat_mini, {"NVIDIA_NIM_API_KEY": "x", "ANTHROPIC_API_KEY": "y"}, rot_mini)
    for m in cfg["model_list"]:
        p = m["litellm_params"]
        if m["model_info"]["plano"] in ("FREE", "LOCAL"):
            assert (p["input_cost_per_token"], p["output_cost_per_token"]) == (0.0, 0.0), m["model_name"]
        else:
            assert "input_cost_per_token" not in p, m["model_name"]   # PAID usa o preço real do LiteLLM


def test_provedor_pode_descartar_params(cat_mini, rot_mini):
    # Groq devolve 400 "property 'prompt_cache_key' is unsupported" e drop_params não o remove
    cfg = gerar_config(cat_mini, {"CLOUDFLARE_API_KEY": "x", "CLOUDFLARE_ACCOUNT_ID": "y"}, rot_mini)
    for m in cfg["model_list"]:
        if m["model_info"]["provedor"] == "cloudflare":
            assert m["litellm_params"]["additional_drop_params"] == ["prompt_cache_key"]


def test_reserva_de_codigo_entra_antes_do_local(cat_mini, rot_mini):
    rot_mini["ordem"]["tudoia-codigo-reserva"] = ["cloudflare/gpt-oss-120b", "or/sem-chave"]
    cfg = gerar_config(cat_mini, {"NVIDIA_NIM_API_KEY": "x", "CLOUDFLARE_API_KEY": "c", "CLOUDFLARE_ACCOUNT_ID": "a"}, rot_mini)
    assert [m["model_info"]["membro"] for m in grupo(cfg, "tudoia-codigo-reserva")] == ["cloudflare/gpt-oss-120b"]
    assert {"tudoia-codigo": ["tudoia-codigo-reserva", "tudoia-local-agente"]} in cfg["router_settings"]["fallbacks"]


def test_reserva_sem_membro_nao_existe(cat_mini, rot_mini):
    rot_mini["ordem"]["tudoia-codigo-reserva"] = ["or/sem-chave"]
    cfg = gerar_config(cat_mini, {"NVIDIA_NIM_API_KEY": "x"}, rot_mini)
    assert grupo(cfg, "tudoia-codigo-reserva") == []
    assert {"tudoia-codigo": ["tudoia-local-agente"]} in cfg["router_settings"]["fallbacks"]

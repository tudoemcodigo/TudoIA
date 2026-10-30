"""Gera o config.yaml do LiteLLM a partir do .env, do catálogo e das regras de roteamento."""
import hashlib
import logging
import os
import shutil
from pathlib import Path

import yaml

from .catalogo import Catalogo, carregar_catalogo, carregar_roteamento, provedores_ligados
from .envfile import ler_env

_log = logging.getLogger("tudoia.gerador")

CABECALHO = (
    "# GERADO por tudoia-painel — não edite; use o painel (http://127.0.0.1:3100) ou gere de novo pelo painel.\n"
    "# Fontes: D:\\TudoIA\\.env (chaves), config\\catalogo-modelos.yaml (modelos), config\\roteamento.yaml (ordem).\n"
)

TIMEOUT_NUVEM = 60    # no LiteLLM age como espera máxima SEM receber dados: corta provedor travado, não corta geração longa
TIMEOUT_LOCAL = 600   # o 9B local pode levar minutos num prompt grande de agente
# Agente local com num_ctx 32k (modelos\ollama\Modelfile.tudoia-agente). Medido em 21/10/2026 na RTX 5070 8 GB: com 64k a VRAM
# ficava no limite e o prefill caía a 652 tok/s (mediana de 474 s até o 1º token no Claude Code); com 32k, 1750 tok/s.
# 66% dos pedidos do Claude Code cabem em 30k; o resto o enable_pre_call_checks pula em vez de truncar.
# Vale para TODOS os locais (todos os Modelfile têm num_ctx 32768): sem o limite, um pedido de 32,7k foi parar no
# tudoia-chat, o Ollama encheu a janela e parou com 30 tokens (stop_reason max_tokens no Claude Code).
TIMEOUT_LOCAL_AGENTE = 300
CONTEXTO_LOCAL = 30000
# Timeout de leitura do socket em streaming: vale para o 1º byte E para o silêncio entre chunks (LiteLLM 1.105.1,
# testado em 21/10/2026 com servidor falso: corta em exatamente N s, uma tentativa). Com 15 o GLM-5.3 da NVIDIA era
# cortado no meio da resposta (pausas de até 13,8 s nos sucessos) e o Claude Code mostrava "Server error
# mid-response": depois do 1º conteúdo o LiteLLM não faz fallback. Com 45 o nemotron-3-ultra ainda travava de vez
# no meio (silêncio infinito, não pausa), então o /v1/messages agora segura a resposta e refaz em outro modelo
# (servicos/litellm/roteador_resiliente.py): aqui o valor só decide quanto um travamento custa antes da nova
# tentativa. 30 = ~2× a maior pausa legítima medida.
STREAM_TIMEOUT_NUVEM = 30
GRATIS = {"input_cost_per_token": 0.0, "output_cost_per_token": 0.0}   # sem isso: ModelNotMappedError a cada pedido


def _assinatura_do_codigo() -> str:
    """Hash do gerador e do catálogo como estão no disco agora."""
    h = hashlib.sha1()
    for nome in ("gerador.py", "catalogo.py"):
        h.update((Path(__file__).parent / nome).read_bytes())
    return h.hexdigest()


# Em 20/10/2026 um painel aberto desde a véspera regravou o config.yaml com o gerador antigo da memória e desfez
# as correções de timeout. Gravar só se o código carregado ainda for o do disco.
_ASSINATURA_CARREGADA = _assinatura_do_codigo()


def _obter_modelo_local_padrao(ordem: dict[str, list[str]], env: dict[str, str]) -> str:
    for m in ordem.get("tudoia-local") or []:
        if m.startswith("local/"):
            return m.removeprefix("local/")
    for membros_grupo in ordem.values():
        for m in membros_grupo:
            if m.startswith("local/"):
                return m.removeprefix("local/")
    try:
        import httpx
        ollama_url = env.get("OLLAMA_URL") or "http://127.0.0.1:11434"
        with httpx.Client(timeout=0.6) as cli:
            r = cli.get(f"{ollama_url}/api/tags")
            if r.status_code == 200:
                for mod in r.json().get("models", []):
                    nome = mod.get("name", "")
                    if "embed" not in nome:
                        return nome
    except Exception:
        pass
    return "tudoia-chat"


def _obter_modelo_local_codigo(ordem: dict[str, list[str]], env: dict[str, str], padrao: str) -> str:
    for m in ordem.get("tudoia-local-agente") or ordem.get("tudoia-codigo") or []:
        if m.startswith("local/"):
            return m.removeprefix("local/")
    try:
        import httpx
        ollama_url = env.get("OLLAMA_URL") or "http://127.0.0.1:11434"
        with httpx.Client(timeout=0.6) as cli:
            r = cli.get(f"{ollama_url}/api/tags")
            if r.status_code == 200:
                for mod in r.json().get("models", []):
                    nome = mod.get("name", "")
                    if "coder" in nome or "agente" in nome:
                        return nome
    except Exception:
        pass
    return "tudoia-agente" if padrao == "tudoia-chat" else padrao


def _local(nome_grupo: str, modelo_ollama: str) -> dict:
    # sem raciocínio: no chat o qwen gastava o max_tokens pensando e devolvia resposta vazia; no agente (fallback do
    # Claude Code) o prompt de ~64k já leva ~100 s só de leitura e pensar antes de responder dobrava a espera
    agente = modelo_ollama == "tudoia-agente"
    params = {"model": f"ollama_chat/{modelo_ollama}", "api_base": "os.environ/OLLAMA_URL",
              "timeout": TIMEOUT_LOCAL_AGENTE if agente else TIMEOUT_LOCAL, **GRATIS, "think": False}
    info = {"plano": "LOCAL", "provedor": "local", "papeis": [], "membro": f"local/{modelo_ollama}",
            "max_input_tokens": CONTEXTO_LOCAL}
    return {"model_name": nome_grupo, "litellm_params": params, "model_info": info}


def gerar_config(cat: Catalogo, env: dict, rot: dict) -> dict:
    deployments: dict[str, dict] = {}   # nome do catálogo → deployment
    for prov in provedores_ligados(cat, env):
        for m in prov.modelos:
            if not m.ativo:
                continue
            params = {"model": m.id, "api_key": f"os.environ/{prov.chave}", "timeout": TIMEOUT_NUVEM,
                      "stream_timeout": STREAM_TIMEOUT_NUVEM}
            if prov.tier == "FREE":
                params.update(GRATIS)
            if prov.descartar_params:
                params["additional_drop_params"] = list(prov.descartar_params)
            if prov.api_base:
                params["api_base"] = prov.api_base
            if prov.repeticoes is not None:
                params["num_retries"] = prov.repeticoes
            info = {"plano": prov.tier, "provedor": prov.chave_id, "papeis": list(m.papeis)}
            if m.contexto:
                info["max_input_tokens"] = m.contexto   # enable_pre_call_checks pula o membro em que o pedido não cabe
            deployments[m.nome] = {"model_name": m.nome, "litellm_params": params, "model_info": info}

    model_list = list(deployments.values())
    ordem = rot.get("ordem") or {}
    grupos_desativados = set(rot.get("grupos_desativados") or [])

    def membros(grupo: str, tier: str) -> list[dict]:
        if grupo in grupos_desativados:
            return []
        # `order` só no PAID: o LiteLLM filtra por order ANTES da estratégia de roteamento, então nos grupos
        # FREE ele deixaria só o 1º membro competir e a latência nunca decidiria nada.
        saida = []
        for nome in ordem.get(grupo) or []:
            if nome.startswith("local/"):
                mod_local = nome.removeprefix("local/")
                saida.append(_local(grupo, mod_local))
                continue
            dep = deployments.get(nome)
            if dep and dep["model_info"]["plano"] == tier:
                params = dict(dep["litellm_params"])
                if tier == "PAID":
                    params["order"] = len(saida) + 1
                saida.append({"model_name": grupo, "litellm_params": params, "model_info": dict(dep["model_info"], membro=nome)})
        return saida

    local_padrao = _obter_modelo_local_padrao(ordem, env)
    local_codigo = _obter_modelo_local_codigo(ordem, env, local_padrao)

    nuvem = membros("tudoia-nuvem", "FREE") or [_local("tudoia-nuvem", local_padrao)]
    codigo = membros("tudoia-codigo", "FREE") or [_local("tudoia-codigo", local_codigo)]
    reserva = membros("tudoia-codigo-reserva", "FREE")   # outra nuvem quando a NIM inteira trava ou dá 429
    maximo = membros("tudoia-max", "PAID")
    visao = membros("tudoia-visao", "FREE")   # sem membro não existe: o hook então ignora imagem em vez de cair no local

    # Grupos adicionais customizados
    grupos_padrao = {"tudoia-nuvem", "tudoia-codigo", "tudoia-codigo-reserva", "tudoia-max", "tudoia-visao"}
    custom_membros = []
    for g_nome, g_membros in ordem.items():
        if g_nome not in grupos_padrao and g_nome not in grupos_desativados:
            for m_nome in g_membros:
                if m_nome.startswith("local/"):
                    mod_local = m_nome.removeprefix("local/")
                    custom_membros.append(_local(g_nome, mod_local))
                    continue
                dep = deployments.get(m_nome)
                if dep:
                    custom_membros.append({"model_name": g_nome, "litellm_params": dict(dep["litellm_params"]), "model_info": dict(dep["model_info"], membro=m_nome)})

    model_list += nuvem + codigo + reserva + maximo + visao + custom_membros

    nomes_grupos_presentes = {m["model_name"] for m in model_list}
    if "tudoia-local" not in nomes_grupos_presentes and "tudoia-local" not in grupos_desativados:
        model_list.append(_local("tudoia-local", local_padrao))

    if "tudoia-local-agente" not in nomes_grupos_presentes and "tudoia-local-agente" not in grupos_desativados:
        model_list.append(_local("tudoia-local-agente", local_codigo))

    # tudoia-auto sempre presente apontando para o modelo local real
    model_list.append(_local("tudoia-auto", local_padrao))

    fallbacks = [{"tudoia-nuvem": ["tudoia-local"]},
                 {"tudoia-codigo": (["tudoia-codigo-reserva"] if reserva else []) + ["tudoia-local-agente"]}]
    if maximo:
        fallbacks.append({"tudoia-max": ["tudoia-nuvem"]})
    if visao:
        fallbacks.append({"tudoia-visao": ["tudoia-nuvem"]})   # nuvem pode ignorar a imagem, mas resposta vale mais que erro
    # membro grátis pedido pelo nome (n8n, Open WebUI) também tem para onde ir; PAID pelo nome nunca troca sozinho
    fallbacks += [{nome: ["tudoia-nuvem"]} for nome, dep in deployments.items() if dep["model_info"]["plano"] == "FREE"]

    return {
        "model_list": model_list,
        "router_settings": {
            "routing_strategy": "latency-based-routing",   # membro sem histórico conta como latência 0: todos são testados
            "fallbacks": fallbacks,
            # Vale também para #local: pedido que não cabe no contexto local vai para a nuvem (decisão do dono em
            # 27/10/2026, risco 16 em docs/seguranca.md). Tirar daqui faz o pedido grande falhar sem sair da máquina.
            "context_window_fallbacks": [{"tudoia-local": ["tudoia-nuvem"]}],
            "enable_pre_call_checks": True,
            # 408/429/401/404 esfriam o membro na hora e timeout ganha penalidade de latência (a nova tentativa vai a
            # outro membro); allowed_fails 1 só evita que um 500 isolado tire o melhor modelo do grupo. Com 0/300 s um
            # soluço deixava o grupo sem o GLM-5.3 por 5 min e tudo caía no local (~2 min por resposta).
            "allowed_fails": 1,
            # por tipo (lógica v1 do LiteLLM: esfria quando falhas no minuto > valor). Em 21/10 os ReadTimeout da NIM
            # eram travamentos passageiros (sucessos com 1º token em p99 21 s) e, com só 2 membros no tudoia-codigo,
            # 2 timeouts esvaziavam o grupo: 37 RouterRateLimitError num dia. 400 quase sempre é o pedido, não o membro.
            "allowed_fails_policy": {"TimeoutErrorAllowedFails": 3, "RateLimitErrorAllowedFails": 1,
                                     "InternalServerErrorAllowedFails": 2, "BadRequestErrorAllowedFails": 5,
                                     "AuthenticationErrorAllowedFails": 0},
            "cooldown_time": 60,
            "num_retries": 1,
        },
        "general_settings": {
            "master_key": "os.environ/LITELLM_MASTER_KEY",
            "database_url": "os.environ/DATABASE_URL",
            "store_model_in_db": True,
            "proxy_budget_resets": True,
        },
        "litellm_settings": {
            "drop_params": True,
            "set_verbose": False,
            "telemetry": False,
            "request_timeout": 60,
            "callbacks": "roteador.proxy_handler_instance",
        },
    }


def gravar_config(cfg: dict, destino: Path) -> None:
    if _ASSINATURA_CARREGADA != _assinatura_do_codigo():
        raise RuntimeError("o código do gerador mudou desde que o painel abriu: reinicie o painel e gere de novo")
    texto = CABECALHO + yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True, width=200)
    if yaml.safe_load(texto) != cfg:
        raise ValueError("config gerado não sobrevive ao round-trip do YAML")
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists():
        shutil.copyfile(destino, destino.with_name(destino.name + ".anterior"))
    tmp = destino.with_name(destino.name + ".tmp")
    tmp.write_text(texto, encoding="utf-8", newline="\n")
    os.replace(tmp, destino)


def regenerar_config_litellm(raiz: Path) -> bool:
    """Gera e grava runtime/litellm/config.yaml a partir das fontes. Única porta de regeneração do painel.

    Devolve False em erro, sem levantar: quem chama já gravou a mudança do usuário (catálogo, roteamento), e o config
    fica para o próximo "Gerar". O erro vai para o log, não some. O LiteLLM só lê o arquivo ao subir, então quem
    chama deve avisar que é preciso reiniciá-lo.
    """
    try:
        cfg = gerar_config(carregar_catalogo(raiz / "config" / "catalogo-modelos.yaml"), ler_env(raiz / ".env"),
                           carregar_roteamento(raiz / "config" / "roteamento.yaml"))
        gravar_config(cfg, raiz / "runtime" / "litellm" / "config.yaml")
        return True
    except Exception as e:  # noqa: BLE001 — falha de geração não desfaz a gravação que o usuário pediu
        _log.warning("config do LiteLLM não regenerado: %s: %s", type(e).__name__, e)
        return False

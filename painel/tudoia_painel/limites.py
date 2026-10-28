"""Cálculo e agregação de limites e consumo de tokens por provedor."""
from __future__ import annotations

import fnmatch
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import httpx
import yaml

from tudoia_painel import upstreams
from tudoia_painel.envfile import ler_env


def normalizar_provedor(provedor_raw: str | None, modelo_raw: str | None) -> str:
    """Normaliza o identificador do provedor a partir de vários formatos de log."""
    p = (provedor_raw or "").lower().strip()
    m = (modelo_raw or "").lower().strip()

    if p in ("local", "ollama") or m.startswith("ollama") or "tudoia-chat" in m or "tudoia-agente" in m:
        return "ollama"
    if "nvidia" in p or "nvidia" in m:
        return "nvidia"
    if "groq" in p or "groq" in m:
        return "groq"
    if "openrouter" in p or "openrouter" in m or m.startswith("or/"):
        return "openrouter"
    if "gemini" in p or "google" in p or "gemini" in m:
        return "gemini"
    if "cloudflare" in p or "cloudflare" in m or "@cf" in m:
        return "cloudflare"
    if "anthropic" in p or "claude" in m:
        return "anthropic"
    if "openai" in p or "gpt" in m:
        return "openai"
    if "deepseek" in p or "deepseek" in m:
        return "deepseek"
    if "xai" in p or "grok" in m:
        return "xai"
    if "huggingface" in p or "hf" in m:
        return "huggingface"

    return p or "outros"


def carregar_precos_referencia(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def encontrar_preco_equivalente(modelo_nome: str, precos_ref: dict) -> dict | None:
    if not precos_ref:
        return None
    modelos_ref = precos_ref.get("modelos") or {}
    equivalencias = precos_ref.get("equivalencias") or []
    padrao_padrao = precos_ref.get("referencia_padrao", "gpt-6-luna")

    for eq in equivalencias:
        padrao = eq.get("padrao", "")
        if fnmatch.fnmatch(modelo_nome, padrao):
            ref_chave = eq.get("referencia")
            if ref_chave and ref_chave in modelos_ref:
                return modelos_ref[ref_chave]

    return modelos_ref.get(padrao_padrao)


def calcular_economia_tokens(tokens_in: int, tokens_out: int, modelo_nome: str, precos_ref: dict) -> float:
    ref = encontrar_preco_equivalente(modelo_nome, precos_ref)
    if not ref:
        return 0.0
    p_in = float(ref.get("entrada_usd_mtok", 0.0) or 0.0)
    p_out = float(ref.get("saida_usd_mtok", 0.0) or 0.0)
    custo = (tokens_in / 1_000_000.0) * p_in + (tokens_out / 1_000_000.0) * p_out
    return round(custo, 5)


def ler_logs_litellm(k: str, periodo_horas: int | None = 24) -> list[dict]:
    """Logs de gasto do LiteLLM só do período pedido. Sem filtro o endpoint devolve até 10 mil registros com o
    pedido inteiro de cada um (27 MB medidos em 27/10/2026, a cada atualização da tela) e o timeout de 3 s estourava.
    O filtro do LiteLLM é por dia: a janela vai do dia de início até amanhã, e quem chama corta pela hora exata."""
    if not k:
        return []
    params: dict[str, str] = {}
    if periodo_horas and periodo_horas > 0:
        agora = datetime.now()
        params = {"start_date": (agora - timedelta(hours=periodo_horas)).date().isoformat(),
                  "end_date": (agora + timedelta(days=1)).date().isoformat(), "summarize": "false"}
    try:
        with httpx.Client(timeout=10.0) as cliente:
            resp = cliente.get(
                f"{upstreams.LITELLM}/spend/logs",
                headers={"Authorization": f"Bearer {k}"},
                params=params,
            )
            if resp.status_code == 200:
                dados = resp.json()
                return dados if isinstance(dados, list) else []
    except Exception:
        pass
    return []


def ler_logs_eventos(path_eventos: Path) -> list[dict]:
    if not path_eventos.is_file():
        return []
    registros = []
    try:
        with path_eventos.open("r", encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if not linha:
                    continue
                try:
                    obj = json.loads(linha)
                    registros.append(obj)
                except Exception:
                    continue
    except Exception:
        pass
    return registros


def obter_metricas_limites(raiz: Path, periodo_horas: int | None = 24) -> dict[str, Any]:
    """Agrega e calcula métricas completas de limites e tokens por provedor."""
    raiz = Path(raiz)
    env = ler_env(raiz / ".env")
    master_key = env.get("LITELLM_MASTER_KEY", "")

    # Carregar catálogo
    catalogo_yaml = raiz / "config" / "catalogo-modelos.yaml"
    catalogo_dados = {}
    if catalogo_yaml.is_file():
        try:
            catalogo_dados = yaml.safe_load(catalogo_yaml.read_text(encoding="utf-8")) or {}
        except Exception:
            catalogo_dados = {}

    provedores_cfg = catalogo_dados.get("provedores") or {}
    precos_ref = carregar_precos_referencia(raiz / "config" / "precos-referencia.yaml")

    # Coletar logs das duas fontes
    logs_llm = ler_logs_litellm(master_key, periodo_horas)
    logs_evt = ler_logs_eventos(raiz / "dados" / "logs" / "eventos.jsonl")

    agora = datetime.now(timezone.utc)
    limite_tempo = agora - timedelta(hours=periodo_horas) if periodo_horas and periodo_horas > 0 else None
    um_minuto_atras = agora - timedelta(seconds=60)

    # Unificação de chamadas por ID
    chamadas_processadas: dict[str, dict] = {}

    for item in logs_llm:
        cid = str(item.get("request_id") or item.get("litellm_call_id") or "")
        if not cid:
            continue
        st_raw = item.get("startTime") or item.get("created_at") or ""
        dt = None
        if st_raw:
            try:
                dt = datetime.fromisoformat(st_raw.replace("Z", "+00:00"))
            except Exception:
                pass

        total_tok = int(item.get("total_tokens", 0) or 0)
        prompt_tok = int(item.get("prompt_tokens", 0) or 0)
        comp_tok = int(item.get("completion_tokens", 0) or 0)
        spend = float(item.get("spend", 0.0) or 0.0)
        status = str(item.get("status", "success")).lower()
        custom_p = item.get("custom_llm_provider")
        modelo = str(item.get("model", "") or "")
        prov = normalizar_provedor(custom_p, modelo)

        chamadas_processadas[cid] = {
            "id": cid,
            "dt": dt,
            "provedor": prov,
            "modelo": modelo,
            "prompt_tokens": prompt_tok,
            "completion_tokens": comp_tok,
            "total_tokens": total_tok,
            "spend": spend,
            "ok": status == "success",
            "erro": None if status == "success" else "failure",
        }

    for evt in logs_evt:
        tipo = evt.get("tipo")
        if tipo not in ("fim", "erro"):
            continue
        cid = str(evt.get("id") or "")
        if not cid:
            continue

        ts_raw = evt.get("ts", "")
        dt = None
        if ts_raw:
            try:
                dt = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            except Exception:
                pass

        prompt_tok = int(evt.get("tokens_entrada", 0) or 0)
        comp_tok = int(evt.get("tokens_saida", 0) or 0)
        total_tok = prompt_tok + comp_tok
        spend = float(evt.get("custo_usd", 0.0) or 0.0)
        ok = bool(evt.get("ok", tipo != "erro"))
        erro = evt.get("erro")
        modelo = str(evt.get("modelo") or evt.get("membro") or "")
        prov = normalizar_provedor(evt.get("provedor"), modelo)

        if cid in chamadas_processadas:
            # Enriquecer se faltava algo
            if not chamadas_processadas[cid]["total_tokens"] and total_tok > 0:
                chamadas_processadas[cid]["total_tokens"] = total_tok
                chamadas_processadas[cid]["prompt_tokens"] = prompt_tok
                chamadas_processadas[cid]["completion_tokens"] = comp_tok
            if erro and not chamadas_processadas[cid].get("erro"):
                chamadas_processadas[cid]["erro"] = erro
        else:
            chamadas_processadas[cid] = {
                "id": cid,
                "dt": dt,
                "provedor": prov,
                "modelo": modelo,
                "prompt_tokens": prompt_tok,
                "completion_tokens": comp_tok,
                "total_tokens": total_tok,
                "spend": spend,
                "ok": ok,
                "erro": erro,
            }

    # Provedores base (do catálogo + Ollama local)
    provedores_dict: dict[str, dict] = {}

    # Provedor local (Ollama)
    provedores_dict["ollama"] = {
        "id": "ollama",
        "nome": "Ollama (Local GPU)",
        "tier": "LOCAL",
        "ativo": True,
        "chave": None,
        "chave_configurada": True,
        "site_chave": "http://localhost:11434",
        "limites": {
            "rpm": None,
            "rpd": None,
            "tpm": None,
            "tpd": None,
            "usd_dia": None,
            "reset": "Sem limites de rede (Acelerado em GPU Local)"
        },
        "fonte_limites": "Execução local ilimitada na NVIDIA GeForce RTX 5070.",
        "modelos_cadastrados": ["tudoia-chat", "tudoia-agente", "qwen2.5-coder:7b"],
    }

    for pid, pdata in provedores_cfg.items():
        chave_var = pdata.get("chave", "")
        chaves_extras = pdata.get("chaves_extras", [])
        todas_chaves = [chave_var] + list(chaves_extras) if chave_var else list(chaves_extras)
        configurada = all(bool(env.get(k, "").strip()) for k in todas_chaves) if todas_chaves else False

        mod_nomes = [m.get("nome", "") for m in pdata.get("modelos", []) if isinstance(m, dict)]

        provedores_dict[pid] = {
            "id": pid,
            "nome": pdata.get("nome", pid),
            "tier": pdata.get("tier", "FREE"),
            "ativo": configurada,
            "chave": chave_var,
            "chave_configurada": configurada,
            "site_chave": pdata.get("site_chave", ""),
            "limites": pdata.get("limites") or {},
            "fonte_limites": pdata.get("fonte_limites") or "",
            "modelos_cadastrados": mod_nomes,
        }

    # Acumuladores por provedor
    estatisticas_provedores: dict[str, dict] = {}
    for pid in provedores_dict:
        estatisticas_provedores[pid] = {
            "requisicoes": 0,
            "requisicoes_sucesso": 0,
            "requisicoes_erro": 0,
            "tokens_entrada": 0,
            "tokens_saida": 0,
            "tokens_total": 0,
            "custo_usd": 0.0,
            "economia_usd": 0.0,
            "reqs_ultimo_minuto": 0,
            "erros_rate_limit": 0,
            "modelos_uso": {},
        }

    # Filtrar chamadas pelo período e acumular
    total_tokens_geral = 0
    total_entrada_geral = 0
    total_saida_geral = 0
    total_requisicoes_geral = 0
    total_custo_geral = 0.0
    total_economia_geral = 0.0

    for ch in chamadas_processadas.values():
        dt = ch.get("dt")
        if limite_tempo and dt and dt < limite_tempo:
            continue

        prov = ch.get("provedor") or "outros"
        if prov not in estatisticas_provedores:
            estatisticas_provedores[prov] = {
                "requisicoes": 0,
                "requisicoes_sucesso": 0,
                "requisicoes_erro": 0,
                "tokens_entrada": 0,
                "tokens_saida": 0,
                "tokens_total": 0,
                "custo_usd": 0.0,
                "economia_usd": 0.0,
                "reqs_ultimo_minuto": 0,
                "erros_rate_limit": 0,
                "modelos_uso": {},
            }
            if prov not in provedores_dict:
                provedores_dict[prov] = {
                    "id": prov,
                    "nome": prov.capitalize(),
                    "tier": "OUTROS",
                    "ativo": True,
                    "chave": None,
                    "chave_configurada": True,
                    "site_chave": "",
                    "limites": {},
                    "fonte_limites": "",
                    "modelos_cadastrados": [],
                }

        ep = estatisticas_provedores[prov]
        ep["requisicoes"] += 1
        total_requisicoes_geral += 1

        if ch["ok"]:
            ep["requisicoes_sucesso"] += 1
        else:
            ep["requisicoes_erro"] += 1
            err_str = str(ch.get("erro") or "")
            if "429" in err_str or "ratelimit" in err_str.lower() or "quota" in err_str.lower():
                ep["erros_rate_limit"] += 1

        t_in = ch["prompt_tokens"]
        t_out = ch["completion_tokens"]
        t_tot = ch["total_tokens"] or (t_in + t_out)
        spend = ch["spend"]

        ep["tokens_entrada"] += t_in
        ep["tokens_saida"] += t_out
        ep["tokens_total"] += t_tot
        ep["custo_usd"] += spend

        total_tokens_geral += t_tot
        total_entrada_geral += t_in
        total_saida_geral += t_out
        total_custo_geral += spend

        # Economia gerada se o provedor for FREE ou LOCAL
        tier = provedores_dict[prov].get("tier")
        if tier in ("FREE", "LOCAL"):
            econ = calcular_economia_tokens(t_in, t_out, ch["modelo"], precos_ref)
            ep["economia_usd"] += econ
            total_economia_geral += econ

        # Requisição no último minuto para RPM
        if dt and dt >= um_minuto_atras:
            ep["reqs_ultimo_minuto"] += 1

        # Acúmulo por modelo
        mod_key = ch["modelo"] or "desconhecido"
        if mod_key not in ep["modelos_uso"]:
            ep["modelos_uso"][mod_key] = {
                "modelo": mod_key,
                "requisicoes": 0,
                "tokens_entrada": 0,
                "tokens_saida": 0,
                "tokens_total": 0,
                "custo_usd": 0.0,
                "economia_usd": 0.0,
                "ultimo_uso": dt.isoformat() if dt else None,
            }
        mu = ep["modelos_uso"][mod_key]
        mu["requisicoes"] += 1
        mu["tokens_entrada"] += t_in
        mu["tokens_saida"] += t_out
        mu["tokens_total"] += t_tot
        mu["custo_usd"] += spend
        if tier in ("FREE", "LOCAL"):
            mu["economia_usd"] += calcular_economia_tokens(t_in, t_out, mod_key, precos_ref)
        if dt:
            mu["ultimo_uso"] = dt.isoformat()

    # Formatar lista final de provedores com indicadores de alerta e cotas
    lista_provedores_resp = []
    alertas_criticos_count = 0

    for pid, pbase in provedores_dict.items():
        ep = estatisticas_provedores.get(pid, {
            "requisicoes": 0, "requisicoes_sucesso": 0, "requisicoes_erro": 0,
            "tokens_entrada": 0, "tokens_saida": 0, "tokens_total": 0,
            "custo_usd": 0.0, "economia_usd": 0.0, "reqs_ultimo_minuto": 0,
            "erros_rate_limit": 0, "modelos_uso": {},
        })

        limites = pbase.get("limites") or {}
        rpd_limite = limites.get("rpd")
        rpm_limite = limites.get("rpm")
        usd_dia_limite = limites.get("usd_dia")

        pct_rpd = None
        if rpd_limite and rpd_limite > 0:
            pct_rpd = round((ep["requisicoes"] / float(rpd_limite)) * 100.0, 1)

        pct_rpm = None
        if rpm_limite and rpm_limite > 0:
            pct_rpm = round((ep["reqs_ultimo_minuto"] / float(rpm_limite)) * 100.0, 1)

        pct_usd = None
        if usd_dia_limite and usd_dia_limite > 0:
            pct_usd = round((ep["custo_usd"] / float(usd_dia_limite)) * 100.0, 1)

        # Status do alerta
        status_alerta = "normal"
        motivo_alerta = "Dentro dos limites operacionais"

        if ep["erros_rate_limit"] > 0:
            status_alerta = "rate_limited"
            motivo_alerta = f"{ep['erros_rate_limit']} requisições bloqueadas por Rate Limit (HTTP 429)"
            alertas_criticos_count += 1
        elif pct_rpd is not None and pct_rpd >= 90.0:
            status_alerta = "critico"
            motivo_alerta = f"Quota diária em {pct_rpd}% ({ep['requisicoes']}/{rpd_limite} RPD)"
            alertas_criticos_count += 1
        elif pct_rpd is not None and pct_rpd >= 70.0:
            status_alerta = "atencao"
            motivo_alerta = f"Quota diária em {pct_rpd}% ({ep['requisicoes']}/{rpd_limite} RPD)"
        elif pct_rpm is not None and pct_rpm >= 80.0:
            status_alerta = "atencao"
            motivo_alerta = f"Pico por minuto em {pct_rpm}% ({ep['reqs_ultimo_minuto']}/{rpm_limite} RPM)"

        # Lista de modelos ordenados por volume de tokens
        modelos_ordenados = sorted(
            ep["modelos_uso"].values(),
            key=lambda x: x["tokens_total"],
            reverse=True
        )

        lista_provedores_resp.append({
            "id": pid,
            "nome": pbase["nome"],
            "tier": pbase["tier"],
            "ativo": pbase["ativo"],
            "chave": pbase.get("chave"),
            "chave_configurada": pbase["chave_configurada"],
            "site_chave": pbase.get("site_chave"),
            "limites": limites,
            "fonte_limites": pbase.get("fonte_limites"),
            "consumo": {
                "requisicoes": ep["requisicoes"],
                "requisicoes_sucesso": ep["requisicoes_sucesso"],
                "requisicoes_erro": ep["requisicoes_erro"],
                "tokens_entrada": ep["tokens_entrada"],
                "tokens_saida": ep["tokens_saida"],
                "tokens_total": ep["tokens_total"],
                "custo_usd": round(ep["custo_usd"], 5),
                "economia_usd": round(ep["economia_usd"], 4),
                "rpm_atual": ep["reqs_ultimo_minuto"],
                "pct_rpd": pct_rpd,
                "pct_rpm": pct_rpm,
                "pct_usd": pct_usd,
                "status_alerta": status_alerta,
                "motivo_alerta": motivo_alerta,
            },
            "modelos": modelos_ordenados,
            "modelos_cadastrados": pbase.get("modelos_cadastrados", []),
        })

    # Ordenar provedores: primeiro com tráfego, depois por tokens decrescente
    lista_provedores_resp.sort(
        key=lambda x: (x["consumo"]["tokens_total"] > 0, x["consumo"]["tokens_total"], x["ativo"]),
        reverse=True
    )

    # Distribuição percentual para gráfico/breakdown
    distribuicao = []
    cores_tier = {
        "LOCAL": "#10b981",    # verde esmeralda
        "FREE": "#3b82f6",     # azul primário
        "PAID": "#f59e0b",     # âmbar/ouro
        "OUTROS": "#8b5cf6",   # roxo
    }
    for prov in lista_provedores_resp:
        t_tok = prov["consumo"]["tokens_total"]
        if t_tok > 0:
            pct = round((t_tok / float(total_tokens_geral)) * 100.0, 1) if total_tokens_geral > 0 else 0.0
            distribuicao.append({
                "provedor_id": prov["id"],
                "nome": prov["nome"],
                "tier": prov["tier"],
                "tokens": t_tok,
                "pct": pct,
                "cor": cores_tier.get(prov["tier"], "#6b7280"),
            })

    # Ranking geral de modelos mais consumidos
    ranking_modelos = []
    for prov in lista_provedores_resp:
        for m in prov["modelos"]:
            ranking_modelos.append({
                **m,
                "provedor_id": prov["id"],
                "provedor_nome": prov["nome"],
                "tier": prov["tier"],
                "pct_do_total": round((m["tokens_total"] / float(total_tokens_geral)) * 100.0, 1) if total_tokens_geral > 0 else 0.0
            })
    ranking_modelos.sort(key=lambda x: x["tokens_total"], reverse=True)

    return {
        "periodo_horas": periodo_horas,
        "resumo": {
            "total_tokens": total_tokens_geral,
            "total_entrada": total_entrada_geral,
            "total_saida": total_saida_geral,
            "total_requisicoes": total_requisicoes_geral,
            "custo_total_usd": round(total_custo_geral, 5),
            "economia_estimada_usd": round(total_economia_geral, 4),
            "provedores_com_trafego": sum(1 for p in lista_provedores_resp if p["consumo"]["tokens_total"] > 0),
            "total_provedores": len(lista_provedores_resp),
            "alertas_criticos": alertas_criticos_count,
        },
        "distribuicao": distribuicao,
        "provedores": lista_provedores_resp,
        "ranking_modelos": ranking_modelos[:20],
    }

"""Serviço para gerenciamento dinâmico e auto-vinculação dos grupos do roteador LiteLLM."""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Any

import yaml

from tudoia_painel.catalogo import carregar_catalogo, provedores_ligados
from tudoia_painel.envfile import ler_env
from tudoia_painel.gerador import regenerar_config_litellm
from tudoia_painel.regras import carregar_modulo_regras

RE_GRUPO_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")

GRUPOS_CANONICOS = {
    "tudoia-nuvem": {
        "nome": "tudoia-nuvem",
        "titulo": "Nuvem Geral (Chat & Raciocínio Rápido)",
        "descricao": "Respostas rápidas e tarefas gerais de nuvem gratuita roteadas por menor latência.",
        "papeis": ["chat", "rapido", "raciocinio"],
        "tier": "FREE",
    },
    "tudoia-codigo": {
        "nome": "tudoia-codigo",
        "titulo": "Código & Agentes (Tool Use)",
        "descricao": "Modelos com suporte a ferramentas e chamadas de função (Claude Code, Cursor, Codex).",
        "papeis": ["codigo", "agente"],
        "tier": "FREE",
    },
    "tudoia-codigo-reserva": {
        "nome": "tudoia-codigo-reserva",
        "titulo": "Reserva de Código (Fallback de Nuvem)",
        "descricao": "Outro provedor de nuvem acionado quando o pool principal de código der 429 ou timeout.",
        "papeis": ["codigo", "agente", "chat"],
        "tier": "FREE",
    },
    "tudoia-visao": {
        "nome": "tudoia-visao",
        "titulo": "Visão Computacional & Multimodal",
        "descricao": "Acionado automaticamente para prompts que contêm imagens ou capturas de tela.",
        "papeis": ["visao"],
        "tier": "FREE",
    },
    "tudoia-max": {
        "nome": "tudoia-max",
        "titulo": "Modelos Pagos de Alta Inteligência",
        "descricao": "APIs comerciais (Claude Sonnet/Opus, GPT, DeepSeek) acionadas por #max ou roteamento explícito.",
        "papeis": ["chat", "codigo", "agente", "raciocinio"],
        "tier": "PAID",
    },
}

# Grupos fundamentais que não podem ser completamente excluídos (apenas desativados se desejado)
GRUPOS_PROTEGIDOS = {"tudoia-nuvem", "tudoia-codigo"}


def gravar_yaml_atomico(caminho: Path, dados: dict) -> None:
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    conteudo = yaml.dump(dados, allow_unicode=True, sort_keys=False, default_flow_style=False)

    fd, tmp_path = tempfile.mkstemp(dir=caminho.parent, prefix="rot_", suffix=".tmp")
    try:
        with open(fd, "w", encoding="utf-8") as f:
            f.write(conteudo)
        os.replace(tmp_path, caminho)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def obter_detalhes_grupos_roteador(raiz: Path) -> dict[str, Any]:
    raiz = Path(raiz)
    catalogo = carregar_catalogo(raiz / "config" / "catalogo-modelos.yaml")
    caminho_rot = raiz / "config" / "roteamento.yaml"
    roteamento = yaml.safe_load(caminho_rot.read_text(encoding="utf-8")) or {}
    env = ler_env(raiz / ".env")

    ordem_atual = roteamento.get("ordem") or {}
    desativados = set(roteamento.get("grupos_desativados") or [])
    customizados = roteamento.get("grupos_customizados") or {}

    # Mapear todos os modelos do catálogo
    todos_modelos: dict[str, dict[str, Any]] = {}
    for prov in catalogo.provedores:
        tem_chave = all(bool(env.get(k, "").strip()) for k in prov.todas_as_chaves())
        for m in prov.modelos:
            todos_modelos[m.nome] = {
                "nome": m.nome,
                "id": m.id,
                "provedor_id": prov.chave_id,
                "provedor_nome": prov.nome,
                "tier": prov.tier,
                "papeis": list(m.papeis),
                "ativo": m.ativo,
                "tem_chave": tem_chave,
                "contexto": m.contexto,
            }

    # Todos os grupos conhecidos (canônicos + presentes na ordem)
    todos_grupos_chaves = list(GRUPOS_CANONICOS.keys())
    for gid in ordem_atual:
        if gid not in todos_grupos_chaves:
            todos_grupos_chaves.append(gid)

    grupos_resultado = []
    for gid in todos_grupos_chaves:
        membros_nomes = ordem_atual.get(gid, [])
        membros_detalhados = []
        for nome in membros_nomes:
            if nome in todos_modelos:
                membros_detalhados.append(todos_modelos[nome])
            else:
                membros_detalhados.append({
                    "nome": nome,
                    "id": nome,
                    "provedor_id": "desconhecido",
                    "provedor_nome": "Desconhecido",
                    "tier": "FREE",
                    "papeis": [],
                    "ativo": False,
                    "tem_chave": False,
                    "contexto": None,
                })

        gmeta = GRUPOS_CANONICOS.get(gid) or customizados.get(gid) or {
            "titulo": gid.replace("tudoia-", "").capitalize(),
            "descricao": "Grupo customizado de roteamento LiteLLM",
            "tier": "FREE",
            "papeis": ["chat", "codigo"]
        }

        papeis_alvo = set(gmeta.get("papeis") or [])
        tier_alvo = gmeta.get("tier", "FREE")
        membros_set = set(membros_nomes)

        elegiveis = []
        for mnome, mdata in todos_modelos.items():
            if mnome in membros_set:
                continue
            if mdata["tier"] != tier_alvo:
                continue
            if not papeis_alvo or any(p in papeis_alvo for p in mdata["papeis"]):
                elegiveis.append(mdata)

        elegiveis.sort(key=lambda x: (x["tem_chave"], x["ativo"]), reverse=True)

        grupos_resultado.append({
            "id": gid,
            "titulo": gmeta.get("titulo", gid),
            "descricao": gmeta.get("descricao", ""),
            "tier": tier_alvo,
            "papeis_esperados": list(papeis_alvo),
            "ativo": gid not in desativados,
            "pode_excluir": gid not in GRUPOS_PROTEGIDOS,
            "membros": membros_detalhados,
            "modelos_elegiveis": elegiveis,
        })

    return {
        "limiar": roteamento.get("limiar", 3),
        "pesos": roteamento.get("pesos", {}),
        "limites_texto": roteamento.get("limites_texto", {}),
        "grupos": grupos_resultado
    }


def salvar_composicao_grupos(raiz: Path, nova_ordem: dict[str, list[str]]) -> dict[str, Any]:
    raiz = Path(raiz)
    caminho_rot = raiz / "config" / "roteamento.yaml"
    roteamento = yaml.safe_load(caminho_rot.read_text(encoding="utf-8")) or {}

    ordem_atual = roteamento.setdefault("ordem", {})
    for gid, membros in nova_ordem.items():
        if isinstance(membros, list):
            ordem_atual[gid] = [str(m).strip() for m in membros if str(m).strip()]

    regras_modulo = carregar_modulo_regras()
    regras_modulo.validar_regras(roteamento)
    gravar_yaml_atomico(caminho_rot, roteamento)

    _sincronizar_litellm_silencioso(raiz, caminho_rot)
    return {"ok": True, "ordem": roteamento["ordem"]}


def criar_grupo_roteador(
    raiz: Path,
    id_grupo: str | None = None,
    titulo: str | None = None,
    descricao: str | None = None,
    modelos: list[str] | None = None,
    tier: str = "FREE",
    dados: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raiz = Path(raiz)
    d = dict(dados or {})
    if id_grupo:
        d["id"] = id_grupo
    if titulo:
        d["titulo"] = titulo
    if descricao is not None:
        d["descricao"] = descricao
    if modelos is not None:
        d["membros"] = modelos
    if tier:
        d.setdefault("tier", tier)

    gid = str(d.get("id", "")).lower().strip()
    if not RE_GRUPO_ID.match(gid):
        raise ValueError(f"ID de grupo inválido '{gid}'. Use letras minúsculas, números e hífens.")

    caminho_rot = raiz / "config" / "roteamento.yaml"
    roteamento = yaml.safe_load(caminho_rot.read_text(encoding="utf-8")) or {}
    ordem = roteamento.setdefault("ordem", {})
    if gid in ordem:
        raise ValueError(f"Grupo '{gid}' já existe.")

    titulo_final = str(d.get("titulo", "")).strip() or gid
    descricao_final = str(d.get("descricao", "")).strip() or "Grupo customizado"
    tier_final = str(d.get("tier", "FREE")).upper().strip()
    if tier_final not in ("FREE", "PAID"):
        raise ValueError("Tier deve ser 'FREE' ou 'PAID'")

    membros = d.get("membros") or []
    if not isinstance(membros, list):
        membros = []

    ordem[gid] = [str(m).strip() for m in membros if str(m).strip()]

    customizados = roteamento.setdefault("grupos_customizados", {})
    customizados[gid] = {
        "titulo": titulo_final,
        "descricao": descricao_final,
        "tier": tier_final,
        "papeis": d.get("papeis") or ["chat"]
    }

    regras_modulo = carregar_modulo_regras()
    regras_modulo.validar_regras(roteamento)
    gravar_yaml_atomico(caminho_rot, roteamento)
    _sincronizar_litellm_silencioso(raiz, caminho_rot)

    return {"ok": True, "id": gid, "titulo": titulo_final}


def atualizar_grupo_roteador(
    raiz: Path,
    grupo_id: str,
    titulo: str | None = None,
    descricao: str | None = None,
    ativo: bool | None = None,
    modelos: list[str] | None = None,
    dados: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raiz = Path(raiz)
    d = dict(dados or {})
    if titulo is not None:
        d["titulo"] = titulo
    if descricao is not None:
        d["descricao"] = descricao
    if ativo is not None:
        d["ativo"] = ativo
    if modelos is not None:
        d["membros"] = modelos

    caminho_rot = raiz / "config" / "roteamento.yaml"
    roteamento = yaml.safe_load(caminho_rot.read_text(encoding="utf-8")) or {}
    ordem = roteamento.setdefault("ordem", {})
    if grupo_id not in ordem and grupo_id not in GRUPOS_CANONICOS:
        raise ValueError(f"Grupo '{grupo_id}' não encontrado.")

    # Ativação / Desativação
    desativados = set(roteamento.setdefault("grupos_desativados", []))
    if "ativo" in d:
        if d["ativo"] is False:
            desativados.add(grupo_id)
        else:
            desativados.discard(grupo_id)
        roteamento["grupos_desativados"] = sorted(list(desativados))

    # Atualização de membros se fornecido
    if "membros" in d and isinstance(d["membros"], list):
        ordem[grupo_id] = [str(m).strip() for m in d["membros"] if str(m).strip()]

    # Título e Descrição
    customizados = roteamento.setdefault("grupos_customizados", {})
    info_meta = customizados.setdefault(grupo_id, {})
    if "titulo" in d and d["titulo"]:
        info_meta["titulo"] = str(d["titulo"]).strip()
    if "descricao" in d and d["descricao"] is not None:
        info_meta["descricao"] = str(d["descricao"]).strip()

    regras_modulo = carregar_modulo_regras()
    regras_modulo.validar_regras(roteamento)
    gravar_yaml_atomico(caminho_rot, roteamento)
    _sincronizar_litellm_silencioso(raiz, caminho_rot)

    return {"ok": True, "id": grupo_id, "ativo": grupo_id not in desativados}


def excluir_grupo_roteador(raiz: Path, grupo_id: str) -> dict[str, Any]:
    raiz = Path(raiz)
    if grupo_id in GRUPOS_PROTEGIDOS:
        raise ValueError(f"O grupo base '{grupo_id}' não pode ser excluído; você pode desativá-lo.")

    caminho_rot = raiz / "config" / "roteamento.yaml"
    roteamento = yaml.safe_load(caminho_rot.read_text(encoding="utf-8")) or {}
    ordem = roteamento.setdefault("ordem", {})

    ordem.pop(grupo_id, None)
    desativados = set(roteamento.get("grupos_desativados") or [])
    desativados.discard(grupo_id)
    roteamento["grupos_desativados"] = sorted(list(desativados))

    customizados = roteamento.get("grupos_customizados") or {}
    customizados.pop(grupo_id, None)

    regras_modulo = carregar_modulo_regras()
    regras_modulo.validar_regras(roteamento)
    gravar_yaml_atomico(caminho_rot, roteamento)
    _sincronizar_litellm_silencioso(raiz, caminho_rot)

    return {"ok": True, "id": grupo_id, "mensagem": f"Grupo '{grupo_id}' excluído com sucesso."}


def auto_vincular_modelos_por_papeis(raiz: Path) -> dict[str, Any]:
    raiz = Path(raiz)
    caminho_rot = raiz / "config" / "roteamento.yaml"
    roteamento = yaml.safe_load(caminho_rot.read_text(encoding="utf-8")) or {}
    catalogo = carregar_catalogo(raiz / "config" / "catalogo-modelos.yaml")
    env = ler_env(raiz / ".env")

    provs_ativos = provedores_ligados(catalogo, env)
    ordem = roteamento.setdefault("ordem", {})

    for gid in GRUPOS_CANONICOS:
        if gid not in ordem:
            ordem[gid] = []

    modelos_vinculados_count = 0

    for prov in provs_ativos:
        for m in prov.modelos:
            if not m.ativo:
                continue

            papeis_set = set(m.papeis)

            # 1. TudoIA Nuvem (chat / rapido / raciocinio em tier FREE)
            if prov.tier == "FREE" and (papeis_set.intersection({"chat", "rapido", "raciocinio"})):
                if m.nome not in ordem["tudoia-nuvem"]:
                    ordem["tudoia-nuvem"].append(m.nome)
                    modelos_vinculados_count += 1

            # 2. TudoIA Código (codigo / agente em tier FREE)
            if prov.tier == "FREE" and (papeis_set.intersection({"codigo", "agente"})):
                if m.nome not in ordem["tudoia-codigo"]:
                    ordem["tudoia-codigo"].append(m.nome)
                    modelos_vinculados_count += 1
                if "tudoia-codigo-reserva" in ordem and m.nome not in ordem["tudoia-codigo-reserva"] and m.nome != ordem["tudoia-codigo"][0]:
                    if len(ordem["tudoia-codigo-reserva"]) < 4:
                        ordem["tudoia-codigo-reserva"].append(m.nome)

            # 3. TudoIA Visão (visao em tier FREE)
            if prov.tier == "FREE" and "visao" in papeis_set:
                if m.nome not in ordem["tudoia-visao"]:
                    ordem["tudoia-visao"].append(m.nome)
                    modelos_vinculados_count += 1

            # 4. TudoIA Max (tier PAID)
            if prov.tier == "PAID":
                if m.nome not in ordem["tudoia-max"]:
                    ordem["tudoia-max"].append(m.nome)
                    modelos_vinculados_count += 1

    regras_modulo = carregar_modulo_regras()
    regras_modulo.validar_regras(roteamento)
    gravar_yaml_atomico(caminho_rot, roteamento)
    _sincronizar_litellm_silencioso(raiz, caminho_rot)

    return {
        "ok": True,
        "modelos_vinculados": modelos_vinculados_count,
        "ordem": ordem
    }


def _sincronizar_litellm_silencioso(raiz: Path, caminho_rot: Path) -> None:
    regenerar_config_litellm(raiz)

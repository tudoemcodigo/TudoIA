"""Serviço para gerenciamento dinâmico e auto-vinculação dos grupos do roteador LiteLLM."""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Any

import httpx
import yaml

from tudoia_painel.catalogo import carregar_catalogo, provedores_ligados
from tudoia_painel.envfile import ler_env
from tudoia_painel.gerador import regenerar_config_litellm
from tudoia_painel.regras import carregar_modulo_regras
from tudoia_painel import upstreams

RE_GRUPO_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")

GRUPOS_CANONICOS: dict[str, dict[str, Any]] = {}

# Grupos fundamentais que não podem ser completamente excluídos (apenas desativados se desejado)
GRUPOS_PROTEGIDOS: set[str] = set()


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
                "origem": "nuvem",
                "contexto": m.contexto,
            }

    # Modelos locais reais instalados no Ollama (apenas modelos que existem fisicamente)
    modelos_locais_nomes: list[str] = []
    try:
        ollama_url = env.get("OLLAMA_URL") or upstreams.OLLAMA
        with httpx.Client(timeout=0.6) as cliente:
            resp = cliente.get(f"{ollama_url}/api/tags")
            if resp.status_code == 200:
                for item in resp.json().get("models", []):
                    tag_nome = item.get("name", "")
                    if tag_nome:
                        nome_com_prefixo = f"local/{tag_nome}"
                        if nome_com_prefixo not in modelos_locais_nomes:
                            modelos_locais_nomes.append(nome_com_prefixo)
    except Exception:
        pass

    for mlocal in modelos_locais_nomes:
        papeis_loc = ["codigo", "agente"] if ("agente" in mlocal or "coder" in mlocal) else ["chat"]
        todos_modelos[mlocal] = {
            "nome": mlocal,
            "id": mlocal.removeprefix("local/"),
            "provedor_id": "local",
            "provedor_nome": "Ollama Local",
            "tier": "LOCAL",
            "papeis": papeis_loc,
            "ativo": True,
            "tem_chave": True,
            "origem": "local",
            "contexto": 30000,
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
            elif nome.startswith("local/"):
                membros_detalhados.append({
                    "nome": nome,
                    "id": nome.removeprefix("local/"),
                    "provedor_id": "local",
                    "provedor_nome": "Ollama Local",
                    "tier": "LOCAL",
                    "papeis": ["chat"],
                    "ativo": True,
                    "tem_chave": True,
                    "origem": "local",
                    "contexto": 30000,
                })
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
                    "origem": "nuvem",
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

            compativel_tier = (mdata.get("tier") == tier_alvo) or (mdata.get("tier") == "LOCAL")
            compativel_papel = not papeis_alvo or any(p in papeis_alvo for p in mdata.get("papeis", []))
            recomendado = bool(compativel_tier and compativel_papel)

            copia = dict(mdata)
            copia["recomendado"] = recomendado
            elegiveis.append(copia)

        # Ordenar: recomendados primeiro, depois chaves/locais, depois ativos, e alfabético por nome
        elegiveis.sort(
            key=lambda x: (
                1 if x.get("recomendado") else 0,
                1 if x.get("tem_chave") else 0,
                1 if x.get("origem") == "local" else 0,
                1 if x.get("ativo") else 0,
                x.get("nome", "")
            ),
            reverse=True,
        )

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
        "papeis": d.get("papeis") or ["chat", "codigo", "agente", "raciocinio", "rapido"]
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
    customizados = roteamento.get("grupos_customizados") or {}

    for gid in GRUPOS_CANONICOS:
        if gid not in ordem:
            ordem[gid] = []

    modelos_vinculados_count = 0

    for prov in provs_ativos:
        for m in prov.modelos:
            if not m.ativo:
                continue

            papeis_set = set(m.papeis)

            for gid, lista_membros in ordem.items():
                gmeta = GRUPOS_CANONICOS.get(gid) or customizados.get(gid) or {}
                tier_alvo = gmeta.get("tier", "FREE")
                papeis_alvo = set(gmeta.get("papeis") or ["chat", "codigo"])
                if prov.tier == tier_alvo and (not papeis_alvo or papeis_set.intersection(papeis_alvo)):
                    if m.nome not in lista_membros:
                        lista_membros.append(m.nome)
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

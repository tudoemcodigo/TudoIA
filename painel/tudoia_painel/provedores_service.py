"""Serviço para gerenciamento dinâmico de provedores e descoberta de modelos em nuvem."""
from __future__ import annotations

import os
import re
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

import httpx
import yaml

from tudoia_painel.envfile import gravar_valor, ler_env

RE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
RE_CHAVE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")

# Heurística de papéis pelo ID do modelo. Só o ID: descrições citam 'code' ou 'vision' sem o modelo ser desse papel.
PAPEIS_POR_TERMO_NO_ID = (
    ("codigo", ("code", "coder")),
    ("visao", ("vision", "-vl", "vlm")),
    ("raciocinio", ("reason", "think", "-r1", "magistral")),
)


class FalhaApi(RuntimeError):
    """A consulta ao endpoint de modelos do provedor falhou. Quem chama não deve alterar o catálogo desse provedor."""

    def __init__(self, mensagem: str, status_code: int = 0):
        super().__init__(mensagem)
        self.status_code = status_code


def gravar_yaml_atomico(caminho: Path, dados: dict) -> None:
    """Gravação atômica em arquivo YAML para prevenir corrupção fail-closed."""
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    conteudo = yaml.dump(dados, allow_unicode=True, sort_keys=False, default_flow_style=False)

    fd, tmp_path = tempfile.mkstemp(dir=caminho.parent, prefix="cat_", suffix=".tmp")
    try:
        with open(fd, "w", encoding="utf-8") as f:
            f.write(conteudo)
        os.replace(tmp_path, caminho)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def cadastrar_provedor(
    caminho_yaml: Path,
    caminho_env: Path,
    dados: dict[str, Any],
    dir_backup: Path | None = None
) -> dict[str, Any]:
    """Valida e cadastra um novo provedor no catálogo e opcionalmente grava chave no .env."""
    pid = str(dados.get("id", "")).lower().strip()
    if not RE_ID.match(pid):
        raise ValueError(f"ID de provedor inválido '{pid}'. Use apenas letras minúsculas, números e hífens.")

    nome = str(dados.get("nome", "")).strip() or pid.upper()
    tier = str(dados.get("tier", "FREE")).upper().strip()
    if tier not in ("FREE", "PAID"):
        raise ValueError("Tier deve ser 'FREE' ou 'PAID'.")

    chave = str(dados.get("chave", "")).strip().upper()
    if not RE_CHAVE.match(chave):
        raise ValueError(f"Nome da variável de chave inválido '{chave}'. Use padrão 'NOME_PROVEDOR_API_KEY'.")

    # Campo opcional chega como None quando ausente; str(None) viraria o texto "None", que passa como URL
    site_chave = (dados.get("site_chave") or "").strip()
    api_base = (dados.get("api_base") or "").strip() or None
    url_modelos = (dados.get("url_modelos") or "").strip() or None
    fonte_limites = str(dados.get("fonte_limites", "")).strip() or "Configurado pelo usuário no painel"

    limites = dados.get("limites") or {}
    if not isinstance(limites, dict):
        limites = {}

    caminho_yaml = Path(caminho_yaml)
    catalogo_dados = {}
    if caminho_yaml.is_file():
        catalogo_dados = yaml.safe_load(caminho_yaml.read_text(encoding="utf-8")) or {}

    provedores = catalogo_dados.setdefault("provedores", {})
    if pid in provedores:
        raise ValueError(f"Provedor com ID '{pid}' já está cadastrado no catálogo.")

    novo_entry = {
        "nome": nome,
        "tier": tier,
        "chave": chave,
        "site_chave": site_chave,
        "limites": limites,
        "fonte_limites": fonte_limites,
        "modelos": []
    }
    if api_base:
        novo_entry["api_base"] = api_base
    if url_modelos:
        novo_entry["url_modelos"] = url_modelos

    provedores[pid] = novo_entry
    gravar_yaml_atomico(caminho_yaml, catalogo_dados)

    # Se informou o valor da chave, grava no .env
    valor_chave = str(dados.get("valor_chave", "")).strip()
    if valor_chave:
        backup = dir_backup or (caminho_env.parent / "dados" / "backups" / "env")
        gravar_valor(caminho_env, chave, valor_chave, backup)

    return {"ok": True, "id": pid, "nome": nome, "tier": tier, "chave": chave}


def _extrair_modelos(dados_api: Any) -> list[dict[str, Any]]:
    """Normaliza a resposta de listagem de modelos (formatos OpenAI, Gemini e lista pura)."""
    modelos_api: list[dict[str, Any]] = []

    if isinstance(dados_api, dict):
        if "data" in dados_api and isinstance(dados_api["data"], list):
            for item in dados_api["data"]:
                if isinstance(item, dict) and "id" in item:
                    mid = item["id"]
                    is_free = ":free" in mid or bool(item.get("pricing", {}).get("prompt") == "0")
                    modelos_api.append({
                        "id": mid,
                        "nome": item.get("name") or mid,
                        "contexto": item.get("context_length"),
                        "free": is_free,
                        "descricao": item.get("description", "")
                    })
        elif "result" in dados_api and isinstance(dados_api["result"], list):
            # Cloudflare Workers AI: o ID que o LiteLLM usa é o `name` (@cf/...); o `id` é um UUID interno.
            for item in dados_api["result"]:
                if isinstance(item, dict) and item.get("name"):
                    modelos_api.append({
                        "id": item["name"],
                        "nome": item["name"],
                        "contexto": None,
                        "free": False,
                        "descricao": item.get("description", "")
                    })
        elif "models" in dados_api and isinstance(dados_api["models"], list):
            for item in dados_api["models"]:
                if isinstance(item, dict):
                    mid = item.get("name") or item.get("id") or ""
                    modelos_api.append({
                        "id": mid.replace("models/", ""),
                        "nome": item.get("displayName") or mid,
                        "contexto": item.get("inputTokenLimit"),
                        "free": False,
                        "descricao": item.get("description", "")
                    })
    elif isinstance(dados_api, list):
        for item in dados_api:
            if isinstance(item, dict) and "id" in item:
                modelos_api.append({
                    "id": item["id"],
                    "nome": item.get("name") or item["id"],
                    "contexto": item.get("context_length"),
                    "free": ":free" in item["id"],
                    "descricao": ""
                })
    return modelos_api


RE_VARIAVEL_URL = re.compile(r"\{([A-Z][A-Z0-9_]*)\}")


def _resolver_url(url: str, env: dict[str, str]) -> str:
    """Substitui {VARIAVEL} da URL pelo valor do .env. Variável ausente vira FalhaApi com o nome dela."""
    def trocar(m: re.Match) -> str:
        valor = env.get(m.group(1), "").strip()
        if not valor:
            raise FalhaApi(f"Variável {m.group(1)} não configurada no .env (necessária para montar a URL de modelos)")
        return valor
    return RE_VARIAVEL_URL.sub(trocar, url)


def _montar_cabecalhos(url: str, token: str) -> dict[str, str]:
    """Cada API de listagem tem seu header de autenticação. Gemini (API nativa) não aceita Bearer."""
    headers = {"User-Agent": "TudoIA-Scanner/1.0"}
    if not token:
        return headers
    if "anthropic.com" in url:
        headers["x-api-key"] = token
        headers["anthropic-version"] = "2023-06-01"
    elif "googleapis.com" in url:
        headers["x-goog-api-key"] = token
    else:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _buscar_modelos_api(p: dict[str, Any], caminho_env: Path) -> list[dict[str, Any]]:
    """Consulta a url_modelos do provedor. Levanta FalhaApi em qualquer erro de rede, status ou formato."""
    env = ler_env(caminho_env)
    url = _resolver_url(p["url_modelos"], env)
    chave = p.get("chave", "")
    token = env.get(chave, "").strip()
    headers = _montar_cabecalhos(url, token)

    modelos: list[dict[str, Any]] = []
    params = _primeira_pagina(url)
    try:
        # Sem seguir redirecionamento: x-api-key e x-goog-api-key não são removidos pelo httpx ao trocar de host.
        with httpx.Client(timeout=10.0, follow_redirects=False) as cliente:
            for _ in range(MAX_PAGINAS):
                resp = cliente.get(url, headers=headers, params=params)
                if resp.status_code in (401, 403) and not token:
                    raise FalhaApi(f"Chave {chave} não configurada no .env (a API recusou a consulta sem autenticação)",
                                   status_code=resp.status_code)
                if resp.status_code != 200:
                    raise FalhaApi(
                        f"API externa retornou status {resp.status_code}: {resp.text[:200]}",
                        status_code=resp.status_code,
                    )
                dados_api = resp.json()
                modelos.extend(_extrair_modelos(dados_api))
                params = _proxima_pagina(dados_api, params)
                if params is None:
                    return modelos
    except FalhaApi:
        raise
    except Exception as e:
        raise FalhaApi(f"Falha de conexão com a API ({type(e).__name__}): {str(e)}") from e
    # Lista incompleta não pode virar "descontinuado": a sincronização inativaria quem está nas páginas seguintes.
    raise FalhaApi(f"Listagem com mais de {MAX_PAGINAS} páginas: resposta tratada como incompleta")


MAX_PAGINAS = 20


def _primeira_pagina(url: str) -> dict[str, Any]:
    """Página grande onde a API pagina por padrão (Anthropic: 20 itens, Gemini: 50). As outras devolvem tudo."""
    if "anthropic.com" in url:
        return {"limit": 1000}
    if "googleapis.com" in url:
        return {"pageSize": 1000}
    if "api.cloudflare.com" in url:
        return {"per_page": 100, "page": 1}
    return {}


def _proxima_pagina(dados_api: Any, params: dict[str, Any]) -> dict[str, Any] | None:
    """Parâmetros da próxima página, ou None quando a listagem acabou. Cada API sinaliza do seu jeito."""
    if not isinstance(dados_api, dict):
        return None
    if dados_api.get("has_more") and dados_api.get("last_id"):          # Anthropic
        return {**params, "after_id": dados_api["last_id"]}
    if dados_api.get("nextPageToken"):                                   # Gemini
        return {**params, "pageToken": dados_api["nextPageToken"]}
    info = dados_api.get("result_info")                                 # Cloudflare
    if isinstance(info, dict) and isinstance(dados_api.get("result"), list):
        pagina, por_pagina = int(info.get("page") or params.get("page") or 1), int(info.get("per_page") or 0)
        total = info.get("total_count") or info.get("count")
        paginas = info.get("total_pages")
        tem_mais = (int(paginas) > pagina) if paginas else (
            bool(total) and por_pagina > 0 and pagina * por_pagina < int(total) and len(dados_api["result"]) > 0)
        return {**params, "page": pagina + 1} if tem_mais else None
    return None


def _prefixo_litellm(p: dict[str, Any], provedor_id: str) -> str:
    """Namespace que o LiteLLM usa para o provedor, lido dos IDs já cadastrados (ex.: 'groq', 'openrouter')."""
    contagem = Counter(
        str(m["id"]).split("/", 1)[0]
        for m in p.get("modelos") or []
        if isinstance(m, dict) and "/" in str(m.get("id", ""))
    )
    return contagem.most_common(1)[0][0] if contagem else provedor_id


def _id_na_api(id_catalogo: str, prefixo: str) -> str:
    """'openrouter/google/gemma:free' com prefixo 'openrouter' vira 'google/gemma:free', o ID que a API devolve."""
    return id_catalogo[len(prefixo) + 1:] if id_catalogo.startswith(prefixo + "/") else id_catalogo


def inferir_papeis(mid: str) -> list[str]:
    minusc = mid.lower()
    papeis = [papel for papel, termos in PAPEIS_POR_TERMO_NO_ID if any(t in minusc for t in termos)]
    return papeis or ["chat"]


def _novos_do_provedor(p: dict[str, Any], provedor_id: str, modelos_api: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Modelos que a API oferece e o catálogo ainda não tem, já no formato de entrada do catálogo."""
    prefixo = _prefixo_litellm(p, provedor_id)
    presentes = {
        _id_na_api(str(m.get("id", "")), prefixo)
        for m in p.get("modelos") or []
        if isinstance(m, dict)
    }
    nomes = {m.get("nome") for m in p.get("modelos") or [] if isinstance(m, dict)}

    novos = []
    for m in modelos_api:
        if m["id"] in presentes:
            continue
        id_catalogo = f"{prefixo}/{m['id']}"
        nome = f"{provedor_id}/{m['id'].split('/')[-1].replace(':free', '')}"
        if nome in nomes:
            nome = id_catalogo
        if nome in nomes:
            continue
        entrada = {
            "nome": nome,
            "id": id_catalogo,
            "papeis": inferir_papeis(m["id"]),
            "free": bool(m.get("free")),
        }
        if isinstance(m.get("contexto"), int):
            entrada["contexto"] = m["contexto"]
        novos.append(entrada)
        nomes.add(nome)
    return novos


def descobrir_modelos_api(
    caminho_yaml: Path,
    caminho_env: Path,
    provedor_id: str
) -> dict[str, Any]:
    """Consulta a url_modelos do provedor em tempo real e compara com o catálogo local."""
    caminho_yaml = Path(caminho_yaml)
    catalogo_dados = yaml.safe_load(caminho_yaml.read_text(encoding="utf-8")) or {}
    provedores = catalogo_dados.get("provedores") or {}

    p = provedores.get(provedor_id)
    if not p:
        raise ValueError(f"Provedor '{provedor_id}' não encontrado no catálogo.")

    if not p.get("url_modelos"):
        raise ValueError(f"O provedor '{p.get('nome', provedor_id)}' não possui URL de descoberta ('url_modelos') configurada.")

    try:
        modelos_api = _buscar_modelos_api(p, caminho_env)
    except FalhaApi as e:
        return {
            "ok": False,
            "status_code": e.status_code,
            "erro": str(e),
            "provedor": provedor_id,
            "modelos_cadastrados": p.get("modelos", []),
            "modelos_novos": []
        }

    prefixo = _prefixo_litellm(p, provedor_id)
    api_ids_set = {m["id"] for m in modelos_api}

    cadastrados_analisados = []
    for m in p.get("modelos") or []:
        if not isinstance(m, dict):
            continue
        status_api = "ativo_na_api" if _id_na_api(str(m.get("id", "")), prefixo) in api_ids_set else "ausente_ou_descontinuado"
        cadastrados_analisados.append({**m, "status_api": status_api})

    novos = _novos_do_provedor(p, provedor_id, modelos_api)

    return {
        "ok": True,
        "provedor": provedor_id,
        "nome_provedor": p.get("nome", provedor_id),
        "total_na_api": len(modelos_api),
        "cadastrados": cadastrados_analisados,
        "novos_disponiveis": novos[:100]  # Limita para não saturar payload
    }


def _nomes_e_ids_referenciados(caminho_roteamento: Path) -> set[str]:
    """Todo texto do roteamento. Modelo citado ali não é removido do catálogo, para não quebrar o roteamento."""
    def coletar(dado: Any) -> set[str]:
        if isinstance(dado, str):
            return {dado}
        if isinstance(dado, dict):
            dado = list(dado.values())
        if isinstance(dado, list):
            return set().union(*(coletar(x) for x in dado)) if dado else set()
        return set()

    return coletar(yaml.safe_load(Path(caminho_roteamento).read_text(encoding="utf-8")) or {})


def provedor_configurado(p: dict[str, Any], env: dict[str, str]) -> bool:
    """Verifica se o provedor possui todas as chaves e variáveis obrigatórias configuradas no .env."""
    chave = p.get("chave")
    if chave and not (env.get(chave) or "").strip():
        return False
    chaves_extras = p.get("chaves_extras") or ()
    if isinstance(chaves_extras, (list, tuple)):
        for k in chaves_extras:
            if k and not (env.get(k) or "").strip():
                return False
    url = p.get("url_modelos") or ""
    for var in re.findall(r"\{([A-Za-z0-9_]+)\}", url):
        if not (env.get(var) or "").strip():
            return False
    return True


def buscar_listagens(caminho_yaml: Path, caminho_env: Path) -> dict[str, list[dict[str, Any]] | Exception]:
    """Consulta a listagem de todo provedor com url_modelos. Só rede, nada de disco além da leitura: quem chama
    faz isto FORA da trava do painel (são ~10 APIs de até 10 s) e passa o resultado a `sincronizar_catalogo`."""
    catalogo_dados = yaml.safe_load(Path(caminho_yaml).read_text(encoding="utf-8")) or {}
    env = ler_env(caminho_env)
    listagens: dict[str, list[dict[str, Any]] | Exception] = {}
    for pid, p in (catalogo_dados.get("provedores") or {}).items():
        if isinstance(p, dict) and p.get("url_modelos"):
            if not provedor_configurado(p, env):
                continue
            try:
                listagens[pid] = _buscar_modelos_api(p, caminho_env)
            except Exception as e:  # noqa: BLE001 — a falha de um provedor vira resumo dele, não derruba os outros
                listagens[pid] = e
    return listagens


def sincronizar_catalogo(
    caminho_yaml: Path,
    caminho_env: Path,
    caminho_roteamento: Path,
    aplicar: bool,
    listagens: dict[str, list[dict[str, Any]] | Exception] | None = None,
) -> dict[str, Any]:
    """Adiciona modelos novos (inativos) e remove descontinuados de todos os provedores com url_modelos.

    Com aplicar=False só calcula o resultado, sem gravar. Provedor cuja API falhou não é alterado,
    e lista vazia da API não apaga nada: falha de rede nunca vira remoção. Com `listagens` (de `buscar_listagens`),
    não consulta a rede: o catálogo é relido aqui, então mudanças feitas enquanto a rede respondia não se perdem.
    """
    caminho_yaml = Path(caminho_yaml)
    catalogo_dados = yaml.safe_load(caminho_yaml.read_text(encoding="utf-8")) or {}
    provedores = catalogo_dados.get("provedores") or {}
    referenciados = _nomes_e_ids_referenciados(caminho_roteamento)

    resumo: dict[str, Any] = {}
    alterado = False
    for pid, p in provedores.items():
        if not isinstance(p, dict) or not p.get("url_modelos"):
            continue
        if listagens is not None and pid not in listagens:
            resumo[pid] = {"ok": False, "erro": "provedor não consultado (cadastrado durante a sincronização)"}
            continue
        try:
            obtido = listagens[pid] if listagens is not None else _buscar_modelos_api(p, caminho_env)
            if isinstance(obtido, Exception):
                raise obtido
            modelos_api = obtido
        except Exception as e:
            resumo[pid] = {"ok": False, "erro": str(e)}
            continue

        novos = _novos_do_provedor(p, pid, modelos_api)
        prefixo = _prefixo_litellm(p, pid)
        api_ids_set = {m["id"] for m in modelos_api}
        modelos = p.setdefault("modelos", [])

        inativados, protegidos = [], []
        if modelos_api:
            for m in modelos:
                if not isinstance(m, dict) or not m.get("ativo", True):
                    continue
                if _id_na_api(str(m.get("id", "")), prefixo) in api_ids_set:
                    continue
                if m.get("nome") in referenciados or m.get("id") in referenciados:
                    protegidos.append(m.get("nome"))
                    continue
                m["ativo"] = False
                inativados.append(m.get("nome"))

        adicionados = []
        for entrada in novos:
            modelos.append({**{k: v for k, v in entrada.items() if k != "free"}, "ativo": False})
            adicionados.append(entrada["nome"])

        if adicionados or inativados:
            alterado = True
        resumo[pid] = {
            "ok": True,
            "adicionados": adicionados,
            "inativados": inativados,
            "protegidos_pelo_roteamento": protegidos,
        }

    if aplicar and alterado:
        gravar_yaml_atomico(caminho_yaml, catalogo_dados)
    return {"ok": True, "aplicado": aplicar and alterado, "provedores": resumo}


def listar_novos_catalogo(caminho_yaml: Path, caminho_env: Path, provedor: str | None = None) -> dict[str, Any]:
    """Modelos novos de todos os provedores com url_modelos (ou só de um), sem gravar nada. Para escolher quais incluir."""
    catalogo_dados = yaml.safe_load(Path(caminho_yaml).read_text(encoding="utf-8")) or {}
    provedores = catalogo_dados.get("provedores") or {}
    env = ler_env(caminho_env)
    if provedor is not None and provedor not in provedores:
        raise ValueError(f"Provedor '{provedor}' não encontrado no catálogo.")

    novos, erros = [], {}
    for pid, p in provedores.items():
        if provedor is not None and pid != provedor:
            continue
        if not isinstance(p, dict) or not p.get("url_modelos"):
            if provedor is not None:
                erros[pid] = "Provedor sem url_modelos configurada: não há listagem para consultar."
            continue
        if not provedor_configurado(p, env):
            if provedor is not None:
                chave_nome = p.get("chave") or "chaves necessárias"
                erros[pid] = f"Provedor sem chave configurada no .env ({chave_nome})"
            continue
        try:
            modelos_api = _buscar_modelos_api(p, caminho_env)
        except Exception as e:
            erros[pid] = str(e)
            continue
        for entrada in _novos_do_provedor(p, pid, modelos_api):
            novos.append({"provedor": pid, "tier": str(p.get("tier", "")).upper(), **entrada})
    return {"ok": True, "novos": novos, "erros": erros}


_SINAIS_MODELO_EXTINTO = ("decommissioned", "deprecated", "does not exist", "no longer supported",
                          "no longer available", "model_not_found", "model not found", "not a valid model")
# Erros do próprio LiteLLM: o modelo não está no config carregado (config gerado e ainda não recarregado). Não é o
# provedor dizendo que o modelo acabou.
_SINAIS_DO_PROXY = ("proxymodelnotfound", "invalid model name", "model_group")


def litellm_sem_o_modelo(resultado: dict[str, Any]) -> bool:
    """O LiteLLM respondeu que não conhece o modelo: o config foi regenerado e o LiteLLM ainda não foi reiniciado."""
    erro = str(resultado.get("erro") or "").lower()
    return not resultado.get("ok") and any(s in erro for s in _SINAIS_DO_PROXY)


def falha_definitiva(resultado: dict[str, Any]) -> bool:
    """Só o provedor dizendo que o modelo não existe mais justifica inativar sozinho.

    Conexão recusada (LiteLLM ou Ollama fora), timeout, cota, 5xx e chave inválida dizem algo sobre o ambiente,
    não sobre o modelo: inativar nesses casos tirava do roteamento todo modelo testado com o LiteLLM parado.
    """
    if resultado.get("ok"):
        return False
    erro = str(resultado.get("erro") or "").lower()
    if any(s in erro for s in _SINAIS_DO_PROXY):
        return False
    return resultado.get("status_http") == 404 or (
        resultado.get("status_http") in (400, 410) and any(s in erro for s in _SINAIS_MODELO_EXTINTO))


def desativar_modelo_por_falha(
    caminho_yaml: Path,
    caminho_roteamento: Path,
    nome: str,
    motivo: str,
) -> dict[str, Any]:
    """Tira do roteamento e inativa um modelo ativo do catálogo cujo teste falhou.

    Ordem das gravações: roteamento primeiro, catálogo depois. Se a segunda falhar, o modelo fica ativo
    mas fora do roteamento, que é um estado seguro. A ordem inversa deixaria um modelo roteado sem config.
    Modelo já inativo, ou que não está no catálogo, não gera nenhuma gravação.
    """
    caminho_yaml, caminho_roteamento = Path(caminho_yaml), Path(caminho_roteamento)
    catalogo_dados = yaml.safe_load(caminho_yaml.read_text(encoding="utf-8")) or {}

    alvo = None
    for p in (catalogo_dados.get("provedores") or {}).values():
        for m in (p.get("modelos") or []) if isinstance(p, dict) else []:
            if isinstance(m, dict) and m.get("nome") == nome and m.get("ativo", True):
                alvo = m
                break
        if alvo:
            break
    if alvo is None:
        return {"desativado": False, "removido_de_grupos": []}

    rot = yaml.safe_load(caminho_roteamento.read_text(encoding="utf-8")) or {}
    ordem = rot.get("ordem") or {}
    removido_de = []
    for grupo, membros in ordem.items():
        if isinstance(membros, list) and nome in membros:
            ordem[grupo] = [x for x in membros if x != nome]
            removido_de.append(grupo)
    if removido_de:
        gravar_yaml_atomico(caminho_roteamento, rot)

    alvo["ativo"] = False
    alvo["desativado_por_falha"] = motivo[:200]
    gravar_yaml_atomico(caminho_yaml, catalogo_dados)
    return {"desativado": True, "removido_de_grupos": removido_de}


def adicionar_modelos_lote(caminho_yaml: Path, itens: list[dict[str, Any]]) -> dict[str, Any]:
    """Adiciona modelos escolhidos em uma só gravação. Item inválido ou duplicado é reportado, sem abortar o lote."""
    caminho_yaml = Path(caminho_yaml)
    catalogo_dados = yaml.safe_load(caminho_yaml.read_text(encoding="utf-8")) or {}
    provedores = catalogo_dados.get("provedores") or {}

    adicionados, recusados = [], []
    for item in itens:
        pid = item.get("provedor", "")
        p = provedores.get(pid)
        if not isinstance(p, dict):
            recusados.append({"id": item.get("id"), "motivo": f"Provedor '{pid}' não existe."})
            continue
        nome, mid = str(item.get("nome", "")).strip(), str(item.get("id", "")).strip()
        modelos = p.setdefault("modelos", [])
        if not nome or not mid:
            recusados.append({"id": mid, "motivo": "Nome e ID são obrigatórios."})
            continue
        if any(m.get("nome") == nome or m.get("id") == mid for m in modelos if isinstance(m, dict)):
            recusados.append({"id": mid, "motivo": "Já existe no catálogo."})
            continue
        novo = {"nome": nome, "id": mid, "papeis": list(item.get("papeis") or []) or inferir_papeis(mid), "ativo": True}
        if item.get("contexto"):
            novo["contexto"] = int(item["contexto"])
        modelos.append(novo)
        adicionados.append(nome)

    if adicionados:
        gravar_yaml_atomico(caminho_yaml, catalogo_dados)
    return {"ok": True, "adicionados": adicionados, "recusados": recusados}


def adicionar_modelo_provedor(
    caminho_yaml: Path,
    provedor_id: str,
    modelo_dados: dict[str, Any]
) -> dict[str, Any]:
    """Adiciona um modelo ao catálogo do provedor especificado."""
    caminho_yaml = Path(caminho_yaml)
    catalogo_dados = yaml.safe_load(caminho_yaml.read_text(encoding="utf-8")) or {}
    provedores = catalogo_dados.setdefault("provedores", {})

    p = provedores.get(provedor_id)
    if not p:
        raise ValueError(f"Provedor '{provedor_id}' não existe no catálogo.")

    nome = str(modelo_dados.get("nome", "")).strip()
    mid = str(modelo_dados.get("id", "")).strip()
    if not nome or not mid:
        raise ValueError("Campos 'nome' e 'id' do modelo são obrigatórios.")

    papeis = modelo_dados.get("papeis") or inferir_papeis(mid)
    if isinstance(papeis, str):
        papeis = [p.strip() for p in papeis.split(",") if p.strip()]

    contexto = modelo_dados.get("contexto")
    if contexto:
        try:
            contexto = int(contexto)
        except ValueError:
            contexto = None

    modelos = p.setdefault("modelos", [])
    # Verifica se já existe
    for m in modelos:
        if m.get("nome") == nome or m.get("id") == mid:
            raise ValueError(f"Modelo '{nome}' ou ID '{mid}' já existe no provedor '{provedor_id}'.")

    novo_mod = {
        "nome": nome,
        "id": mid,
        "papeis": list(papeis)
    }
    if contexto:
        novo_mod["contexto"] = contexto
    novo_mod["ativo"] = bool(modelo_dados.get("ativo", True))

    modelos.append(novo_mod)
    gravar_yaml_atomico(caminho_yaml, catalogo_dados)

    return {"ok": True, "provedor": provedor_id, "modelo": novo_mod}

"""Segredos do .env: listar mascarados, gravar, revelar (admin) e testar contra o provedor."""
import json
import logging
import re
import time

import httpx
from fastapi import APIRouter


from ..catalogo import carregar_catalogo
from ..video_nuvem import catalogo_video
from ..envfile import gravar_valor, ler_env, mascarar
from ..erros import ErroApi
from ..ambiente import Contexto
from ..schemas import Valor
from .. import upstreams


CHAVE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
CATEGORIAS_CHAVES = {
    "NVIDIA_NIM_API_KEY": ("FREE", "NVIDIA NIM"),
    "NVIDIA_NIM_API_BASE": ("FREE", "NVIDIA NIM Base URL"),
    "OPENROUTER_API_KEY": ("FREE", "OpenRouter"),
    "GROQ_API_KEY": ("FREE", "Groq Cloud"),
    "GEMINI_API_KEY": ("FREE", "Google Gemini AI Studio"),
    "CLOUDFLARE_API_KEY": ("FREE", "Cloudflare Workers AI"),
    "CLOUDFLARE_ACCOUNT_ID": ("FREE", "Cloudflare Account ID"),
    "ANTHROPIC_API_KEY": ("PAID", "Anthropic Claude"),
    "OPENAI_API_KEY": ("PAID", "OpenAI"),
    "DEEPSEEK_API_KEY": ("PAID", "DeepSeek"),
    "XAI_API_KEY": ("PAID", "xAI Grok"),
    "HF_TOKEN": ("PAID", "Hugging Face"),
    "MUAPI_API_KEY": ("PAID", "MuAPI (música e áudio)"),
    "FAL_AI_API_KEY": ("PAID", "fal.ai (vídeo na nuvem pelo LiteLLM)"),
    "CONTEXT7_API_KEY": ("GOVERNANCA", "Context7 MCP"),
    "SUPABASE_ACCESS_TOKEN": ("GOVERNANCA", "Supabase Access Token"),
    "SUPABASE_SERVICE_ROLE_KEY": ("GOVERNANCA", "Supabase Service Role"),
    "SUPABASE_URL": ("GOVERNANCA", "Supabase Project URL"),
    "GITHUB_PERSONAL_ACCESS_TOKEN": ("GOVERNANCA", "GitHub MCP Token"),
    "CEREBRO_TOKEN_ESTATICO": ("GOVERNANCA", "MCP: cerebro"),
    "LITELLM_MASTER_KEY": ("SISTEMA", "Chave mestra do LiteLLM"),
    "LITELLM_DB_PASSWORD": ("SISTEMA", "Senha do banco do LiteLLM"),
    "WEBUI_SECRET_KEY": ("SISTEMA", "Segredo do Open WebUI"),
    "SEARXNG_SECRET": ("SISTEMA", "Segredo do SearXNG"),
    "N8N_ENCRYPTION_KEY": ("SISTEMA", "Chave de criptografia do n8n"),
    "KEYCLOAK_DB_PASSWORD": ("SISTEMA", "Senha do banco do Keycloak"),
    "TZ": ("SISTEMA", "Fuso horário"),
    "OLLAMA_URL": ("SISTEMA", "Endereço do Ollama (containers)"),
    "COMPOSE_PROFILES": ("SISTEMA", "Perfis do Docker Compose"),
    "TUDOIA_COMPOSE_PROJETO": ("SISTEMA", "Nome do projeto no Docker Compose"),
    "TUDOIA_COMFYUI_PORTABLE": ("SISTEMA", "Pasta do ComfyUI portátil"),
    "TUDOIA_OLLAMA_MODELS": ("SISTEMA", "Pasta dos modelos do Ollama"),
    "TUDOIA_ESTUDIO_POLLINATIONS": ("SISTEMA", "Estúdio: usar Pollinations na nuvem"),
    "TUDOIA_OIDC_ISSUER": ("SISTEMA", "Login: endereço do emissor (Keycloak)"),
    "TUDOIA_OIDC_CLIENT_ID": ("SISTEMA", "Login: cliente do painel"),
    "TUDOIA_OIDC_CLIENT_SECRET": ("SISTEMA", "Login: segredo do cliente do painel"),
    "TUDOIA_OIDC_SCOPE": ("SISTEMA", "Login: escopos pedidos"),
    "TUDOIA_SESSAO_SEGREDO": ("SISTEMA", "Login: segredo das sessões do painel"),
    "TUDOIA_COOKIE_SEGURO": ("SISTEMA", "Login: cookie só em HTTPS"),
    "TUDOIA_KEYCLOAK_URL": ("SISTEMA", "Keycloak: endereço"),
    "TUDOIA_KEYCLOAK_ADMIN": ("SISTEMA", "Keycloak: usuário administrador"),
    "TUDOIA_KEYCLOAK_ADMIN_PASSWORD": ("SISTEMA", "Keycloak: senha do administrador"),
    "TUDOIA_MCP_CLIENT_ID": ("SISTEMA", "Login do Cérebro: cliente"),
    "TUDOIA_MCP_CLIENT_SECRET": ("SISTEMA", "Login do Cérebro: segredo do cliente"),
    "TUDOIA_CAPTURAS_CLIENT_ID": ("SISTEMA", "Capturas de tela: cliente"),
    "TUDOIA_CAPTURAS_CLIENT_SECRET": ("SISTEMA", "Capturas de tela: segredo do cliente"),
}

# Grupo de exibição das chaves de SISTEMA (a categoria continua a mesma, para não quebrar quem lê a API).
GRUPO_SISTEMA = {
    **dict.fromkeys(("TUDOIA_OIDC_ISSUER", "TUDOIA_OIDC_CLIENT_ID", "TUDOIA_OIDC_CLIENT_SECRET", "TUDOIA_OIDC_SCOPE",
                     "TUDOIA_SESSAO_SEGREDO", "TUDOIA_COOKIE_SEGURO", "TUDOIA_KEYCLOAK_URL", "TUDOIA_KEYCLOAK_ADMIN",
                     "TUDOIA_KEYCLOAK_ADMIN_PASSWORD", "TUDOIA_MCP_CLIENT_ID", "TUDOIA_MCP_CLIENT_SECRET",
                     "TUDOIA_CAPTURAS_CLIENT_ID", "TUDOIA_CAPTURAS_CLIENT_SECRET"), "acesso"),
    **dict.fromkeys(("TZ", "OLLAMA_URL", "COMPOSE_PROFILES", "TUDOIA_COMPOSE_PROJETO", "TUDOIA_COMFYUI_PORTABLE",
                     "TUDOIA_OLLAMA_MODELS", "TUDOIA_ESTUDIO_POLLINATIONS"), "configuracao"),
}
GRUPO_DA_CATEGORIA = {"FREE": "gratuitos", "PAID": "pagos", "GOVERNANCA": "mcp"}
# Valores que não são segredo (endereços, ids, pastas, opções). Continuam mascarados na listagem por precaução.
NAO_SECRETAS = {
    "TZ", "OLLAMA_URL", "COMPOSE_PROFILES", "TUDOIA_COMPOSE_PROJETO", "TUDOIA_COMFYUI_PORTABLE", "TUDOIA_OLLAMA_MODELS",
    "TUDOIA_ESTUDIO_POLLINATIONS", "TUDOIA_OIDC_ISSUER", "TUDOIA_OIDC_CLIENT_ID", "TUDOIA_OIDC_SCOPE",
    "TUDOIA_COOKIE_SEGURO", "TUDOIA_KEYCLOAK_URL", "TUDOIA_KEYCLOAK_ADMIN", "TUDOIA_MCP_CLIENT_ID",
    "TUDOIA_CAPTURAS_CLIENT_ID", "NVIDIA_NIM_API_BASE", "SUPABASE_URL", "CLOUDFLARE_ACCOUNT_ID",
}


def grupo_da_chave(chave: str, categoria: str) -> str:
    if categoria in GRUPO_DA_CATEGORIA:
        return GRUPO_DA_CATEGORIA[categoria]
    return GRUPO_SISTEMA.get(chave, "servicos")

LINKS_PROVEDORES: dict[str, str] = {
    # Provedores de Modelos LLM / Difusão
    "NVIDIA_NIM_API_KEY": "https://build.nvidia.com",
    "NVIDIA_NIM_API_BASE": "https://build.nvidia.com",
    "OPENROUTER_API_KEY": "https://openrouter.ai/keys",
    "GROQ_API_KEY": "https://console.groq.com/keys",
    "GEMINI_API_KEY": "https://aistudio.google.com/apikey",
    "CLOUDFLARE_API_KEY": "https://dash.cloudflare.com/profile/api-tokens",
    "CLOUDFLARE_ACCOUNT_ID": "https://dash.cloudflare.com",
    "ANTHROPIC_API_KEY": "https://console.anthropic.com/settings/keys",
    "OPENAI_API_KEY": "https://platform.openai.com/api-keys",
    "DEEPSEEK_API_KEY": "https://platform.deepseek.com/api_keys",
    "XAI_API_KEY": "https://console.x.ai",
    "HF_TOKEN": "https://huggingface.co/settings/tokens",
    "MUAPI_API_KEY": "https://muapi.ai",
    "FAL_AI_API_KEY": "https://fal.ai/dashboard/keys",
    # Governança, MCP e Serviços em Nuvem
    "CONTEXT7_API_KEY": "https://context7.com",
    "SUPABASE_ACCESS_TOKEN": "https://supabase.com/dashboard/account/tokens",
    "SUPABASE_SERVICE_ROLE_KEY": "https://supabase.com/dashboard/project/_/settings/api",
    "SUPABASE_URL": "https://supabase.com/dashboard",
    "GITHUB_PERSONAL_ACCESS_TOKEN": "https://github.com/settings/tokens",
    "BRAVE_API_KEY": "https://api.search.brave.com/app/keys",
    "TAVILY_API_KEY": "https://app.tavily.com/home",
    # Serviços Locais e Upstreams
    "OLLAMA_URL": "https://ollama.com",
    "CEREBRO_TOKEN_ESTATICO": "http://127.0.0.1:8765",
    "LITELLM_MASTER_KEY": "http://127.0.0.1:4000",
    "LITELLM_DB_PASSWORD": "http://127.0.0.1:4000",
    "WEBUI_SECRET_KEY": "http://127.0.0.1:3000",
    "SEARXNG_SECRET": "http://127.0.0.1:8080",
    "N8N_ENCRYPTION_KEY": "http://127.0.0.1:5678",
}


log = logging.getLogger(__name__)


def criar_router(ctx: Contexto) -> APIRouter:
    router = APIRouter()
    raiz = ctx.raiz
    trava = ctx.trava

    # ------------------------------------------------ segredos
    @router.get("/api/segredos")
    def listar_segredos():
        env = ler_env(raiz / ".env")
        catalogo = carregar_catalogo(raiz / "config" / "catalogo-modelos.yaml")
        chaves = set(env)
        for p in catalogo.provedores:
            chaves.add(p.chave)
            chaves.update(p.chaves_extras)
        chaves.update(m.chave for m in catalogo_video(raiz))   # vídeo na nuvem (config/video-nuvem.yaml)

        # Inspeciona dinamicamente servidores MCP em governanca/mcp.json
        chaves_mcp: dict[str, str] = {}
        mcp_path = raiz / "governanca" / "mcp.json"
        if mcp_path.is_file():
            try:
                mcp_data = json.loads(mcp_path.read_text(encoding="utf-8")).get("mcpServers", {})
                for mcp_nome, mcp_cfg in mcp_data.items():
                    # 1. Variáveis explicitamente declaradas na chave 'env'
                    for var_k in mcp_cfg.get("env", {}).keys():
                        chaves_mcp[var_k] = mcp_nome
                        chaves.add(var_k)
                    # 2. Variáveis interpoladas com sintaxe ${VAR} em qualquer campo
                    cfg_str = json.dumps(mcp_cfg)
                    for match in re.findall(r"\$\{([A-Z0-9_]+)(?::-[^}]*)?\}", cfg_str):
                        chaves_mcp[match] = mcp_nome
                        chaves.add(match)
            except Exception as e:   # mcp.json ilegível: as chaves dos MCP só deixam de aparecer na lista
                log.warning("mcp.json ilegível ao listar segredos (%s)", type(e).__name__)

        # Mescla links canônicos com links dinâmicos do catálogo de modelos
        mapa_links = dict(LINKS_PROVEDORES)
        for p in catalogo.provedores:
            if p.site_chave:
                mapa_links[p.chave] = p.site_chave
                for extra in p.chaves_extras:
                    mapa_links.setdefault(extra, p.site_chave)

        saida = []
        for k in sorted(chaves):
            cat, nome_prov = CATEGORIAS_CHAVES.get(k, ("SISTEMA", k))
            if k in chaves_mcp and cat in ("SISTEMA", "GOVERNANCA"):
                cat = "GOVERNANCA"
                if k not in CATEGORIAS_CHAVES:
                    nome_prov = f"MCP: {chaves_mcp[k]}"

            testavel = k in (
                "NVIDIA_NIM_API_KEY", "OPENROUTER_API_KEY", "GROQ_API_KEY", "GEMINI_API_KEY",
                "CLOUDFLARE_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY",
                "XAI_API_KEY", "HF_TOKEN", "GITHUB_PERSONAL_ACCESS_TOKEN", "SUPABASE_ACCESS_TOKEN",
                "LITELLM_MASTER_KEY", "FAL_AI_API_KEY"
            )
            saida.append({
                "chave": k,
                "categoria": cat,
                "nome_provedor": nome_prov,
                "definido": bool(env.get(k)),
                "mascarado": mascarar(env.get(k, "")),
                "testavel": testavel,
                "link": mapa_links.get(k),
                "grupo": grupo_da_chave(k, cat),
                "secreto": k not in NAO_SECRETAS,
            })
        return saida

    @router.put("/api/segredos/{chave}")
    def gravar_segredo(chave: str, corpo: Valor):
        if not CHAVE.match(chave):
            raise ErroApi(422, "validacao", "nome de variável inválido", campo="chave")
        with trava:
            try:
                gravar_valor(raiz / ".env", chave, corpo.valor, raiz / "dados" / "backups" / "env")
            except ValueError as e:
                raise ErroApi(422, "validacao", str(e), campo="valor") from e
        return {"ok": True, "chave": chave}

    @router.post("/api/segredos/{chave}/revelar")
    def revelar_segredo(chave: str):
        if not CHAVE.match(chave):
            raise ErroApi(422, "validacao", "nome de variável inválido", campo="chave")
        env = ler_env(raiz / ".env")
        return {"ok": True, "chave": chave, "valor": env.get(chave, "")}

    @router.post("/api/segredos/{chave}/testar")
    def testar_segredo(chave: str):
        env = ler_env(raiz / ".env")
        valor = env.get(chave, "").strip()
        if not valor:
            raise ErroApi(422, "validacao", f"A chave {chave} não está preenchida no .env")

        inicio = time.perf_counter()
        headers = {}
        url = ""
        params = {}

        if chave == "OPENAI_API_KEY":
            url = "https://api.openai.com/v1/models"
            headers = {"Authorization": f"Bearer {valor}"}
        elif chave == "GROQ_API_KEY":
            url = "https://api.groq.com/openai/v1/models"
            headers = {"Authorization": f"Bearer {valor}"}
        elif chave == "OPENROUTER_API_KEY":
            url = "https://openrouter.ai/api/v1/auth/key"
            headers = {"Authorization": f"Bearer {valor}"}
        elif chave == "NVIDIA_NIM_API_KEY":
            url = "https://integrate.api.nvidia.com/v1/models"
            headers = {"Authorization": f"Bearer {valor}"}
        elif chave == "GEMINI_API_KEY":
            url = "https://generativelanguage.googleapis.com/v1beta/models"
            params = {"key": valor}
        elif chave == "ANTHROPIC_API_KEY":
            url = "https://api.anthropic.com/v1/models"
            headers = {"x-api-key": valor, "anthropic-version": "2023-06-01"}
        elif chave == "DEEPSEEK_API_KEY":
            url = "https://api.deepseek.com/models"
            headers = {"Authorization": f"Bearer {valor}"}
        elif chave == "XAI_API_KEY":
            url = "https://api.x.ai/v1/models"
            headers = {"Authorization": f"Bearer {valor}"}
        elif chave == "HF_TOKEN":
            url = "https://huggingface.co/api/whoami-v2"
            headers = {"Authorization": f"Bearer {valor}"}
        elif chave == "GITHUB_PERSONAL_ACCESS_TOKEN":
            url = "https://api.github.com/user"
            headers = {"Authorization": f"token {valor}"}
        elif chave == "SUPABASE_ACCESS_TOKEN":
            url = "https://api.supabase.com/v1/projects"
            headers = {"Authorization": f"Bearer {valor}"}
        elif chave == "FAL_AI_API_KEY":
            # consulta de preço exige chave e não gera nada (não cobra)
            url = "https://api.fal.ai/v1/models/pricing"
            headers = {"Authorization": f"Key {valor}"}
            params = {"endpoint_id": "alibaba/wan-3.0/text-to-video"}
        elif chave == "LITELLM_MASTER_KEY":
            url = f"{upstreams.LITELLM}/v1/models"
            headers = {"Authorization": f"Bearer {valor}"}
        else:
            return {"valido": True, "status_http": 200, "mensagem": "Chave configurada (teste específico não requerido)", "latencia_ms": 1}

        try:
            with httpx.Client(timeout=8.0) as cliente:
                resp = cliente.get(url, headers=headers, params=params)
                latencia_ms = int((time.perf_counter() - inicio) * 1000)
                if resp.status_code == 200:
                    return {"valido": True, "status_http": 200, "mensagem": "Chave válida e autenticada com sucesso!", "latencia_ms": latencia_ms}
                elif resp.status_code in (401, 403):
                    return {"valido": False, "status_http": resp.status_code, "mensagem": f"Autenticação recusada ({resp.status_code}): chave inválida ou expirada", "latencia_ms": latencia_ms}
                elif resp.status_code == 429:
                    return {"valido": True, "status_http": 429, "mensagem": "Chave válida mas atingiu limite de cota/rate limit", "latencia_ms": latencia_ms}
                else:
                    return {"valido": False, "status_http": resp.status_code, "mensagem": f"Provedor retornou status {resp.status_code}", "latencia_ms": latencia_ms}
        except Exception as e:
            latencia_ms = int((time.perf_counter() - inicio) * 1000)
            return {"valido": False, "status_http": 0, "mensagem": f"Falha de conexão com provedor: {type(e).__name__}", "latencia_ms": latencia_ms}

    return router

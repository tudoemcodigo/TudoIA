"""Segredos do .env: listar mascarados, gravar, revelar (admin) e testar contra o provedor."""
import json
import logging
import re
import time

import httpx
from fastapi import APIRouter


from ..catalogo import carregar_catalogo
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
    "CONTEXT7_API_KEY": ("GOVERNANCA", "Context7 MCP"),
    "SUPABASE_ACCESS_TOKEN": ("GOVERNANCA", "Supabase Access Token"),
    "SUPABASE_SERVICE_ROLE_KEY": ("GOVERNANCA", "Supabase Service Role"),
    "SUPABASE_URL": ("GOVERNANCA", "Supabase Project URL"),
    "GITHUB_PERSONAL_ACCESS_TOKEN": ("GOVERNANCA", "GitHub MCP Token"),
    "LITELLM_MASTER_KEY": ("SISTEMA", "LiteLLM Master Key"),
    "LITELLM_DB_PASSWORD": ("SISTEMA", "LiteLLM DB Password"),
    "WEBUI_SECRET_KEY": ("SISTEMA", "Open WebUI Secret"),
    "SEARXNG_SECRET": ("SISTEMA", "SearXNG Secret"),
    "N8N_ENCRYPTION_KEY": ("SISTEMA", "n8n Encryption Key"),
    "TZ": ("SISTEMA", "Fuso Horário"),
    "OLLAMA_URL": ("SISTEMA", "Ollama Container URL"),
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
                "LITELLM_MASTER_KEY"
            )
            saida.append({
                "chave": k,
                "categoria": cat,
                "nome_provedor": nome_prov,
                "definido": bool(env.get(k)),
                "mascarado": mascarar(env.get(k, "")),
                "testavel": testavel
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

"""Teste de um servidor MCP do catálogo: HTTP (GET) ou stdio (handshake JSON-RPC). Só admin; o stdio executa o comando."""
import os
import re
import shutil
import time
from urllib.parse import urlsplit

import httpx

from . import mcp_stdio

VARIAVEL = re.compile(r"^\$\{([A-Z0-9_]+)(?::-.*)?\}$")
HOSTS_DO_CEREBRO = ("localhost", "127.0.0.1", "host.docker.internal", "cerebro")
SAUDE_DO_CEREBRO = "http://127.0.0.1:8765/saude"


def _ms(inicio: float) -> int:
    return int((time.perf_counter() - inicio) * 1000)


def alvo_http(url: str) -> str:
    """O Cérebro é testado pelo /saude local (o /mcp exige token). Compara host e porta, não um trecho da URL."""
    try:
        partes = urlsplit(url)
        if partes.hostname in HOSTS_DO_CEREBRO and partes.port == 8765:
            return SAUDE_DO_CEREBRO
    except ValueError:
        pass
    return url


def testar_http(id: str, cfg: dict, env_local: dict[str, str]) -> dict:
    is_oauth = cfg.get("auth") == "oauth"
    headers: dict[str, str] = {}
    if not is_oauth:
        for v in (cfg.get("env") or {}).values():
            m = VARIAVEL.match(str(v))
            if m:
                valor = env_local.get(m.group(1), "").strip()
                if not valor and ":-" not in str(v):
                    return {"ok": False, "id": id, "tipo": "http", "latencia_ms": 0,
                            "mensagem": f"Variável obrigatória '{m.group(1)}' não configurada no .env. Configure na aba Segredos ou mude para OAuth."}
                if valor:
                    headers["Authorization"] = f"Bearer {valor}"
            elif v:
                headers["Authorization"] = f"Bearer {v}"

    inicio = time.perf_counter()
    try:
        # sem seguir redirecionamento: o token não pode acompanhar um 3xx para outro host
        with httpx.Client(timeout=4.0, follow_redirects=False) as cliente:
            r = cliente.get(alvo_http(cfg.get("url", "")), headers=headers)
        lat = _ms(inicio)
        if r.status_code in (200, 201, 204):
            return {"ok": True, "id": id, "tipo": "http", "latencia_ms": lat,
                    "mensagem": f"Servidor HTTP operacional (HTTP {r.status_code})"}
        if is_oauth and (r.status_code == 401 or "oauth" in r.headers.get("www-authenticate", "").lower()):
            return {"ok": True, "id": id, "tipo": "oauth", "latencia_ms": lat,
                    "mensagem": "Servidor OAuth operacional (Endpoint ativo aguardando handshake do cliente)"}
        return {"ok": False, "id": id, "tipo": "http", "latencia_ms": lat, "mensagem": f"Servidor retornou HTTP {r.status_code}"}
    except Exception as e:
        return {"ok": False, "id": id, "tipo": "http", "latencia_ms": _ms(inicio),
                "mensagem": f"Falha de conexão: {type(e).__name__}"}


def _falha_stdio(id: str, mensagem: str, lat: int = 0) -> dict:
    return {"ok": False, "id": id, "tipo": "stdio", "latencia_ms": lat, "mensagem": mensagem}


def testar_stdio(id: str, cfg: dict, env_local: dict[str, str]) -> dict:
    cmd, args = cfg.get("command"), cfg.get("args", [])
    full_env = os.environ.copy()
    for k, v in (cfg.get("env") or {}).items():
        m = VARIAVEL.match(str(v))
        if m:
            valor = env_local.get(m.group(1), "").strip()
            if not valor and ":-" not in str(v):
                return _falha_stdio(id, f"Variável obrigatória '{m.group(1)}' não configurada no .env")
            full_env[k] = valor or full_env.get(k, "")
        else:
            full_env[k] = str(v)

    if not cmd:
        return _falha_stdio(id, "Configuração sem comando executável")
    cmd_exec = f"{cmd}.cmd" if os.name == "nt" and cmd in ("npx", "npm", "uvx") else cmd
    if not shutil.which(cmd_exec):
        return _falha_stdio(id, f"Comando '{cmd}' não encontrado no PATH")

    inicio = time.perf_counter()
    try:
        try:
            resp = mcp_stdio.handshake([cmd_exec, *args], full_env)
        except mcp_stdio.SemResposta as e:
            return _falha_stdio(id, str(e), _ms(inicio))
        lat = _ms(inicio)
        if "result" in resp:
            info = resp["result"].get("serverInfo", {})
            nome, ver = info.get("name", id), info.get("version", "")
            tem_tools = "tools" in resp["result"].get("capabilities", {})
            msg = f"{nome}{' v' + ver if ver else ''} operacional" + (" (com ferramentas)" if tem_tools else "")
            return {"ok": True, "id": id, "tipo": "stdio", "latencia_ms": lat, "servidor": nome, "versao": ver, "mensagem": msg}
        if "error" in resp:
            return _falha_stdio(id, resp["error"].get("message", "Erro JSON-RPC"), lat)
        return _falha_stdio(id, "Resposta JSON-RPC inválida", lat)
    except Exception as e:
        return _falha_stdio(id, f"Erro de execução: {type(e).__name__}", _ms(inicio))


def testar(id: str, cfg: dict, env_local: dict[str, str]) -> dict:
    if cfg.get("type") == "http" or "url" in cfg:
        return testar_http(id, cfg, env_local)
    return testar_stdio(id, cfg, env_local)

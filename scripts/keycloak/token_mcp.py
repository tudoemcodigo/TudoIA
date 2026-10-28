"""Obtém um access token do cliente de serviço `tudoia-mcp` (client_credentials) para o Cérebro.

Uso (na raiz do repositório):
    .venv\\Scripts\\python.exe scripts\\keycloak\\token_mcp.py              mostra só a validade
    .venv\\Scripts\\python.exe scripts\\keycloak\\token_mcp.py --imprimir   imprime o token (stdout)

Lê .env (ambiente tem prioridade): TUDOIA_KEYCLOAK_URL, TUDOIA_KEYCLOAK_REALM, TUDOIA_MCP_CLIENT_ID,
TUDOIA_MCP_CLIENT_SECRET. O segredo nunca é impresso. O token vale o tempo do cliente no realm (8 h).

Códigos de saída: 0 ok, 1 configuração ausente, 2 Keycloak inacessível ou credencial recusada.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import httpx

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "painel"))
from tudoia_painel.envfile import ler_env  # noqa: E402

URL_PADRAO = "http://localhost:8180"
REALM_PADRAO = "tudoia"
CLIENTE_PADRAO = "tudoia-mcp"
TIMEOUT = httpx.Timeout(10.0, connect=5.0)


def configuracao(ambiente: dict[str, str], arquivo_env: Path) -> dict[str, str]:
    """.env e ambiente, só chaves TUDOIA_ (o ambiente vence). Não imprime nada."""
    valores = {k: v for k, v in ler_env(arquivo_env).items() if k.startswith("TUDOIA_")}
    valores.update({k: v for k, v in ambiente.items() if k.startswith("TUDOIA_")})
    return {
        "url": (valores.get("TUDOIA_KEYCLOAK_URL") or URL_PADRAO).rstrip("/"),
        "realm": valores.get("TUDOIA_KEYCLOAK_REALM") or REALM_PADRAO,
        "cliente": valores.get("TUDOIA_MCP_CLIENT_ID") or CLIENTE_PADRAO,
        "segredo": valores.get("TUDOIA_MCP_CLIENT_SECRET") or "",
    }


def obter_token(cfg: dict[str, str], cliente: httpx.Client) -> dict:
    """Resposta do endpoint de token (client_credentials). Lança RuntimeError com mensagem segura."""
    url = f"{cfg['url']}/realms/{cfg['realm']}/protocol/openid-connect/token"
    try:
        resp = cliente.post(
            url,
            data={"grant_type": "client_credentials", "client_id": cfg["cliente"], "client_secret": cfg["segredo"]},
            timeout=TIMEOUT,
        )
    except httpx.HTTPError:
        raise RuntimeError(f"não foi possível conectar em {cfg['url']}") from None
    if resp.status_code in (400, 401):
        raise RuntimeError("credencial do cliente recusada (rode o provisionar e confira o .env)")
    if resp.status_code != 200:
        raise RuntimeError(f"Keycloak respondeu HTTP {resp.status_code}")
    try:
        dados = resp.json()
    except ValueError:
        raise RuntimeError("resposta de token inesperada do Keycloak") from None
    if not dados.get("access_token"):
        raise RuntimeError("resposta de token sem access_token")
    return dados


def main(argv: list[str] | None = None, ambiente: dict[str, str] | None = None, arquivo_env: Path | None = None) -> int:
    parser = argparse.ArgumentParser(description="Token do cliente tudoia-mcp (client_credentials).")
    parser.add_argument("--imprimir", action="store_true", help="imprime o token em stdout (só ele)")
    args = parser.parse_args(argv)

    cfg = configuracao(dict(os.environ) if ambiente is None else ambiente, arquivo_env or RAIZ / ".env")
    if not cfg["segredo"]:
        print("TUDOIA_MCP_CLIENT_SECRET ausente: rode scripts\\keycloak\\provisionar.py", file=sys.stderr)
        return 1
    try:
        with httpx.Client() as cliente:
            dados = obter_token(cfg, cliente)
    except RuntimeError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 2

    if args.imprimir:
        print(dados["access_token"])
    else:
        expira_em = time.localtime(time.time() + int(dados.get("expires_in", 0)))
        print(f"token obtido; válido por {dados.get('expires_in')} s (expira às {time.strftime('%H:%M:%S', expira_em)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

r"""Cria (ou atualiza) no n8n a credencial OAuth2 que o fluxo `ingerir-documento` usa para indexar no Cérebro.

Uso (na raiz do repositório, com o container `n8n` no ar):
    .venv\Scripts\python.exe -m scripts.n8n.credencial_cerebro

O segredo do cliente `tudoia-mcp` sai do .env e vai para o cofre do n8n (cifrado com N8N_ENCRYPTION_KEY). Ele passa
pelo stdin do `docker exec`, nunca por argumento (que apareceria na lista de processos), e o arquivo temporário dentro
do container é criado com umask 077 e apagado logo depois. Rodar de novo só sobrescreve a mesma credencial (mesmo id).

Assim o n8n não precisa de segredo em variável de ambiente e roda com N8N_BLOCK_ENV_ACCESS_IN_NODE=true: nenhum nó
Code ou expressão de nenhum fluxo lê os segredos do container.

Códigos de saída: 0 ok, 1 configuração ausente, 2 falha no docker/n8n.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "painel"))
from tudoia_painel.envfile import ler_env  # noqa: E402

# Precisam bater com automacao/n8n/ingerir-documento.json (nó "Indexar no cérebro").
ID_CREDENCIAL = "tudoiaCerebroOAuth"
NOME_CREDENCIAL = "TudoIA Cérebro (client_credentials)"
# De dentro do container o Keycloak é o host.
URL_TOKEN = "http://host.docker.internal:8180/realms/{realm}/protocol/openid-connect/token"
CONTAINER = "n8n"
SCRIPT_IMPORTAR = "umask 077; cat > /tmp/cred.json; n8n import:credentials --input=/tmp/cred.json; s=$?; rm -f /tmp/cred.json; exit $s"


class ErroConfiguracao(Exception):
    pass


def montar_credencial(env: dict[str, str]) -> list[dict]:
    """Credencial no formato do `n8n export:credentials --decrypted`. Falha se faltar o segredo."""
    cliente = (env.get("TUDOIA_MCP_CLIENT_ID") or "tudoia-mcp").strip()
    segredo = (env.get("TUDOIA_MCP_CLIENT_SECRET") or "").strip()
    if not segredo:
        raise ErroConfiguracao("TUDOIA_MCP_CLIENT_SECRET ausente no .env (rode o provisionamento do Keycloak)")
    realm = (env.get("TUDOIA_KEYCLOAK_REALM") or "tudoia").strip()
    return [{
        "id": ID_CREDENCIAL,
        "name": NOME_CREDENCIAL,
        "type": "oAuth2Api",
        "data": {
            "grantType": "clientCredentials",
            "accessTokenUrl": URL_TOKEN.format(realm=realm),
            "clientId": cliente,
            "clientSecret": segredo,
            "scope": "",
            "authentication": "body",
        },
    }]


def main(argv: list[str] | None = None) -> int:
    env = {**ler_env(RAIZ / ".env"), **{k: v for k, v in os.environ.items() if k.startswith("TUDOIA_")}}
    try:
        corpo = json.dumps(montar_credencial(env), ensure_ascii=False)
    except ErroConfiguracao as e:
        print(f"erro: {e}", file=sys.stderr)
        return 1
    try:
        r = subprocess.run(["docker", "exec", "-i", CONTAINER, "sh", "-c", SCRIPT_IMPORTAR],
                           input=corpo, text=True, capture_output=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"erro: docker indisponível ({type(e).__name__})", file=sys.stderr)
        return 2
    if r.returncode != 0:
        # A saída do n8n não ecoa os dados da credencial; mesmo assim só o fim dela é mostrado.
        print(f"erro: n8n recusou a importação (código {r.returncode}): {(r.stderr or r.stdout).strip()[-400:]}",
              file=sys.stderr)
        return 2
    print(f"ok: credencial '{NOME_CREDENCIAL}' gravada no n8n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

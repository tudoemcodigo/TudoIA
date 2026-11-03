"""Gera a chave virtual do LiteLLM que só a SquadTI usa e a grava no .env como SQUADTI_API_KEY.

A chave tem alias e tag `squadti` (o gasto da Squad aparece separado em Atividade e Custos), validade de 90 dias e lista só os
perfis que a Squad aceita. `tudoia-max` (pago) e `tudoia-auto` ficam de fora de propósito: a chave não consegue chamá-los nem
por engano. O valor da chave nunca é impresso nem logado.

Uso (na raiz do repositório):
    uv run python -m scripts.squadti.chave                  # só gera se SQUADTI_API_KEY estiver vazia
    uv run python -m scripts.squadti.chave --rotacionar     # apaga a chave do alias e gera outra

Variáveis: LITELLM_MASTER_KEY (do .env), TUDOIA_LITELLM_URL (padrão http://127.0.0.1:4000).
Códigos de saída: 0 ok (inclusive "já existe"), 1 recusado pelo LiteLLM, 2 sem conexão ou sem master key.
Depois de gerar, recrie o container para ele ler a chave nova: `docker compose ... up -d squadti`.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import httpx

from tudoia_painel.envfile import gravar_valor, ler_env

RAIZ = Path(__file__).resolve().parents[2]
ALIAS = "squadti"
DURACAO = "90d"
MODELOS = ("tudoia-local-estrito", "tudoia-local-estrito-agente", "tudoia-local", "tudoia-local-agente",
           "tudoia-hibrido", "tudoia-nuvem", "tudoia-auto")
TIMEOUT_S = 20.0
TRANSPORTE = None   # seam dos testes: httpx.MockTransport


class ErroChave(Exception):
    def __init__(self, codigo: int, mensagem: str):
        super().__init__(mensagem)
        self.codigo = codigo


def _url() -> str:
    url = os.environ.get("TUDOIA_LITELLM_URL", "http://127.0.0.1:4000").rstrip("/")
    if not url.startswith(("http://127.0.0.1", "http://localhost")):
        raise ErroChave(2, "TUDOIA_LITELLM_URL deve apontar para o próprio computador (127.0.0.1 ou localhost)")
    return url


def gerar(raiz: Path | None = None, rotacionar: bool = False) -> str:
    """Devolve 'criada', 'ja-existe' ou 'rotacionada'. Levanta ErroChave. Nunca devolve nem imprime a chave."""
    raiz = raiz or RAIZ
    env_path = raiz / ".env"
    env = ler_env(env_path) if env_path.exists() else {}
    if (env.get("SQUADTI_API_KEY") or "").strip() and not rotacionar:
        return "ja-existe"
    mestre = (env.get("LITELLM_MASTER_KEY") or "").strip()
    if not mestre:
        raise ErroChave(2, "LITELLM_MASTER_KEY ausente no .env: rode `tudoia segredos` antes")
    cab = {"Authorization": f"Bearer {mestre}"}
    url = _url()
    try:
        with httpx.Client(timeout=TIMEOUT_S, transport=TRANSPORTE) as c:
            if rotacionar:
                c.post(f"{url}/key/delete", headers=cab, json={"key_aliases": [ALIAS]})
            r = c.post(f"{url}/key/generate", headers=cab, json={
                "key_alias": ALIAS, "duration": DURACAO, "models": list(MODELOS), "metadata": {"tags": [ALIAS]}})
    except httpx.HTTPError as e:
        raise ErroChave(2, f"não consegui falar com o LiteLLM em {url}: ele está no ar? ({type(e).__name__})") from e
    if r.status_code != 200:
        # sem repetir o corpo: o LiteLLM pode devolver pedaços da chave
        dica = "; já existe uma chave com o alias squadti: use --rotacionar" if r.status_code in (400, 409) else ""
        raise ErroChave(1, f"o LiteLLM recusou a criação da chave (HTTP {r.status_code}){dica}")
    chave = (r.json() or {}).get("key") or ""
    if not chave:
        raise ErroChave(1, "o LiteLLM não devolveu a chave")
    gravar_valor(env_path, "SQUADTI_API_KEY", chave, raiz / "dados" / "backups" / "env")
    return "rotacionada" if rotacionar else "criada"


MENSAGENS = {
    "criada": "SQUADTI_API_KEY criada no .env (alias e tag squadti, 90 dias).",
    "rotacionada": "SQUADTI_API_KEY rotacionada no .env.",
    "ja-existe": "SQUADTI_API_KEY já existe: nada a fazer (use --rotacionar para trocar).",
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rotacionar", action="store_true", help="apaga a chave do alias squadti e gera outra")
    args = ap.parse_args(argv)
    try:
        resultado = gerar(rotacionar=args.rotacionar)
    except ErroChave as e:
        print(f"erro: {e}", file=sys.stderr)
        return e.codigo
    print(MENSAGENS[resultado])
    if resultado != "ja-existe":
        print("Recrie o container para ele ler a chave: docker compose up -d squadti")
    return 0


if __name__ == "__main__":
    sys.exit(main())

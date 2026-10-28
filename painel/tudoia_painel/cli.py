"""Linha de comando: tudoia painel | sync | verificar."""
import argparse
import os
import secrets
import sys
from pathlib import Path

import governanca

from .envfile import ler_env, gravar_valor

RAIZ = Path(__file__).resolve().parents[2]

# Segredos internos gerados na primeira instalação. Só preenche o que está em branco: nunca troca um valor existente.
SEGREDOS_INTERNOS = ("WEBUI_SECRET_KEY", "SEARXNG_SECRET", "N8N_ENCRYPTION_KEY", "LITELLM_MASTER_KEY",
                     "LITELLM_DB_PASSWORD", "TUDOIA_SESSAO_SEGREDO", "CEREBRO_TOKEN_ESTATICO")


# Só com o perfil `keycloak` no COMPOSE_PROFILES: quem usa um Keycloak próprio já tem a senha de admin dele no .env.
SEGREDOS_KEYCLOAK = ("TUDOIA_KEYCLOAK_ADMIN_PASSWORD", "KEYCLOAK_DB_PASSWORD")


def preencher_segredos(raiz: Path) -> list[str]:
    """Gera segredos aleatórios para as chaves internas vazias. Devolve os nomes preenchidos (sem valores)."""
    env_path = raiz / ".env"
    atuais = ler_env(env_path) if env_path.exists() else {}
    preenchidos = []
    perfis = {p.strip() for p in (atuais.get("COMPOSE_PROFILES") or "").split(",")}
    for chave in SEGREDOS_INTERNOS + (SEGREDOS_KEYCLOAK if "keycloak" in perfis else ()):
        if not (atuais.get(chave) or "").strip():
            gravar_valor(env_path, chave, secrets.token_urlsafe(32), raiz / "dados" / "backups" / "env")
            preenchidos.append(chave)
    return preenchidos


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tudoia")
    sub = p.add_subparsers(dest="cmd", required=True)
    pn = sub.add_parser("painel", help="sobe o painel único em 127.0.0.1")
    pn.add_argument("--porta", type=int, default=3100)
    sub.add_parser("sync", help="distribui regras, skills e MCP para os clientes de IA")
    sub.add_parser("verificar", help="lista divergências (drift) sem escrever")
    sub.add_parser("segredos", help="gera os segredos internos vazios no .env (não troca os existentes)")
    sub.add_parser("gerar-config", help="gera runtime/litellm/config.yaml a partir do catálogo, do roteamento e do .env")
    args = p.parse_args(argv)

    if args.cmd == "painel":
        import uvicorn
        from .app import criar_app
        os.environ["TUDOIA_PAINEL_PORTA"] = str(args.porta)
        if sys.platform == "win32":
            try:
                from asyncio.proactor_events import _ProactorBasePipeTransport
                orig_call_connection_lost = _ProactorBasePipeTransport._call_connection_lost
                def _silenced_call_connection_lost(self, exc):
                    try:
                        orig_call_connection_lost(self, exc)
                    except (ConnectionResetError, ConnectionAbortedError, OSError):
                        pass
                _ProactorBasePipeTransport._call_connection_lost = _silenced_call_connection_lost
            except Exception:
                pass
        uvicorn.run(criar_app(RAIZ), host="127.0.0.1", port=args.porta, log_level="warning")
        return 0
    if args.cmd == "gerar-config":
        from .gerador import regenerar_config_litellm
        if not regenerar_config_litellm(RAIZ):
            print("ERRO: não consegui gerar o config do LiteLLM (veja o log acima)", file=sys.stderr)
            return 1
        print("gerado: runtime/litellm/config.yaml")
        return 0
    if args.cmd == "segredos":
        feitos = preencher_segredos(RAIZ)
        print("\n".join(f"gerado: {c}" for c in feitos) or "nada a gerar: todos os segredos já estão definidos")
        return 0
    try:
        if args.cmd == "sync":
            for alvo, estado in governanca.sincronizar(RAIZ).items():
                print(f"{estado:11} {alvo}")
            return 0
        drift = governanca.verificar(RAIZ)
    except governanca.ErroGovernanca as e:
        print(f"ERRO: {e}", file=sys.stderr)
        return 1
    print("\n".join(drift) or "tudo em sincronia")
    return 1 if drift else 0


if __name__ == "__main__":
    sys.exit(main())
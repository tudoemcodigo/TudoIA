import asyncio
import logging
import os

import uvicorn

from .autenticacao import ConfigOidc, Verificador, token_estatico_do_ambiente
from .servidor import PORTA, criar_app_http, criar_servidor

log = logging.getLogger("cerebro")


def _cfg() -> dict:
    return {
        "ollama_url": os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434"),
        "searxng_url": os.environ.get("SEARXNG_URL", "http://127.0.0.1:8080"),
        "docs": os.environ.get("CEREBRO_DOCS", "/docs"),
        "docs_host": os.environ.get("CEREBRO_DOCS_HOST", ""),
        "dados": os.environ.get("CEREBRO_DADOS", "/dados"),
    }


def _verificador() -> Verificador | None:
    config = ConfigOidc.do_ambiente(dict(os.environ))
    if config is None:
        log.warning("autenticação não configurada (CEREBRO_OIDC_ISSUER, CEREBRO_OIDC_JWKS_URL, CEREBRO_OIDC_CLIENT_ID): /mcp e /indexar recusam tudo")
        return None
    return Verificador(config)


async def _rodar() -> None:
    mcp = criar_servidor(_cfg())
    estatico = token_estatico_do_ambiente(dict(os.environ))
    if estatico is not None:
        # só o fato é registrado, nunca o valor
        log.info("token estático ativo (papel tudoia-operador, sem expiração)")
    app = criar_app_http(mcp, _verificador(), estatico)
    servidor = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=PORTA, log_level="info"))
    fundo = asyncio.create_task(mcp.tarefa_fundo())
    try:
        await servidor.serve()
    finally:
        fundo.cancel()


def _configurar_log() -> None:
    # sem isso os log.info do Cérebro somem (o handler de último recurso só mostra WARNING)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    log.setLevel(logging.INFO)  # o Cérebro em INFO mesmo que a raiz já tenha sido configurada por outro
    # httpx/httpcore em INFO registram a URL inteira de cada requisição, inclusive ?q=<consulta> do SearXNG
    for nome in ("httpx", "httpcore"):
        logging.getLogger(nome).setLevel(logging.WARNING)


if __name__ == "__main__":
    _configurar_log()
    asyncio.run(_rodar())

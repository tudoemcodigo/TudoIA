"""Trilha de auditoria do painel: quem alterou o quê, e quem viu um segredo.

Uma linha JSON por pedido que muda estado em /api (POST/PUT/PATCH/DELETE), inclusive os negados (403), em
dados/logs/auditoria.jsonl. Campos: instante, id do pedido (X-Request-ID), usuário, papéis, método, rota e status.
Nunca o corpo: ele pode trazer segredo (PUT /api/segredos) ou texto de prompt.
"""
import json
import logging
import threading
import time
from pathlib import Path

log = logging.getLogger(__name__)

METODOS_QUE_ALTERAM = {"POST", "PUT", "PATCH", "DELETE"}
LIMITE_ARQUIVO = 5 * 1024 * 1024  # ao passar disto, vira auditoria.jsonl.1 (sobrescreve a cópia anterior)


class Auditoria:
    """Middleware ASGI. Fica DENTRO do SessionMiddleware e POR FORA da GuardaAutorizacao: quando a guarda termina,
    a sessão (ou o token Bearer) já diz quem pediu, e o status diz se foi negado."""

    def __init__(self, app, arquivo: Path | None):
        self.app = app
        self.arquivo = Path(arquivo) if arquivo else None
        self._trava = threading.Lock()

    async def __call__(self, scope, receive, send):
        caminho = scope.get("path", "") if scope["type"] == "http" else ""
        if (self.arquivo is None or scope.get("method") not in METODOS_QUE_ALTERAM
                or not caminho.startswith("/api/")):
            return await self.app(scope, receive, send)
        status = 0

        async def enviar(msg):
            nonlocal status
            if msg["type"] == "http.response.start":
                status = msg["status"]
            await send(msg)

        try:
            await self.app(scope, receive, enviar)
        finally:
            self._registrar(scope, caminho, status or 500)

    def _registrar(self, scope, caminho: str, status: int) -> None:
        sessao = scope.get("session") or {}
        bearer = scope.get("tudoia_bearer") or {}
        usuario = sessao.get("usuario") or {}
        claims = bearer.get("claims") or {}
        linha = {
            "instante": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "id": scope.get("tudoia_id"),
            "usuario": usuario.get("email") or usuario.get("login") or usuario.get("sub")
                       or (f"cliente:{claims.get('azp')}" if claims else None),
            "papeis": sessao.get("papeis") or bearer.get("papeis") or [],
            "metodo": scope.get("method"),
            "rota": caminho,
            "status": status,
        }
        try:
            with self._trava:
                self.arquivo.parent.mkdir(parents=True, exist_ok=True)
                if self.arquivo.exists() and self.arquivo.stat().st_size > LIMITE_ARQUIVO:
                    self.arquivo.replace(self.arquivo.with_name(self.arquivo.name + ".1"))
                with self.arquivo.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(linha, ensure_ascii=False) + "\n")
        except OSError as e:  # disco cheio ou arquivo preso não derrubam o pedido; o aviso fica no log
            log.warning("auditoria não gravada (%s): %s %s", type(e).__name__, linha["metodo"], caminho)

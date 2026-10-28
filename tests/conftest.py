"""Sem rede de verdade nos testes.

Antes, testes do painel falavam com o ComfyUI, o Ollama e a Groq da máquina: o resultado e o tempo dependiam do
que estava no ar, e um deles descarregava os modelos do Ollama a cada execução. Aqui todo transporte HTTP real do
httpx falha com ConnectError; os testes que precisam de resposta usam httpx.MockTransport (não é afetado), e o
TestClient do FastAPI também não passa pela rede.

O teste de integração com o Keycloak (opt-in, TUDOIA_KEYCLOAK_IT=1) continua com rede.
"""
import os

import httpx
import pytest


def _sem_rede(self, request):
    raise httpx.ConnectError(f"rede bloqueada nos testes: {request.url.host}", request=request)


async def _sem_rede_async(self, request):
    raise httpx.ConnectError(f"rede bloqueada nos testes: {request.url.host}", request=request)


@pytest.fixture(autouse=True)
def _bloquear_rede(monkeypatch):
    if os.environ.get("TUDOIA_KEYCLOAK_IT") == "1":
        return
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", _sem_rede)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", _sem_rede_async)

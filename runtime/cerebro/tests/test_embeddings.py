import json

import httpx
import numpy as np
import pytest

from cerebro import embeddings
from cerebro.embeddings import ErroEmbeddings, OllamaEmbedder


def _usar(monkeypatch, handler):
    real = httpx.AsyncClient
    monkeypatch.setattr(
        embeddings.httpx, "AsyncClient",
        lambda **kw: real(transport=httpx.MockTransport(handler), **kw),
    )


async def test_33_textos_viram_2_lotes_e_saem_normalizados(monkeypatch):
    tamanhos = []

    def handler(req):
        corpo = json.loads(req.content)
        assert corpo["model"] == "bge-m3" and corpo["options"] == {"num_gpu": 0}
        tamanhos.append(len(corpo["input"]))
        return httpx.Response(200, json={"embeddings": [[3.0, 4.0]] * len(corpo["input"])})

    _usar(monkeypatch, handler)
    r = await OllamaEmbedder("http://x").embed([f"t{i}" for i in range(33)])
    assert tamanhos == [32, 1] and len(r) == 33
    assert all(abs(np.linalg.norm(v) - 1) < 1e-6 for v in r)


async def test_http_500_vira_erro_embeddings(monkeypatch):
    _usar(monkeypatch, lambda req: httpx.Response(500))
    with pytest.raises(ErroEmbeddings, match="500"):
        await OllamaEmbedder("http://x").embed(["a"])


async def test_falha_de_conexao_vira_erro_embeddings(monkeypatch):
    def handler(req):
        raise httpx.ConnectError("recusado")

    _usar(monkeypatch, handler)
    with pytest.raises(ErroEmbeddings, match="Ollama"):
        await OllamaEmbedder("http://x").embed(["a"])


async def test_resposta_sem_chave_embeddings(monkeypatch):
    _usar(monkeypatch, lambda req: httpx.Response(200, json={"outro": 1}))
    with pytest.raises(ErroEmbeddings, match="inesperada"):
        await OllamaEmbedder("http://x").embed(["a"])


async def test_quantidade_de_vetores_diferente_dos_textos(monkeypatch):
    _usar(monkeypatch, lambda req: httpx.Response(200, json={"embeddings": []}))
    with pytest.raises(ErroEmbeddings, match="0 vetores para 1"):
        await OllamaEmbedder("http://x").embed(["a"])

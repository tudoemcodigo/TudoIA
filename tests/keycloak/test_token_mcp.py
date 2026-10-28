"""Helper que obtém o token do tudoia-mcp (sem rede: httpx.MockTransport)."""

import json

import httpx
import pytest

from scripts.keycloak import token_mcp as tm

SEGREDO = "segredo-de-teste-123"


def _cliente(resposta):
    def handler(request: httpx.Request) -> httpx.Response:
        handler.corpo = dict(x.split("=", 1) for x in request.content.decode().split("&"))
        return resposta(request)

    return httpx.Client(transport=httpx.MockTransport(handler)), handler


def test_configuracao_ambiente_vence_env_file(tmp_path):
    env = tmp_path / ".env"
    env.write_text("TUDOIA_MCP_CLIENT_SECRET=do-arquivo\nTUDOIA_MCP_CLIENT_ID=arquivo\n", encoding="utf-8")
    cfg = tm.configuracao({"TUDOIA_MCP_CLIENT_ID": "ambiente"}, env)
    assert cfg["cliente"] == "ambiente" and cfg["segredo"] == "do-arquivo"


def test_configuracao_padroes(tmp_path):
    cfg = tm.configuracao({}, tmp_path / "nao-existe.env")
    assert cfg == {"url": "http://localhost:8180", "realm": "tudoia", "cliente": "tudoia-mcp", "segredo": ""}


def test_sem_segredo_sai_com_1(tmp_path, capsys):
    assert tm.main([], ambiente={}, arquivo_env=tmp_path / "x.env") == 1
    assert "TUDOIA_MCP_CLIENT_SECRET ausente" in capsys.readouterr().err


def test_obter_token_envia_client_credentials_e_devolve_o_token():
    cliente, handler = _cliente(lambda r: httpx.Response(200, json={"access_token": "tok", "expires_in": 28800}))
    dados = tm.obter_token({"url": "http://kc", "realm": "tudoia", "cliente": "tudoia-mcp", "segredo": SEGREDO}, cliente)
    assert dados["access_token"] == "tok" and dados["expires_in"] == 28800
    assert handler.corpo["grant_type"] == "client_credentials" and handler.corpo["client_id"] == "tudoia-mcp"


def test_credencial_recusada_nao_vaza_o_segredo():
    cliente, _ = _cliente(lambda r: httpx.Response(401, json={"error": "unauthorized_client"}))
    with pytest.raises(RuntimeError) as e:
        tm.obter_token({"url": "http://kc", "realm": "tudoia", "cliente": "tudoia-mcp", "segredo": SEGREDO}, cliente)
    assert SEGREDO not in str(e.value)


def test_keycloak_fora_nao_vaza_o_segredo():
    def falha(request):
        raise httpx.ConnectError("recusada")

    cliente = httpx.Client(transport=httpx.MockTransport(falha))
    with pytest.raises(RuntimeError) as e:
        tm.obter_token({"url": "http://kc", "realm": "tudoia", "cliente": "tudoia-mcp", "segredo": SEGREDO}, cliente)
    assert SEGREDO not in str(e.value)


def test_resposta_sem_access_token_e_erro():
    cliente, _ = _cliente(lambda r: httpx.Response(200, content=json.dumps({"expires_in": 5}).encode()))
    with pytest.raises(RuntimeError, match="access_token"):
        tm.obter_token({"url": "http://kc", "realm": "tudoia", "cliente": "tudoia-mcp", "segredo": SEGREDO}, cliente)

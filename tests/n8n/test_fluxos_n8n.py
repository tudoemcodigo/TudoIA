"""Fluxos do n8n versionados: nenhum segredo por variável de ambiente e formulário de ingestão autenticado."""
import json
from pathlib import Path

import pytest

from scripts.n8n.credencial_cerebro import ID_CREDENCIAL, NOME_CREDENCIAL, ErroConfiguracao, montar_credencial

FLUXOS = sorted((Path(__file__).resolve().parents[2] / "automacao" / "n8n").glob("*.json"))


@pytest.mark.parametrize("fluxo", FLUXOS, ids=lambda p: p.name)
def test_fluxo_nao_le_variavel_de_ambiente(fluxo):
    """O compose roda o n8n com N8N_BLOCK_ENV_ACCESS_IN_NODE=true: `$env` quebraria o fluxo."""
    texto = fluxo.read_text(encoding="utf-8")
    assert "$env" not in texto and "process.env" not in texto


def _no(nome):
    fluxo = json.loads((FLUXOS[0].parent / "ingerir-documento.json").read_text(encoding="utf-8"))
    return next(n for n in fluxo["nodes"] if n["name"] == nome), fluxo


def test_formulario_de_ingestao_exige_login_no_n8n():
    no, _ = _no("Formulário")
    assert no["parameters"]["authentication"] == "n8nUserAuth" and no["typeVersion"] >= 2.6


def test_indexacao_usa_a_credencial_que_o_script_cria():
    no, fluxo = _no("Indexar no cérebro")
    assert no["parameters"]["genericAuthType"] == "oAuth2Api"
    assert no["credentials"]["oAuth2Api"] == {"id": ID_CREDENCIAL, "name": NOME_CREDENCIAL}
    assert fluxo["connections"]["Salvar resumo"]["main"][0][0]["node"] == "Indexar no cérebro"


def test_credencial_client_credentials_com_segredo_do_env():
    [c] = montar_credencial({"TUDOIA_MCP_CLIENT_ID": "tudoia-mcp", "TUDOIA_MCP_CLIENT_SECRET": "s3gredo"})
    assert c["type"] == "oAuth2Api" and c["data"]["grantType"] == "clientCredentials"
    assert c["data"]["clientSecret"] == "s3gredo"
    assert c["data"]["accessTokenUrl"].endswith("/realms/tudoia/protocol/openid-connect/token")


@pytest.mark.parametrize("env", [{}, {"TUDOIA_MCP_CLIENT_SECRET": "   "}])
def test_sem_segredo_recusa_antes_do_docker(env):
    with pytest.raises(ErroConfiguracao):
        montar_credencial(env)

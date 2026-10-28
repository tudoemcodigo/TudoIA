"""Token estático (sem expiração, papel de operador): caminho feliz e cenários adversariais. Sem rede."""

import pytest

from cerebro import autenticacao as au
from cerebro.autenticacao import ErroAuth

SEGREDO = "s" * 43  # tamanho de secrets.token_urlsafe(32)
OUTRO = "o" * 43


def _bearer(token: str) -> list[tuple[bytes, bytes]]:
    return [(b"authorization", f"Bearer {token}".encode())]


# ----------------------------------------------------------------- configuração


def test_segredo_ausente_ou_curto_desliga_o_caminho():
    assert au.token_estatico_do_ambiente({}) is None
    assert au.token_estatico_do_ambiente({"CEREBRO_TOKEN_ESTATICO": ""}) is None
    assert au.token_estatico_do_ambiente({"CEREBRO_TOKEN_ESTATICO": "c" * 31}) is None


def test_segredo_com_tamanho_minimo_e_lido_sem_espacos():
    assert au.token_estatico_do_ambiente({"CEREBRO_TOKEN_ESTATICO": f"  {SEGREDO}\n"}) == SEGREDO


# ----------------------------------------------------------------- caminho feliz


async def test_token_estatico_devolve_papel_de_operador_sem_verificador():
    assert await au.autenticar(None, _bearer(SEGREDO), estatico=SEGREDO) == ["tudoia-operador"]


async def test_token_estatico_funciona_junto_com_o_verificador_jwt(verificador):
    assert await au.autenticar(verificador, _bearer(SEGREDO), estatico=SEGREDO) == ["tudoia-operador"]


# ----------------------------------------------------------------- adversarial


async def test_token_estatico_errado_e_401_e_nao_vira_jwt(verificador):
    with pytest.raises(ErroAuth) as erro:
        await au.autenticar(verificador, _bearer(OUTRO), estatico=SEGREDO)
    assert erro.value.status == 401


async def test_sem_segredo_configurado_o_token_estatico_nao_e_aceito(verificador):
    with pytest.raises(ErroAuth) as erro:
        await au.autenticar(verificador, _bearer(SEGREDO), estatico=None)
    assert erro.value.status == 401


async def test_revogacao_troca_o_segredo_e_o_antigo_passa_a_ser_recusado(verificador):
    with pytest.raises(ErroAuth):
        await au.autenticar(verificador, _bearer(SEGREDO), estatico=OUTRO)


async def test_bearer_vazio_com_segredo_configurado_e_401():
    with pytest.raises(ErroAuth) as erro:
        await au.autenticar(None, [(b"authorization", b"Bearer ")], estatico=SEGREDO)
    assert erro.value.status == 401


async def test_erro_do_token_estatico_nao_vaza_o_segredo(verificador):
    with pytest.raises(ErroAuth) as erro:
        await au.autenticar(verificador, _bearer(OUTRO), estatico=SEGREDO)
    assert SEGREDO not in erro.value.mensagem and OUTRO not in erro.value.mensagem


async def test_token_estatico_sem_verificador_e_o_unico_caminho_aberto():
    # sem CEREBRO_OIDC_* e sem segredo, o token JWT segue negado com 503 (fail-closed preservado)
    with pytest.raises(ErroAuth) as erro:
        await au.autenticar(None, _bearer(OUTRO), estatico=None)
    assert erro.value.status == 503

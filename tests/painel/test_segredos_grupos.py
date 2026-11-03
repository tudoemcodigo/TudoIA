"""Grupos de exibição e rótulos da tela Chaves e segredos (campos grupo/secreto em GET /api/segredos)."""
from tests.painel.test_painel import cenario  # noqa: F401  (fixture)
from tudoia_painel.rotas.segredos import grupo_da_chave


def _por_chave(c) -> dict:
    return {s["chave"]: s for s in c.get("/api/segredos").json()}


def test_toda_chave_tem_grupo_conhecido_e_flag_secreto(cenario):  # noqa: F811
    itens = _por_chave(cenario)
    grupos_validos = {"pagos", "gratuitos", "mcp", "servicos", "acesso", "configuracao"}
    assert itens and all(s["grupo"] in grupos_validos for s in itens.values())
    assert all(isinstance(s["secreto"], bool) for s in itens.values())


def test_grupo_segue_a_categoria_dos_provedores(cenario):  # noqa: F811
    itens = _por_chave(cenario)
    assert itens["OPENAI_API_KEY"]["grupo"] == "pagos"
    assert itens["GROQ_API_KEY"]["grupo"] == "gratuitos"
    assert itens["OPENAI_API_KEY"]["secreto"] is True


def test_configuracao_comum_nao_e_marcada_como_segredo_mas_continua_mascarada(cenario):  # noqa: F811
    tz = _por_chave(cenario)["TZ"]
    assert tz["grupo"] == "configuracao"
    assert tz["secreto"] is False
    assert tz["nome_provedor"] == "Fuso horário"
    assert "America/Sao_Paulo" not in cenario.get("/api/segredos").text


def test_chave_desconhecida_de_sistema_cai_em_servicos():
    assert grupo_da_chave("ALGUMA_SENHA_NOVA", "SISTEMA") == "servicos"
    assert grupo_da_chave("TUDOIA_OIDC_CLIENT_SECRET", "SISTEMA") == "acesso"
    assert grupo_da_chave("QUALQUER", "GOVERNANCA") == "mcp"

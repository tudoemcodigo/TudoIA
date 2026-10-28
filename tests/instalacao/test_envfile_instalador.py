import pytest

from tudoia_instalador import envfile
from tudoia_instalador.opcoes import Opcoes

MODELO = "# comentário\nTZ=\nCOMPOSE_PROFILES=cerebro\nGROQ_API_KEY=\nSEGREDO_EXISTENTE=nao-mexer\n"


def _o(**kw) -> Opcoes:
    return Opcoes(pasta_instalacao=r"D:\IA\TudoIA", admin_email="a@b.com", **kw)


def test_troca_a_chave_existente_e_acrescenta_a_que_falta():
    t = envfile.definir(MODELO, "TZ", "America/Sao_Paulo")
    assert "TZ=America/Sao_Paulo\n" in t and t.count("TZ=") == 1 and "# comentário" in t
    assert envfile.definir(MODELO, "NOVA_CHAVE", "x").endswith("NOVA_CHAVE=x\n")


@pytest.mark.parametrize("chave,valor", [("minuscula", "x"), ("A B", "x"), ("A=B", "x"), ("OK", "a\nB=c"), ("OK", "a\x00")])
def test_chave_ou_valor_perigosos_sao_recusados(chave, valor):
    with pytest.raises(ValueError):
        envfile.definir(MODELO, chave, valor)


def test_valor_com_barra_invertida_e_cifrao_fica_literal():
    t = envfile.definir("X=\n", "X", r"C:\pasta\$1\x")
    assert envfile.ler(t)["X"] == r"C:\pasta\$1\x"


def test_montar_aplica_so_o_que_as_opcoes_controlam():
    o = _o(componentes=["cerebro", "keycloak", "ollama"], chaves_provedores={"GROQ_API_KEY": "gsk_abc"}, projeto_compose="meu-tudoia")
    v = envfile.ler(envfile.montar(MODELO, o))
    assert v["COMPOSE_PROFILES"] == "cerebro,keycloak" and v["TUDOIA_COMPOSE_PROJETO"] == "meu-tudoia"
    assert v["GROQ_API_KEY"] == "gsk_abc" and v["SEGREDO_EXISTENTE"] == "nao-mexer"
    assert v["TUDOIA_OLLAMA_MODELS"] == r"D:\IA\TudoIA\modelos\ollama\models" and v["TUDOIA_COMFYUI_PORTABLE"] == ""


def test_montar_sem_ollama_nem_comfyui_deixa_os_caminhos_vazios():
    v = envfile.ler(envfile.montar(MODELO, _o(componentes=["keycloak"])))
    assert v["TUDOIA_OLLAMA_MODELS"] == "" and v["TUDOIA_COMFYUI_PORTABLE"] == ""


def test_keycloak_existente_grava_as_credenciais_do_admin():
    o = _o(componentes=["cerebro"], keycloak_existente=True, keycloak_existente_admin="root", keycloak_existente_senha="s3nha-longa")
    v = envfile.ler(envfile.montar(MODELO, o))
    assert v["TUDOIA_KEYCLOAK_ADMIN"] == "root" and v["TUDOIA_KEYCLOAK_ADMIN_PASSWORD"] == "s3nha-longa"
    assert "keycloak" not in v["COMPOSE_PROFILES"]


def test_montar_normaliza_crlf_e_e_idempotente():
    o = _o()
    uma = envfile.montar(MODELO.replace("\n", "\r\n"), o)
    assert "\r" not in uma and envfile.montar(uma, o) == uma

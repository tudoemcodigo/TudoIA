import pytest

from tudoia_instalador.opcoes import CHAVES_PROVEDORES, Opcoes, validar


def _ok(**mudancas) -> Opcoes:
    base = dict(pasta_instalacao=r"C:\TudoIA", admin_email="admin@exemplo.com.br")
    base.update(mudancas)
    return Opcoes(**base)


def campos(o: Opcoes) -> set[str]:
    return {c for c, _ in validar(o)}


def test_padrao_com_email_valido_passa():
    assert validar(_ok()) == []


@pytest.mark.parametrize("pasta", [
    r"C:\TudoIA & calc", r"C:\Tudo%PATH%", r"C:\Tudo$(x)", "C:\\Tudo`x", r"C:\Tudo'x", r"C:\Tudo;x", r"C:\Tudo^x",
    r"C:\Tudo!x", r"C:\..\Windows", r"C:\TudoIA\..\x", r"TudoIA", r"\\servidor\pasta", r"C:", "C:\\", "",
    r"C:\Windows\TudoIA", r"C:\Program Files\TudoIA", r"C:\ProgramData\TudoIA", r"C:\Tudo|x", r"C:\Tudo<x>",
    r"C:\Tudo*", r"C:\Tudo?", "C:\\Tudo\"x", r"C:\pasta.", "C:\\" + "a" * 100,
])
def test_pasta_perigosa_ou_invalida_e_recusada(pasta):
    assert "pasta_instalacao" in campos(_ok(pasta_instalacao=pasta))


@pytest.mark.parametrize("pasta", [r"C:\TudoIA", r"D:\IA\Tudo IA", r"C:\Users\fulano\TudoIA", r"E:\Ferramentas\TudoIA-2", r"C:\Instalações\TudoIA"])
def test_pastas_normais_passam(pasta):
    assert "pasta_instalacao" not in campos(_ok(pasta_instalacao=pasta))


def test_pastas_opcionais_vazias_sao_aceitas_e_preenchidas_com_o_padrao():
    o = _ok(pasta_instalacao=r"D:\IA\TudoIA")
    assert (str(o.dados), str(o.pesos_ollama)) == (r"D:\IA\TudoIA\dados", r"D:\IA\TudoIA\modelos\ollama\models")
    assert str(o.comfyui).endswith(r"modelos\comfyui\ComfyUI_windows_portable")


def test_pasta_opcional_invalida_e_recusada():
    assert "pasta_dados" in campos(_ok(pasta_dados=r"C:\x & y"))
    assert "pasta_pesos_ollama" in campos(_ok(pasta_pesos_ollama=r"relativa\pasta"))


@pytest.mark.parametrize("nome", ["", "Tudo", "-x", "a b", "a" * 40, "a;b", "../x"])
def test_nome_de_projeto_docker_invalido(nome):
    assert "projeto_compose" in campos(_ok(projeto_compose=nome))


def test_componente_desconhecido_ou_repetido():
    assert "componentes" in campos(_ok(componentes=["keycloak", "naoexiste"]))
    assert "componentes" in campos(_ok(componentes=["keycloak", "keycloak"]))


def test_painel_exige_login():
    assert "componentes" in campos(_ok(componentes=["cerebro"]))                         # sem Keycloak embutido nem existente
    assert validar(_ok(componentes=["cerebro"], keycloak_existente=True, keycloak_existente_senha="x" * 8)) == []


def test_keycloak_embutido_e_existente_juntos_e_recusado():
    assert "keycloak_existente" in campos(_ok(componentes=["keycloak"], keycloak_existente=True, keycloak_existente_senha="abcdefgh"))


def test_keycloak_existente_exige_usuario_e_senha_sem_quebra_de_linha():
    base = dict(componentes=["cerebro"], keycloak_existente=True)
    assert "keycloak_existente_senha" in campos(_ok(**base))
    assert "keycloak_existente_senha" in campos(_ok(**base, keycloak_existente_senha="abc\ndef"))
    assert "keycloak_existente_admin" in campos(_ok(**base, keycloak_existente_senha="x" * 8, keycloak_existente_admin="a b;c"))


@pytest.mark.parametrize("email", ["", "sem-arroba", "a@b", "a b@c.com", "<script>@x.com", "a@@b.com"])
def test_email_invalido(email):
    assert "admin_email" in campos(_ok(admin_email=email))


def test_fonte_github_valida_repo_e_ref():
    assert validar(_ok(fonte_codigo="github")) == []
    assert "github_repo" in campos(_ok(fonte_codigo="github", github_repo="so-um-nome"))
    assert "github_repo" in campos(_ok(fonte_codigo="github", github_repo="a/b; rm -rf"))
    assert "github_ref" in campos(_ok(fonte_codigo="github", github_ref="../../etc"))
    assert "fonte_codigo" in campos(_ok(fonte_codigo="ftp"))


def test_chaves_de_provedor_so_as_conhecidas_e_sem_quebra_de_linha():
    assert validar(_ok(chaves_provedores={"GROQ_API_KEY": "gsk_abc"})) == []
    assert "chaves_provedores" in campos(_ok(chaves_provedores={"PATH": "x"}))
    assert "chaves_provedores" in campos(_ok(chaves_provedores={"GROQ_API_KEY": "a\nPATH=x"}))
    assert "chaves_provedores" in campos(_ok(chaves_provedores={"GROQ_API_KEY": "a" * 600}))
    assert set(CHAVES_PROVEDORES) >= {"GROQ_API_KEY", "ANTHROPIC_API_KEY"}


def test_fuso_invalido():
    assert "fuso" in campos(_ok(fuso="America/Sao Paulo; x"))
    assert validar(_ok(fuso="UTC")) == []


def test_campo_desconhecido_vindo_da_tela_e_erro():
    with pytest.raises(ValueError):
        Opcoes.de_dict({"pasta_instalacao": r"C:\x", "executar": "calc"})


def test_publico_nunca_inclui_segredos():
    o = _ok(chaves_provedores={"GROQ_API_KEY": "gsk_segredo123"}, keycloak_existente_senha="senha-secreta")
    texto = str(o.publico())
    assert "gsk_segredo123" not in texto and "senha-secreta" not in texto
    assert o.publico()["chaves_provedores"] == ["GROQ_API_KEY"]


def test_perfis_do_compose():
    assert _ok(componentes=["cerebro", "keycloak", "ollama"]).perfis == ["cerebro", "keycloak"]
    assert _ok(componentes=["cerebro"], keycloak_existente=True).perfis == ["cerebro"]
    assert _ok(componentes=["webui", "n8n", "keycloak", "cerebro"]).perfis == ["cerebro", "webui", "n8n", "keycloak"]

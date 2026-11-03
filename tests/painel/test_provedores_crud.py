"""CRUD de provedores e modelos do catálogo pela API: GET/PATCH/DELETE /api/provedores[/{id}[/modelos/{nome}]].

Seam: só HTTP (TestClient), com o catálogo e o roteamento reais copiados para uma raiz temporária."""
import pytest
import yaml

from tests.painel.test_painel import PAPEL_ADMIN, cenario, sessao_assinada  # noqa: F401  (fixture)
from tudoia_painel.autenticacao import PAPEL_LEITOR, PAPEL_OPERADOR, decidir

SEGREDOS_DO_ENV = ("sk-super-secreto-1234567890", "gsk_123456", "sk-or-teste", "token-de-teste")


def _catalogo(c) -> dict:
    return yaml.safe_load((c.raiz / "config" / "catalogo-modelos.yaml").read_text(encoding="utf-8"))


def _texto_catalogo(c) -> str:
    return (c.raiz / "config" / "catalogo-modelos.yaml").read_text(encoding="utf-8")


def _item(c, pid) -> dict:
    return next(p for p in c.get("/api/provedores").json() if p["id"] == pid)


def _modelo_em_uso(c, nome="or/free", mid="openrouter/openrouter/free"):
    assert c.post("/api/provedores/openrouter/modelos",
                  json={"nome": nome, "id": mid, "papeis": ["chat"], "ativo": True}).status_code == 200
    assert c.put("/api/roteador/grupos", json={"ordem": {"tudoia-nuvem": [nome]}}).status_code == 200


# ------------------------------------------------------------ listagem
def test_lista_na_ordem_do_catalogo_com_formato_do_contrato(cenario):  # noqa: F811
    r = cenario.get("/api/provedores")
    assert r.status_code == 200
    itens = r.json()
    assert [p["id"] for p in itens] == list(_catalogo(cenario)["provedores"])

    chaves = {"id", "nome", "tier", "chave", "chaves_extras", "tem_chave", "chaves_faltando", "site_chave",
              "site_limites", "api_base", "url_modelos", "limites", "fonte_limites", "descartar_params",
              "total_modelos", "modelos_ativos", "modelos"}
    assert all(set(p) == chaves for p in itens)

    por_id = {p["id"]: p for p in itens}
    assert por_id["openrouter"]["tem_chave"] is True and por_id["openrouter"]["chaves_faltando"] == []
    assert por_id["openrouter"]["site_limites"] == "https://openrouter.ai/docs/api-reference/limits"
    assert por_id["nvidia"]["site_limites"] == ""   # fonte sem página oficial: nada inventado
    assert por_id["nvidia"]["api_base"] == "os.environ/NVIDIA_NIM_API_BASE"
    # Cloudflare precisa de duas variáveis; nenhuma está no .env do cenário
    assert por_id["cloudflare"]["tem_chave"] is False
    assert por_id["cloudflare"]["chaves_faltando"] == ["CLOUDFLARE_API_KEY", "CLOUDFLARE_ACCOUNT_ID"]
    assert por_id["groq"]["descartar_params"] == ["prompt_cache_key"]


def test_lista_nunca_devolve_valor_de_segredo(cenario):  # noqa: F811
    texto = cenario.get("/api/provedores").text
    assert not any(s in texto for s in SEGREDOS_DO_ENV)


def test_lista_marca_modelo_em_uso_no_roteamento(cenario):  # noqa: F811
    _modelo_em_uso(cenario)
    cenario.post("/api/provedores/openrouter/modelos", json={"nome": "or/livre", "id": "openrouter/x/livre"})
    modelos = {m["nome"]: m for m in _item(cenario, "openrouter")["modelos"]}
    assert modelos["or/free"]["em_uso"] is True and modelos["or/livre"]["em_uso"] is False
    item = _item(cenario, "openrouter")
    assert item["total_modelos"] == 2 and item["modelos_ativos"] == 2


# ------------------------------------------------------------ PATCH provedor
def test_editar_provedor_grava_e_devolve_o_item(cenario):  # noqa: F811
    r = cenario.patch("/api/provedores/openrouter", json={
        "nome": "OpenRouter editado",
        "tier": "PAID",
        "site_limites": "https://openrouter.ai/docs/limites-novos",
        "api_base": "os.environ/OPENROUTER_API_BASE",
        "limites": {"rpm": 10, "usd_dia": 0.5, "reset": "utc"},
        "url_modelos": "",   # "" limpa
    })
    assert r.status_code == 200, r.text
    item = r.json()
    assert item == _item(cenario, "openrouter")
    assert item["nome"] == "OpenRouter editado" and item["tier"] == "PAID"
    assert item["api_base"] == "os.environ/OPENROUTER_API_BASE" and item["url_modelos"] == ""
    assert item["limites"] == {"rpm": 10, "usd_dia": 0.5, "reset": "utc"}

    p = _catalogo(cenario)["provedores"]["openrouter"]
    assert "url_modelos" not in p
    assert isinstance(p["limites"]["rpm"], int)   # 10, não 10.0
    assert p["fonte_limites"].startswith("openrouter.ai/docs")   # campo não enviado não muda
    assert list(p)[-1] == "modelos"   # campo novo não fica depois da lista de modelos


def test_editar_sem_mudanca_nao_regrava_o_catalogo(cenario):  # noqa: F811
    antes = _texto_catalogo(cenario)
    assert cenario.patch("/api/provedores/groq", json={}).status_code == 200
    assert cenario.patch("/api/provedores/groq", json={"tier": "FREE", "nome": None}).status_code == 200
    assert _texto_catalogo(cenario) == antes


@pytest.mark.parametrize("corpo, campo", [
    ({"site_chave": "javascript:alert(1)"}, "site_chave"),
    ({"site_limites": "ftp://exemplo.com/limites"}, "site_limites"),
    ({"url_modelos": "https://"}, "url_modelos"),
    ({"site_limites": "https://exemplo.com/a b"}, "site_limites"),
    ({"api_base": "os.environ/minusculo"}, "api_base"),
    ({"api_base": "data:text/html,oi"}, "api_base"),
    ({"tier": "GRATIS"}, "tier"),
    ({"campo_x": 1}, "campo_x"),
    ({"chave": "OUTRA_API_KEY"}, "chave"),   # trocar a variável da chave não é edição suportada
    ({"limites": {"rpm": True}}, "limites.rpm"),
    ({"limites": {"rpm": "10"}}, "limites.rpm"),
    ({"limites": {"rpm": -1}}, "limites.rpm"),
    ({"limites": {"desconhecido": 1}}, "limites.desconhecido"),
    ({"nome": "x" * 129}, "nome"),
])
def test_editar_provedor_recusa_entrada_invalida(cenario, corpo, campo):  # noqa: F811
    antes = _texto_catalogo(cenario)
    r = cenario.patch("/api/provedores/openrouter", json=corpo)
    assert r.status_code == 422, r.text
    assert r.json()["erro"]["codigo"] == "validacao" and r.json()["erro"]["campo"] == campo
    assert _texto_catalogo(cenario) == antes


def test_editar_nome_so_com_espacos_e_recusado(cenario):  # noqa: F811
    antes = _texto_catalogo(cenario)
    r = cenario.patch("/api/provedores/openrouter", json={"nome": "   "})
    assert r.status_code == 422 and _texto_catalogo(cenario) == antes


# ------------------------------------------------------------ 404
@pytest.mark.parametrize("metodo, caminho, corpo", [
    ("PATCH", "/api/provedores/nao-existe", {"nome": "x"}),
    ("DELETE", "/api/provedores/nao-existe", None),
    ("PATCH", "/api/provedores/nao-existe/modelos/a/b", {"ativo": False}),
    ("DELETE", "/api/provedores/nao-existe/modelos/a/b", None),
    ("PATCH", "/api/provedores/openrouter/modelos/nao/existe", {"ativo": False}),
    ("DELETE", "/api/provedores/openrouter/modelos/nao/existe", None),
])
def test_provedor_ou_modelo_desconhecido_da_404(cenario, metodo, caminho, corpo):  # noqa: F811
    antes = _texto_catalogo(cenario)
    r = cenario.request(metodo, caminho, json=corpo) if corpo is not None else cenario.request(metodo, caminho)
    assert r.status_code == 404, r.text
    assert r.json()["erro"]["codigo"] == "nao_encontrado"
    assert _texto_catalogo(cenario) == antes


# ------------------------------------------------------------ DELETE provedor
def test_remover_provedor_com_modelo_no_roteamento_da_409(cenario):  # noqa: F811
    _modelo_em_uso(cenario)
    r = cenario.delete("/api/provedores/openrouter")
    assert r.status_code == 409
    erro = r.json()["erro"]
    assert erro["codigo"] == "em_uso_no_roteamento"
    assert erro["extras"]["referencias"] == [{"modelo": "or/free", "grupos": ["tudoia-nuvem"]}]
    assert "openrouter" in _catalogo(cenario)["provedores"]


def test_remover_provedor_livre_tira_do_catalogo_e_mantem_o_env(cenario):  # noqa: F811
    env_antes = (cenario.raiz / ".env").read_bytes()
    r = cenario.delete("/api/provedores/cloudflare")
    assert r.status_code == 200, r.text
    dados = r.json()
    assert dados["ok"] is True and dados["id"] == "cloudflare"
    assert dados["chaves_mantidas"] == ["CLOUDFLARE_API_KEY", "CLOUDFLARE_ACCOUNT_ID"]
    assert "cloudflare" not in _catalogo(cenario)["provedores"]
    assert "cloudflare" not in [p["id"] for p in cenario.get("/api/provedores").json()]
    assert (cenario.raiz / ".env").read_bytes() == env_antes


def test_remover_provedor_com_chave_preenchida_nao_vaza_o_valor(cenario):  # noqa: F811
    r = cenario.delete("/api/provedores/openai")
    assert r.status_code == 200 and r.json()["chaves_mantidas"] == ["OPENAI_API_KEY"]
    assert not any(s in r.text for s in SEGREDOS_DO_ENV)


# ------------------------------------------------------------ modelos
def test_editar_modelo_com_nome_que_tem_barra(cenario):  # noqa: F811
    cenario.post("/api/provedores/openrouter/modelos",
                 json={"nome": "or/meu-modelo", "id": "openrouter/vendor/meu-modelo:free", "papeis": ["chat"]})
    r = cenario.patch("/api/provedores/openrouter/modelos/or/meu-modelo",
                      json={"ativo": False, "papeis": ["codigo", "chat", "codigo"], "contexto": 32000})
    assert r.status_code == 200, r.text
    assert r.json()["modelo"] == {"nome": "or/meu-modelo", "id": "openrouter/vendor/meu-modelo:free",
                                  "papeis": ["codigo", "chat"], "contexto": 32000, "ativo": False}
    m = next(m for m in _item(cenario, "openrouter")["modelos"] if m["nome"] == "or/meu-modelo")
    assert m["ativo"] is False and m["contexto"] == 32000 and m["papeis"] == ["codigo", "chat"]


@pytest.mark.parametrize("corpo, campo", [
    ({"contexto": 0}, "contexto"),
    ({"contexto": True}, "contexto"),
    ({"contexto": 1.5}, "contexto"),
    ({"ativo": "talvez"}, "ativo"),
    ({"papeis": ["chat"] * 17}, "papeis"),
    ({"papeis": [""]}, "papeis[0]"),
    ({"nome": "outro"}, "nome"),
])
def test_editar_modelo_recusa_entrada_invalida(cenario, corpo, campo):  # noqa: F811
    cenario.post("/api/provedores/openrouter/modelos", json={"nome": "or/m", "id": "openrouter/v/m"})
    antes = _texto_catalogo(cenario)
    r = cenario.patch("/api/provedores/openrouter/modelos/or/m", json=corpo)
    assert r.status_code == 422, r.text
    assert r.json()["erro"]["campo"] == campo
    assert _texto_catalogo(cenario) == antes


def test_remover_modelo_em_uso_da_409_e_livre_sai(cenario):  # noqa: F811
    _modelo_em_uso(cenario)
    cenario.post("/api/provedores/openrouter/modelos", json={"nome": "or/livre", "id": "openrouter/x/livre"})

    r = cenario.delete("/api/provedores/openrouter/modelos/or/free")
    assert r.status_code == 409
    assert r.json()["erro"]["extras"]["referencias"] == [{"modelo": "or/free", "grupos": ["tudoia-nuvem"]}]

    r = cenario.delete("/api/provedores/openrouter/modelos/or/livre")
    assert r.status_code == 200 and r.json()["removido"] == "or/livre"
    assert [m["nome"] for m in _catalogo(cenario)["provedores"]["openrouter"]["modelos"]] == ["or/free"]


# ------------------------------------------------------------ cadastro com site_limites
def test_cadastro_guarda_site_limites_e_fonte_padrao(cenario):  # noqa: F811
    r = cenario.post("/api/provedores", json={
        "id": "mistral", "nome": "Mistral AI", "tier": "PAID", "chave": "MISTRAL_API_KEY",
        "site_limites": "https://docs.mistral.ai/limites",
    })
    assert r.status_code == 200, r.text
    item = _item(cenario, "mistral")
    assert item["site_limites"] == "https://docs.mistral.ai/limites"
    assert item["fonte_limites"] == "Configurado pelo usuário no painel"   # antes virava o texto "None"
    # sem valor_chave o .env não é tocado (antes gravava MISTRAL_API_KEY=None e o provedor parecia configurado)
    assert item["tem_chave"] is False and item["chaves_faltando"] == ["MISTRAL_API_KEY"]
    assert "MISTRAL_API_KEY" not in (cenario.raiz / ".env").read_text(encoding="utf-8")


def test_cadastro_recusa_link_que_nao_e_http(cenario):  # noqa: F811
    r = cenario.post("/api/provedores", json={
        "id": "mau", "nome": "Mau", "tier": "PAID", "chave": "MAU_API_KEY", "site_limites": "javascript:alert(1)"})
    assert r.status_code == 422 and r.json()["erro"]["campo"] == "site_limites"
    assert "mau" not in _catalogo(cenario)["provedores"]


# ------------------------------------------------------------ autorização
@pytest.mark.parametrize("metodo, caminho", [
    ("GET", "/api/provedores"),
    ("PATCH", "/api/provedores/groq"),
    ("DELETE", "/api/provedores/groq"),
    ("PATCH", "/api/provedores/groq/modelos/a/b"),
    ("DELETE", "/api/provedores/groq/modelos/a/b"),
])
@pytest.mark.parametrize("papel", [PAPEL_OPERADOR, PAPEL_LEITOR])
def test_crud_de_provedores_e_so_admin(metodo, caminho, papel):
    assert decidir(metodo, caminho, [papel])[0] == 403
    assert decidir(metodo, caminho, [PAPEL_ADMIN]) is None


def test_operador_recebe_403_na_api_real(cenario):  # noqa: F811
    antes = _texto_catalogo(cenario)
    cenario.cookies.set("tudoia_sessao", sessao_assinada([PAPEL_OPERADOR]))
    assert cenario.patch("/api/provedores/groq", json={"nome": "x"}).status_code == 403
    assert cenario.delete("/api/provedores/groq").status_code == 403
    assert _texto_catalogo(cenario) == antes

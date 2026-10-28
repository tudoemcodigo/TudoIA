"""Token Bearer de cliente de serviço no /api do painel (cliente tudoia-capturas, somente leitura).

As chaves são geradas no próprio teste e injetadas no cache de JWKS, então não há rede nem Keycloak.
Cobre o caminho feliz (leitor lê) e o que tem que falhar: assinatura, emissor, validade, cliente (azp),
algoritmo forjado, papel insuficiente e IdP indisponível (fail-closed).
"""
import time

import pytest
from joserfc import jwt as jose_jwt
from joserfc.jwk import KeySet, OctKey, RSAKey
from fastapi.testclient import TestClient

from tudoia_painel.app import criar_app
from tudoia_painel.autenticacao import ConfigAuth

ISSUER = "https://idp.teste/realms/tudoia"
CLIENTE = "tudoia-capturas"
BASE = "http://127.0.0.1:3100"
SEGREDO = "s" * 48

CONFIG = ConfigAuth(
    issuer=ISSUER, client_id="tudoia-painel", client_secret="segredo-de-teste",
    segredo_sessao=SEGREDO, bearer_clientes=frozenset({CLIENTE}),
)

_CHAVE = RSAKey.generate_key(2048, parameters={"kid": "k1", "alg": "RS256"}, private=True)
_CHAVE_PUBLICA = KeySet.import_key_set({"keys": [_CHAVE.as_dict(private=False)]})
_CHAVE_INTRUSA = RSAKey.generate_key(2048, parameters={"kid": "k1", "alg": "RS256"}, private=True)


def token(*, papeis=("tudoia-leitor",), azp=CLIENTE, iss=ISSUER, expira_em=None, chave=_CHAVE, alg="RS256",
          aud=("tudoia-painel",), kid="k1"):
    agora = int(time.time())
    payload = {
        "iss": iss, "azp": azp, "sub": "svc-1", "iat": agora,
        "exp": expira_em if expira_em is not None else agora + 300,
        "realm_access": {"roles": list(papeis)}, "groups": list(papeis),
    }
    if aud is not None:
        payload["aud"] = list(aud)
    cabecalho = {"alg": alg, "kid": kid}
    if alg == "HS256":  # ataque clássico de confusão de algoritmo: usa a chave pública como segredo HMAC
        return jose_jwt.encode(cabecalho, payload, OctKey.import_key(b"segredo-publico"))
    return jose_jwt.encode(cabecalho, payload, chave)


@pytest.fixture
def app_bearer(tmp_path, monkeypatch):
    async def chaves_de_teste(self):
        return _CHAVE_PUBLICA

    monkeypatch.setattr("tudoia_painel.autenticacao.CacheJwks._baixar", chaves_de_teste)
    raiz = tmp_path / "raiz"
    raiz.mkdir()
    return criar_app(raiz, servicos=_ServicoFalso(), home=tmp_path / "home", autenticacao=CONFIG)


class _ServicoFalso:
    def listar(self):
        return []

    def acao(self, nome, acao):
        pass

    def acao_todos(self, acao):
        pass


def bearer(valor):
    return {"Authorization": f"Bearer {valor}"}


def test_leitor_com_token_valido_le_o_api(app_bearer):
    with TestClient(app_bearer, base_url=BASE) as c:
        r = c.get("/api/servicos", headers=bearer(token()))
        assert r.status_code == 200


def test_token_de_leitor_nao_altera(app_bearer):
    with TestClient(app_bearer, base_url=BASE) as c:
        r = c.post("/api/servicos/teste/acao", headers=bearer(token()), json={})
        assert r.status_code == 403
        assert r.json()["erro"]["codigo"] == "papel_insuficiente"


def test_token_de_leitor_nao_acessa_rota_de_admin(app_bearer):
    with TestClient(app_bearer, base_url=BASE) as c:
        r = c.get("/api/segredos", headers=bearer(token()))
        assert r.status_code == 403
        assert r.json()["erro"]["codigo"] == "papel_insuficiente"


def test_token_expirado_e_recusado(app_bearer):
    with TestClient(app_bearer, base_url=BASE) as c:
        r = c.get("/api/servicos", headers=bearer(token(expira_em=int(time.time()) - 60)))
        assert r.status_code == 401
        assert r.json()["erro"]["codigo"] == "token_invalido"


def test_token_de_outro_cliente_e_recusado(app_bearer):
    with TestClient(app_bearer, base_url=BASE) as c:
        r = c.get("/api/servicos", headers=bearer(token(azp="tudoia-mcp")))
        assert r.status_code == 401


def test_token_de_outro_emissor_e_recusado(app_bearer):
    with TestClient(app_bearer, base_url=BASE) as c:
        r = c.get("/api/servicos", headers=bearer(token(iss="https://outro.idp/realms/x")))
        assert r.status_code == 401


def test_token_assinado_por_outra_chave_e_recusado(app_bearer):
    with TestClient(app_bearer, base_url=BASE) as c:
        r = c.get("/api/servicos", headers=bearer(token(chave=_CHAVE_INTRUSA)))
        assert r.status_code == 401


def test_token_hs256_com_chave_publica_e_recusado(app_bearer):
    with TestClient(app_bearer, base_url=BASE) as c:
        r = c.get("/api/servicos", headers=bearer(token(alg="HS256")))
        assert r.status_code == 401


def test_token_sem_papel_do_painel_e_recusado(app_bearer):
    with TestClient(app_bearer, base_url=BASE) as c:
        r = c.get("/api/servicos", headers=bearer(token(papeis=("papel-qualquer",))))
        assert r.status_code == 403
        assert r.json()["erro"]["codigo"] == "papel_insuficiente"


def test_cabecalho_que_nao_e_bearer_e_recusado(app_bearer):
    with TestClient(app_bearer, base_url=BASE) as c:
        r = c.get("/api/servicos", headers={"Authorization": "Basic dGVzdGU6dGVzdGU="})
        assert r.status_code == 401


def test_bearer_desligado_quando_nenhum_cliente_e_autorizado(tmp_path, monkeypatch):
    async def chaves_de_teste(self):
        return _CHAVE_PUBLICA

    monkeypatch.setattr("tudoia_painel.autenticacao.CacheJwks._baixar", chaves_de_teste)
    raiz = tmp_path / "raiz"
    raiz.mkdir()
    sem_clientes = ConfigAuth(issuer=ISSUER, client_id="tudoia-painel", client_secret="x", segredo_sessao=SEGREDO)
    app = criar_app(raiz, servicos=_ServicoFalso(), home=tmp_path / "home", autenticacao=sem_clientes)
    with TestClient(app, base_url=BASE) as c:
        r = c.get("/api/servicos", headers=bearer(token()))
        assert r.status_code == 401
        assert r.json()["erro"]["codigo"] == "bearer_desativado"


def test_idp_indisponivel_nega_fail_closed(tmp_path, monkeypatch):
    async def fora_do_ar(self):
        raise ConnectionError("keycloak fora")

    monkeypatch.setattr("tudoia_painel.autenticacao.CacheJwks._baixar", fora_do_ar)
    raiz = tmp_path / "raiz"
    raiz.mkdir()
    app = criar_app(raiz, servicos=_ServicoFalso(), home=tmp_path / "home", autenticacao=CONFIG)
    with TestClient(app, base_url=BASE) as c:
        r = c.get("/api/servicos", headers=bearer(token()))
        assert r.status_code == 503
        assert r.json()["erro"]["codigo"] == "identidade_indisponivel"


def test_sessao_mostra_a_identidade_do_token(app_bearer):
    with TestClient(app_bearer, base_url=BASE) as c:
        dados = c.get("/api/sessao", headers=bearer(token())).json()
        assert dados["autenticado"] is True
        assert dados["via"] == "bearer"
        assert dados["papeis"] == ["tudoia-leitor"]
        assert dados["admin"] is False and dados["pode_alterar"] is False


def test_sessao_sem_token_continua_nao_autenticada(app_bearer):
    with TestClient(app_bearer, base_url=BASE) as c:
        assert c.get("/api/sessao").json()["autenticado"] is False


def test_token_sem_audiencia_do_painel_e_recusado(app_bearer):
    # token válido de outro serviço do realm (azp igual, mas emitido para outro recurso)
    for aud in (None, ("tudoia-mcp",), ()):
        r = TestClient(app_bearer, base_url=BASE).get("/api/servicos", headers=bearer(token(aud=aud)))
        assert r.status_code == 401, aud


def test_jwks_renova_com_kid_desconhecido_respeitando_o_intervalo(monkeypatch):
    import asyncio

    from tudoia_painel import autenticacao as a

    nova = RSAKey.generate_key(2048, parameters={"kid": "k2", "alg": "RS256"}, private=True)
    versoes = [_CHAVE_PUBLICA, KeySet.import_key_set({"keys": [_CHAVE.as_dict(private=False), nova.as_dict(private=False)]})]
    buscas = []

    async def buscar():
        buscas.append(1)
        return versoes[min(len(buscas) - 1, 1)]

    relogio = [1000.0]
    monkeypatch.setattr(a.time, "time", lambda: relogio[0])
    cache = a.CacheJwks(ISSUER, buscar=buscar)
    obter = lambda kid: asyncio.run(cache.obter(kid))  # noqa: E731
    obter("k1")
    obter("k1")
    assert len(buscas) == 1                       # kid conhecido: usa o cache
    obter("k2")
    assert len(buscas) == 1                       # kid novo, mas dentro do intervalo mínimo: não martela o IdP
    relogio[0] += a.INTERVALO_MIN_RECARGA_JWKS_S + 1
    chaves = obter("k2")
    assert len(buscas) == 2 and any(k.kid == "k2" for k in chaves.keys)   # rotação absorvida sem esperar o TTL
    obter("forjado")                              # kid inexistente logo depois: sem nova busca
    assert len(buscas) == 2


def test_jwks_busca_unica_com_pedidos_simultaneos():
    import asyncio

    from tudoia_painel import autenticacao as a

    buscas = []

    async def buscar():
        buscas.append(1)
        await asyncio.sleep(0.05)
        return _CHAVE_PUBLICA

    cache = a.CacheJwks(ISSUER, buscar=buscar)

    async def todos():
        await asyncio.gather(*(cache.obter("k1") for _ in range(10)))

    asyncio.run(todos())
    assert len(buscas) == 1


def test_kid_do_token_ignora_lixo():
    from tudoia_painel.autenticacao import kid_do_token

    assert kid_do_token("isso.nao.eh-jwt") is None
    assert kid_do_token("") is None
    assert kid_do_token(token()) == "k1"

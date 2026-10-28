"""Verificação de JWT do Cérebro: caminho feliz e os cenários adversariais (sem rede; JWKS injetado)."""

import base64
import hashlib
import hmac
import json

import pytest

from cerebro import autenticacao as au
from cerebro.autenticacao import ConfigOidc, ErroAuth, Verificador
from conftest import CLIENTE_TESTE, ISSUER_TESTE


def _b64(dados: bytes) -> str:
    return base64.urlsafe_b64encode(dados).rstrip(b"=").decode()


def _bruto(header: dict, claims: dict, assinatura: bytes = b"") -> str:
    partes = [_b64(json.dumps(header).encode()), _b64(json.dumps(claims).encode()), _b64(assinatura)]
    return ".".join(partes)


def _bearer(token: str) -> list[tuple[bytes, bytes]]:
    return [(b"authorization", f"Bearer {token}".encode())]


class Relogio:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


# ----------------------------------------------------------------- caminho feliz


async def test_token_valido_devolve_papeis(verificador, emitir):
    papeis = await au.autenticar(verificador, _bearer(emitir()))
    assert papeis == ["tudoia-operador"]


async def test_papel_vem_do_claim_groups_com_caminho(verificador, emitir):
    token = emitir(realm_access=None, groups=["/tudoia-leitor"])
    assert await au.autenticar(verificador, _bearer(token)) == ["tudoia-leitor"]


def test_papeis_do_token_ignora_papeis_que_nao_sao_do_cerebro():
    claims = {"realm_access": {"roles": ["offline_access", "tudoia-admin"]}, "groups": ["outro"]}
    assert au.papeis_do_token(claims) == ["tudoia-admin"]


def test_config_exige_os_tres_campos_e_http():
    completo = {"CEREBRO_OIDC_ISSUER": "http://localhost:8180/realms/tudoia/",
                "CEREBRO_OIDC_JWKS_URL": "http://host.docker.internal:8180/x",
                "CEREBRO_OIDC_CLIENT_ID": "tudoia-mcp"}
    config = ConfigOidc.do_ambiente(completo)
    assert config.issuers == ("http://localhost:8180/realms/tudoia",)  # barra final removida
    for faltando in completo:
        assert ConfigOidc.do_ambiente({k: v for k, v in completo.items() if k != faltando}) is None
    assert ConfigOidc.do_ambiente({**completo, "CEREBRO_OIDC_JWKS_URL": "file:///etc/passwd"}) is None


# ----------------------------------------------------------------- adversariais: token


async def test_token_expirado_e_recusado(verificador, emitir):
    token = emitir(exp=1)
    with pytest.raises(ErroAuth) as e:
        await au.autenticar(verificador, _bearer(token))
    assert e.value.status == 401


async def test_nbf_no_futuro_e_recusado(verificador, emitir):
    import time

    with pytest.raises(ErroAuth) as e:
        await au.autenticar(verificador, _bearer(emitir(nbf=int(time.time()) + 3600)))
    assert e.value.status == 401


async def test_emissor_errado_e_recusado(verificador, emitir):
    with pytest.raises(ErroAuth) as e:
        await au.autenticar(verificador, _bearer(emitir(iss="http://evil.example/realms/tudoia")))
    assert e.value.status == 401


async def test_emissor_sem_barra_final_e_recusado_quando_difere(verificador, emitir):
    # Comparação exata: o iss precisa ser igual ao configurado, sem normalização.
    with pytest.raises(ErroAuth):
        await au.autenticar(verificador, _bearer(emitir(iss=ISSUER_TESTE + "/")))


async def test_azp_de_outro_cliente_e_recusado(verificador, emitir):
    with pytest.raises(ErroAuth) as e:
        await au.autenticar(verificador, _bearer(emitir(azp="tudoia-painel")))
    assert e.value.status == 401


async def test_aud_sem_o_cliente_esperado_e_recusado(verificador, emitir):
    with pytest.raises(ErroAuth) as e:
        await au.autenticar(verificador, _bearer(emitir(aud=["account", "outro-cliente"])))
    assert e.value.status == 401


async def test_token_sem_aud_e_recusado(verificador, emitir):
    with pytest.raises(ErroAuth):
        await au.autenticar(verificador, _bearer(emitir(aud=None)))


async def test_alg_none_sem_assinatura_e_recusado(verificador, emitir):
    import time

    agora = int(time.time())
    claims = {"iss": ISSUER_TESTE, "azp": CLIENTE_TESTE, "aud": [CLIENTE_TESTE], "exp": agora + 600,
              "realm_access": {"roles": ["tudoia-admin"]}}
    token = _bruto({"alg": "none", "kid": "chave-1"}, claims)
    with pytest.raises(ErroAuth) as e:
        await au.autenticar(verificador, _bearer(token))
    assert e.value.status == 401


async def test_hs256_com_a_chave_publica_como_segredo_e_recusado(verificador, emitir, chave_rsa):
    # Ataque clássico de confusão de algoritmo: assinar HS256 usando a chave pública como segredo.
    import time

    agora = int(time.time())
    claims = {"iss": ISSUER_TESTE, "azp": CLIENTE_TESTE, "aud": [CLIENTE_TESTE], "exp": agora + 600,
              "realm_access": {"roles": ["tudoia-admin"]}}
    cab = _b64(json.dumps({"alg": "HS256", "kid": "chave-1"}).encode())
    corpo = _b64(json.dumps(claims).encode())
    segredo = json.dumps(chave_rsa.as_dict(private=False)).encode()
    assinatura = hmac.new(segredo, f"{cab}.{corpo}".encode(), hashlib.sha256).digest()
    with pytest.raises(ErroAuth) as e:
        await au.autenticar(verificador, _bearer(f"{cab}.{corpo}.{_b64(assinatura)}"))
    assert e.value.status == 401


async def test_assinado_por_outra_chave_com_o_mesmo_kid_e_recusado(verificador, emitir, chave_intrusa):
    with pytest.raises(ErroAuth) as e:
        await au.autenticar(verificador, _bearer(emitir(chave=chave_intrusa)))
    assert e.value.status == 401


async def test_kid_desconhecido_e_recusado(verificador, emitir):
    with pytest.raises(ErroAuth) as e:
        await au.autenticar(verificador, _bearer(emitir(kid="chave-que-nao-existe")))
    assert e.value.status == 401


async def test_token_sem_kid_e_recusado(verificador, chave_rsa):
    import time

    from joserfc import jwt

    token = jwt.encode({"alg": "RS256"}, {"iss": ISSUER_TESTE, "exp": int(time.time()) + 60,
                                          "azp": CLIENTE_TESTE, "aud": [CLIENTE_TESTE]}, chave_rsa)
    with pytest.raises(ErroAuth) as e:
        await au.autenticar(verificador, _bearer(token))
    assert e.value.status == 401


async def test_token_grande_demais_e_recusado_antes_de_decodificar(verificador):
    with pytest.raises(ErroAuth) as e:
        await au.autenticar(verificador, _bearer("a" * (au.TAMANHO_MAX_TOKEN + 1)))
    assert e.value.status == 401


# ----------------------------------------------------------------- adversariais: cabeçalho e papel


async def test_sem_cabecalho_e_401(verificador):
    with pytest.raises(ErroAuth) as e:
        await au.autenticar(verificador, [])
    assert (e.value.status, e.value.codigo) == (401, "token_ausente")


@pytest.mark.parametrize("valor", [b"Basic dXNlcjpzZW5oYQ==", b"Bearer", b"Bearer ", b"Bearer \xff\xfe", b"Token x"])
async def test_esquema_ou_valor_invalido_e_401(verificador, valor):
    with pytest.raises(ErroAuth) as e:
        await au.autenticar(verificador, [(b"authorization", valor)])
    assert e.value.status == 401


async def test_dois_cabecalhos_authorization_e_401(verificador, emitir):
    token = emitir()
    cabs = [(b"authorization", f"Bearer {token}".encode()), (b"authorization", f"Bearer {token}".encode())]
    with pytest.raises(ErroAuth) as e:
        await au.autenticar(verificador, cabs)
    assert e.value.status == 401


async def test_token_sem_papel_do_cerebro_e_403(verificador, emitir):
    token = emitir(realm_access={"roles": ["offline_access"]}, groups=["outro-grupo"])
    with pytest.raises(ErroAuth) as e:
        await au.autenticar(verificador, _bearer(token))
    assert (e.value.status, e.value.codigo) == (403, "papel_insuficiente")


async def test_sem_verificador_configurado_nega_tudo(emitir):
    with pytest.raises(ErroAuth) as e:
        await au.autenticar(None, _bearer(emitir()))
    assert e.value.status == 503


async def test_erro_nao_vaza_o_token_nem_detalhes_da_chave(verificador, emitir):
    token = emitir(exp=1)
    with pytest.raises(ErroAuth) as e:
        await au.autenticar(verificador, _bearer(token))
    assert token not in e.value.mensagem and "expired" not in e.value.mensagem.lower()


# ----------------------------------------------------------------- adversariais: JWKS indisponível


async def test_jwks_inacessivel_sem_cache_e_503(emitir, jwks_teste):
    jwks_teste.falhar = True
    v = Verificador(ConfigOidc((ISSUER_TESTE,), "http://x/jwks", CLIENTE_TESTE), buscar_jwks=jwks_teste)
    with pytest.raises(ErroAuth) as e:
        await au.autenticar(v, _bearer(emitir()))
    assert e.value.status == 503


async def test_jwks_sem_chave_rsa_de_assinatura_e_503(emitir, jwks_teste):
    jwks_teste.dados = {"keys": [{"kty": "oct", "kid": "chave-1", "k": "c2VjcmV0"}]}
    v = Verificador(ConfigOidc((ISSUER_TESTE,), "http://x/jwks", CLIENTE_TESTE), buscar_jwks=jwks_teste)
    with pytest.raises(ErroAuth) as e:
        await au.autenticar(v, _bearer(emitir()))
    assert e.value.status == 503


async def test_jwks_que_nao_e_json_e_503(emitir):
    async def quebrado():
        raise ValueError("corpo não é JSON")

    v = Verificador(ConfigOidc((ISSUER_TESTE,), "http://x/jwks", CLIENTE_TESTE), buscar_jwks=quebrado)
    with pytest.raises(ErroAuth) as e:
        await au.autenticar(v, _bearer(emitir()))
    assert e.value.status == 503


async def test_cache_expirado_e_jwks_fora_do_ar_falha_fechado(emitir, jwks_teste):
    relogio = Relogio()
    v = Verificador(ConfigOidc((ISSUER_TESTE,), "http://x/jwks", CLIENTE_TESTE), buscar_jwks=jwks_teste, relogio=relogio)
    assert await au.autenticar(v, _bearer(emitir()))  # popula o cache
    relogio.t += au.TTL_CHAVES + 1  # cache vence
    jwks_teste.falhar = True
    with pytest.raises(ErroAuth) as e:
        await au.autenticar(v, _bearer(emitir()))
    assert e.value.status == 503


async def test_falha_do_jwks_tem_backoff_e_nao_martela_o_keycloak(emitir, jwks_teste):
    relogio = Relogio()
    jwks_teste.falhar = True
    v = Verificador(ConfigOidc((ISSUER_TESTE,), "http://x/jwks", CLIENTE_TESTE), buscar_jwks=jwks_teste, relogio=relogio)
    for _ in range(50):
        with pytest.raises(ErroAuth):
            await au.autenticar(v, _bearer(emitir()))
    assert jwks_teste.chamadas == 1  # 49 pedidos dentro do backoff não geram nova busca


async def test_kid_desconhecido_nao_gera_busca_a_cada_requisicao(emitir, jwks_teste):
    relogio = Relogio()
    v = Verificador(ConfigOidc((ISSUER_TESTE,), "http://x/jwks", CLIENTE_TESTE), buscar_jwks=jwks_teste, relogio=relogio)
    await au.autenticar(v, _bearer(emitir()))  # 1 busca
    for _ in range(100):
        with pytest.raises(ErroAuth):
            await au.autenticar(v, _bearer(emitir(kid="falso")))
    assert jwks_teste.chamadas == 1


async def test_rotacao_de_chave_e_absorvida_quando_o_kid_muda(emitir, jwks_teste, chave_intrusa):
    relogio = Relogio()
    v = Verificador(ConfigOidc((ISSUER_TESTE,), "http://x/jwks", CLIENTE_TESTE), buscar_jwks=jwks_teste, relogio=relogio)
    await au.autenticar(v, _bearer(emitir()))
    nova = chave_intrusa.as_dict(private=False)
    nova["kid"] = "chave-2"
    jwks_teste.dados = {"keys": [nova]}
    relogio.t += au.INTERVALO_MIN_RECARGA + 1
    assert await au.autenticar(v, _bearer(emitir(chave=chave_intrusa, kid="chave-2")))



async def test_segundo_host_do_mesmo_realm_e_aceito(jwks_teste, emitir):
    """Token do container sai com iss=host.docker.internal; do host, com localhost. Os dois valem."""
    outro = "http://host.docker.internal:8180/realms/tudoia"
    v = Verificador(ConfigOidc((ISSUER_TESTE, outro), "http://x/jwks", CLIENTE_TESTE), buscar_jwks=jwks_teste)
    assert await au.autenticar(v, _bearer(emitir(iss=outro))) == ["tudoia-operador"]
    assert await au.autenticar(v, _bearer(emitir(iss=ISSUER_TESTE))) == ["tudoia-operador"]


async def test_terceiro_host_nao_listado_e_recusado(jwks_teste, emitir):
    outro = "http://host.docker.internal:8180/realms/tudoia"
    v = Verificador(ConfigOidc((ISSUER_TESTE, outro), "http://x/jwks", CLIENTE_TESTE), buscar_jwks=jwks_teste)
    with pytest.raises(ErroAuth):
        await au.autenticar(v, _bearer(emitir(iss="http://evil.example/realms/tudoia")))


def test_config_normaliza_issuer_str_para_tupla():
    """Um str passado como issuers seria iterado por caractere: a dataclass precisa normalizar."""
    assert ConfigOidc("http://a/realms/x", "http://j", "c").issuers == ("http://a/realms/x",)

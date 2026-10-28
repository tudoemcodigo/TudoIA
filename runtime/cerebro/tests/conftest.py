import hashlib
import re

import numpy as np
import pytest

from cerebro.banco import Banco

DIM = 1024


class EmbedderFalso:
    """Determinístico: cada palavra vira um índice por hash; mesmas palavras, cosseno alto."""

    async def embed(self, textos: list[str]) -> list[np.ndarray]:
        saida = []
        for t in textos:
            v = np.zeros(DIM, dtype=np.float32)
            for palavra in re.findall(r"\w+", t.lower()):
                v[int(hashlib.md5(palavra.encode()).hexdigest(), 16) % DIM] += 1.0
            n = np.linalg.norm(v)
            saida.append(v / n if n else v)
        return saida


@pytest.fixture
def embedder():
    return EmbedderFalso()


@pytest.fixture
def banco(tmp_path):
    return Banco(tmp_path / "cerebro.db")


# ---------------------------------------------------------------- autenticação (chaves e tokens de teste)

ISSUER_TESTE = "http://localhost:8180/realms/tudoia"
CLIENTE_TESTE = "tudoia-mcp"


@pytest.fixture(scope="session")
def chave_rsa():
    """Chave que assina os tokens bons. Só a parte pública aparece no JWKS de teste."""
    from joserfc.jwk import RSAKey

    return RSAKey.generate_key(2048, parameters={"kid": "chave-1", "use": "sig"})


@pytest.fixture(scope="session")
def chave_intrusa():
    """Chave de outro emissor, com o mesmo kid da legítima: assinatura que não bate com o JWKS."""
    from joserfc.jwk import RSAKey

    return RSAKey.generate_key(2048, parameters={"kid": "chave-1", "use": "sig"})


@pytest.fixture
def emitir(chave_rsa):
    """Fábrica de tokens RS256 assinados por `chave_rsa`. Cada chamada pode sobrescrever claims."""
    import time

    from joserfc import jwt

    def _emitir(chave=None, *, alg="RS256", kid="chave-1", **sobrescritas):
        agora = int(time.time())
        claims = {
            "iss": ISSUER_TESTE,
            "azp": CLIENTE_TESTE,
            "aud": ["account", CLIENTE_TESTE],
            "sub": "service-account-tudoia-mcp",
            "iat": agora,
            "nbf": agora - 5,
            "exp": agora + 3600,
            "realm_access": {"roles": ["tudoia-operador"]},
        }
        for nome, valor in sobrescritas.items():
            if valor is None:
                claims.pop(nome, None)
            else:
                claims[nome] = valor
        return jwt.encode({"alg": alg, "kid": kid}, claims, chave or chave_rsa)

    return _emitir


@pytest.fixture
def jwks_teste(chave_rsa):
    """JWKS público com a chave legítima. Mutável: o teste troca `jwks_teste.dados` para simular rotação/queda."""

    class Jwks:
        def __init__(self):
            self.dados = {"keys": [chave_rsa.as_dict(private=False)]}
            self.chamadas = 0
            self.falhar = False

        async def __call__(self):
            self.chamadas += 1
            if self.falhar:
                raise OSError("Keycloak fora do ar")
            return self.dados

    return Jwks()


@pytest.fixture
def verificador(jwks_teste):
    from cerebro.autenticacao import ConfigOidc, Verificador

    config = ConfigOidc(issuers=(ISSUER_TESTE,), jwks_url="http://host.docker.internal:8180/jwks", client_id=CLIENTE_TESTE)
    return Verificador(config, buscar_jwks=jwks_teste)

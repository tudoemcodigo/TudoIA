"""Testes do provisionamento do realm Keycloak (sem rede, exceto o teste de integração opcional)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
import pytest

from scripts.keycloak import provisionar as p

TEMPLATE = p.TEMPLATE_PADRAO
IDPS_VAZIO = Path(__file__).parent / "_idps_inexistente"


def _config(**extra: str) -> dict[str, str]:
    base = {
        "TUDOIA_KEYCLOAK_URL": "http://localhost:8180",
        "TUDOIA_KEYCLOAK_REALM": "tudoia",
        "TUDOIA_PAINEL_PORTA": "3100",
    }
    base.update(extra)
    return base


def _template() -> dict:
    return json.loads(TEMPLATE.read_text(encoding="utf-8"))


def _gravar_template(tmp_path: Path, dados: dict) -> Path:
    arq = tmp_path / "realm.json"
    arq.write_text(json.dumps(dados), encoding="utf-8")
    return arq


# ----------------------------------------------------------------- template


def test_template_real_carrega_e_valida():
    t = p.carregar_template(TEMPLATE)
    assert [r["name"] for r in t["roles"]] == ["tudoia-admin", "tudoia-operador", "tudoia-leitor"]
    assert [g["name"] for g in t["grupos"]] == ["tudoia-admin", "tudoia-operador", "tudoia-leitor"]
    assert t["realm"]["ssoSessionIdleTimeout"] == 28800
    assert t["realm"]["ssoSessionMaxLifespan"] == 86400


def test_template_nao_contem_segredo():
    bruto = TEMPLATE.read_text(encoding="utf-8").lower()
    assert "clientsecret" not in bruto
    assert '"secret"' not in bruto


def test_template_com_chave_de_segredo_e_rejeitado(tmp_path):
    dados = _template()
    dados["cliente"]["secret"] = "nao-deveria-estar-aqui"
    with pytest.raises(p.ErroValidacao, match="segredos"):
        p.carregar_template(_gravar_template(tmp_path, dados))


def test_cliente_publico_e_rejeitado(tmp_path):
    dados = _template()
    dados["cliente"]["publicClient"] = True
    with pytest.raises(p.ErroValidacao, match="publicClient"):
        p.carregar_template(_gravar_template(tmp_path, dados))


def test_pkce_plain_ou_ausente_e_rejeitado(tmp_path):
    dados = _template()
    dados["cliente"]["attributes"]["pkce.code.challenge.method"] = "plain"
    with pytest.raises(p.ErroValidacao, match="PKCE"):
        p.carregar_template(_gravar_template(tmp_path, dados))


def test_direct_access_grants_e_rejeitado(tmp_path):
    dados = _template()
    dados["cliente"]["directAccessGrantsEnabled"] = True
    with pytest.raises(p.ErroValidacao, match="directAccessGrantsEnabled"):
        p.carregar_template(_gravar_template(tmp_path, dados))


def test_grupo_com_papel_inexistente_e_rejeitado(tmp_path):
    dados = _template()
    dados["grupos"][0]["roles"] = ["papel-que-nao-existe"]
    with pytest.raises(p.ErroValidacao, match="papel inexistente"):
        p.carregar_template(_gravar_template(tmp_path, dados))


def test_template_quebrado_e_rejeitado(tmp_path):
    arq = tmp_path / "x.json"
    arq.write_text("{ nao e json", encoding="utf-8")
    with pytest.raises(p.ErroValidacao, match="ilegível"):
        p.carregar_template(arq)


# ----------------------------------------------------------------- placeholders


def test_substituir_falha_fechado_com_variavel_ausente():
    with pytest.raises(p.ErroValidacao, match="TUDOIA_IDP_X_SECRET"):
        p.substituir({"clientSecret": "${TUDOIA_IDP_X_SECRET}"}, {})


def test_variavel_vazia_conta_como_ausente():
    with pytest.raises(p.ErroValidacao, match="ausente"):
        p.substituir({"clientSecret": "${TUDOIA_IDP_X_SECRET}"}, {"TUDOIA_IDP_X_SECRET": ""})


def test_substituir_nao_reinterpreta_valor_injetado():
    resultado = p.substituir({"a": "${X}"}, {"X": "${Y}", "Y": "nao"})
    assert resultado == {"a": "${Y}"}


# ----------------------------------------------------------------- plano do cliente


def test_cliente_pkce_s256_e_redirects_com_porta_padrao():
    plano = p.montar_plano(_template(), _config(), IDPS_VAZIO)
    cli = plano.cliente
    assert cli["attributes"]["pkce.code.challenge.method"] == "S256"
    assert cli["redirectUris"] == [
        "http://127.0.0.1:3100/auth/callback",
        "http://localhost:3100/auth/callback",
    ]
    assert cli["attributes"]["post.logout.redirect.uris"] == (
        "http://127.0.0.1:3100/*##http://localhost:3100/*"
    )
    assert cli["webOrigins"] == []
    assert cli["publicClient"] is False
    assert "tudoia-groups" in cli["defaultClientScopes"]


def test_cliente_respeita_porta_configurada():
    plano = p.montar_plano(_template(), _config(TUDOIA_PAINEL_PORTA="3200"), IDPS_VAZIO)
    assert plano.cliente["redirectUris"][0] == "http://127.0.0.1:3200/auth/callback"


def test_porta_invalida_e_rejeitada():
    with pytest.raises(p.ErroValidacao, match="TUDOIA_PAINEL_PORTA"):
        p.montar_plano(_template(), _config(TUDOIA_PAINEL_PORTA="99999"), IDPS_VAZIO)


def test_realm_do_plano_vem_da_configuracao():
    plano = p.montar_plano(_template(), _config(TUDOIA_KEYCLOAK_REALM="outro"), IDPS_VAZIO)
    assert plano.realm["realm"] == "outro"


def test_mapper_de_grupos_emite_claim_groups_sem_caminho():
    escopo = p.montar_plano(_template(), _config(), IDPS_VAZIO).escopo
    mapper = escopo["protocolMappers"][0]
    assert mapper["protocolMapper"] == "oidc-group-membership-mapper"
    assert mapper["config"]["claim.name"] == "groups"
    assert mapper["config"]["full.path"] == "false"
    for chave in ("id.token.claim", "access.token.claim", "userinfo.token.claim"):
        assert mapper["config"][chave] == "true"


# ----------------------------------------------------------------- IdPs


def test_idps_example_nao_sao_aplicados(tmp_path):
    (tmp_path / "entra-id.example.json").write_text('{"alias":"x","providerId":"oidc","config":{"clientSecret":"${Q}"}}')
    assert p.carregar_idps(tmp_path, {}) == []


def test_idp_real_com_variavel_ausente_falha_antes_de_criar(tmp_path):
    (tmp_path / "entra-id.json").write_text(
        json.dumps({"alias": "entra-id", "providerId": "oidc", "config": {"clientSecret": "${TUDOIA_IDP_ENTRA_CLIENT_SECRET}"}}),
        encoding="utf-8",
    )
    with pytest.raises(p.ErroValidacao, match="TUDOIA_IDP_ENTRA_CLIENT_SECRET"):
        p.carregar_idps(tmp_path, {})


def test_idp_real_resolve_placeholders_e_separa_mappers(tmp_path):
    (tmp_path / "oidc.json").write_text(
        json.dumps(
            {
                "alias": "oidc-x",
                "providerId": "oidc",
                "config": {"clientSecret": "${S}", "clientId": "${ID}"},
                "mappers": [{"name": "m", "identityProviderMapper": "oidc-advanced-group-idp-mapper", "config": {"group": "/tudoia-admin"}}],
            }
        ),
        encoding="utf-8",
    )
    idps = p.carregar_idps(tmp_path, {"S": "segredo", "ID": "cid"})
    assert len(idps) == 1
    assert idps[0].representacao["config"] == {"clientSecret": "segredo", "clientId": "cid"}
    assert "mappers" not in idps[0].representacao
    assert idps[0].mappers[0]["name"] == "m"


def test_exemplos_entra_e_generico_sao_json_valido_e_usam_placeholders():
    for nome in ("entra-id.example.json", "oidc-generico.example.json"):
        dados = json.loads((p.IDPS_PADRAO / nome).read_text(encoding="utf-8"))
        assert dados["config"]["clientSecret"].startswith("${TUDOIA_IDP_")
        assert dados["mappers"], nome


def test_idp_com_alias_invalido_e_rejeitado(tmp_path):
    (tmp_path / "ruim.json").write_text(
        json.dumps({"alias": "Entra ID!", "providerId": "oidc", "config": {}}), encoding="utf-8"
    )
    with pytest.raises(p.ErroValidacao, match="alias"):
        p.carregar_idps(tmp_path, {})


# ----------------------------------------------------------------- configuração


def test_config_ambiente_vence_env_file(tmp_path, monkeypatch):
    arq = tmp_path / ".env"
    arq.write_text("TUDOIA_KEYCLOAK_URL=http://arquivo:8180\nOUTRA=1\n", encoding="utf-8")
    cfg = p.montar_config(arq, {"TUDOIA_KEYCLOAK_URL": "http://ambiente:8180/"})
    assert cfg["TUDOIA_KEYCLOAK_URL"] == "http://ambiente:8180"
    assert cfg["TUDOIA_KEYCLOAK_REALM"] == "tudoia"
    assert cfg["TUDOIA_PAINEL_PORTA"] == "3100"
    assert "OUTRA" not in cfg


def test_diferencas_ignora_campos_extras_no_vivo():
    assert p.diferencas({"a": 1}, {"a": 1, "b": 2}) == []
    assert p.diferencas({"a": 1}, {"a": 2}) == ["a"]
    assert p.diferencas({"l": ["x", "y"]}, {"l": ["y", "x"]}) == []
    assert p.diferencas({"l": ["x"]}, {}) == ["l"]
    assert p.diferencas({"a": {"b": "1"}}, {"a": {}}) == ["a.b"]


# ----------------------------------------------------------------- fail-closed sem rede


def _transporte_proibido(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"nenhuma chamada de rede deveria ocorrer: {request.url}")


def test_variavel_ausente_falha_antes_de_qualquer_chamada(tmp_path):
    (tmp_path / "entra-id.json").write_text(
        json.dumps({"alias": "entra-id", "providerId": "oidc", "config": {"clientSecret": "${FALTA}"}}),
        encoding="utf-8",
    )
    cliente = httpx.Client(transport=httpx.MockTransport(_transporte_proibido))
    with pytest.raises(p.ErroValidacao, match="FALTA"):
        p.provisionar(
            _config(),
            "admin",
            "senha",
            idps_dir=tmp_path,
            env_path=tmp_path / ".env",
            cliente_http=cliente,
        )


def test_credencial_recusada_vira_erro_de_autenticacao():
    def recusa(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid_grant"})

    cliente = httpx.Client(transport=httpx.MockTransport(recusa))
    with pytest.raises(p.ErroConexao, match="recusadas"):
        p.obter_token("http://localhost:8180", "admin", "x", cliente)


def test_servidor_inacessivel_vira_erro_de_conexao():
    def sem_rede(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("recusado", request=request)

    cliente = httpx.Client(transport=httpx.MockTransport(sem_rede))
    with pytest.raises(p.ErroConexao, match="não foi possível conectar"):
        p.obter_token("http://localhost:8180", "admin", "x", cliente)


def test_main_sem_credenciais_sai_com_2(monkeypatch, tmp_path):
    monkeypatch.delenv("TUDOIA_KEYCLOAK_ADMIN", raising=False)
    monkeypatch.delenv("TUDOIA_KEYCLOAK_ADMIN_PASSWORD", raising=False)
    monkeypatch.setattr(p, "ENV_PADRAO", tmp_path / ".env")
    assert p.main(["--verificar"]) == 2


def test_main_url_invalida_sai_com_1(monkeypatch, tmp_path):
    monkeypatch.setenv("TUDOIA_KEYCLOAK_URL", "ftp://nao-e-http")
    monkeypatch.setenv("TUDOIA_KEYCLOAK_ADMIN", "admin")
    monkeypatch.setenv("TUDOIA_KEYCLOAK_ADMIN_PASSWORD", "x")
    monkeypatch.setattr(p, "ENV_PADRAO", tmp_path / ".env")
    assert p.main(["--verificar"]) == 1


# ----------------------------------------------------------------- integração (opcional)


@pytest.mark.skipif(os.environ.get("TUDOIA_KEYCLOAK_IT") != "1", reason="defina TUDOIA_KEYCLOAK_IT=1")
def test_integracao_verificar_contra_keycloak_vivo():
    assert p.main(["--verificar"]) == 0




# ----------------------------------------------------------------- cliente de serviço do Cérebro (tudoia-mcp)


def test_cliente_servico_do_cerebro_no_template():
    servico = p.montar_plano(_template(), _config(), IDPS_VAZIO).cliente_servico
    assert servico["clientId"] == "tudoia-mcp"
    assert servico["serviceAccountsEnabled"] is True
    assert servico["standardFlowEnabled"] is False
    assert servico["attributes"]["access.token.lifespan"] == "28800"  # 8 h
    mapper = servico["protocolMappers"][0]
    assert mapper["protocolMapper"] == "oidc-audience-mapper"
    assert mapper["config"]["included.client.audience"] == "tudoia-mcp"


def test_cliente_servico_sem_conta_de_servico_e_rejeitado(tmp_path):
    dados = _template()
    dados["clienteServico"]["serviceAccountsEnabled"] = False
    with pytest.raises(p.ErroValidacao, match="serviceAccountsEnabled"):
        p.carregar_template(_gravar_template(tmp_path, dados))


def test_cliente_servico_com_lifespan_invalido_e_rejeitado(tmp_path):
    dados = _template()
    dados["clienteServico"]["attributes"]["access.token.lifespan"] = "8h"
    with pytest.raises(p.ErroValidacao, match="lifespan"):
        p.carregar_template(_gravar_template(tmp_path, dados))


def test_cliente_servico_sem_segredo_no_template():
    bruto = json.dumps(_template()["clienteServico"]).lower()
    assert "secret" not in bruto


def test_gravar_env_registra_pares_do_mcp(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("OUTRA=1\n", encoding="utf-8")
    monkeypatch.setattr(p, "BACKUP_ENV", tmp_path / "backup")
    registros: list[str] = []
    p._gravar_env(env, [("TUDOIA_MCP_CLIENT_ID", "tudoia-mcp"), ("TUDOIA_MCP_CLIENT_SECRET", "s3gredo")], registros)
    from tudoia_painel.envfile import ler_env

    lido = ler_env(env)
    assert lido["TUDOIA_MCP_CLIENT_ID"] == "tudoia-mcp" and lido["TUDOIA_MCP_CLIENT_SECRET"] == "s3gredo"
    assert lido["OUTRA"] == "1"
    assert all("s3gredo" not in r for r in registros)  # registro nunca traz o valor
    # idempotente: segunda gravação com os mesmos valores não registra nada
    registros.clear()
    p._gravar_env(env, [("TUDOIA_MCP_CLIENT_ID", "tudoia-mcp"), ("TUDOIA_MCP_CLIENT_SECRET", "s3gredo")], registros)
    assert registros == []


def test_token_do_painel_dura_a_sessao_do_painel():
    """O painel confirma a sessão no userinfo a cada 30 s com o access_token do login. Com o padrão do Keycloak
    (300 s) o userinfo passava a recusar e a sessão caía em 5 min. A revogação continua valendo: o userinfo recusa
    token de sessão SSO encerrada ou de conta desativada."""
    from tudoia_painel.autenticacao import IDADE_MAXIMA_SESSAO
    vida = int(_template()["cliente"]["attributes"]["access.token.lifespan"])
    assert vida >= IDADE_MAXIMA_SESSAO
    assert vida <= _template()["realm"]["ssoSessionIdleTimeout"]

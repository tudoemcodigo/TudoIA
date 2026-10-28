"""Contrato do docker-compose: cada container recebe só os segredos de que precisa."""
import re
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[2]
COMPOSE = yaml.safe_load((RAIZ / "runtime" / "docker-compose.yml").read_text(encoding="utf-8"))
SERVICOS = COMPOSE["services"]


def _nomes(servico: str) -> set[str]:
    return {item.split("=", 1)[0] for item in SERVICOS[servico].get("environment", [])}


def test_nenhum_container_recebe_o_env_inteiro():
    assert all("env_file" not in s for s in SERVICOS.values())


def test_litellm_recebe_toda_chave_que_o_config_gerado_referencia():
    """O gerador escreve `os.environ/<chave do provedor>`: faltar aqui = provedor sem chave dentro do container."""
    catalogo = (RAIZ / "config" / "catalogo-modelos.yaml").read_text(encoding="utf-8")
    chaves = set(re.findall(r"^\s+chave:\s*([A-Z][A-Z0-9_]+)\s*$", catalogo, re.M))
    chaves |= set(re.findall(r"os\.environ/([A-Z][A-Z0-9_]+)", catalogo))
    gerador = (RAIZ / "painel" / "tudoia_painel" / "gerador.py").read_text(encoding="utf-8")
    chaves |= set(re.findall(r"os\.environ/([A-Z][A-Z0-9_]+)", gerador))
    assert chaves, "catálogo sem provedores: o regex parou de casar"
    assert chaves <= _nomes("litellm"), sorted(chaves - _nomes("litellm"))


def test_litellm_nao_recebe_segredo_de_outro_servico():
    alheios = {"TUDOIA_KEYCLOAK_ADMIN_PASSWORD", "GITHUB_PERSONAL_ACCESS_TOKEN", "SUPABASE_SERVICE_ROLE_KEY",
               "SUPABASE_ACCESS_TOKEN", "N8N_ENCRYPTION_KEY", "WEBUI_SECRET_KEY", "TUDOIA_SESSAO_SEGREDO",
               "CEREBRO_TOKEN_ESTATICO", "TUDOIA_MCP_CLIENT_SECRET", "TUDOIA_OIDC_CLIENT_SECRET"}
    assert not (alheios & _nomes("litellm"))


def test_n8n_bloqueia_env_nos_fluxos_e_nao_recebe_segredo_do_cerebro():
    env = dict(item.split("=", 1) for item in SERVICOS["n8n"]["environment"])
    assert env["N8N_BLOCK_ENV_ACCESS_IN_NODE"] == "true"
    assert "TUDOIA_MCP_CLIENT_SECRET" not in env


def test_portas_so_em_loopback():
    for nome, s in SERVICOS.items():
        for porta in s.get("ports", []):
            assert str(porta).startswith("127.0.0.1:"), (nome, porta)


def test_so_litellm_e_o_banco_sobem_sem_perfil():
    """Quem não liga perfil nenhum fica só com o gateway. Todo o resto é opcional e escolhido no .env."""
    sem_perfil = {nome for nome, s in SERVICOS.items() if not s.get("profiles")}
    assert sem_perfil == {"litellm", "litellm-db"}


def test_dependencias_ficam_no_mesmo_perfil_do_dependente():
    """Perfil ligado com dependência desligada faz o compose recusar o `up`: toda dependência precisa vir junto."""
    for nome, s in SERVICOS.items():
        perfis = set(s.get("profiles", []))
        deps = s.get("depends_on", [])
        for dep in (deps if isinstance(deps, list) else deps.keys()):
            dep_perfis = set(SERVICOS[dep].get("profiles", []))
            assert not dep_perfis or perfis <= dep_perfis, (nome, dep)


def test_keycloak_embutido_usa_imagem_fixada_e_segredos_do_env():
    kc, db = SERVICOS["keycloak"], SERVICOS["keycloak-db"]
    assert "@sha256:" in kc["image"] and "@sha256:" in db["image"]
    assert kc["profiles"] == ["keycloak"] and db["profiles"] == ["keycloak"]
    envs = dict(i.split("=", 1) for i in kc["environment"])
    assert "${TUDOIA_KEYCLOAK_ADMIN_PASSWORD" in envs["KC_BOOTSTRAP_ADMIN_PASSWORD"]
    assert "${KEYCLOAK_DB_PASSWORD" in envs["KC_DB_PASSWORD"]
    assert not any("PASSWORD=" in i and "${" not in i for i in kc["environment"] + db["environment"])

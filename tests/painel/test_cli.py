"""`tudoia segredos`: gera os segredos internos vazios e nunca troca um valor existente."""
from tudoia_painel.cli import preencher_segredos
from tudoia_painel.envfile import ler_env


def test_gera_os_vazios_inclusive_o_token_do_cerebro(tmp_path):
    (tmp_path / ".env").write_text("LITELLM_MASTER_KEY=ja-existe\nCEREBRO_TOKEN_ESTATICO=\n", encoding="utf-8")
    preenchidos = preencher_segredos(tmp_path)
    env = ler_env(tmp_path / ".env")
    assert "CEREBRO_TOKEN_ESTATICO" in preenchidos and "LITELLM_MASTER_KEY" not in preenchidos
    assert env["LITELLM_MASTER_KEY"] == "ja-existe"
    assert len(env["CEREBRO_TOKEN_ESTATICO"]) >= 32  # o Cérebro recusa token estático menor que 32


def test_segunda_execucao_nao_troca_nada(tmp_path):
    preencher_segredos(tmp_path)
    antes = ler_env(tmp_path / ".env")
    assert preencher_segredos(tmp_path) == []
    assert ler_env(tmp_path / ".env") == antes


def test_segredos_do_keycloak_so_com_o_perfil_keycloak(tmp_path):
    (tmp_path / ".env").write_text("COMPOSE_PROFILES=cerebro,n8n\n", encoding="utf-8")
    assert "KEYCLOAK_DB_PASSWORD" not in preencher_segredos(tmp_path)
    assert not ler_env(tmp_path / ".env").get("TUDOIA_KEYCLOAK_ADMIN_PASSWORD")   # Keycloak próprio: não inventa senha

    (tmp_path / ".env").write_text("COMPOSE_PROFILES=cerebro,keycloak\nTUDOIA_KEYCLOAK_ADMIN_PASSWORD=ja-existe\n", encoding="utf-8")
    feitos = preencher_segredos(tmp_path)
    env = ler_env(tmp_path / ".env")
    assert "KEYCLOAK_DB_PASSWORD" in feitos and "TUDOIA_KEYCLOAK_ADMIN_PASSWORD" not in feitos
    assert env["TUDOIA_KEYCLOAK_ADMIN_PASSWORD"] == "ja-existe" and len(env["KEYCLOAK_DB_PASSWORD"]) >= 32


def test_gerar_config_cria_o_config_do_litellm_numa_raiz_nova(tmp_path, monkeypatch):
    import shutil
    from pathlib import Path

    from tudoia_painel import cli

    repo = Path(__file__).resolve().parents[2]
    shutil.copytree(repo / "config", tmp_path / "config")
    (tmp_path / "runtime" / "litellm").mkdir(parents=True)
    (tmp_path / ".env").write_text("LITELLM_MASTER_KEY=x\n", encoding="utf-8")
    monkeypatch.setattr(cli, "RAIZ", tmp_path)
    assert cli.main(["gerar-config"]) == 0
    texto = (tmp_path / "runtime" / "litellm" / "config.yaml").read_text(encoding="utf-8")
    assert "tudoia-auto" in texto and "os.environ/LITELLM_MASTER_KEY" in texto

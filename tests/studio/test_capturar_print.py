"""Helper de captura do Studio: leitura do .env e contrato das rotas. A captura de navegador fica de fora (exige o Studio no ar)."""
import pytest

from scripts.studio import capturar_print as cp


def test_ler_env_ignora_comentarios_e_linhas_vazias(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "# comentário\n\nTUDOIA_CAPTURAS_CLIENT_ID=tudoia-capturas\nTUDOIA_OIDC_ISSUER=http://localhost:8180/realms/tudoia\n",
        encoding="utf-8",
    )
    assert cp.ler_env(env) == {
        "TUDOIA_CAPTURAS_CLIENT_ID": "tudoia-capturas",
        "TUDOIA_OIDC_ISSUER": "http://localhost:8180/realms/tudoia",
    }


def test_rotas_cobrem_os_quatro_prints_do_calendario():
    assert {"hardware", "servicos", "roteador", "imagens"} <= set(cp.ROTAS)
    for fragmento, texto in cp.ROTAS.values():
        assert fragmento.startswith("#") and texto


def test_rota_desconhecida_e_recusada_antes_de_qualquer_rede(capsys):
    with pytest.raises(SystemExit) as saida:
        cp.main(["--rota", "inexistente", "--saida", "x.png"])
    assert saida.value.code == 2

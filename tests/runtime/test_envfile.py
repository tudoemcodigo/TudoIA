import pytest

from tudoia_painel.envfile import gravar_valor, ler_env, limpar_valor, mascarar


def test_ler_env_ignora_comentarios_e_aceita_igual_no_valor(tmp_path):
    p = tmp_path / ".env"
    p.write_bytes("﻿# c\r\nA=1\r\nB=x=y\r\nC=\r\n".encode())
    assert ler_env(p) == {"A": "1", "B": "x=y", "C": ""}


def test_ler_env_inexistente_devolve_vazio(tmp_path):
    assert ler_env(tmp_path / "nao-existe") == {}


def test_gravar_valor_preserva_comentarios_ordem_e_crlf(tmp_path):
    p = tmp_path / ".env"
    p.write_bytes(b"# FREE\r\nGROQ_API_KEY=\r\n\r\n# PAID\r\nOPENAI_API_KEY=\r\n")
    gravar_valor(p, "GROQ_API_KEY", "gsk_abc", tmp_path / "bk")
    assert p.read_bytes() == b"# FREE\r\nGROQ_API_KEY=gsk_abc\r\n\r\n# PAID\r\nOPENAI_API_KEY=\r\n"


def test_gravar_valor_preserva_lf_e_remove_bom(tmp_path):
    p = tmp_path / ".env"
    p.write_bytes("﻿A=1\nB=2\n".encode())
    gravar_valor(p, "B", "3", tmp_path / "bk")
    assert p.read_bytes() == b"A=1\nB=3\n"


def test_gravar_valor_cria_backup_e_mantem_10(tmp_path):
    p = tmp_path / ".env"
    p.write_text("A=0\n")
    bk = tmp_path / "bk"
    ultimo = None
    for i in range(12):
        ultimo = gravar_valor(p, "A", str(i + 1), bk)
    arquivos = sorted(bk.iterdir())
    assert len(arquivos) == 10
    assert ultimo in arquivos and ultimo.read_text() == "A=11\n"


def test_gravar_valor_chave_inexistente_acrescenta_no_fim(tmp_path):
    p = tmp_path / ".env"
    p.write_text("A=1\n")
    gravar_valor(p, "NOVA", "x", tmp_path / "bk")
    assert p.read_text() == "A=1\nNOVA=x\n"


def test_gravar_valor_limpa_o_valor(tmp_path):
    p = tmp_path / ".env"
    p.write_text("K=\n")
    gravar_valor(p, "K", '  "sk-or-v1-x"\n', tmp_path / "bk")
    assert ler_env(p)["K"] == "sk-or-v1-x"


def test_limpar_valor_tira_espacos_e_aspas():
    assert limpar_valor('  "sk-or-v1-x"\n') == "sk-or-v1-x"
    assert limpar_valor("'abc'") == "abc"


def test_limpar_valor_recusa_quebra_no_meio():
    with pytest.raises(ValueError):
        limpar_valor("abc\ndef")


def test_mascarar():
    assert mascarar("nvapi-1234567890abcd") == "nvapi-…abcd"
    assert mascarar("sk-or-v1-97d0000000000025b") == "sk-…025b"
    assert mascarar("gsk_123456789012") == "gsk_…9012"
    assert mascarar("") == ""
    assert mascarar("curta") == "…"

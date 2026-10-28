import subprocess
from pathlib import Path

import pytest

from scripts.openwebui import verificar_env as v

IMG = "ghcr.io/open-webui/open-webui:main@sha256:" + "a" * 64
COMPOSE = f"services:\n  open-webui:\n    image: {IMG}\n"


def _raiz(tmp_path: Path, local: str, aprovado: str | None) -> Path:
    (tmp_path / "runtime" / "open-webui").mkdir(parents=True)
    (tmp_path / "runtime" / "docker-compose.yml").write_text(COMPOSE, encoding="utf-8")
    (tmp_path / "runtime" / "open-webui" / "env.py").write_text(local, encoding="utf-8")
    if aprovado is not None:
        (tmp_path / "runtime" / "open-webui" / "env.py.aprovado.diff").write_text(aprovado, encoding="utf-8")
    return tmp_path


def test_imagem_vem_do_digest_do_compose():
    assert v.imagem_do_compose(COMPOSE) == IMG
    with pytest.raises(v.ErroVerificacao):
        v.imagem_do_compose("image: ghcr.io/open-webui/open-webui:main\n")   # sem digest não vale


def test_crlf_nao_conta_como_diferenca():
    assert v.diff_normalizado("a\nb\n", "a\r\nb\r\n") == ""


def test_igual_ao_aprovado_passa(tmp_path):
    aprovado = v.diff_normalizado("nome = 'A'\n", "nome = 'B'\n")
    raiz = _raiz(tmp_path, "nome = 'B'\n", aprovado)
    assert v.principal([], raiz, lambda img: "nome = 'A'\n") == 0


def test_imagem_que_mudou_reprova_e_mostra_o_diff(tmp_path, capsys):
    aprovado = v.diff_normalizado("nome = 'A'\n", "nome = 'B'\n")
    raiz = _raiz(tmp_path, "nome = 'B'\n", aprovado)
    assert v.principal([], raiz, lambda img: "nome = 'A2'\n") == 1   # upstream mudou: a cópia ficou para trás
    assert "A2" in capsys.readouterr().out


def test_copia_editada_sem_aprovacao_reprova(tmp_path):
    aprovado = v.diff_normalizado("nome = 'A'\n", "nome = 'B'\n")
    raiz = _raiz(tmp_path, "nome = 'B'\nextra = 1\n", aprovado)
    assert v.principal([], raiz, lambda img: "nome = 'A'\n") == 1


def test_sem_arquivo_aprovado_reprova_ate_aprovar(tmp_path):
    raiz = _raiz(tmp_path, "x = 1\n", None)
    assert v.principal([], raiz, lambda img: "x = 2\n") == 1
    assert v.principal(["--aprovar"], raiz, lambda img: "x = 2\n") == 0
    assert v.principal([], raiz, lambda img: "x = 2\n") == 0


def test_docker_indisponivel_nao_e_aprovacao(tmp_path):
    raiz = _raiz(tmp_path, "x = 1\n", "")

    def sem_docker(*a, **k):
        raise FileNotFoundError("docker")
    assert v.principal([], raiz, lambda img: v.extrair_da_imagem(img, sem_docker)) == 2


def test_extrair_recusa_saida_vazia_ou_erro():
    ruim = lambda *a, **k: subprocess.CompletedProcess(a, 1, b"", b"erro")  # noqa: E731
    with pytest.raises(v.ErroVerificacao):
        v.extrair_da_imagem(IMG, ruim)
    vazio = lambda *a, **k: subprocess.CompletedProcess(a, 0, b"", b"")  # noqa: E731
    with pytest.raises(v.ErroVerificacao):
        v.extrair_da_imagem(IMG, vazio)


def test_repositorio_esta_aprovado_contra_a_imagem_fixada():
    """Só roda com docker e a imagem fixada já baixada: sem isso, pula (não vira falso verde)."""
    raiz = Path(__file__).resolve().parents[2]
    imagem = v.imagem_do_compose((raiz / "runtime" / "docker-compose.yml").read_text(encoding="utf-8"))
    try:
        subprocess.run(["docker", "image", "inspect", imagem], capture_output=True, timeout=20, check=True)
    except (OSError, subprocess.SubprocessError):
        pytest.skip("docker ou a imagem fixada do Open WebUI não está disponível")
    igual, atual = v.verificar(raiz)
    assert igual, f"env.py divergiu do aprovado; revise:\n{atual}"

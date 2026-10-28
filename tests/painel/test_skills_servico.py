"""Importação de skill: pedido validado antes de qualquer processo, versão do pacote fixa e troca sem perda."""
import subprocess
import threading
from pathlib import Path

import pytest

from tudoia_painel import skills_servico as ss
from tudoia_painel.erros import ErroApi


@pytest.mark.parametrize("repo", ["dono/repo; calc", "dono/repo & del x", "https://evil.example/dono/repo",
                                  "http://github.com/dono/repo", "dono/repo|x", "dono/repo\"x", "../../x"])
def test_repositorio_fora_do_github_ou_com_metacaractere_e_recusado(repo):
    with pytest.raises(ErroApi) as e:
        ss.interpretar_pedido(None, repo, "minha-skill")
    assert e.value.status == 422


@pytest.mark.parametrize("nome", ["", "../x", "a b", "a;b", ".oculta", "x" * 65])
def test_nome_de_skill_invalido_e_recusado(nome):
    with pytest.raises(ErroApi):
        ss.interpretar_pedido(None, "dono/repo", nome)


def test_comando_colado_vira_url_e_nome():
    url, nome = ss.interpretar_pedido("npx skills add https://github.com/dono/repo --skill minha-skill", None, None)
    assert (url, nome) == ("https://github.com/dono/repo", "minha-skill")
    assert ss.interpretar_pedido(None, "dono/repo", "s1") == ("https://github.com/dono/repo", "s1")


def test_comando_do_npx_usa_versao_fixa():
    cmd = ss.comando_npx("https://github.com/dono/repo", "s1")
    assert f"skills@{ss.VERSAO_SKILLS_CLI}" in cmd and "skills" not in cmd and "skills@latest" not in cmd
    assert ss.VERSAO_SKILLS_CLI.replace(".", "").isdigit()


def _npx_falso(monkeypatch, escrever):
    def run(cmd, cwd, **kw):
        escrever(Path(cwd))
        return subprocess.CompletedProcess(cmd, 0, "", "")
    monkeypatch.setattr(subprocess, "run", run)


def test_troca_preserva_a_skill_antiga_se_a_copia_falhar(tmp_path, monkeypatch):
    raiz = tmp_path
    velha = raiz / "governanca" / "skills" / "s1"
    velha.mkdir(parents=True)
    (velha / "SKILL.md").write_text("antiga", encoding="utf-8")

    def escrever(cwd):
        d = cwd / "s1"
        d.mkdir()
        (d / "SKILL.md").write_text("nova", encoding="utf-8")
    _npx_falso(monkeypatch, escrever)

    def quebrado(*a, **k):
        raise OSError("disco cheio")
    monkeypatch.setattr(ss.shutil, "copytree", quebrado)
    with pytest.raises(OSError):
        ss.importar(raiz, threading.Lock(), "https://github.com/dono/repo", "s1")
    assert (velha / "SKILL.md").read_text(encoding="utf-8") == "antiga"


def test_importa_e_substitui(tmp_path, monkeypatch):
    raiz = tmp_path
    (raiz / "governanca" / "skills" / "s1").mkdir(parents=True)
    (raiz / "governanca" / "skills" / "s1" / "velho.txt").write_text("x", encoding="utf-8")

    def escrever(cwd):
        d = cwd / "pasta" / "s1"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text("nova", encoding="utf-8")
    _npx_falso(monkeypatch, escrever)
    destino = ss.importar(raiz, threading.Lock(), "https://github.com/dono/repo", "s1")
    assert (destino / "SKILL.md").read_text(encoding="utf-8") == "nova" and not (destino / "velho.txt").exists()
    assert not list((raiz / "governanca").glob(".skill-novo-*"))


def test_skill_com_link_simbolico_e_recusada(tmp_path, monkeypatch):
    alvo = tmp_path / "segredo.txt"
    alvo.write_text("chave-privada", encoding="utf-8")

    def escrever(cwd):
        d = cwd / "s1"
        d.mkdir()
        (d / "SKILL.md").write_text("x", encoding="utf-8")
        try:
            (d / "ssh").symlink_to(alvo)
        except OSError:
            pytest.skip("sem permissão para criar link simbólico neste Windows")
    _npx_falso(monkeypatch, escrever)
    with pytest.raises(ErroApi) as e:
        ss.importar(tmp_path / "raiz", threading.Lock(), "https://github.com/dono/repo", "s1")
    assert e.value.codigo == "skill_invalida"


def test_npx_com_erro_vira_422_e_timeout_vira_408(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, "", "boom"))
    with pytest.raises(ErroApi) as e:
        ss.importar(tmp_path, threading.Lock(), "https://github.com/dono/repo", "s1")
    assert e.value.status == 422

    def estourou(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 1)
    monkeypatch.setattr(subprocess, "run", estourou)
    with pytest.raises(ErroApi) as e:
        ss.importar(tmp_path, threading.Lock(), "https://github.com/dono/repo", "s1")
    assert e.value.status == 408

import json
import os
import subprocess

import pytest

from tudoia_instalador import desinstalar as d
from tudoia_instalador.execucao import Redator

from .duplos import ExecutorFalso


def _instalacao(tmp_path, pasta_dados=None, nome="TudoIA"):
    raiz = tmp_path / nome
    (raiz / "scripts").mkdir(parents=True)
    (raiz / "app.py").write_text("x")
    (raiz / ".env").write_text("SEGREDO=1")
    (raiz / "dados").mkdir()
    (raiz / "dados" / "cerebro.db").write_text("BANCO")
    (raiz / "modelos").mkdir()
    (raiz / "modelos" / "peso.gguf").write_text("PESO")
    (raiz / d.MARCA).write_text(json.dumps({"projeto_compose": "meu", "pasta_dados": str(pasta_dados or raiz / "dados")}))
    return raiz


def _ex():
    logs = []
    return ExecutorFalso(logs.append, Redator()), logs


def test_sem_a_marca_do_instalador_nada_e_apagado(tmp_path):
    pasta = tmp_path / "Documentos"
    pasta.mkdir()
    (pasta / "tese.docx").write_text("importante")
    with pytest.raises(d.ErroDesinstalacao, match="marca"):
        d.desinstalar(pasta, False, executor=_ex()[0])
    assert (pasta / "tese.docx").exists()


@pytest.mark.parametrize("alvo", ["raiz_do_disco", "home"])
def test_recusa_raiz_do_disco_e_pasta_do_usuario(alvo, tmp_path):
    from pathlib import Path
    pasta = Path(Path.cwd().anchor) if alvo == "raiz_do_disco" else Path.home()
    with pytest.raises(d.ErroDesinstalacao, match="inválida"):
        d.desinstalar(pasta, True, executor=_ex()[0])


def test_mantem_dados_e_modelos_por_padrao(tmp_path):
    raiz = _instalacao(tmp_path)
    ex, _ = _ex()
    d.desinstalar(raiz, False, log=lambda t: None, executor=ex)
    assert not (raiz / "app.py").exists() and not (raiz / ".env").exists() and not (raiz / d.MARCA).exists()
    assert (raiz / "dados" / "cerebro.db").read_text() == "BANCO" and (raiz / "modelos" / "peso.gguf").exists()


def test_remover_dados_apaga_tudo_e_a_pasta(tmp_path):
    raiz = _instalacao(tmp_path)
    d.desinstalar(raiz, True, log=lambda t: None, executor=_ex()[0])
    assert not raiz.exists()


@pytest.mark.skipif(os.name != "nt", reason="junção é recurso do Windows")
def test_juncao_de_dados_nao_e_seguida_ao_apagar(tmp_path):
    destino = tmp_path / "OutroDisco" / "dados"
    destino.mkdir(parents=True)
    (destino / "cerebro.db").write_text("BANCO")
    raiz = _instalacao(tmp_path, pasta_dados=destino)
    import shutil
    shutil.rmtree(raiz / "dados")
    subprocess.run(["cmd", "/c", "mklink", "/J", str(raiz / "dados"), str(destino)], check=True, capture_output=True)
    d.desinstalar(raiz, False, log=lambda t: None, executor=_ex()[0])
    assert (destino / "cerebro.db").read_text() == "BANCO"          # sem --remover-dados o destino da junção é intocável
    raiz2 = _instalacao(tmp_path / "b", pasta_dados=destino)
    shutil.rmtree(raiz2 / "dados")
    subprocess.run(["cmd", "/c", "mklink", "/J", str(raiz2 / "dados"), str(destino)], check=True, capture_output=True)
    d.desinstalar(raiz2, True, log=lambda t: None, executor=_ex()[0])
    assert not destino.exists()                                       # com --remover-dados o destino sai, de propósito


def test_para_os_servicos_e_derruba_o_compose_com_o_nome_do_projeto(tmp_path, monkeypatch):
    raiz = _instalacao(tmp_path)
    (raiz / "scripts" / "parar.ps1").write_text("")
    (raiz / "runtime").mkdir()
    (raiz / "runtime" / "docker-compose.yml").write_text("")
    monkeypatch.setattr(d, "docker_exe", lambda: "docker.exe")
    ex, _ = _ex()
    d.desinstalar(raiz, True, log=lambda t: None, executor=ex)
    cmds = ex.comandos()
    assert any("parar.ps1" in c for c in cmds)
    down = next(c for c in cmds if " down " in c)
    assert "-p meu" in down and down.endswith("-v")


def test_sem_remover_dados_o_compose_down_nao_apaga_volumes(tmp_path, monkeypatch):
    raiz = _instalacao(tmp_path)
    (raiz / "runtime").mkdir()
    (raiz / "runtime" / "docker-compose.yml").write_text("")
    monkeypatch.setattr(d, "docker_exe", lambda: "docker.exe")
    ex, _ = _ex()
    d.desinstalar(raiz, False, log=lambda t: None, executor=ex)
    assert not next(c for c in ex.comandos() if " down " in c).endswith("-v")


def test_remove_os_atalhos(tmp_path, monkeypatch):
    raiz = _instalacao(tmp_path)
    pasta = tmp_path / "Menu" / "TudoIA"
    pasta.mkdir(parents=True)
    for nome, *_ in d.ATALHOS:
        (pasta / f"{nome}.lnk").write_text("")
    (pasta / "Outro programa.lnk").write_text("")
    monkeypatch.setattr(d, "pastas_de_atalho", lambda: [pasta])
    d.desinstalar(raiz, False, log=lambda t: None, executor=_ex()[0])
    assert [p.name for p in pasta.iterdir()] == ["Outro programa.lnk"]

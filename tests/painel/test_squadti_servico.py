"""A API da Squad como serviço do host: sobe só com a configuração completa, segredos só por ambiente, e fora do 'todos'."""
import subprocess

import pytest

from tudoia_painel import servicos as sv

TOKEN = "k" * 40


@pytest.fixture
def popen(monkeypatch):
    chamadas = []

    class Falso:
        def __init__(self, cmd, **kw):
            chamadas.append((list(cmd), kw))

    monkeypatch.setattr(sv.subprocess, "Popen", Falso)
    return chamadas


def _squadti(tmp_path, env_linhas, com_arquivos=True):
    raiz = tmp_path / "raiz"
    raiz.mkdir(parents=True)
    base = tmp_path / "SquadTI"
    if com_arquivos:
        (base / "orquestrador").mkdir(parents=True)
        (base / "orquestrador" / "api.py").write_text("", encoding="utf-8")
        (base / ".venv" / "Scripts").mkdir(parents=True)
        (base / ".venv" / "Scripts" / "python.exe").write_text("", encoding="utf-8")
    linhas = [l.replace("{base}", str(base)) for l in env_linhas]
    (raiz / ".env").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return sv.ServicosDocker(raiz), base


COMPLETO = ["TUDOIA_SQUADTI_DIR={base}", f"TUDOIA_SQUADTI_TOKEN={TOKEN}", "SQUADTI_API_KEY=sk-chave-do-gateway-123456",
            "DOUTRINA_TEC=D:/Doutrina"]


def test_sobe_com_segredos_so_no_ambiente(tmp_path, popen):
    s, base = _squadti(tmp_path, COMPLETO)
    s.acao("squadti", "start")
    (cmd, kw), = popen
    assert cmd[1].endswith("api.py") and "--porta" in cmd and "8790" in cmd
    assert TOKEN not in " ".join(cmd) and "sk-chave-do-gateway" not in " ".join(cmd)   # nada de segredo na linha de comando
    assert kw["env"]["TUDOIA_SQUADTI_TOKEN"] == TOKEN and kw["env"]["TUDOIA_API_KEY"] == "sk-chave-do-gateway-123456"
    assert kw["env"]["TUDOIA_MODEL"] == "tudoia-local-estrito"
    assert str(kw["cwd"]).endswith("squadti")   # workspace e checkpoint ficam em dados/squadti, fora do repositório da Squad


@pytest.mark.parametrize("sem", ["TUDOIA_SQUADTI_DIR", "TUDOIA_SQUADTI_TOKEN", "SQUADTI_API_KEY", "DOUTRINA_TEC"])
def test_sem_item_obrigatorio_nao_sobe(tmp_path, popen, sem):
    s, _ = _squadti(tmp_path, [l for l in COMPLETO if not l.startswith(sem)])
    with pytest.raises(RuntimeError, match=sem):
        s.acao("squadti", "start")
    assert popen == []


def test_token_curto_e_instalacao_ausente_nao_sobem(tmp_path, popen):
    s, _ = _squadti(tmp_path, [l if "TOKEN" not in l else "TUDOIA_SQUADTI_TOKEN=curto" for l in COMPLETO])
    with pytest.raises(RuntimeError, match="32"):
        s.acao("squadti", "start")
    s2, _ = _squadti(tmp_path / "outro", COMPLETO, com_arquivos=False)
    with pytest.raises(RuntimeError, match="não encontrada"):
        s2.acao("squadti", "start")
    assert popen == []


def test_squadti_aparece_na_lista_e_fica_fora_do_todos(tmp_path, monkeypatch):
    s, _ = _squadti(tmp_path, COMPLETO)
    monkeypatch.setattr(sv, "porta_aberta", lambda p: p == 8790)
    monkeypatch.setattr(sv.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, stdout="", stderr=""))
    squad = next(x for x in s.listar() if x["nome"] == "squadti")
    assert squad["tipo"] == "host" and squad["ativo"] is True and squad["porta"] == 8790
    parados = []
    monkeypatch.setattr(s, "_stop_host", lambda n: parados.append(n))
    monkeypatch.setattr(s, "_start_ollama", lambda: None)
    monkeypatch.setattr(s, "_start_comfyui", lambda: None)
    s.acao_todos("stop")
    s.acao_todos("restart")
    assert "squadti" not in parados and set(parados) == {"ollama", "comfyui"}

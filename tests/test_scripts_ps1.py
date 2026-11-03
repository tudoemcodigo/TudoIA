"""Guarda dos scripts do Windows: ASCII puro (o PowerShell 5.1 le .ps1 sem BOM como ANSI) e o teste de porta por conexao real."""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
CICLO_DE_VIDA = ("_comum.ps1", "iniciar.ps1", "parar.ps1", "reiniciar.ps1", "painel.ps1")


def test_scripts_de_ciclo_de_vida_sao_ascii():
    ruins = [n for n in CICLO_DE_VIDA if any(b > 127 for b in (SCRIPTS / n).read_bytes())]
    assert ruins == []


def test_os_scripts_de_ciclo_de_vida_existem_e_usam_o_modulo_comum():
    for nome in ("iniciar.ps1", "parar.ps1", "reiniciar.ps1", "painel.ps1"):
        texto = (SCRIPTS / nome).read_text(encoding="ascii")
        assert '. "$PSScriptRoot\_comum.ps1"' in texto, nome


def test_porta_aberta_nao_confia_na_entrada_listen_do_windows():
    """Get-NetTCPConnection -State Listen devolve entradas fantasma (PID 0) de processos mortos: o launcher achava o painel no ar."""
    comum = (SCRIPTS / "_comum.ps1").read_text(encoding="ascii")
    corpo = comum[comum.index("function PortaAberta"):comum.index("function Esperar")]
    assert "TcpClient" in corpo and "Get-NetTCPConnection" not in corpo


def test_parar_porta_ignora_pid_zero_e_confere_a_linha_de_comando():
    comum = (SCRIPTS / "_comum.ps1").read_text(encoding="ascii")
    corpo = comum[comum.index("function DonosDaPorta"):comum.index("# ---------------------------------------------------------------- painel")]
    assert "OwningProcess -gt 0" in corpo and "$deveConter" in corpo


def test_squadti_no_ar_confere_o_saude_e_nao_so_a_porta():
    """O Docker publica a porta antes de o processo do container escutar: porta aberta nao e API pronta."""
    comum = (SCRIPTS / "_comum.ps1").read_text(encoding="ascii")
    corpo = comum[comum.index("function SquadtiNoAr"):comum.index("# `up -d --build squadti`")]
    assert "/saude" in corpo and "PortaAberta" not in corpo


# ───────── parar o painel: não depender do estado da conexão (Windows com State vazio) e testar de verdade
def test_nenhum_script_filtra_porta_por_state_listen():
    """Em alguns Windows o Get-NetTCPConnection devolve State vazio: `-State Listen` não acha nada (parar.ps1 deixava o painel no ar)."""
    for p in SCRIPTS.glob("*.ps1"):
        for n, linha in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if "Get-NetTCPConnection" in linha and "-State" in linha and not linha.lstrip().startswith("#"):
                pytest.fail(f"{p.name}:{n}: {linha.strip()}")


def test_parar_confere_o_resultado_e_so_mexe_nos_servicos_do_tudoia():
    parar = (SCRIPTS / "parar.ps1").read_text(encoding="ascii")
    assert "PainelNoAr" in parar and "exit 1" in parar                       # painel que sobrou não vira "parado" em silêncio


def test_parar_desliga_o_ecossistema_inteiro_sem_depender_de_variaveis_do_env():
    parar = (SCRIPTS / "parar.ps1").read_text(encoding="ascii")
    comum = (SCRIPTS / "_comum.ps1").read_text(encoding="ascii")
    for chamada in ("PararPainel", "PararSquadti", "PararOllama", "PararComfyui"):
        assert chamada in parar, chamada
    assert "ValorEnv 'TUDOIA_OLLAMA_MODELS'" not in parar and "ValorEnv 'TUDOIA_COMFYUI_PORTABLE'" not in parar   # sem gate: para sempre
    assert "--profile '*'" in parar                                              # inclui servicos de perfil opcional (squadti, n8n...)
    assert "PararServicoDoHost 11434 'ollama'" in comum and "PararServicoDoHost 8188 'ComfyUI'" in comum   # confere a linha de comando
    assert "PortaAberta 11434" in parar and "PortaAberta 8188" in parar          # confirma que fechou


def test_iniciar_sobe_o_painel_mesmo_se_docker_ou_compose_falharem():
    iniciar = (SCRIPTS / "iniciar.ps1").read_text(encoding="ascii")
    assert iniciar.index("try {") < iniciar.index("docker compose") < iniciar.index("} catch") < iniciar.index("IniciarPainel")
    assert "$erroInfra" in iniciar and iniciar.rindex("exit 1") > iniciar.index("IniciarPainel")   # falha de infra continua sendo erro


def test_tudoia_up_sobe_o_painel():
    tudoia = (SCRIPTS / "tudoia.ps1").read_text(encoding="utf-8")
    assert '_comum.ps1' in tudoia and "IniciarPainel" in tudoia and "PortaAberta 11434" in tudoia


def _ps(comando: str, **env) -> subprocess.CompletedProcess:
    return subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", comando], capture_output=True, text=True,
                          timeout=120, env={**os.environ, **env})


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _servidor_falso(tmp_path: Path, modulo: str, porta: int) -> subprocess.Popen:
    """`python -m <modulo> painel` que escuta na porta: imita o painel (launcher do venv + processo real não importam aqui)."""
    (tmp_path / modulo).mkdir()
    (tmp_path / modulo / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / modulo / "__main__.py").write_text(
        f"import socket, time\ns = socket.socket()\ns.bind(('127.0.0.1', {porta}))\ns.listen()\ntime.sleep(300)\n", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, "-m", modulo, "painel"], cwd=tmp_path, env={**os.environ, "PYTHONPATH": str(tmp_path)},
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        with socket.socket() as c:
            c.settimeout(0.2)
            if c.connect_ex(("127.0.0.1", porta)) == 0:
                return proc
        time.sleep(0.1)
    proc.kill()
    raise AssertionError("servidor falso não subiu")


def _vivo(proc: subprocess.Popen) -> bool:
    return proc.poll() is None


def _carregar(porta: int, linha: str, corpo: str) -> str:
    comum = str(SCRIPTS / "_comum.ps1")
    return f"$raiz = '{SCRIPTS.parent}'; . '{comum}'; $script:PortaPainel = {porta}; $script:LinhaDoPainel = '{linha}'; {corpo}"


@pytest.mark.skipif(os.name != "nt", reason="PowerShell do Windows")
def test_parar_painel_encerra_de_verdade_quem_escuta_a_porta(tmp_path):
    porta = _porta_livre()
    proc = _servidor_falso(tmp_path, "tudoia_painel_teste", porta)
    try:
        r = _ps(_carregar(porta, "-m tudoia_painel_teste painel", "[void](PararPainel); 'aberta=' + (PortaAberta $script:PortaPainel)"))
        assert r.returncode == 0, r.stderr
        assert "aberta=False" in r.stdout
        proc.wait(timeout=10)
    finally:
        proc.kill()


@pytest.mark.skipif(os.name != "nt", reason="PowerShell do Windows")
def test_parar_porta_nao_mata_processo_que_nao_e_o_esperado(tmp_path):
    porta = _porta_livre()
    proc = _servidor_falso(tmp_path, "outro_programa", porta)
    try:
        r = _ps(_carregar(porta, "-m x", f"PararPorta {porta} 'tudoia_painel'"))
        assert r.returncode == 0, r.stderr
        assert _vivo(proc)                      # outro programa na mesma porta continua vivo
    finally:
        proc.kill()


@pytest.mark.skipif(os.name != "nt", reason="PowerShell do Windows")
def test_parar_por_linha_de_comando_so_atinge_quem_casa_o_texto_literal(tmp_path):
    alvo = _servidor_falso(tmp_path, "tudoia_painel_alvo", _porta_livre())
    vizinho = _servidor_falso(tmp_path, "tudoia_painel_vizinho", _porta_livre())
    try:
        # texto com curingas do PowerShell não pode virar padrão: '*' e '[a]' são literais
        r = _ps(_carregar(1, "x", "(PararPorLinhaDeComando '-m tudoia_painel_*') ; (PararPorLinhaDeComando '[t]udoia_painel_alvo')"))
        assert r.returncode == 0, r.stderr
        assert _vivo(alvo) and _vivo(vizinho)
        r = _ps(_carregar(1, "x", "PararPorLinhaDeComando '-m tudoia_painel_alvo painel'"))
        assert r.returncode == 0 and int(r.stdout.strip()) >= 1, r.stdout + r.stderr   # o venv gera launcher + processo real: 1 ou 2
        alvo.wait(timeout=10)
        assert _vivo(vizinho)
    finally:
        alvo.kill()
        vizinho.kill()


@pytest.mark.skipif(os.name != "nt", reason="PowerShell do Windows")
def test_parar_por_linha_de_comando_vazia_nao_faz_nada():
    r = _ps(_carregar(1, "x", "PararPorLinhaDeComando ''"))
    assert r.returncode == 0 and r.stdout.strip() == "0", r.stdout + r.stderr


@pytest.mark.skipif(os.name != "nt", reason="PowerShell do Windows")
def test_parar_servico_do_host_encerra_pela_porta_e_pela_linha_de_comando(tmp_path):
    """Mesma função de PararOllama/PararComfyui, com um servidor falso. NUNCA use "ollama" ou "ComfyUI" nos padrões destes testes:
    as linhas de comando são comparadas com os processos reais da máquina e o serviço de verdade seria encerrado."""
    porta = _porta_livre()
    proc = _servidor_falso(tmp_path, "servico_falso_do_host", porta)
    try:
        r = _ps(_carregar(1, "x", f"[void](PararServicoDoHost {porta} 'servico_falso_do_host' @('servico_falso_do_host')); 'aberta=' + (PortaAberta {porta})"))
        assert r.returncode == 0, r.stderr
        assert "aberta=False" in r.stdout
        proc.wait(timeout=10)
    finally:
        proc.kill()


@pytest.mark.skipif(os.name != "nt", reason="PowerShell do Windows")
def test_parar_servico_do_host_nao_mata_outro_programa_na_mesma_porta(tmp_path):
    porta = _porta_livre()
    proc = _servidor_falso(tmp_path, "programa_alheio", porta)
    try:
        r = _ps(_carregar(1, "x", f"[void](PararServicoDoHost {porta} 'servico_esperado_inexistente' @('servico_esperado_inexistente.exe'))"))
        assert r.returncode == 0, r.stderr
        assert _vivo(proc)
    finally:
        proc.kill()

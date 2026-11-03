"""Guarda dos scripts do Windows: ASCII puro (o PowerShell 5.1 le .ps1 sem BOM como ANSI) e o teste de porta por conexao real."""
from pathlib import Path

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
    corpo = comum[comum.index("function PararPorta"):comum.index("# ---------------------------------------------------------------- painel")]
    assert "OwningProcess -gt 0" in corpo and "$deveConter" in corpo

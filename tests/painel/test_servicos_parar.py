import os
import subprocess

import pytest

from tudoia_painel import servicos as sv

BARRA, CRASE, ASPA = chr(92), chr(96), chr(39)
PASTA_HOSTIL = f"C:{BARRA}x$(calc){CRASE}y[1]*{ASPA}z"


def test_caminho_do_comfyui_vai_por_variavel_e_nao_no_texto_do_comando(tmp_path, monkeypatch):
    chamadas = []
    monkeypatch.setattr(sv.subprocess, "run", lambda cmd, **kw: chamadas.append((cmd, kw)) or subprocess.CompletedProcess(cmd, 0))
    monkeypatch.setattr(sv, "comfyui_portable", lambda raiz: PASTA_HOSTIL)
    sv.ServicosDocker(tmp_path)._stop_host("comfyui")
    cmd, kw = chamadas[-1]
    assert PASTA_HOSTIL not in " ".join(cmd) and "calc" not in " ".join(cmd)
    assert kw["env"]["TUDOIA_COMFYUI_DIR"] == PASTA_HOSTIL


def _casa(linha: str) -> str:
    """Mesma comparação do comando de parada, contra uma linha de comando de processo."""
    literal = linha.replace(ASPA, ASPA * 2)
    cmd = ("$dir = $env:TUDOIA_COMFYUI_DIR; "
           f"[string]({ASPA}{literal}{ASPA}.IndexOf($dir, [StringComparison]::OrdinalIgnoreCase) -ge 0)")
    r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True,
                       env={**os.environ, "TUDOIA_COMFYUI_DIR": PASTA_HOSTIL}, timeout=60)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


@pytest.mark.skipif(os.name != "nt", reason="PowerShell do Windows")
def test_powershell_compara_a_pasta_hostil_como_texto_puro():
    assert _casa(PASTA_HOSTIL + BARRA + "run.bat") == "True"
    assert _casa(f"C:{BARRA}x$(calc){CRASE}y[1]*{ASPA}zz{BARRA}python.exe") == "True"   # crase, [] e * são texto
    assert _casa(f"C:{BARRA}x$(calc){CRASE}yX1X*{ASPA}z") == "False"                   # sem curinga: [1] não casa X1X
    assert _casa(f"C:{BARRA}outra{BARRA}pasta") == "False"

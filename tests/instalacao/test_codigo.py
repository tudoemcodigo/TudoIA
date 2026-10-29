import io
import json
import zipfile
from pathlib import Path

import pytest

from tudoia_instalador import codigo


def _zip(caminho: Path, arquivos: dict[str, bytes | str], extra=None) -> Path:
    with zipfile.ZipFile(caminho, "w") as z:
        for nome, dados in arquivos.items():
            z.writestr(nome, dados)
        if extra:
            extra(z)
    return caminho


@pytest.mark.parametrize("nome", ["../fora.txt", "a/../../fora.txt", "/abs/x.txt", "C:/x.txt", "..\\fora.txt", "C:\\x.txt"])
def test_zip_slip_e_recusado(tmp_path, nome):
    z = _zip(tmp_path / "p.zip", {nome: "x"})
    with pytest.raises(codigo.ErroCodigo):
        codigo.extrair(z, tmp_path / "dest")
    assert not (tmp_path / "fora.txt").exists()


def test_link_simbolico_no_zip_e_recusado(tmp_path):
    def link(z):
        info = zipfile.ZipInfo("atalho")
        info.external_attr = 0o120777 << 16
        z.writestr(info, "../../segredo")
    z = _zip(tmp_path / "p.zip", {"a.txt": "x"}, extra=link)
    with pytest.raises(codigo.ErroCodigo):
        codigo.extrair(z, tmp_path / "dest")


def test_limites_de_quantidade_e_de_tamanho(tmp_path, monkeypatch):
    z = _zip(tmp_path / "p.zip", {f"f{i}.txt": "x" for i in range(5)})
    monkeypatch.setattr(codigo, "MAX_ARQUIVOS", 3)
    with pytest.raises(codigo.ErroCodigo, match="arquivos demais"):
        codigo.extrair(z, tmp_path / "d1")
    monkeypatch.setattr(codigo, "MAX_ARQUIVOS", 100)
    monkeypatch.setattr(codigo, "MAX_BYTES_DESCOMPRIMIDOS", 3)
    with pytest.raises(codigo.ErroCodigo, match="grande demais"):
        codigo.extrair(z, tmp_path / "d2")


def test_remove_o_prefixo_unico_do_zip_do_github(tmp_path):
    z = _zip(tmp_path / "p.zip", {"TudoIA-main/a.txt": "1", "TudoIA-main/sub/b.txt": "2"})
    assert codigo.extrair(z, tmp_path / "d", remover_prefixo=True) == 2
    assert (tmp_path / "d" / "a.txt").read_text() == "1" and (tmp_path / "d" / "sub" / "b.txt").read_text() == "2"


def test_reinstalacao_preserva_env_dados_e_modelos(tmp_path):
    raiz = tmp_path / "raiz"
    (raiz / "dados").mkdir(parents=True)
    (raiz / "dados" / "cerebro.db").write_text("MEU-BANCO")
    (raiz / ".env").write_text("SEGREDO=meu")
    (raiz / "modelos").mkdir()
    (raiz / "modelos" / "peso.gguf").write_text("PESO")
    (raiz / "app.py").write_text("antigo")
    z = _zip(tmp_path / "p.zip", {".env": "VAZIO=1", "dados/cerebro.db": "NOVO", "modelos/peso.gguf": "NOVO", "app.py": "novo", "novo.py": "1"})
    codigo.instalar(z, raiz, remover_prefixo=False)
    assert (raiz / ".env").read_text() == "SEGREDO=meu"
    assert (raiz / "dados" / "cerebro.db").read_text() == "MEU-BANCO" and (raiz / "modelos" / "peso.gguf").read_text() == "PESO"
    assert (raiz / "app.py").read_text() == "novo" and (raiz / "novo.py").exists()
    assert not list(raiz.glob(".codigo-*"))


def test_instalacao_nova_grava_tudo_inclusive_o_exemplo_de_env(tmp_path):
    z = _zip(tmp_path / "p.zip", {".env.example": "A=", "runtime/docker-compose.yml": "x"})
    codigo.instalar(z, tmp_path / "raiz", remover_prefixo=False)
    assert (tmp_path / "raiz" / ".env.example").exists()


def test_payload_embutido_confere_o_sha256(tmp_path, monkeypatch):
    pasta = tmp_path / "dados"
    pasta.mkdir()
    z = _zip(pasta / "payload.zip", {"a": "1"})
    (pasta / "payload.manifest.json").write_text(json.dumps({"sha256": codigo.sha256_arquivo(z), "versao": "9"}))
    monkeypatch.setattr(codigo, "_pasta_dados_empacotados", lambda: pasta)
    assert codigo.payload_embutido()[1]["versao"] == "9"
    (pasta / "payload.manifest.json").write_text(json.dumps({"sha256": "0" * 64}))
    with pytest.raises(codigo.ErroCodigo, match="corrompido"):
        codigo.payload_embutido()


def test_payload_ausente_orienta_a_usar_o_github(tmp_path, monkeypatch):
    monkeypatch.setattr(codigo, "_pasta_dados_empacotados", lambda: tmp_path / "nada")
    with pytest.raises(codigo.ErroCodigo, match="GitHub"):
        codigo.payload_embutido()


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def test_download_so_aceita_https_nos_hosts_permitidos(tmp_path):
    with pytest.raises(codigo.ErroCodigo):
        codigo.baixar_https("http://github.com/x.zip", tmp_path / "x", codigo.HOSTS_GITHUB, 10)
    with pytest.raises(codigo.ErroCodigo):
        codigo.baixar_https("https://evil.example/x.zip", tmp_path / "x", codigo.HOSTS_GITHUB, 10)
    with pytest.raises(codigo.ErroCodigo):
        codigo.baixar_https("https://github.com.evil.example/x.zip", tmp_path / "x", codigo.HOSTS_GITHUB, 10)


def test_download_respeita_o_limite_e_apaga_o_parcial(tmp_path):
    alvo = tmp_path / "x.zip"
    with pytest.raises(codigo.ErroCodigo, match="limite"):
        codigo.baixar_https("https://github.com/x.zip", alvo, codigo.HOSTS_GITHUB, 5, abrir=lambda req, timeout: _Resp(b"123456789"))
    assert not alvo.exists()
    codigo.baixar_https("https://github.com/x.zip", alvo, codigo.HOSTS_GITHUB, 50, abrir=lambda req, timeout: _Resp(b"123456789"))
    assert alvo.read_bytes() == b"123456789"


def test_redirecionamento_para_fora_do_github_e_recusado():
    manipulador = codigo._so_hosts(codigo.HOSTS_GITHUB)()
    with pytest.raises(codigo.ErroCodigo):
        manipulador.redirect_request(None, None, 302, "", {}, "https://evil.example/x.zip")
    with pytest.raises(codigo.ErroCodigo):
        manipulador.redirect_request(None, None, 302, "", {}, "http://codeload.github.com/x.zip")


def test_url_do_github_escapa_a_ref():
    assert codigo.url_github("tudoemcodigo/TudoIA", "main") == "https://github.com/tudoemcodigo/TudoIA/archive/main.zip"
    assert " " not in codigo.url_github("a/b", "x y")


def test_instalar_nao_aplica_dacl_restrita_de_mkdtemp(tmp_path):
    """Regressão real: tempfile.mkdtemp no Python 3.12+ cria pasta 0o700 (sem BUILTIN\\Usuários) e os.replace
    preservava essa DACL em runtime/searxng/settings.yml, quebrando o SearXNG e o LiteLLM no Docker."""
    import subprocess
    import sys

    raiz = tmp_path / "raiz"
    raiz.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        # Garante que `raiz` tenha ACE herdável (no Python 3.12.10 do CI o tmp_path do pytest nasce sem OI/CI)
        subprocess.run(["icacls", str(raiz), "/grant", "*S-1-5-32-545:(OI)(CI)(RX)"],
                       capture_output=True, text=True, errors="replace", check=True)
    z = _zip(tmp_path / "p.zip", {"runtime/searxng/settings.yml": "use_default_settings: true\n"})
    codigo.instalar(z, raiz, remover_prefixo=False)
    arq = raiz / "runtime" / "searxng" / "settings.yml"
    assert arq.is_file()
    if sys.platform == "win32":
        r = subprocess.run(["icacls", str(arq)], capture_output=True, text=True, errors="replace", check=False)
        assert "(I)" in r.stdout, f"esperava ACL herdada (I) em {arq}, obtive:\n{r.stdout}"

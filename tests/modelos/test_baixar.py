"""Testes do baixador de modelos (scripts/modelos/baixar.py). Sem internet: servidor HTTPS local em thread.

O servidor precisa de TLS porque o baixador so aceita https://. O certificado de teste e gerado com o
openssl do sistema; sem openssl os testes HTTPS sao pulados com motivo claro.
"""
from __future__ import annotations

import hashlib
import http.server
import importlib.util
import os
import shutil
import socket
import ssl
import subprocess
import sys
import threading
import types
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("baixar_modelos", RAIZ / "scripts" / "modelos" / "baixar.py")
baixar = importlib.util.module_from_spec(_spec)
sys.modules["baixar_modelos"] = baixar
_spec.loader.exec_module(baixar)

TOKEN = "hf_SEGREDO_DE_TESTE_123456"


def sha(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def modelo(id_: str = "teste", origem: str | None = "https://127.0.0.1/x.bin", destino: str = "pasta/x.bin",
           sha256: str | None = None, tamanho: float | None = None, tipo: str = "url",
           notas: str = "teste") -> "baixar.Modelo":
    return baixar.Modelo(
        id=id_, tipo=tipo, destino=destino, origem=origem, arquivo=None, revisao="main",
        tamanho_aprox_gb=tamanho, licenca_nome=None, licenca_url=None, obrigatorio=False,
        usado_por="teste", sha256=sha256, notas=notas,
    )


# ---------------------------------------------------------------- TLS e servidor local
@pytest.fixture(scope="session")
def certificado(tmp_path_factory):
    openssl = shutil.which("openssl")
    if openssl is None:
        pytest.skip("openssl ausente: os testes HTTPS precisam gerar um certificado de teste")
    pasta = tmp_path_factory.mktemp("tls")
    cert, chave = pasta / "cert.pem", pasta / "chave.pem"
    subprocess.run(
        [openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(chave), "-out", str(cert),
         "-days", "2", "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1"],
        check=True, capture_output=True, timeout=120,
    )
    return cert, chave


@pytest.fixture(scope="session")
def contexto(certificado):
    cert, _ = certificado
    return ssl.create_default_context(cafile=str(cert))


class Estado:
    def __init__(self):
        self.arquivos: dict[str, bytes] = {}
        self.redirecionar: dict[str, tuple[int, str]] = {}
        self.falhas: dict[str, list[int]] = {}
        self.truncar: set[str] = set()
        self.etags: dict[str, str] = {}           # caminho -> ETag; If-Range diferente => 200 com o arquivo todo
        self.faixa_errada: set[str] = set()       # 206 com Content-Range comecando em 0, nao onde o Range pediu
        self.ignorar_range: set[str] = set()      # responde 200 mesmo com Range
        self.sem_tamanho: set[str] = set()        # sem Content-Length (fim = fechar a conexao)
        self.registro: list[tuple[str, dict]] = []
        self.trava = threading.Lock()

    def pedidos(self, caminho: str) -> list[dict]:
        return [cab for c, cab in self.registro if c == caminho]


@pytest.fixture
def servidor(certificado):
    cert, chave = certificado
    estado = Estado()

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            caminho = self.path.split("?")[0]
            with estado.trava:
                estado.registro.append((caminho, dict(self.headers)))
                falha = estado.falhas.get(caminho)
                codigo_falha = falha.pop(0) if falha else None
            if codigo_falha:
                self.send_error(codigo_falha)
                return
            if caminho in estado.redirecionar:
                codigo, destino = estado.redirecionar[caminho]
                self.send_response(codigo)
                self.send_header("Location", destino)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if caminho not in estado.arquivos:
                self.send_error(404)
                return
            dados = estado.arquivos[caminho]
            inicio = 0
            intervalo = self.headers.get("Range", "")
            if intervalo.startswith("bytes="):
                inicio = int(intervalo[len("bytes="):].split("-")[0])
            etag = estado.etags.get(caminho)
            if_range = self.headers.get("If-Range")
            if caminho in estado.ignorar_range or (if_range is not None and if_range != etag):
                inicio = 0
            if inicio and caminho in estado.faixa_errada:
                inicio = 0
                corpo = dados
                self.send_response(206)
                self.send_header("Content-Range", f"bytes 0-{len(dados) - 1}/{len(dados)}")
            else:
                corpo = dados[inicio:]
                if inicio:
                    self.send_response(206)
                    self.send_header("Content-Range", f"bytes {inicio}-{len(dados) - 1}/{len(dados)}")
                else:
                    self.send_response(200)
            if etag:
                self.send_header("ETag", etag)
            if caminho not in estado.sem_tamanho:
                self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            if caminho in estado.truncar:
                self.wfile.write(corpo[: len(corpo) // 2])
                return
            self.wfile.write(corpo)

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ctx.load_cert_chain(str(cert), str(chave))
    srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield estado, srv.server_address[1]
    finally:
        srv.shutdown()
        srv.server_close()


@pytest.fixture(autouse=True)
def _sem_configuracao_do_usuario(tmp_path, monkeypatch):
    """Isola os testes do .env real e de TUDOIA_OLLAMA_MODELS da maquina."""
    monkeypatch.delenv("TUDOIA_OLLAMA_MODELS", raising=False)
    monkeypatch.setattr(baixar, "ARQUIVO_ENV", tmp_path / "nao-existe.env")


def porta_fechada() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    porta = s.getsockname()[1]
    s.close()
    return porta


# ---------------------------------------------------------------- download
def test_download_feliz_grava_arquivo_completo_sem_parcial(tmp_path, servidor, contexto):
    estado, porta = servidor
    dados = os.urandom(3 * 1024 * 1024 + 17)
    estado.arquivos["/a.bin"] = dados
    m = modelo(origem=f"https://127.0.0.1:{porta}/a.bin", sha256=sha(dados))

    resultado = baixar.baixar_modelo(m, tmp_path, contexto_ssl=contexto, pausa=0)

    assert resultado == "baixado"
    alvo = tmp_path / "pasta" / "x.bin"
    assert alvo.read_bytes() == dados
    assert not (alvo.parent / "x.bin.part").exists()
    assert not (alvo.parent / "x.bin.part.lock").exists()


def test_retoma_a_partir_do_part_com_range(tmp_path, servidor, contexto):
    estado, porta = servidor
    dados = os.urandom(1024 * 1024)
    estado.arquivos["/r.bin"] = dados
    parcial = tmp_path / "pasta" / "x.bin.part"
    parcial.parent.mkdir(parents=True)
    parcial.write_bytes(dados[:400_000])
    m = modelo(origem=f"https://127.0.0.1:{porta}/r.bin", sha256=sha(dados))

    baixar.baixar_modelo(m, tmp_path, contexto_ssl=contexto, pausa=0)

    assert estado.pedidos("/r.bin")[-1]["Range"] == "bytes=400000-"
    assert (tmp_path / "pasta" / "x.bin").read_bytes() == dados
    assert not parcial.exists()


def test_sha256_divergente_descarta_parcial_e_falha(tmp_path, servidor, contexto):
    estado, porta = servidor
    estado.arquivos["/s.bin"] = b"conteudo real"
    m = modelo(origem=f"https://127.0.0.1:{porta}/s.bin", sha256=sha(b"outro conteudo"))

    with pytest.raises(baixar.ErroVerificacao) as info:
        baixar.baixar_modelo(m, tmp_path, contexto_ssl=contexto, pausa=0)

    assert info.value.codigo_saida == 1
    assert not (tmp_path / "pasta" / "x.bin").exists()
    assert not (tmp_path / "pasta" / "x.bin.part").exists()


def test_erro_transitorio_503_e_repetido(tmp_path, servidor, contexto):
    estado, porta = servidor
    dados = b"abc" * 1000
    estado.arquivos["/b.bin"] = dados
    estado.falhas["/b.bin"] = [503]
    m = modelo(origem=f"https://127.0.0.1:{porta}/b.bin", sha256=sha(dados))

    assert baixar.baixar_modelo(m, tmp_path, contexto_ssl=contexto, pausa=0) == "baixado"
    assert len(estado.pedidos("/b.bin")) == 2


def test_404_nao_e_repetido(tmp_path, servidor, contexto):
    estado, porta = servidor
    m = modelo(origem=f"https://127.0.0.1:{porta}/nao-existe.bin")

    with pytest.raises(baixar.ErroRede) as info:
        baixar.baixar_modelo(m, tmp_path, contexto_ssl=contexto, pausa=0)

    assert info.value.codigo_saida == 2
    assert len(estado.pedidos("/nao-existe.bin")) == 1


def test_conexao_truncada_mantem_parcial_para_retomar_e_nao_cria_final(tmp_path, servidor, contexto):
    estado, porta = servidor
    estado.arquivos["/t.bin"] = os.urandom(200_000)
    estado.truncar.add("/t.bin")
    m = modelo(origem=f"https://127.0.0.1:{porta}/t.bin")

    with pytest.raises(baixar.ErroRede):
        baixar.baixar_modelo(m, tmp_path, contexto_ssl=contexto, tentativas=2, pausa=0)

    parcial = tmp_path / "pasta" / "x.bin.part"
    assert not (tmp_path / "pasta" / "x.bin").exists()
    assert parcial.is_file() and 0 < parcial.stat().st_size < 200_000


def test_download_ja_presente_com_sha_correto_nao_rebaixa(tmp_path, servidor, contexto):
    estado, porta = servidor
    dados = b"ja estou aqui"
    alvo = tmp_path / "pasta" / "x.bin"
    alvo.parent.mkdir(parents=True)
    alvo.write_bytes(dados)
    m = modelo(origem=f"https://127.0.0.1:{porta}/x.bin", sha256=sha(dados))

    assert baixar.baixar_modelo(m, tmp_path, contexto_ssl=contexto) == "ja-presente"
    assert estado.registro == []


def test_trava_impede_dois_downloads_no_mesmo_parcial(tmp_path, servidor, contexto):
    estado, porta = servidor
    estado.arquivos["/l.bin"] = b"x"
    parcial = tmp_path / "pasta" / "x.bin.part"
    parcial.parent.mkdir(parents=True)
    (parcial.parent / "x.bin.part.lock").write_bytes(b"")
    m = modelo(origem=f"https://127.0.0.1:{porta}/l.bin")

    with pytest.raises(baixar.ErroModelo, match="em andamento"):
        baixar.baixar_modelo(m, tmp_path, contexto_ssl=contexto, pausa=0)
    assert estado.pedidos("/l.bin") == []


def test_rede_fora_do_ar_sai_com_codigo_2(tmp_path, contexto):
    m = modelo(origem=f"https://127.0.0.1:{porta_fechada()}/x.bin")

    with pytest.raises(baixar.ErroRede) as info:
        baixar.baixar_modelo(m, tmp_path, contexto_ssl=contexto, tentativas=2, pausa=0)
    assert info.value.codigo_saida == 2


def test_espaco_insuficiente_falha_antes_de_baixar(tmp_path, servidor, contexto, monkeypatch):
    estado, porta = servidor
    estado.arquivos["/e.bin"] = b"x"
    monkeypatch.setattr(baixar.shutil, "disk_usage", lambda _p: types.SimpleNamespace(total=0, used=0, free=0))
    m = modelo(origem=f"https://127.0.0.1:{porta}/e.bin", tamanho=1.0)

    with pytest.raises(baixar.ErroEspaco) as info:
        baixar.baixar_modelo(m, tmp_path, contexto_ssl=contexto)
    assert info.value.codigo_saida == 2
    assert estado.registro == []


# ---------------------------------------------------------------- retomada: If-Range, Content-Range, sem tamanho
def _parcial(tmp_path: Path) -> Path:
    return tmp_path / "pasta" / "x.bin.part"


def test_retomada_manda_if_range_com_a_etag_salva(tmp_path, servidor, contexto):
    estado, porta = servidor
    dados = os.urandom(300_000)
    estado.arquivos["/i.bin"] = dados
    estado.etags["/i.bin"] = '"v1"'
    estado.truncar.add("/i.bin")
    m = modelo(origem=f"https://127.0.0.1:{porta}/i.bin")

    with pytest.raises(baixar.ErroRede):
        baixar.baixar_modelo(m, tmp_path, contexto_ssl=contexto, tentativas=1, pausa=0)
    meta = _parcial(tmp_path).with_name("x.bin.part.meta")
    assert meta.is_file() and str(porta) not in meta.read_text(encoding="utf-8")  # guarda hash, nao a URL
    tamanho_parcial = _parcial(tmp_path).stat().st_size

    estado.truncar.clear()
    assert baixar.baixar_modelo(m, tmp_path, contexto_ssl=contexto, tentativas=1, pausa=0) == "baixado"

    ultimo = estado.pedidos("/i.bin")[-1]
    assert ultimo["Range"] == f"bytes={tamanho_parcial}-"
    assert ultimo["If-Range"] == '"v1"'
    assert (tmp_path / "pasta" / "x.bin").read_bytes() == dados
    assert not _parcial(tmp_path).exists() and not meta.exists()


def test_arquivo_mudou_no_servidor_recomeca_do_zero_sem_misturar_versoes(tmp_path, servidor, contexto):
    estado, porta = servidor
    v1, v2 = os.urandom(300_000), os.urandom(300_000)
    estado.arquivos["/v.bin"] = v1
    estado.etags["/v.bin"] = '"v1"'
    estado.truncar.add("/v.bin")
    m = modelo(origem=f"https://127.0.0.1:{porta}/v.bin")
    with pytest.raises(baixar.ErroRede):
        baixar.baixar_modelo(m, tmp_path, contexto_ssl=contexto, tentativas=1, pausa=0)

    estado.arquivos["/v.bin"] = v2       # nova versao publicada com o mesmo nome
    estado.etags["/v.bin"] = '"v2"'
    estado.truncar.clear()
    baixar.baixar_modelo(m, tmp_path, contexto_ssl=contexto, tentativas=1, pausa=0)

    assert estado.pedidos("/v.bin")[-1]["If-Range"] == '"v1"'
    assert (tmp_path / "pasta" / "x.bin").read_bytes() == v2


def test_206_que_nao_continua_o_parcial_descarta_e_recomeca(tmp_path, servidor, contexto):
    estado, porta = servidor
    dados = os.urandom(500_000)
    estado.arquivos["/f.bin"] = dados
    estado.faixa_errada.add("/f.bin")
    _parcial(tmp_path).parent.mkdir(parents=True)
    _parcial(tmp_path).write_bytes(dados[:400_000])
    m = modelo(origem=f"https://127.0.0.1:{porta}/f.bin", sha256=sha(dados))

    assert baixar.baixar_modelo(m, tmp_path, contexto_ssl=contexto, tentativas=2, pausa=0) == "baixado"

    pedidos = estado.pedidos("/f.bin")
    assert pedidos[0]["Range"] == "bytes=400000-"
    assert "Range" not in pedidos[1]            # recomecou do zero, sem juntar a faixa errada
    assert (tmp_path / "pasta" / "x.bin").read_bytes() == dados


def test_200_numa_retomada_sobrescreve_o_parcial(tmp_path, servidor, contexto):
    estado, porta = servidor
    dados = os.urandom(200_000)
    estado.arquivos["/z.bin"] = dados
    estado.ignorar_range.add("/z.bin")
    _parcial(tmp_path).parent.mkdir(parents=True)
    _parcial(tmp_path).write_bytes(b"lixo de outra versao" * 100)
    m = modelo(origem=f"https://127.0.0.1:{porta}/z.bin", sha256=sha(dados))

    assert baixar.baixar_modelo(m, tmp_path, contexto_ssl=contexto, tentativas=1, pausa=0) == "baixado"
    assert estado.pedidos("/z.bin")[0]["Range"].startswith("bytes=")
    assert (tmp_path / "pasta" / "x.bin").read_bytes() == dados


def test_parcial_sem_validador_e_sem_sha_recomeca_do_zero(tmp_path, servidor, contexto):
    estado, porta = servidor
    dados = os.urandom(100_000)
    estado.arquivos["/n.bin"] = dados
    _parcial(tmp_path).parent.mkdir(parents=True)
    _parcial(tmp_path).write_bytes(os.urandom(50_000))   # .part antigo, de versao desconhecida
    m = modelo(origem=f"https://127.0.0.1:{porta}/n.bin")

    baixar.baixar_modelo(m, tmp_path, contexto_ssl=contexto, tentativas=1, pausa=0)

    assert "Range" not in estado.pedidos("/n.bin")[0]
    assert (tmp_path / "pasta" / "x.bin").read_bytes() == dados


def test_sem_content_length_e_sem_sha_e_tratado_como_incompleto(tmp_path, servidor, contexto):
    estado, porta = servidor
    estado.arquivos["/c.bin"] = os.urandom(50_000)
    estado.sem_tamanho.add("/c.bin")
    m = modelo(origem=f"https://127.0.0.1:{porta}/c.bin")

    with pytest.raises(baixar.ErroRede, match="tamanho"):
        baixar.baixar_modelo(m, tmp_path, contexto_ssl=contexto, tentativas=3, pausa=0)
    assert not (tmp_path / "pasta" / "x.bin").exists()
    assert len(estado.pedidos("/c.bin")) == 1       # repetir nao resolve: falha direto


def test_sem_content_length_aceito_quando_o_sha_confere(tmp_path, servidor, contexto):
    estado, porta = servidor
    dados = os.urandom(50_000)
    estado.arquivos["/c.bin"] = dados
    estado.sem_tamanho.add("/c.bin")
    m = modelo(origem=f"https://127.0.0.1:{porta}/c.bin", sha256=sha(dados))

    assert baixar.baixar_modelo(m, tmp_path, contexto_ssl=contexto, tentativas=1, pausa=0) == "baixado"
    assert (tmp_path / "pasta" / "x.bin").read_bytes() == dados


def test_sem_content_length_truncado_nao_vira_arquivo_final(tmp_path, servidor, contexto):
    estado, porta = servidor
    dados = os.urandom(50_000)
    estado.arquivos["/c.bin"] = dados
    estado.sem_tamanho.add("/c.bin")
    estado.truncar.add("/c.bin")
    m = modelo(origem=f"https://127.0.0.1:{porta}/c.bin", sha256=sha(dados))

    with pytest.raises(baixar.ErroRede):
        baixar.baixar_modelo(m, tmp_path, contexto_ssl=contexto, tentativas=2, pausa=0)
    assert not (tmp_path / "pasta" / "x.bin").exists()


# ---------------------------------------------------------------- seguranca: URL, redirect, token
def test_recusa_origem_http_sem_conectar(tmp_path):
    m = modelo(origem="http://127.0.0.1:9/x.bin")

    with pytest.raises(baixar.ErroSeguranca, match="https"):
        baixar.baixar_modelo(m, tmp_path, pausa=0)
    assert not (tmp_path / "pasta").exists()


def test_redirecionamento_para_http_e_recusado(tmp_path, servidor, contexto):
    estado, porta = servidor
    estado.redirecionar["/r.bin"] = (302, "http://127.0.0.1:9/x.bin")
    m = modelo(origem=f"https://127.0.0.1:{porta}/r.bin")

    with pytest.raises(baixar.ErroSeguranca, match="https"):
        baixar.baixar_modelo(m, tmp_path, contexto_ssl=contexto, pausa=0)
    assert len(estado.registro) == 1
    assert not (tmp_path / "pasta" / "x.bin").exists()


def test_token_hf_nao_vai_para_host_que_nao_e_huggingface(tmp_path, servidor, contexto, monkeypatch):
    estado, porta = servidor
    dados = b"sem token aqui"
    estado.arquivos["/a.bin"] = dados
    estado.arquivos["/destino.bin"] = dados
    # redirecionamento para outro nome de host (localhost): urllib copiaria o Authorization
    estado.redirecionar["/r.bin"] = (302, f"https://localhost:{porta}/destino.bin")
    monkeypatch.setenv("HF_TOKEN", TOKEN)
    m = modelo(origem=f"https://127.0.0.1:{porta}/r.bin", sha256=sha(dados))

    baixar.baixar_modelo(m, tmp_path, contexto_ssl=contexto, pausa=0)

    todos = estado.pedidos("/r.bin") + estado.pedidos("/destino.bin")
    assert todos, "a requisicao nao chegou ao servidor"
    for cabecalhos in todos:
        assert "Authorization" not in cabecalhos


@pytest.mark.parametrize("url, esperado", [
    ("https://huggingface.co/x/resolve/main/a", True),
    ("https://cdn-lfs.huggingface.co/a", True),
    ("https://evilhuggingface.co/a", False),
    ("https://huggingface.co.evil.example/a", False),
    ("https://huggingface.co@evil.example/a", False),
    ("https://127.0.0.1:8443/a", False),
])
def test_predicado_de_host_do_token(url, esperado):
    assert baixar._host_recebe_token(url) is esperado


def test_erro_de_autenticacao_nao_ecoa_token(tmp_path, servidor, contexto, monkeypatch, capsys):
    estado, porta = servidor
    estado.falhas["/p.bin"] = [401]
    monkeypatch.setenv("HF_TOKEN", TOKEN)
    m = modelo(origem=f"https://127.0.0.1:{porta}/p.bin")

    with pytest.raises(baixar.ErroRede) as info:
        baixar.baixar_modelo(m, tmp_path, contexto_ssl=contexto, pausa=0)

    saida = capsys.readouterr()
    assert TOKEN not in str(info.value) and TOKEN not in saida.out + saida.err
    assert len(estado.pedidos("/p.bin")) == 1


@pytest.mark.parametrize("url", [
    "https://user:senha@example.com/x.bin",
    "https:///sem-host.bin",
    "ftp://example.com/x.bin",
    "https://example.com/x bin",
])
def test_validar_url_recusa_formas_perigosas(url):
    with pytest.raises(baixar.ErroSeguranca):
        baixar.validar_url_https(url)


# ---------------------------------------------------------------- pendente e ollama
def test_origem_pendente_nao_baixa_e_aparece_como_pendente(tmp_path):
    m = modelo(origem=None, notas="PENDENTE: informar origem (teste)")

    assert baixar.status_modelo(m, tmp_path) == "pendente-origem"
    with pytest.raises(baixar.ErroPendente):
        baixar.baixar_modelo(m, tmp_path)
    assert not (tmp_path / "pasta").exists()


def test_ollama_presenca_checada_pelo_manifesto_local(tmp_path):
    m = baixar.Modelo(id="o", tipo="ollama", destino="ollama/models", origem="qwen3.5:9b", arquivo=None,
                      revisao="main", tamanho_aprox_gb=None, licenca_nome=None, licenca_url=None,
                      obrigatorio=False, usado_por="t", sha256=None, notas="t")
    assert baixar.status_modelo(m, tmp_path) == "ausente"
    manif = tmp_path / "ollama" / "models" / "manifests" / "registry.ollama.ai" / "library" / "qwen3.5" / "9b"
    manif.parent.mkdir(parents=True)
    manif.write_text("{}", encoding="utf-8")
    assert baixar.status_modelo(m, tmp_path) == "presente"


def test_ollama_sem_binario_informa_comando_manual(tmp_path, monkeypatch):
    monkeypatch.setattr(baixar.shutil, "which", lambda _nome: None)
    m = baixar.Modelo(id="o", tipo="ollama", destino="ollama/models", origem="qwen3.5:9b", arquivo=None,
                      revisao="main", tamanho_aprox_gb=None, licenca_nome=None, licenca_url=None,
                      obrigatorio=False, usado_por="t", sha256=None, notas="t")

    with pytest.raises(baixar.ErroDependencia, match="ollama pull qwen3.5:9b"):
        baixar.baixar_modelo(m, tmp_path)


def test_ollama_pull_usa_argv_em_lista_sem_shell(tmp_path, monkeypatch):
    chamadas = []
    monkeypatch.setattr(baixar.shutil, "which", lambda _nome: "/usr/bin/ollama")

    def falso_run(args, **kwargs):
        chamadas.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(baixar.subprocess, "run", falso_run)
    m = baixar.Modelo(id="o", tipo="ollama", destino="ollama/models", origem="qwen3.5:9b", arquivo=None,
                      revisao="main", tamanho_aprox_gb=None, licenca_nome=None, licenca_url=None,
                      obrigatorio=False, usado_por="t", sha256=None, notas="t")

    assert baixar.baixar_modelo(m, tmp_path) == "ollama"
    args, kwargs = chamadas[0]
    assert args == ["/usr/bin/ollama", "pull", "qwen3.5:9b"]
    assert not kwargs.get("shell")


def test_ollama_ja_presente_nao_chama_pull(tmp_path, monkeypatch):
    manif = tmp_path / "ollama" / "models" / "manifests" / "registry.ollama.ai" / "library" / "qwen3.5" / "9b"
    manif.parent.mkdir(parents=True)
    manif.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(baixar.subprocess, "run", lambda *a, **k: pytest.fail("nao deve chamar ollama pull"))
    m = baixar.Modelo(id="o", tipo="ollama", destino="ollama/models", origem="qwen3.5:9b", arquivo=None,
                      revisao="main", tamanho_aprox_gb=None, licenca_nome=None, licenca_url=None,
                      obrigatorio=False, usado_por="t", sha256=None, notas="t")

    assert baixar.baixar_modelo(m, tmp_path) == "ja-presente"


def _modelo_ollama() -> "baixar.Modelo":
    return baixar.Modelo(id="o", tipo="ollama", destino="ollama/models", origem="qwen3.5:9b", arquivo=None,
                         revisao="main", tamanho_aprox_gb=None, licenca_nome=None, licenca_url=None,
                         obrigatorio=False, usado_por="t", sha256=None, notas="t")


def _criar_manifesto_ollama(pasta: Path) -> None:
    manif = pasta / "manifests" / "registry.ollama.ai" / "library" / "qwen3.5" / "9b"
    manif.parent.mkdir(parents=True)
    manif.write_text("{}", encoding="utf-8")


def test_ollama_presenca_respeita_tudoia_ollama_models_do_ambiente(tmp_path, monkeypatch):
    pesos = tmp_path / "outro-disco" / "pesos"
    _criar_manifesto_ollama(pesos)
    m = _modelo_ollama()
    assert baixar.status_modelo(m, tmp_path / "base") == "ausente"

    monkeypatch.setenv("TUDOIA_OLLAMA_MODELS", str(pesos))
    assert baixar.status_modelo(m, tmp_path / "base") == "presente"


def test_ollama_presenca_respeita_tudoia_ollama_models_do_env(tmp_path, monkeypatch):
    pesos = tmp_path / "pesos com espaco"
    _criar_manifesto_ollama(pesos)
    env = tmp_path / ".env"
    env.write_text(f'OUTRA=1\nTUDOIA_OLLAMA_MODELS=\nTUDOIA_OLLAMA_MODELS="{pesos}"\n', encoding="utf-8")
    monkeypatch.setattr(baixar, "ARQUIVO_ENV", env)

    assert baixar.status_modelo(_modelo_ollama(), tmp_path / "base") == "presente"


# ---------------------------------------------------------------- manifesto
def _manifesto(tmp_path: Path, trecho_modelo: str) -> Path:
    arquivo = tmp_path / "modelos.yaml"
    arquivo.write_text("versao: 1\nmodelos:\n" + trecho_modelo, encoding="utf-8")
    return arquivo


def _entrada(id_="a", **campos) -> str:
    base = {
        "tipo": "url", "destino": "pasta/a.bin", "origem": "https://example.com/a.bin",
        "tamanho_aprox_gb": 1, "licenca": "{nome: null, url: null}", "obrigatorio": "false",
        "usado_por": "teste", "sha256": "null", "notas": "teste",
    }
    base.update({k: str(v) for k, v in campos.items()})
    linhas = [f"  - id: {id_}"]
    linhas += [f"    {k}: {v}" for k, v in base.items()]
    return "\n".join(linhas) + "\n"


def test_manifesto_valido_carrega(tmp_path):
    modelos = baixar.carregar_manifesto(_manifesto(tmp_path, _entrada("a")))
    assert [m.id for m in modelos] == ["a"]


@pytest.mark.parametrize("trecho, mensagem", [
    (_entrada("a") + _entrada("a", destino="pasta/b.bin"), "duplicado"),
    (_entrada("a", destino="../fora.bin"), "'..'"),
    (_entrada("a", destino="pasta/../../fora.bin"), "'..'"),
    (_entrada("a", destino="/etc/passwd"), "absoluto"),
    (_entrada("a", destino="C:/windows/x.bin"), "caractere invalido"),
    (_entrada("a", destino="pasta:stream.bin"), "caractere invalido"),
    (_entrada("a", origem="http://example.com/a.bin"), "https"),
    (_entrada("a", origem="https://user:pw@example.com/a.bin"), "credenciais"),
    (_entrada("a", origem="null", notas="sem marcador"), "PENDENTE"),
    (_entrada("a", tipo="ollama", origem="../x", sha256="null", destino="ollama/models"), "Ollama invalida"),
    (_entrada("a", tipo="ollama", origem="qwen3:8b", sha256="a" * 64, destino="ollama/models"), "sha256 nao se aplica"),
    (_entrada("a", sha256="ABC"), "sha256"),
    (_entrada("a", tipo="huggingface", origem="dono/repo", arquivo="../x.bin"), "'..'"),
    (_entrada("a", tipo="huggingface", origem="https://huggingface.co/dono/repo"), "dono/repositorio"),
    (_entrada("a", tipo="huggingface", origem="dono/repo"), "exige 'arquivo'"),
    (_entrada("a", tipo="desconhecido"), "tipo invalido"),
    (_entrada("a", obrigatorio="talvez"), "obrigatorio"),
    (_entrada("a") + "    tamanho: 3\n", "desconhecidas"),
    (_entrada("A-Maiusculo"), "id invalido"),
])
def test_manifesto_recusa_entradas_invalidas(tmp_path, trecho, mensagem):
    with pytest.raises(baixar.ErroManifesto, match=mensagem):
        baixar.carregar_manifesto(_manifesto(tmp_path, trecho))


def test_manifesto_do_repositorio_e_valido_e_pendentes_sao_marcados():
    modelos = baixar.carregar_manifesto(baixar.MANIFESTO_PADRAO)
    ids = [m.id for m in modelos]
    assert len(ids) == len(set(ids)) and ids
    for m in modelos:
        if m.pendente:
            assert "PENDENTE" in m.notas, m.id
        assert m.sha256 is None, f"{m.id}: sha256 nao deve ser inventado"


def test_validar_destino_normaliza_barras_do_windows():
    assert baixar.validar_destino("ollama\\models") == "ollama/models"


def test_selecionar_modelos_rejeita_id_desconhecido(tmp_path):
    modelos = baixar.carregar_manifesto(_manifesto(tmp_path, _entrada("a")))
    with pytest.raises(baixar.ErroManifesto, match="desconhecido"):
        baixar.selecionar_modelos(modelos, ["b"])


# ---------------------------------------------------------------- verificacao e CLI
def test_verificar_divergente_e_sem_sha(tmp_path):
    alvo = tmp_path / "pasta" / "x.bin"
    alvo.parent.mkdir(parents=True)
    alvo.write_bytes(b"conteudo")

    divergente = modelo(sha256="0" * 64)
    assert baixar.verificar_modelo(divergente, tmp_path).status == "divergente"
    sem = modelo(sha256=None)
    assert baixar.verificar_modelo(sem, tmp_path).status == "sem-sha256"
    assert baixar.verificar_modelo(modelo(sha256="0" * 64, destino="outro/y.bin"), tmp_path).status == "ausente"


def test_main_codigos_de_saida(tmp_path, capsys):
    manifesto = _manifesto(tmp_path, _entrada("a"))
    base = ["--manifesto", str(manifesto), "--base-dir", str(tmp_path)]

    assert baixar.main(["--listar", *base]) == 0
    assert "ausente" in capsys.readouterr().out
    assert baixar.main(["--modelo", "nao-existe", *base]) == 1
    assert baixar.main([*base]) == 1
    assert baixar.main(["--verificar", *base]) == 1  # 'a' esta ausente


def test_main_falha_de_rede_sai_com_2(tmp_path, monkeypatch, capsys):
    porta = porta_fechada()
    manifesto = _manifesto(tmp_path, _entrada("a", origem=f"https://127.0.0.1:{porta}/a.bin"))
    monkeypatch.setattr(baixar, "PAUSA_PADRAO", 0)
    monkeypatch.setattr(baixar, "TENTATIVAS_PADRAO", 1)
    # sem contexto TLS de teste a conexao recusada ja falha como rede (codigo 2)
    codigo = baixar.main(["--modelo", "a", "--manifesto", str(manifesto), "--base-dir", str(tmp_path)])
    assert codigo == 2
    assert "falha" in capsys.readouterr().err

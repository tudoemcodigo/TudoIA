"""Código-fonte do TudoIA: do pacote embutido no .exe ou de um zip do GitHub, extraído com proteção contra zip-slip."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Callable

MAX_ARQUIVOS = 60_000
MAX_BYTES_DESCOMPRIMIDOS = 1024 ** 3          # 1 GB: o código do projeto tem dezenas de MB
MAX_DOWNLOAD = 400 * 1024 ** 2
HOSTS_GITHUB = ("github.com", "codeload.github.com")
# Nunca sobrescritos nem apagados numa reinstalação: são os dados e a configuração do usuário.
PRESERVAR = (".env", "dados", "modelos", ".venv", ".tudoia-instalacao.json", "ferramentas",
             "runtime/litellm/config.yaml", "runtime/litellm/config.yaml.anterior")


class ErroCodigo(Exception):
    pass


def _pasta_dados_empacotados() -> Path:
    base = getattr(sys, "_MEIPASS", None)
    return Path(base) / "dados" if base else Path(__file__).resolve().parent.parent / "dados"


def payload_embutido() -> tuple[Path, dict]:
    """(zip, manifesto) do pacote que acompanha o instalador. Falta = ErroCodigo (use a fonte GitHub)."""
    pasta = _pasta_dados_empacotados()
    zip_path, manifesto = pasta / "payload.zip", pasta / "payload.manifest.json"
    if not zip_path.is_file() or not manifesto.is_file():
        raise ErroCodigo("este instalador não traz o código embutido; escolha a fonte GitHub")
    info = json.loads(manifesto.read_text(encoding="utf-8"))
    if sha256_arquivo(zip_path) != info.get("sha256"):
        raise ErroCodigo("o pacote embutido está corrompido (sha256 não confere); baixe o instalador de novo")
    return zip_path, info


def sha256_arquivo(caminho: Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def _nome_seguro(nome: str) -> PurePosixPath:
    p = PurePosixPath(nome.replace("\\", "/"))
    if p.is_absolute() or ".." in p.parts or (p.parts and ":" in p.parts[0]) or "\x00" in nome:
        raise ErroCodigo(f"caminho perigoso no pacote: {nome!r}")
    return p


def extrair(zip_path: Path, destino: Path, remover_prefixo: bool = False) -> int:
    """Extrai com limites e sem sair de `destino`. Devolve a quantidade de arquivos."""
    destino.mkdir(parents=True, exist_ok=True)
    base = destino.resolve()
    with zipfile.ZipFile(zip_path) as z:
        membros = z.infolist()
        if len(membros) > MAX_ARQUIVOS:
            raise ErroCodigo("pacote com arquivos demais")
        if sum(m.file_size for m in membros) > MAX_BYTES_DESCOMPRIMIDOS:
            raise ErroCodigo("pacote grande demais depois de descomprimir")
        prefixo = ""
        if remover_prefixo:
            primeiros = {_nome_seguro(m.filename).parts[0] for m in membros if m.filename.strip("/")}
            if len(primeiros) == 1:
                prefixo = next(iter(primeiros))
        feitos = 0
        for m in membros:
            rel = _nome_seguro(m.filename)
            if prefixo and rel.parts and rel.parts[0] == prefixo:
                rel = PurePosixPath(*rel.parts[1:])
            if not rel.parts:
                continue
            alvo = (base / Path(*rel.parts)).resolve()
            if not alvo.is_relative_to(base):
                raise ErroCodigo(f"caminho perigoso no pacote: {m.filename!r}")
            if m.is_dir():
                alvo.mkdir(parents=True, exist_ok=True)
                continue
            if (m.external_attr >> 16) & 0o170000 == 0o120000:   # link simbólico dentro do zip
                raise ErroCodigo(f"link simbólico no pacote: {m.filename!r}")
            alvo.parent.mkdir(parents=True, exist_ok=True)
            with z.open(m) as origem, alvo.open("wb") as saida:
                shutil.copyfileobj(origem, saida)
            feitos += 1
    return feitos


def url_github(repo: str, ref: str) -> str:
    return f"https://github.com/{repo}/archive/{urllib.parse.quote(ref, safe='/')}.zip"


def _so_hosts(hosts: tuple[str, ...]):
    class SoHosts(urllib.request.HTTPRedirectHandler):
        """Segue redirecionamento só entre os hosts permitidos e só em https."""

        def redirect_request(self, req, fp, code, msg, headers, newurl):
            u = urllib.parse.urlsplit(newurl)
            if u.scheme != "https" or u.hostname not in hosts:
                raise ErroCodigo(f"redirecionamento recusado: {u.hostname}")
            return super().redirect_request(req, fp, code, msg, headers, newurl)
    return SoHosts


def _remover_silencioso(caminho: Path) -> None:
    try:
        caminho.unlink(missing_ok=True)
    except PermissionError:
        try:
            os.chmod(caminho, stat.S_IWRITE)
            caminho.unlink(missing_ok=True)
        except OSError:
            pass
    except OSError:
        pass


def baixar_https(url: str, destino: Path, hosts: tuple[str, ...], max_bytes: int, abrir: Callable | None = None,
                 progresso: Callable[[int], None] | None = None) -> Path:
    """Baixa `url` para `destino`: só https, só nos hosts dados (inclusive nos redirecionamentos), com teto de tamanho."""
    u = urllib.parse.urlsplit(url)
    if u.scheme != "https" or u.hostname not in hosts:
        raise ErroCodigo(f"só https em {', '.join(hosts)} é aceito (recebi {u.hostname})")
    abrir = abrir or urllib.request.build_opener(_so_hosts(hosts)).open
    if destino.is_file():
        try:
            os.chmod(destino, stat.S_IWRITE)
        except OSError:
            pass
    try:
        with abrir(urllib.request.Request(url, headers={"User-Agent": "TudoIA-Setup"}), timeout=60) as r, destino.open("wb") as f:
            total = 0
            while bloco := r.read(1024 * 256):
                total += len(bloco)
                if total > max_bytes:
                    raise ErroCodigo("download maior que o limite")
                f.write(bloco)
                if progresso:
                    progresso(total)
    except ErroCodigo:
        _remover_silencioso(destino)
        raise
    except OSError as e:
        _remover_silencioso(destino)
        raise ErroCodigo(f"não consegui baixar {u.hostname}{u.path} ({type(e).__name__})") from e
    return destino


def baixar_github(repo: str, ref: str, destino: Path, abrir: Callable | None = None,
                  progresso: Callable[[int], None] | None = None) -> Path:
    """Zip do repositório público no GitHub."""
    try:
        return baixar_https(url_github(repo, ref), destino, HOSTS_GITHUB, MAX_DOWNLOAD, abrir, progresso)
    except ErroCodigo as e:
        raise ErroCodigo(f"{e}. O repositório {repo}@{ref} é público e existe?") from e


def instalar(zip_path: Path, raiz: Path, remover_prefixo: bool) -> int:
    """Extrai numa pasta temporária ao lado e copia por cima da raiz, sem tocar no que é do usuário (PRESERVAR)."""
    raiz.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=".codigo-", dir=raiz))
    try:
        extrair(zip_path, tmp, remover_prefixo)
        copiados = 0
        for origem in sorted(p for p in tmp.rglob("*") if p.is_file()):
            rel = origem.relative_to(tmp).as_posix()
            if any(rel == p or rel.startswith(p + "/") for p in PRESERVAR) and (raiz / rel).exists():
                continue
            alvo = raiz / rel
            alvo.parent.mkdir(parents=True, exist_ok=True)
            os.replace(origem, alvo) if alvo.drive == origem.drive else shutil.move(str(origem), str(alvo))
            copiados += 1
        return copiados
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

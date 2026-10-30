#!/usr/bin/env python3
"""Lista, baixa e verifica os modelos de IA do TudoIA a partir de config/modelos.yaml.

Os pesos NAO fazem parte do projeto: cada maquina baixa os seus. Usa so a biblioteca
padrao e o PyYAML (ja dependencia do projeto).

Exemplos:
  python scripts/modelos/baixar.py --listar
  python scripts/modelos/baixar.py --obrigatorios
  python scripts/modelos/baixar.py --modelo ollama-qwen3.5-9b comfy-ae
  python scripts/modelos/baixar.py --verificar --obrigatorios

Codigos de saida: 0 ok | 1 validacao/verificacao/uso indevido | 2 rede/IO.
Variaveis de ambiente: TUDOIA_MODELOS_DIR (pasta base), HF_TOKEN (so para huggingface.co),
TUDOIA_OLLAMA_MODELS (pasta de pesos do Ollama; tambem lida do .env da raiz, como no tudoia.ps1/sh).
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Iterator
from urllib.parse import quote, urljoin, urlsplit

try:  # PyYAML e dependencia do projeto (pyproject.toml); nada novo entra por aqui
    import yaml
except ImportError:  # pragma: no cover - depende do ambiente
    yaml = None

RAIZ_REPO = Path(__file__).resolve().parents[2]
MANIFESTO_PADRAO = RAIZ_REPO / "config" / "modelos.yaml"
BASE_PADRAO = RAIZ_REPO / "modelos"
VAR_BASE = "TUDOIA_MODELOS_DIR"
VAR_TOKEN = "HF_TOKEN"
VAR_OLLAMA = "TUDOIA_OLLAMA_MODELS"
VAR_COMFYUI = "TUDOIA_COMFYUI_PORTABLE"
ARQUIVO_ENV = RAIZ_REPO / ".env"

TIPOS = ("ollama", "url", "huggingface", "comfyui-node-asset")
CHAVES = frozenset({
    "id", "tipo", "destino", "origem", "arquivo", "revisao", "tamanho_aprox_gb",
    "licenca", "obrigatorio", "usado_por", "sha256", "notas",
})
CHAVES_OBRIGATORIAS = CHAVES - {"arquivo", "revisao"}

TIMEOUT_SOCKET = 30.0            # segundos por operacao de socket
TIMEOUT_OLLAMA = 6 * 3600.0      # um pull grande pode demorar; ainda assim tem teto
TENTATIVAS_PADRAO = 4
PAUSA_PADRAO = 2.0               # backoff: pausa * 2**(n-1)
MAX_REDIRECIONAMENTOS = 5
BLOCO = 1024 * 1024
CODIGOS_TRANSITORIOS = frozenset({408, 425, 429, 500, 502, 503, 504})
CODIGOS_REDIRECIONAMENTO = frozenset({301, 302, 303, 307, 308})

_RE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,79}")
_RE_SHA256 = re.compile(r"[0-9a-f]{64}")
_RE_OLLAMA = re.compile(r"[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)?(?::[A-Za-z0-9._-]+)?")
_RE_HF_REPO = re.compile(r"[A-Za-z0-9._-]+/[A-Za-z0-9._-]+")
_RE_REVISAO = re.compile(r"[A-Za-z0-9._/-]{1,100}")
_RE_CONTENT_RANGE = re.compile(r"bytes (\d+)-\d+/(\d+|\*)")
MAX_META = 4096                  # o .part.meta e minusculo; acima disso e lixo


# ----------------------------------------------------------------- erros
class ErroModelo(Exception):
    """Falha esperada. A mensagem e segura para exibir: nunca contem segredos nem URLs com query."""

    codigo_saida = 1


class ErroManifesto(ErroModelo):
    """Manifesto invalido, id desconhecido ou destino fora da pasta base."""


class ErroSeguranca(ErroModelo):
    """URL ou redirecionamento recusado (nao https, credenciais embutidas, host invalido)."""


class ErroPendente(ErroModelo):
    """Entrada sem origem informada (PENDENTE). Nada e baixado."""


class ErroVerificacao(ErroModelo):
    """sha256 divergente do declarado no manifesto."""


class ErroDependencia(ErroModelo):
    """Ferramenta externa ausente (ollama) ou PyYAML nao instalado."""


class ErroRede(ErroModelo):
    codigo_saida = 2


class ErroEspaco(ErroModelo):
    codigo_saida = 2


class _Transitorio(Exception):
    """Falha de rede que vale nova tentativa (retomada a partir do .part)."""


# ----------------------------------------------------------------- modelo
@dataclass(frozen=True)
class Modelo:
    id: str
    tipo: str
    destino: str
    origem: str | None
    arquivo: str | None
    revisao: str
    tamanho_aprox_gb: float | None
    licenca_nome: str | None
    licenca_url: str | None
    obrigatorio: bool
    usado_por: str
    sha256: str | None
    notas: str

    @property
    def pendente(self) -> bool:
        return self.origem is None


@dataclass(frozen=True)
class Resultado:
    id: str
    status: str
    detalhe: str = ""


# ------------------------------------------------------------ validacao
def validar_destino(destino: Any, ctx: str = "destino") -> str:
    """Aceita so caminho relativo, sem '..', sem drive, sem ':' (ADS do NTFS)."""
    if not isinstance(destino, str) or not destino.strip():
        raise ErroManifesto(f"{ctx}: destino vazio")
    if any(c in destino for c in '\x00:*?"<>|'):
        raise ErroManifesto(f"{ctx}: destino contem caractere invalido")
    if (destino.startswith(("/", "\\")) or PurePosixPath(destino).is_absolute()
            or PureWindowsPath(destino).is_absolute() or PureWindowsPath(destino).drive):
        raise ErroManifesto(f"{ctx}: destino absoluto recusado ({destino!r}); use caminho relativo a pasta base")
    partes = [p for p in re.split(r"[\\/]+", destino) if p not in ("", ".")]
    if not partes:
        raise ErroManifesto(f"{ctx}: destino vazio")
    if ".." in partes:
        raise ErroManifesto(f"{ctx}: destino com '..' recusado (path traversal)")
    return "/".join(partes)


def validar_url_https(url: Any, erro: type[ErroModelo] = ErroSeguranca) -> None:
    """Somente https://, host presente, sem credenciais. Nao ecoa a URL (pode ter query)."""
    if not isinstance(url, str) or not url:
        raise erro("URL ausente ou invalida")
    if url.startswith("http://") or urlsplit(url).scheme.lower() == "http":
        raise erro("URL http:// recusada: somente https:// e permitido")
    try:
        partes = urlsplit(url)
        porta = partes.port  # noqa: F841 - levanta ValueError se a porta for invalida
        host = partes.hostname
    except ValueError as e:
        raise erro("URL com porta ou host invalido") from e
    if partes.scheme != "https" or not host:
        raise erro("URL recusada: precisa ser https:// com host valido")
    if "@" in partes.netloc:
        raise erro("URL com credenciais embutidas recusada")
    if any(c.isspace() for c in url):
        raise erro("URL com espaco em branco recusada")


def _validar_arquivo_hf(arquivo: str, ctx: str) -> None:
    if "\\" in arquivo or arquivo.startswith("/") or ":" in arquivo:
        raise ErroManifesto(f"{ctx}: 'arquivo' deve ser caminho relativo dentro do repositorio")
    if any(p in ("", ".", "..") for p in arquivo.split("/")):
        raise ErroManifesto(f"{ctx}: 'arquivo' com segmento vazio ou '..' recusado")


def _validar_origem(tipo: str, origem: Any, arquivo: Any, revisao: str, ctx: str):
    """Retorna (origem, arquivo) normalizados ou levanta ErroManifesto."""
    if origem is None:
        if arquivo is not None and not isinstance(arquivo, str):
            raise ErroManifesto(f"{ctx}: 'arquivo' deve ser texto")
        return None, arquivo
    if not isinstance(origem, str) or not origem.strip():
        raise ErroManifesto(f"{ctx}: 'origem' deve ser texto ou null")
    if tipo == "ollama":
        if arquivo is not None:
            raise ErroManifesto(f"{ctx}: 'arquivo' so se aplica a tipo huggingface")
        if not _RE_OLLAMA.fullmatch(origem) or any(p in (".", "..") for p in re.split(r"[/:]", origem)):
            raise ErroManifesto(f"{ctx}: origem Ollama invalida ({origem!r}); use 'nome:tag'")
        return origem, None
    if tipo == "huggingface":
        if not _RE_HF_REPO.fullmatch(origem):
            raise ErroManifesto(f"{ctx}: origem deve ser 'dono/repositorio' do Hugging Face (nao URL)")
        if not isinstance(arquivo, str):
            raise ErroManifesto(f"{ctx}: tipo huggingface exige 'arquivo' (caminho no repositorio)")
        _validar_arquivo_hf(arquivo, ctx)
        if not _RE_REVISAO.fullmatch(revisao) or ".." in revisao:
            raise ErroManifesto(f"{ctx}: 'revisao' invalida")
        return origem, arquivo
    # url e comfyui-node-asset: origem e uma URL https completa
    if arquivo is not None:
        raise ErroManifesto(f"{ctx}: 'arquivo' so se aplica a tipo huggingface")
    try:
        validar_url_https(origem, erro=ErroManifesto)
    except ErroManifesto as e:
        raise ErroManifesto(f"{ctx}: {e}") from None
    return origem, None


def _entrada(bruta: Any, n: int) -> Modelo:
    if not isinstance(bruta, dict):
        raise ErroManifesto(f"entrada #{n}: deve ser um mapa de campos")
    ident = bruta.get("id")
    ctx = f"modelo '{ident}'" if isinstance(ident, str) else f"entrada #{n}"
    desconhecidas = sorted(set(bruta) - CHAVES)
    if desconhecidas:
        raise ErroManifesto(f"{ctx}: chaves desconhecidas {desconhecidas} (typo?)")
    faltando = sorted(CHAVES_OBRIGATORIAS - set(bruta))
    if faltando:
        raise ErroManifesto(f"{ctx}: campos obrigatorios ausentes {faltando}")
    if not isinstance(ident, str) or not _RE_ID.fullmatch(ident):
        raise ErroManifesto(f"{ctx}: id invalido (minusculas, digitos, '.', '_', '-'; ate 80 caracteres)")
    tipo = bruta["tipo"]
    if tipo not in TIPOS:
        raise ErroManifesto(f"{ctx}: tipo invalido {tipo!r}; use um de {list(TIPOS)}")
    destino = validar_destino(bruta["destino"], ctx)
    revisao = bruta.get("revisao") or "main"
    if not isinstance(revisao, str):
        raise ErroManifesto(f"{ctx}: 'revisao' deve ser texto")
    origem, arquivo = _validar_origem(tipo, bruta["origem"], bruta.get("arquivo"), revisao, ctx)

    obrigatorio = bruta["obrigatorio"]
    if not isinstance(obrigatorio, bool):
        raise ErroManifesto(f"{ctx}: 'obrigatorio' deve ser true ou false")
    usado_por = bruta["usado_por"]
    if not isinstance(usado_por, str) or not usado_por.strip():
        raise ErroManifesto(f"{ctx}: 'usado_por' obrigatorio")
    notas = bruta["notas"]
    if not isinstance(notas, str):
        raise ErroManifesto(f"{ctx}: 'notas' deve ser texto")
    if origem is None and "PENDENTE" not in notas:
        raise ErroManifesto(f"{ctx}: origem null exige 'notas' com 'PENDENTE: informar origem'")

    sha = bruta["sha256"]
    if sha is not None:
        if not isinstance(sha, str) or not _RE_SHA256.fullmatch(sha):
            raise ErroManifesto(f"{ctx}: sha256 deve ter 64 hexadecimais minusculos (ou null)")
        if tipo == "ollama":
            raise ErroManifesto(f"{ctx}: sha256 nao se aplica a tipo ollama (o Ollama verifica os digests)")

    tamanho = bruta["tamanho_aprox_gb"]
    if tamanho is not None and (isinstance(tamanho, bool) or not isinstance(tamanho, (int, float)) or tamanho < 0):
        raise ErroManifesto(f"{ctx}: tamanho_aprox_gb deve ser numero positivo ou null")

    licenca = bruta["licenca"]
    if not isinstance(licenca, dict) or not set(licenca) <= {"nome", "url"}:
        raise ErroManifesto(f"{ctx}: 'licenca' deve ser um mapa com nome e/ou url")
    lic_nome = licenca.get("nome")
    lic_url = licenca.get("url")
    if lic_nome is not None and not isinstance(lic_nome, str):
        raise ErroManifesto(f"{ctx}: licenca.nome deve ser texto ou null")
    if lic_url is not None:
        try:
            validar_url_https(lic_url, erro=ErroManifesto)
        except ErroManifesto as e:
            raise ErroManifesto(f"{ctx}: licenca.url {e}") from None

    return Modelo(
        id=ident, tipo=tipo, destino=destino, origem=origem, arquivo=arquivo,
        revisao=revisao, tamanho_aprox_gb=None if tamanho is None else float(tamanho),
        licenca_nome=lic_nome, licenca_url=lic_url, obrigatorio=obrigatorio,
        usado_por=usado_por, sha256=sha, notas=notas,
    )


def carregar_manifesto(caminho: Path | str | None = None) -> list[Modelo]:
    """Le e valida config/modelos.yaml. Qualquer problema vira ErroManifesto (fail closed)."""
    if yaml is None:
        raise ErroDependencia("PyYAML nao instalado (pip install pyyaml)")
    caminho = Path(caminho) if caminho is not None else MANIFESTO_PADRAO
    try:
        texto = caminho.read_text(encoding="utf-8")
    except OSError as e:
        raise ErroManifesto(f"nao foi possivel ler o manifesto ({e.strerror})") from None
    try:
        dados = yaml.safe_load(texto)
    except yaml.YAMLError as e:
        raise ErroManifesto(f"YAML invalido em {caminho.name}: {type(e).__name__}") from None
    if not isinstance(dados, dict) or dados.get("versao") != 1:
        raise ErroManifesto("manifesto precisa de 'versao: 1' no topo")
    brutas = dados.get("modelos")
    if not isinstance(brutas, list) or not brutas:
        raise ErroManifesto("'modelos' deve ser uma lista nao vazia")
    modelos: list[Modelo] = []
    vistos: set[str] = set()
    for n, bruta in enumerate(brutas, start=1):
        m = _entrada(bruta, n)
        if m.id in vistos:
            raise ErroManifesto(f"id duplicado: {m.id!r}")
        vistos.add(m.id)
        modelos.append(m)
    return modelos


# ------------------------------------------------------------- caminhos
def resolver_base(base: Path | str | None = None) -> Path:
    """Pasta base: argumento, depois TUDOIA_MODELOS_DIR, depois <repo>/modelos."""
    if base is None:
        base = os.environ.get(VAR_BASE, "").strip() or BASE_PADRAO
    return Path(base).expanduser().resolve()


def caminho_local(m: Modelo, base: Path | str) -> Path:
    """Destino final de um modelo. Recusa qualquer caminho que saia da pasta base."""
    base_r = Path(base).resolve()
    if m.tipo == "comfyui-node-asset" and "/ComfyUI/models/" in m.destino:
        valor_comfy = os.environ.get(VAR_COMFYUI, "").strip() or _valor_arquivo_env(VAR_COMFYUI)
        if valor_comfy:
            sufixo = m.destino.split("/ComfyUI/models/", 1)[1]
            alvo_c = (Path(valor_comfy).expanduser().resolve() / "ComfyUI" / "models" / sufixo).resolve()
            if alvo_c != base_r and base_r in alvo_c.parents:
                return alvo_c
    alvo = (base_r / m.destino).resolve()
    if alvo == base_r or base_r not in alvo.parents:
        raise ErroSeguranca(f"{m.id}: destino sai da pasta base")
    return alvo


def _manifesto_ollama(origem: str, store: Path) -> Path:
    nome, _, tag = origem.partition(":")
    partes = nome.split("/") if "/" in nome else ["library", nome]
    return store.joinpath("manifests", "registry.ollama.ai", *partes, tag or "latest")


def _valor_arquivo_env(chave: str) -> str:
    """Ultima linha CHAVE=valor do .env da raiz (sem aspas). So le a chave pedida; nada e logado."""
    try:
        linhas = ARQUIVO_ENV.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return ""
    valor = ""
    for linha in linhas:
        nome, sep, resto = linha.strip().partition("=")
        if sep and nome.strip() == chave:
            valor = resto.strip()
            if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
                valor = valor[1:-1].strip()
    return valor


def pasta_ollama(m: Modelo, base: Path | str) -> Path:
    """Onde o servidor Ollama grava os pesos: TUDOIA_OLLAMA_MODELS (ambiente, depois .env), a mesma regra do
    tudoia.ps1/sh e do painel (caminhos.pesos_ollama); sem ela, <base>/<destino>."""
    valor = os.environ.get(VAR_OLLAMA, "").strip() or _valor_arquivo_env(VAR_OLLAMA)
    return Path(valor).expanduser() if valor else caminho_local(m, base)


def _presente(m: Modelo, base: Path | str) -> bool:
    if m.tipo == "ollama":
        return m.origem is not None and _manifesto_ollama(m.origem, pasta_ollama(m, base)).is_file()
    return caminho_local(m, base).is_file()


def status_modelo(m: Modelo, base: Path | str) -> str:
    if _presente(m, base):
        return "presente"
    return "pendente-origem" if m.pendente else "ausente"


def status_modelos(modelos: list[Modelo], base: Path | str) -> list[dict[str, Any]]:
    """Status sem hashear nada: so existencia do arquivo (ou do manifesto Ollama)."""
    return [
        {
            "id": m.id, "tipo": m.tipo, "status": status_modelo(m, base),
            "destino": m.destino, "obrigatorio": m.obrigatorio,
            "tamanho_aprox_gb": m.tamanho_aprox_gb,
        }
        for m in modelos
    ]


def selecionar_modelos(modelos: list[Modelo], ids: list[str] | None = None,
                       *, obrigatorios: bool = False) -> list[Modelo]:
    por_id = {m.id: m for m in modelos}
    escolhidos: dict[str, Modelo] = {}
    for ident in ids or []:
        if ident not in por_id:
            raise ErroManifesto(f"id desconhecido {ident!r}; use --listar para ver os ids")
        escolhidos[ident] = por_id[ident]
    if obrigatorios:
        for m in modelos:
            if m.obrigatorio:
                escolhidos.setdefault(m.id, m)
    return list(escolhidos.values())


def _sha256_arquivo(caminho: Path) -> str:
    digest = hashlib.sha256()
    with open(caminho, "rb") as arq:
        for bloco in iter(lambda: arq.read(BLOCO), b""):
            digest.update(bloco)
    return digest.hexdigest()


# ------------------------------------------------------------ verificacao
def verificar_modelo(m: Modelo, base: Path | str) -> Resultado:
    if not _presente(m, base):
        return Resultado(m.id, "pendente-origem" if m.pendente else "ausente", "nao esta no disco")
    if m.tipo == "ollama":
        return Resultado(m.id, "ollama-ok", "manifesto presente; o Ollama verifica os digests no pull")
    if m.sha256 is None:
        return Resultado(m.id, "sem-sha256", "presente; sha256 nao declarado (integridade nao verificada)")
    if _sha256_arquivo(caminho_local(m, base)) == m.sha256:
        return Resultado(m.id, "verificado", "sha256 confere")
    return Resultado(m.id, "divergente",
                     "sha256 diferente do manifesto; apague o arquivo e baixe de novo")


# -------------------------------------------------------------- download
def montar_url(m: Modelo) -> str:
    if m.tipo == "huggingface":
        url = (f"https://huggingface.co/{m.origem}/resolve/"
               f"{quote(m.revisao, safe='/')}/{quote(m.arquivo or '', safe='/')}")
    else:
        url = m.origem or ""
    validar_url_https(url)
    return url


def _token_hf() -> str | None:
    """Unica fonte do token: variavel de ambiente HF_TOKEN. Nunca logado."""
    return os.environ.get(VAR_TOKEN, "").strip() or None


def _host_recebe_token(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return host == "huggingface.co" or host.endswith(".huggingface.co")


class _SemRedirecionamentoAutomatico(urllib.request.HTTPRedirectHandler):
    """urllib copia o cabecalho Authorization para qualquer host no redirecionamento.
    Por isso os saltos sao refeitos por _abrir, que valida https e o host do token."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None


def _abridor(contexto: ssl.SSLContext | None) -> urllib.request.OpenerDirector:
    ctx = contexto if contexto is not None else ssl.create_default_context()
    return urllib.request.build_opener(_SemRedirecionamentoAutomatico,
                                       urllib.request.HTTPSHandler(context=ctx))


def _abrir(url: str, cabecalhos: dict[str, str], token: str | None,
           contexto: ssl.SSLContext | None, timeout: float):
    atual = url
    for _ in range(MAX_REDIRECIONAMENTOS + 1):
        validar_url_https(atual)
        cab = {"User-Agent": "TudoIA-baixar-modelos/1", "Accept-Encoding": "identity", **cabecalhos}
        if token and _host_recebe_token(atual):
            cab["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(atual, headers=cab, method="GET")
        try:
            return _abridor(contexto).open(req, timeout=timeout)
        except urllib.error.HTTPError as e:
            if e.code not in CODIGOS_REDIRECIONAMENTO:
                raise
            destino = e.headers.get("Location")
            e.close()
            if not destino:
                raise ErroRede("redirecionamento sem cabecalho Location") from None
            atual = urljoin(atual, destino)
    raise ErroRede(f"redirecionamentos demais (limite {MAX_REDIRECIONAMENTOS})")


def _motivo(e: BaseException) -> str:
    razao = getattr(e, "reason", None) or e
    return type(razao).__name__


def _erro_http(codigo: int) -> ErroRede:
    if codigo in (401, 403):
        return ErroRede(f"acesso negado (HTTP {codigo}). Modelos com licenca aceita no Hugging Face "
                        "exigem HF_TOKEN valido na variavel de ambiente e a licenca aceita na conta.")
    if codigo == 404:
        return ErroRede("arquivo nao encontrado no servidor (HTTP 404); confira origem/arquivo no manifesto")
    return ErroRede(f"o servidor respondeu HTTP {codigo}")


def _total_esperado(resposta, status: int) -> int | None:
    if status == 206:
        m = _RE_CONTENT_RANGE.fullmatch(resposta.headers.get("Content-Range", "").strip())
        return int(m.group(2)) if m and m.group(2) != "*" else None
    cl = resposta.headers.get("Content-Length", "")
    return int(cl) if cl.isdigit() else None


# ---- versao do arquivo no servidor (ETag/Last-Modified), guardada ao lado do .part em x.bin.part.meta
def _arquivo_meta(parcial: Path) -> Path:
    return parcial.with_name(parcial.name + ".meta")


def _descartar_parcial(parcial: Path) -> None:
    parcial.unlink(missing_ok=True)
    _arquivo_meta(parcial).unlink(missing_ok=True)


def _id_url(url: str) -> str:
    """Hash da URL: o .meta nao guarda a URL em si (pode ter query)."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def _cabecalho_seguro(valor: Any) -> str | None:
    """ETag/Last-Modified voltam num cabecalho If-Range: so texto curto e imprimivel."""
    if not isinstance(valor, str) or len(valor) > 512 or not valor.isprintable():
        return None
    return valor.strip() or None


def _validador_if_range(resposta) -> str | None:
    """ETag forte, senao Last-Modified. ETag fraca (W/) nao vale em If-Range (RFC 9110, secao 13.1.5)."""
    etag = _cabecalho_seguro(resposta.headers.get("ETag"))
    if etag and not etag.startswith("W/"):
        return etag
    return _cabecalho_seguro(resposta.headers.get("Last-Modified"))


def _gravar_meta(parcial: Path, url: str, validador: str | None) -> None:
    parcial.parent.mkdir(parents=True, exist_ok=True)
    _arquivo_meta(parcial).write_text(json.dumps({"url_sha256": _id_url(url), "if_range": validador}),
                                      encoding="utf-8")


def _ler_meta(parcial: Path, url: str) -> str | None:
    """Validador salvo para ESTA URL, ou None (sem .meta, .meta de outra URL, corrompido ou sem validador)."""
    try:
        with open(_arquivo_meta(parcial), "rb") as arq:
            dados = json.loads(arq.read(MAX_META))
    except (OSError, ValueError):
        return None
    if not isinstance(dados, dict) or dados.get("url_sha256") != _id_url(url):
        return None
    return _cabecalho_seguro(dados.get("if_range"))


def _transferir(url: str, parcial: Path, contexto, timeout: float, sha: str | None = None) -> bool:
    """Uma tentativa. Retoma do .part com Range + If-Range; qualquer falha transitoria vira _Transitorio.

    Retorna True quando o sha256 esperado ja foi conferido aqui (resposta sem tamanho declarado)."""
    inicio = parcial.stat().st_size if parcial.is_file() else 0
    validador = _ler_meta(parcial, url) if inicio else None
    if inicio and validador is None and sha is None:
        # Sem validador nao da para provar que o .part e da mesma versao do arquivo, e sem sha256 nada pegaria
        # no fim uma juncao de versoes diferentes: recomeca do zero.
        _descartar_parcial(parcial)
        inicio = 0
    cabecalhos: dict[str, str] = {}
    if inicio:
        cabecalhos["Range"] = f"bytes={inicio}-"
        if validador:
            cabecalhos["If-Range"] = validador  # se a versao mudou, o servidor responde 200 com o arquivo novo
    try:
        resposta = _abrir(url, cabecalhos, _token_hf(), contexto, timeout)
    except urllib.error.HTTPError as e:
        codigo = e.code
        e.close()  # libera o socket da resposta de erro antes de decidir
        if codigo == 416 and inicio:
            _descartar_parcial(parcial)
            raise _Transitorio("o servidor recusou a retomada; o parcial foi descartado") from None
        if codigo in CODIGOS_TRANSITORIOS:
            raise _Transitorio(f"HTTP {codigo}") from None
        raise _erro_http(codigo) from None
    except ssl.SSLCertVerificationError:
        raise ErroRede("certificado TLS nao confiavel; nada foi baixado") from None
    except (urllib.error.URLError, OSError, http.client.HTTPException) as e:
        raise _Transitorio(f"falha de rede ({_motivo(e)})") from None

    with resposta:
        status = getattr(resposta, "status", 200)
        if status == 206 and inicio:
            faixa = _RE_CONTENT_RANGE.fullmatch(resposta.headers.get("Content-Range", "").strip())
            if faixa is None or int(faixa.group(1)) != inicio:
                # A faixa nao comeca onde o .part termina: juntar daria um arquivo corrompido.
                _descartar_parcial(parcial)
                raise _Transitorio("o servidor devolveu uma faixa que nao continua o parcial; recomecando do zero")
            modo = "ab"
        elif status == 200:
            # 200 numa retomada: o servidor ignorou o Range ou o If-Range nao bateu (arquivo mudou). Do zero.
            modo, inicio = "wb", 0
            _gravar_meta(parcial, url, _validador_if_range(resposta))
        else:
            raise ErroRede(f"resposta inesperada do servidor (HTTP {status})")
        total = _total_esperado(resposta, status)
        parcial.parent.mkdir(parents=True, exist_ok=True)
        with open(parcial, modo) as arq:
            while True:
                try:
                    bloco = resposta.read(BLOCO)
                except (OSError, http.client.HTTPException) as e:
                    raise _Transitorio(f"conexao interrompida ({_motivo(e)})") from None
                if not bloco:
                    break
                arq.write(bloco)
    tamanho = parcial.stat().st_size
    if total is not None:
        if tamanho != total:
            raise _Transitorio(f"download incompleto ({tamanho} de {total} bytes)")
        return False
    # Sem tamanho declarado (sem Content-Length, ex.: chunked): o fim da conexao nao prova que veio tudo.
    if sha is None:
        raise ErroRede("o servidor nao informou o tamanho do arquivo e o manifesto nao tem sha256: nao da para "
                       "confirmar que o download esta completo. Declare o sha256 no manifesto e rode de novo.")
    if _sha256_arquivo(parcial) != sha:
        raise _Transitorio(f"download sem tamanho declarado e o sha256 ainda nao confere ({tamanho} bytes)")
    return True


def _baixar_com_retomada(url: str, parcial: Path, alvo: Path, sha: str | None, *,
                         contexto, timeout: float, tentativas: int, pausa: float) -> None:
    sha_conferido = False
    for n in range(1, tentativas + 1):
        try:
            sha_conferido = _transferir(url, parcial, contexto, timeout, sha)
            break
        except _Transitorio as e:
            if n == tentativas:
                raise ErroRede(f"falha apos {tentativas} tentativas: {e}") from None
            espera = pausa * 2 ** (n - 1)
            _avisar(f"  tentativa {n} falhou ({e}); nova tentativa em {espera:.0f} s")
            time.sleep(espera)
    if sha is not None and not sha_conferido:
        digest = _sha256_arquivo(parcial)
        if digest != sha:
            _descartar_parcial(parcial)
            raise ErroVerificacao(f"sha256 divergente em {alvo.name} (esperado {sha[:12]}..., "
                                  f"obtido {digest[:12]}...); arquivo descartado")
    os.replace(parcial, alvo)  # atomico: o nome final so aparece com conteudo completo
    _arquivo_meta(parcial).unlink(missing_ok=True)


@contextmanager
def _trava(parcial: Path) -> Iterator[None]:
    """Impede dois downloads simultaneos no mesmo .part (corromperiam o arquivo)."""
    lock = parcial.with_name(parcial.name + ".lock")
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as e:
        raise ErroModelo(f"outro download de {parcial.name} parece estar em andamento ({lock.name} "
                         "existe). Se nenhum download estiver rodando, apague esse arquivo.") from e
    os.close(fd)
    try:
        yield
    finally:
        lock.unlink(missing_ok=True)


def _checar_espaco(alvo: Path, tamanho_gb: float | None, ja_baixado: int) -> None:
    if tamanho_gb is None:
        return
    pasta = alvo.parent
    while not pasta.exists() and pasta != pasta.parent:
        pasta = pasta.parent
    livre = shutil.disk_usage(pasta).free
    falta = int(tamanho_gb * 1024**3) - ja_baixado
    if falta > livre:
        raise ErroEspaco(f"espaco livre insuficiente em {pasta}: faltam ~{falta / 1024**3:.1f} GB, "
                         f"ha {livre / 1024**3:.1f} GB livres")


def _baixar_ollama(m: Modelo, base: Path) -> str:
    if m.origem is None:  # defensivo; baixar_modelo ja barra antes
        raise ErroPendente(f"{m.id}: origem nao informada")
    binario = shutil.which("ollama")
    if binario is None:
        raise ErroDependencia(f"'ollama' nao encontrado no PATH. Instale o Ollama e rode: ollama pull {m.origem}")
    # O pull e enviado ao servidor Ollama, que grava em SEU OLLAMA_MODELS (tudoia.ps1/sh: TUDOIA_OLLAMA_MODELS do
    # .env, senao modelos/ollama/models). pasta_ollama segue a mesma regra para checar a presenca.
    try:
        r = subprocess.run([binario, "pull", m.origem], timeout=TIMEOUT_OLLAMA, check=False)
    except subprocess.TimeoutExpired:
        raise ErroRede(f"'ollama pull {m.origem}' excedeu o tempo limite") from None
    except OSError as e:
        raise ErroRede(f"nao foi possivel executar o ollama ({e.strerror})") from None
    if r.returncode != 0:
        raise ErroRede(f"'ollama pull {m.origem}' terminou com codigo {r.returncode}; "
                       "confira se o servidor Ollama esta ativo (ollama serve)")
    return "ollama"


def baixar_modelo(m: Modelo, base_dir: Path | str | None = None, *,
                  contexto_ssl: ssl.SSLContext | None = None, timeout: float | None = None,
                  tentativas: int | None = None, pausa: float | None = None) -> str:
    """Baixa um modelo. Retorna 'ja-presente', 'baixado' ou 'ollama'. Levanta ErroModelo."""
    timeout = TIMEOUT_SOCKET if timeout is None else timeout
    tentativas = TENTATIVAS_PADRAO if tentativas is None else tentativas
    pausa = PAUSA_PADRAO if pausa is None else pausa
    if m.pendente:
        raise ErroPendente(f"{m.id}: origem nao informada no manifesto (PENDENTE). Nada foi baixado.")
    base = resolver_base(base_dir)
    if m.tipo == "ollama":
        # ja presente: nao chama 'ollama pull' (ele consultaria o registro e poderia trazer outra versao)
        return "ja-presente" if _presente(m, base) else _baixar_ollama(m, base)
    alvo = caminho_local(m, base)
    url = montar_url(m)
    if alvo.is_file() and (m.sha256 is None or _sha256_arquivo(alvo) == m.sha256):
        return "ja-presente"
    parcial = alvo.with_name(alvo.name + ".part")
    ja_baixado = parcial.stat().st_size if parcial.is_file() else 0
    _checar_espaco(alvo, m.tamanho_aprox_gb, ja_baixado)
    alvo.parent.mkdir(parents=True, exist_ok=True)
    with _trava(parcial):
        _baixar_com_retomada(url, parcial, alvo, m.sha256, contexto=contexto_ssl,
                             timeout=timeout, tentativas=tentativas, pausa=pausa)
    return "baixado"


# ------------------------------------------------------------------ CLI
def _avisar(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _tabela(modelos: list[Modelo], base: Path) -> None:
    cab = ("STATUS", "ID", "TIPO", "GB", "OBRIG", "DESTINO")
    linhas = [
        (status_modelo(m, base), m.id, m.tipo,
         "-" if m.tamanho_aprox_gb is None else f"{m.tamanho_aprox_gb:.1f}",
         "sim" if m.obrigatorio else "nao", m.destino)
        for m in modelos
    ]
    larguras = [max(len(str(c)) for c in col) for col in zip(cab, *linhas, strict=True)]

    def fmt(linha):
        return "  ".join(str(v).ljust(w) for v, w in zip(linha, larguras, strict=True))

    print(fmt(cab))
    print(fmt(tuple("-" * w for w in larguras)))
    for linha in linhas:
        print(fmt(linha))
    contagem: dict[str, int] = {}
    for linha in linhas:
        contagem[linha[0]] = contagem.get(linha[0], 0) + 1
    print("\nresumo: " + ", ".join(f"{k}={v}" for k, v in sorted(contagem.items())))


def _cmd_baixar(selecionados: list[Modelo], base: Path, contexto=None) -> int:
    codigo = 0
    for m in selecionados:
        try:
            resultado = baixar_modelo(m, base, contexto_ssl=contexto)
            print(f"[{resultado}] {m.id}")
            if resultado == "baixado" and m.sha256 is None:
                print("  aviso: sem sha256 declarado; integridade verificada so pelo tamanho")
        except ErroModelo as e:
            _avisar(f"[falha] {m.id}: {e}")
            codigo = max(codigo, e.codigo_saida)
    return codigo


def _cmd_verificar(selecionados: list[Modelo], base: Path) -> int:
    codigo = 0
    for m in selecionados:
        r = verificar_modelo(m, base)
        print(f"[{r.status}] {r.id}: {r.detalhe}")
        if r.status in ("divergente", "ausente"):
            codigo = 1
    return codigo


def main(argv: list[str] | None = None) -> int:
    for fluxo in (sys.stdout, sys.stderr):
        if hasattr(fluxo, "reconfigure"):
            fluxo.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="Modelos de IA do TudoIA: listar, baixar, verificar.")
    parser.add_argument("--listar", action="store_true", help="tabela com status de cada modelo")
    parser.add_argument("--verificar", action="store_true",
                        help="confere sha256 quando declarado; senao so a presenca (sem ids: todos)")
    parser.add_argument("--modelo", nargs="+", metavar="ID", help="um ou mais ids do manifesto")
    parser.add_argument("--obrigatorios", action="store_true", help="todos os marcados obrigatorio: true")
    parser.add_argument("--base-dir", type=Path, default=None,
                        help=f"pasta base (padrao: ${VAR_BASE} ou {BASE_PADRAO})")
    parser.add_argument("--manifesto", type=Path, default=MANIFESTO_PADRAO, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if not (args.listar or args.verificar or args.modelo or args.obrigatorios):
        parser.print_usage(sys.stderr)
        _avisar("erro: informe --listar, --verificar, --modelo ID ou --obrigatorios")
        return 1
    try:
        modelos = carregar_manifesto(args.manifesto)
        base = resolver_base(args.base_dir)
        if args.listar:
            _tabela(modelos, base)
            return 0
        if args.verificar and not (args.modelo or args.obrigatorios):
            selecionados = modelos
        else:
            selecionados = selecionar_modelos(modelos, args.modelo, obrigatorios=args.obrigatorios)
        if args.verificar:
            return _cmd_verificar(selecionados, base)
        if not selecionados:
            print("nenhum modelo selecionado")
            return 0
        return _cmd_baixar(selecionados, base)
    except ErroModelo as e:
        _avisar(f"erro: {e}")
        return e.codigo_saida


if __name__ == "__main__":
    sys.exit(main())

"""Gera o pacote de código do instalador (payload.zip): o TudoIA sem nada desta máquina.

Lista de permissão por pasta: só entra o que está em INCLUIR. Dados, modelos, `.env`, ambientes virtuais, caches,
memórias de agentes e o config gerado do LiteLLM nunca entram. A seguir, `verificar_conteudo` varre o resultado atrás
de segredos e de dados pessoais; qualquer achado reprova o pacote.
"""
from __future__ import annotations

import fnmatch
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
SAIDA = RAIZ / "instalador" / "dados"

# Pastas e arquivos da raiz que fazem parte do produto.
INCLUIR = (".env.example", ".gitattributes", ".gitignore", ".python-version", "LICENSE", "NOTICE", "README.md", "SPEC.md",
           "AGENTS.md", "pyproject.toml", "uv.lock", ".github", "automacao", "config", "docs", "governanca", "infra",
           "instalador", "painel", "runtime", "scripts", "tests")
# Padrões (fnmatch, sobre o caminho relativo em "/") que nunca entram, em qualquer profundidade.
EXCLUIR = ("*/__pycache__/*", "__pycache__/*", "*.pyc", "*/.pytest_cache/*", "*/.ruff_cache/*", "*/.venv/*",
           "*/node_modules/*", "*.bak", "*.tmp", "*.log", "*.db", "*.sqlite", "*.sqlite3", "*.pem", "*.key",
           "runtime/litellm/config.yaml", "runtime/litellm/config.yaml.*", "instalador/dados/*", "build/*", "dist/*",
           "*/.serena/*", "*/.claude/*", "*/.cursor/*", "*/.codex/*", "*/.gemini/*", "*.egg-info/*",
           "dados/*", "*/dados/*", "modelos/*", "*/modelos/*", ".aider*", "*/.aider*")
EXCLUIR_NOMES = {".env", "auditoria.jsonl", "cerebro.db", "estado.json", "dados", "modelos"}
TIMESTAMP_FIXO = (1980, 1, 1, 0, 0, 0)   # zip reproduzível: mesmo código = mesmo sha256


def _excluido(rel: str) -> bool:
    nome = rel.rsplit("/", 1)[-1]
    if nome in EXCLUIR_NOMES or (nome.startswith(".env") and nome != ".env.example"):
        return True
    return any(fnmatch.fnmatch(rel, p) for p in EXCLUIR)


# Variáveis que `tudoia segredos` gera sozinho na instalação: o MCP que só depende delas pode vir ligado.
GERADAS_PELO_INSTALADOR = {"CEREBRO_TOKEN_ESTATICO", "DOUTRINA_TEC", "TUDOIA_PYTHON"}
_VARIAVEL_OBRIGATORIA = re.compile(r"\$\{([A-Z][A-Z0-9_]*)\}")


def governanca_padrao(governanca_json: bytes, mcp_json: bytes) -> bytes:
    """governanca.json de uma instalação nova: sem as instâncias e pastas desta máquina e só com os MCP que não pedem
    chave. O `sync` falha de propósito quando um MCP ligado precisa de variável ausente no .env; numa máquina nova o
    usuário liga os demais no painel, depois de informar as chaves."""
    cfg = json.loads(governanca_json)
    catalogo = json.loads(mcp_json).get("mcpServers", {})
    def exige_chave(mcp: dict) -> bool:
        return any(v not in GERADAS_PELO_INSTALADOR for v in _VARIAVEL_OBRIGATORIA.findall(json.dumps(mcp)))

    sem_chave = [m for m in cfg.get("mcp", []) if m in catalogo and not exige_chave(catalogo[m])]
    cfg.update({"mcp": sem_chave, "workspaces": [], "instancias": []})
    return (json.dumps(cfg, indent=2, ensure_ascii=False) + chr(10)).encode("utf-8")


def listar_arquivos(raiz: Path = RAIZ) -> list[str]:
    achados: list[str] = []
    for item in INCLUIR:
        base = raiz / item
        if base.is_file():
            achados.append(item)
        elif base.is_dir():
            for dirpath, dirnames, filenames in os.walk(base):
                dirnames[:] = [d for d in dirnames if not _excluido(f"{Path(dirpath, d).relative_to(raiz).as_posix()}/x")]
                for f in filenames:
                    rel = Path(dirpath, f).relative_to(raiz).as_posix()
                    if not _excluido(rel) and not Path(dirpath, f).is_symlink():
                        achados.append(rel)
    return sorted(set(achados))


def _versao(raiz: Path) -> str:
    m = re.search(r'^version\s*=\s*"([^"]+)"', (raiz / "pyproject.toml").read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else "0"


def _commit(raiz: Path) -> str:
    try:
        r = subprocess.run(["git", "-C", str(raiz), "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


# ───────────────────────────── Doutrina TEC embutida
# O pacote leva um instantâneo da Doutrina em `doutrina/`, na versão (SHA) fixada em governanca/doutrina.json. Sem ele a skill
# `doutrina-tec`, o MCP `doutrina-tec` e a SquadTI falham fechado (ECO-CON-01). O que entra: o que o consumo por IA lê.
PASTA_DOUTRINA = "doutrina"
DOUTRINA_INCLUIR = ("gerado", "familias", "INDEX.md", "llms.txt", "VERSION", "LICENSE", "NOTICE", "tools/mcp_doutrina.py")
_RE_SHA = re.compile(r"[0-9a-f]{40}")
_RE_REPO = re.compile(r"(?!\.+/)[A-Za-z0-9_.\-]+/(?!\.+$)[A-Za-z0-9_.\-]+")   # dono/nome; "." e ".." não são nome
_TEXTO_DOUTRINA = (".md", ".json", ".txt", ".py")


class ErroDoutrina(RuntimeError):
    """Doutrina ausente, fora da versão fixada ou incompleta: o pacote não deve ser gerado."""


def ler_pin(raiz: Path = RAIZ) -> dict:
    """governanca/doutrina.json: repositório e SHA completo. SHA curto ou ref móvel (main) não vale: o pacote precisa ser reprodutível."""
    try:
        pin = json.loads((raiz / "governanca" / "doutrina.json").read_text(encoding="utf-8"))
        sha, repo = pin["sha"], pin["repositorio"]
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise ErroDoutrina(f"governanca/doutrina.json ausente ou inválido: {e}") from e
    if not (isinstance(sha, str) and _RE_SHA.fullmatch(sha) and isinstance(repo, str) and _RE_REPO.fullmatch(repo)):
        raise ErroDoutrina("governanca/doutrina.json: use 'repositorio' (dono/nome) e 'sha' com os 40 caracteres do commit")
    return {"repositorio": repo, "sha": sha}


# Onde o SHA de governanca/doutrina.json é repetido porque o Docker não lê JSON. O JSON manda; estes são derivados dele.
PIN_DERIVADOS = (("runtime/squadti/Dockerfile", re.compile(r"(?m)^(ARG DOUTRINA_SHA=)\w+(?=\r?$)")),
                 ("runtime/docker-compose.yml", re.compile(r"(DOUTRINA_SHA: \$\{SQUADTI_DOUTRINA_SHA:-)\w+(\})")))


def ultimo_commit(repo: str, executar=subprocess.run) -> str:
    """SHA completo do commit mais novo do ramo padrão de `repo` no GitHub (git ls-remote). Falha fechado: nunca devolve ref móvel."""
    if not _RE_REPO.fullmatch(repo):
        raise ErroDoutrina(f"repositório inválido: {repo!r}")
    try:
        r = executar(["git", "ls-remote", f"https://github.com/{repo}.git", "HEAD"], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        raise ErroDoutrina(f"não consegui consultar {repo} no GitHub: {e}") from e
    sha = (r.stdout.split() or [""])[0]
    if r.returncode != 0 or not _RE_SHA.fullmatch(sha):
        raise ErroDoutrina(f"não consegui obter o commit mais novo de {repo}: {(r.stderr or r.stdout).strip()[:200]}")
    return sha


def atualizar_pin(raiz: Path = RAIZ, executar=subprocess.run) -> tuple[str, str]:
    """Busca o commit mais novo da Doutrina, grava em governanca/doutrina.json e devolve (sha_antigo, sha_novo)."""
    pin = ler_pin(raiz)
    novo = ultimo_commit(pin["repositorio"], executar)
    if novo != pin["sha"]:
        texto = json.dumps({"repositorio": pin["repositorio"], "sha": novo}, indent=2) + chr(10)
        (raiz / "governanca" / "doutrina.json").write_bytes(texto.encode("utf-8"))
    return pin["sha"], novo


def buscar_no_clone(clone: Path, sha: str, executar=subprocess.run) -> None:
    """Garante que o commit está no clone local (git fetch), para o empacotador lê-lo do histórico."""
    try:
        r = executar(["git", "-C", str(clone), "fetch", "-q", "origin"], capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.SubprocessError) as e:
        raise ErroDoutrina(f"não consegui rodar git fetch em {clone}: {e}") from e
    if r.returncode != 0:
        raise ErroDoutrina(f"git fetch falhou em {clone}: {(r.stderr or '').strip()[:200]}")


def sincronizar_pin(raiz: Path = RAIZ, aplicar: bool = False) -> list[str]:
    """Arquivos cujo SHA da Doutrina difere do JSON (e, com `aplicar`, já corrigidos). Alvo sem exatamente uma ocorrência falha."""
    sha = ler_pin(raiz)["sha"]
    divergentes: list[str] = []
    gravacoes: list[tuple[Path, bytes]] = []   # só grava depois de validar todos os alvos: nada fica pela metade
    for rel, padrao in PIN_DERIVADOS:
        caminho = raiz / rel
        try:
            texto = caminho.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError) as e:
            raise ErroDoutrina(f"{rel}: não consegui ler: {e}") from e
        achados = padrao.findall(texto)
        if len(achados) != 1:
            raise ErroDoutrina(f"{rel}: esperava exatamente uma ocorrência do SHA da Doutrina, achei {len(achados)}")
        novo = padrao.sub(lambda m: m.group(1) + sha + (m.group(2) if m.lastindex == 2 else ""), texto)
        if novo != texto:
            divergentes.append(rel)
            gravacoes.append((caminho, novo.encode("utf-8")))   # bytes: mantém o fim de linha do arquivo
    if aplicar:
        for caminho, dados in gravacoes:
            caminho.write_bytes(dados)
    return divergentes


def instantaneo_doutrina(clone: Path, sha: str) -> dict[str, bytes]:
    """Arquivos da Doutrina no commit `sha`, lidos do histórico git do clone (não da pasta de trabalho: edição local não entra)."""
    cmd = ["git", "-C", str(clone), "archive", "--format=tar", sha, "--", *DOUTRINA_INCLUIR]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as e:
        raise ErroDoutrina(f"não consegui rodar o git em {clone}: {e}") from e
    if r.returncode != 0:
        raise ErroDoutrina(f"não consegui ler {sha[:12]} de {clone} (o commit existe? rode `git fetch` lá; os caminhos esperados existem nele?): "
                            f"{r.stderr.decode(errors='replace').strip()[:200]}")
    arquivos: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(r.stdout)) as t:
        for m in t.getmembers():
            if not m.isfile():
                continue
            if m.name.startswith(("/", "../")) or ".." in m.name.split("/"):
                raise ErroDoutrina(f"caminho perigoso no instantâneo da Doutrina: {m.name!r}")
            dados = t.extractfile(m).read()
            if m.name.endswith(_TEXTO_DOUTRINA) or "." not in m.name.rsplit("/", 1)[-1]:
                dados = dados.replace(b"\r\n", b"\n")
            arquivos[m.name] = dados
    _conferir_doutrina(arquivos)
    return arquivos


def _conferir_doutrina(arquivos: dict[str, bytes]) -> dict:
    """Manifesto legível e todos os arquivos que ele lista presentes: instantâneo incompleto reprova o pacote."""
    try:
        man = json.loads(arquivos["gerado/manifesto.json"])
        listados, versao, hash_ = man["arquivos"], man["versao"], man["hash"]
    except (KeyError, ValueError, TypeError) as e:
        raise ErroDoutrina(f"instantâneo da Doutrina sem gerado/manifesto.json válido: {e!r}") from e
    faltam = [a for a in listados if a not in arquivos]
    if faltam or "tools/mcp_doutrina.py" not in arquivos:
        raise ErroDoutrina(f"instantâneo da Doutrina incompleto: faltam {(faltam + ['tools/mcp_doutrina.py'])[:5]}")
    return {"versao": versao, "hash": hash_}


def gerar(raiz: Path = RAIZ, saida: Path = SAIDA, doutrina: dict[str, bytes] | None = None, pin: dict | None = None) -> dict:
    arquivos = listar_arquivos(raiz)
    saida.mkdir(parents=True, exist_ok=True)
    zip_path = saida / "payload.zip"
    info_doutrina = {**(pin or {}), **_conferir_doutrina(doutrina)} if doutrina else None
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for rel, dados in sorted((doutrina or {}).items()):
            info = zipfile.ZipInfo(f"{PASTA_DOUTRINA}/{rel}", TIMESTAMP_FIXO)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, dados)
        for rel in arquivos:
            dados = (raiz / rel).read_bytes()
            if rel == "governanca/governanca.json":
                dados = governanca_padrao(dados, (raiz / "governanca" / "mcp.json").read_bytes())
            if rel.endswith((".py", ".md", ".yml", ".yaml", ".json", ".toml", ".js", ".css", ".html", ".sh", ".example", ".txt")):
                dados = dados.replace(b"\r\n", b"\n")   # o repositório é LF; o zip não depende de como o Windows gravou
            info = zipfile.ZipInfo(rel, TIMESTAMP_FIXO)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o644 if not rel.endswith(".sh") else 0o755) << 16
            if rel.endswith(".ps1") or rel.endswith(".cmd") or rel.endswith(".bat"):
                dados = dados.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")   # PowerShell e cmd do Windows: CRLF
            z.writestr(info, dados)
    h = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    manifesto = {"versao": _versao(raiz), "commit": _commit(raiz), "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "arquivos": len(arquivos) + len(doutrina or {}), "sha256": h}
    if info_doutrina:
        manifesto["doutrina"] = info_doutrina
    (saida / "payload.manifest.json").write_text(json.dumps(manifesto, indent=2), encoding="utf-8")
    return manifesto


# ───────────────────────────── verificação de conteúdo
SEGREDOS = {
    "chave sk-": re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}"),
    "chave gsk_": re.compile(r"\bgsk_[A-Za-z0-9]{20,}"),
    "chave nvapi-": re.compile(r"\bnvapi-[A-Za-z0-9_\-]{20,}"),
    "token GitHub": re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}"),
    "chave Google": re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}"),
    "token Slack": re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}"),
    "chave privada": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "JWT": re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),
    "AWS": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "senha em URL": re.compile(r"://[^/\s:@]+:[^/\s:@${}]{4,}@[A-Za-z0-9.\-]+"),
}


def _padroes_pessoais() -> dict[str, re.Pattern]:
    """Dados desta máquina: usuário e nome do computador do Windows, e os que o dono listar em PESSOAIS_EXTRA."""
    termos = {os.environ.get("USERNAME", ""), os.environ.get("COMPUTERNAME", ""), *filter(None, os.environ.get("PESSOAIS_EXTRA", "").split(","))}
    padroes = {f"dado pessoal '{t}'": re.compile(re.escape(t), re.I) for t in termos if len(t) >= 4}
    padroes["pasta de usuário do Windows"] = re.compile(r"(?i)\b[A-Z]:\\Users\\(?!Public\b|<|%|\$|\{|\.\.\.|usuario\b|seu|user\b)[A-Za-z0-9._\-]{2,}\\")
    padroes["e-mail pessoal"] = re.compile(r"[A-Za-z0-9._%+\-]+@(?:gmail|hotmail|outlook|yahoo|icloud)\.com", re.I)
    return padroes


# Termos que aparecem em documentação como exemplo e não são dado pessoal.
PERMITIDOS = ("noreply@anthropic.com",)
# Em tests/, valores de fixture com cara de falso (segredo-de-teste, user:senha@, 0000...) não contam como segredo.
MARCAS_DE_FIXTURE = ("teste", "secret", "senha", "user", "example", "0000", "123456", "fake", "falso", "fulano")


def _fixture(nome: str, achado: str) -> bool:
    return (nome.startswith("tests/") or "/tests/" in nome) and any(m in achado.lower() for m in MARCAS_DE_FIXTURE)
TEXTO = (".py", ".md", ".yml", ".yaml", ".json", ".toml", ".js", ".css", ".html", ".sh", ".ps1", ".cmd", ".txt", ".example",
         ".mdc", ".conf", ".ini", ".env", "")


def verificar_conteudo(zip_path: Path) -> list[str]:
    """Achados (arquivo: motivo). Vazio = o pacote está limpo."""
    achados: list[str] = []
    pessoais = _padroes_pessoais()
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            nome = info.filename
            if _excluido(nome) and not nome.startswith(PASTA_DOUTRINA + "/"):   # familias/dados/ da Doutrina não é a pasta de dados
                achados.append(f"{nome}: arquivo que nunca deveria entrar no pacote")
                continue
            if Path(nome).suffix.lower() not in TEXTO or info.file_size > 3 * 1024 * 1024:
                continue
            texto = z.read(info).decode("utf-8", errors="replace")
            for rotulo, padrao in {**SEGREDOS, **pessoais}.items():
                for m in padrao.finditer(texto):
                    if m.group(0) in PERMITIDOS or "exemplo" in m.group(0).lower():
                        continue
                    if _fixture(nome, texto[max(0, m.start() - 40):m.end() + 40]):
                        continue
                    linha = texto.count("\n", 0, m.start()) + 1
                    achados.append(f"{nome}:{linha}: {rotulo}")
                    break
    return achados


def principal(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv in (["--sincronizar-pin"], ["--derivar-pin"]):
        # --sincronizar-pin: busca o commit MAIS NOVO da Doutrina, grava no JSON e propaga. --derivar-pin: só propaga o JSON (sem rede).
        try:
            if argv == ["--sincronizar-pin"]:
                antigo, novo = atualizar_pin()
                clone = os.environ.get("DOUTRINA_TEC")
                if clone:
                    buscar_no_clone(Path(clone), novo)
                print(f"Doutrina: {antigo[:12]} -> {novo[:12]}" if antigo != novo else f"Doutrina: já no commit mais novo ({novo[:12]})")
            mudou = sincronizar_pin(aplicar=True)
        except ErroDoutrina as e:
            print(f"ERRO: {e}", file=sys.stderr)
            return 1
        print("SHA da Doutrina gravado em: " + (", ".join(mudou) or "nenhum arquivo (já estava em dia)"))
        return 0
    if argv:
        print("uso: python -m scripts.empacotar.payload [--sincronizar-pin | --derivar-pin]", file=sys.stderr)
        return 2
    try:
        pin = ler_pin()
        divergentes = sincronizar_pin()
        if divergentes:
            raise ErroDoutrina(f"o SHA de governanca/doutrina.json não está em {', '.join(divergentes)}: "
                               "rode `python -m scripts.empacotar.payload --derivar-pin` (ou --sincronizar-pin para buscar a Doutrina mais nova)")
        clone = os.environ.get("DOUTRINA_TEC")
        if not clone:
            raise ErroDoutrina("defina DOUTRINA_TEC com a pasta do clone da Doutrina (o commit fixado em governanca/doutrina.json precisa estar nele)")
        doutrina = instantaneo_doutrina(Path(clone), pin["sha"])
    except ErroDoutrina as e:
        print(f"ERRO: {e}", file=sys.stderr)
        return 1
    m = gerar(doutrina=doutrina, pin=pin)
    print(f"payload: {m['arquivos']} arquivos, sha256 {m['sha256'][:16]}…, versão {m['versao']} {m['commit']}, "
          f"Doutrina {m['doutrina']['versao']} @ {pin['sha'][:12]}")
    achados = verificar_conteudo(SAIDA / "payload.zip")
    for a in achados:
        print("ACHADO:", a, file=sys.stderr)
    if achados:
        print(f"{len(achados)} achado(s): o pacote NÃO deve ser distribuído.", file=sys.stderr)
        return 1
    print("verificação de conteúdo: limpo")
    return 0


if __name__ == "__main__":
    sys.exit(principal())

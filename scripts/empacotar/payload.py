"""Gera o pacote de código do instalador (payload.zip): o TudoIA sem nada desta máquina.

Lista de permissão por pasta: só entra o que está em INCLUIR. Dados, modelos, `.env`, ambientes virtuais, caches,
memórias de agentes e o config gerado do LiteLLM nunca entram. A seguir, `verificar_conteudo` varre o resultado atrás
de segredos e de dados pessoais; qualquer achado reprova o pacote.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
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
           "*/.serena/*", "*/.claude/*", "*/.cursor/*", "*/.codex/*", "*/.gemini/*", "*.egg-info/*")
EXCLUIR_NOMES = {".env", "auditoria.jsonl", "cerebro.db", "estado.json"}
TIMESTAMP_FIXO = (1980, 1, 1, 0, 0, 0)   # zip reproduzível: mesmo código = mesmo sha256


def _excluido(rel: str) -> bool:
    nome = rel.rsplit("/", 1)[-1]
    if nome in EXCLUIR_NOMES or (nome.startswith(".env") and nome != ".env.example"):
        return True
    return any(fnmatch.fnmatch(rel, p) for p in EXCLUIR)


# Variáveis que `tudoia segredos` gera sozinho na instalação: o MCP que só depende delas pode vir ligado.
GERADAS_PELO_INSTALADOR = {"CEREBRO_TOKEN_ESTATICO"}
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


def gerar(raiz: Path = RAIZ, saida: Path = SAIDA) -> dict:
    arquivos = listar_arquivos(raiz)
    saida.mkdir(parents=True, exist_ok=True)
    zip_path = saida / "payload.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
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
                 "arquivos": len(arquivos), "sha256": h}
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
            if _excluido(nome):
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


def principal() -> int:
    m = gerar()
    print(f"payload: {m['arquivos']} arquivos, sha256 {m['sha256'][:16]}…, versão {m['versao']} {m['commit']}")
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

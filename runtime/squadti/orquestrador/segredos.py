"""
Varredura de segredos no workspace gerado (SEC-SUP / IA-PRV-03 da Doutrina).

Relata SÓ o tipo e o arquivo:linha, nunca o valor achado (o relatório vai para o estado e para o modelo). É um filtro de
padrões conhecidos, não prova de ausência: não substitui um scanner dedicado (gitleaks, trufflehog) no CI do projeto.
"""
import re
from pathlib import Path
from typing import List

IGNORAR_DIRS = {"node_modules", ".git", "bin", "obj", "dist", "build", "TestResults", "coverage", ".vs"}
EXTENSOES = {".cs", ".json", ".yml", ".yaml", ".xml", ".config", ".ts", ".tsx", ".js", ".jsx", ".env", ".md", ".sql",
             ".ps1", ".sh", ".toml", ".ini", ".properties", ".txt", ".csproj", ".props", ".http"}
MAX_ARQUIVOS = 3000
MAX_BYTES = 1_000_000

PADROES = {
    "chave-privada": re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"),
    "chave-aws": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "token-github": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    "token-slack": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),
    "chave-api-sk": re.compile(r"\bsk-[A-Za-z0-9_-]{24,}\b"),
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    "senha-em-connection-string": re.compile(r"(?i)\b(?:password|pwd)\s*=\s*(?!\s*[;\"'<{$%])[^;\s\"']{4,}"),
    "senha-literal": re.compile(r"""(?i)\b(?:password|passwd|senha|secret|api[_-]?key|token)\b["']?\s*[:=]\s*["'](?!\s*["'])(?!\$\{|<|\{\{|%|your|change|xxx|example|exemplo)[^"'\s]{8,}["']"""),
}


def tipo_da_linha(linha: str):
    """Tipo do primeiro padrão de segredo que casa com a linha, ou None."""
    return next((tipo for tipo, regex in PADROES.items() if regex.search(linha)), None)


def redigir(texto: str):
    """(texto sem as linhas com padrão de segredo, quantas linhas foram trocadas). Para o que vai a um prompt (IA-PRV-03):
    a linha inteira some e o marcador não traz o valor."""
    saida, n = [], 0
    for linha in texto.splitlines():
        if tipo_da_linha(linha):
            saida.append("[linha omitida: possível segredo]")
            n += 1
        else:
            saida.append(linha)
    return "\n".join(saida), n


def varrer_arquivos(raiz: Path, relativos) -> List[dict]:
    """Como `varrer`, mas só nos arquivos informados (caminhos relativos já validados), qualquer extensão."""
    raiz = raiz.resolve()
    achados = []
    for rel in relativos:
        p = raiz / rel
        if not p.is_file() or p.is_symlink():
            continue
        try:
            if p.stat().st_size > MAX_BYTES:
                achados.append({"tipo": "arquivo-grande-demais-para-varrer", "arquivo": rel, "linha": 0})
                continue
            texto = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            achados.append({"tipo": "arquivo-ilegivel", "arquivo": rel, "linha": 0})
            continue
        for n, linha in enumerate(texto.splitlines(), 1):
            tipo = tipo_da_linha(linha)
            if tipo:
                achados.append({"tipo": tipo, "arquivo": rel, "linha": n})
    return achados


def varrer(raiz: Path) -> List[dict]:
    """[{'tipo','arquivo','linha'}] sem o valor. Link simbólico e arquivo grande são ignorados (não seguidos)."""
    raiz = raiz.resolve()
    achados, vistos = [], 0
    for p in sorted(raiz.rglob("*")):
        if not p.is_file() or p.is_symlink() or IGNORAR_DIRS & set(p.relative_to(raiz).parts):
            continue
        if p.suffix.lower() not in EXTENSOES and p.name.lower() not in {".env", "dockerfile"}:
            continue
        vistos += 1
        if vistos > MAX_ARQUIVOS:
            achados.append({"tipo": "limite-de-arquivos-excedido", "arquivo": "(varredura incompleta)", "linha": 0})
            break
        try:
            if p.stat().st_size > MAX_BYTES:
                continue
            texto = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for n, linha in enumerate(texto.splitlines(), 1):
            for tipo, regex in PADROES.items():
                if regex.search(linha):
                    achados.append({"tipo": tipo, "arquivo": p.relative_to(raiz).as_posix(), "linha": n})
    return achados

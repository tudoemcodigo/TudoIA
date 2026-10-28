"""Leitura e escrita do .env preservando comentários, ordem e fim de linha."""
import os
import re
from datetime import datetime
from pathlib import Path

_LINHA = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


def _linhas(path: Path) -> tuple[list[str], str]:
    """Linhas sem o terminador e o terminador usado no arquivo (CRLF ou LF)."""
    texto = path.read_bytes().decode("utf-8-sig")
    eol = "\r\n" if "\r\n" in texto else "\n"
    linhas = texto.split(eol)
    if linhas and linhas[-1] == "":
        linhas.pop()
    return linhas, eol


def ler_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    valores = {}
    for linha in _linhas(path)[0]:
        m = _LINHA.match(linha.strip())
        if m:
            valores[m.group(1)] = m.group(2)
    return valores


def limpar_valor(valor: str) -> str:
    v = valor.strip()
    if "\n" in v or "\r" in v:
        raise ValueError("o valor não pode ter quebra de linha no meio")
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        v = v[1:-1].strip()
    return v


def mascarar(valor: str) -> str:
    if not valor:
        return ""
    if len(valor) < 12:
        return "…"
    m = re.match(r"^[^-_]{1,7}[-_]", valor)
    prefixo = m.group(0) if m else ""
    return f"{prefixo}…{valor[-4:]}"


def gravar_valor(path: Path, chave: str, valor: str, dir_backup: Path, manter: int = 10) -> Path:
    """Troca só o valor de `chave` (ou acrescenta no fim). Devolve o caminho do backup."""
    valor = limpar_valor(valor)
    linhas, eol = _linhas(path) if path.exists() else ([], "\n")
    trocou = False
    for i, linha in enumerate(linhas):
        m = _LINHA.match(linha.strip())
        if m and m.group(1) == chave:
            linhas[i] = f"{chave}={valor}"
            trocou = True
            break
    if not trocou:
        linhas.append(f"{chave}={valor}")

    dir_backup.mkdir(parents=True, exist_ok=True)
    # O relógio do Windows tem resolução de ~1 ms: gravações seguidas podem cair no mesmo carimbo
    base = f".env.{datetime.now():%Y%m%d-%H%M%S-%f}"
    backup, n = dir_backup / base, 1
    while backup.exists():
        backup, n = dir_backup / f"{base}-{n:02d}", n + 1
    if path.exists():
        backup.write_bytes(path.read_bytes())
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes((eol.join(linhas) + eol).encode("utf-8"))
    os.replace(tmp, path)

    antigos = sorted(dir_backup.glob(".env.*"))
    for velho in antigos[:-manter] if len(antigos) > manter else []:
        velho.unlink()
    return backup

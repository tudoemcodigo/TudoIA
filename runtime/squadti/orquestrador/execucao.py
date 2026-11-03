"""
Fronteira com o sistema de arquivos e com processos: tudo que a Squad escreve ou executa passa por aqui.

- A saída de um modelo é dado não confiável: caminho validado, tamanho limitado, nunca fora do workspace.
- Comandos vêm da configuração da stack (não do modelo), sem shell, com executável permitido e timeout.
"""
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import List, Tuple

EXECUTAVEIS_PERMITIDOS = {"dotnet", "npm", "npx"}
MAX_ARQUIVOS = 50
MAX_BYTES_ARQUIVO = 200_000
TIMEOUT_PADRAO_S = 900

# Formato que os prompts exigem do modelo:
#   ### ARQUIVO: src/Backend/Foo.cs
#   ```csharp
#   ...
#   ```
RE_BLOCO = re.compile(r"^### ARQUIVO: *(?P<caminho>[^\r\n]+?) *\r?\n```[^\r\n]*\r?\n(?P<corpo>.*?)\r?\n```[ \t]*$",
                      re.MULTILINE | re.DOTALL)


def workspace(state: dict) -> Path:
    """Pasta da tarefa. Tudo que a Squad gera fica aqui, nunca solto no diretório do orquestrador."""
    raiz = Path(state.get("workspace_dir") or Path("workspace") / state.get("task_id", "TASK"))
    raiz.mkdir(parents=True, exist_ok=True)
    return raiz.resolve()


def caminho_seguro(raiz: Path, relativo: str) -> Path:
    """Resolve `relativo` dentro de `raiz` ou levanta ValueError (absoluto, '..', unidade, link de saída)."""
    rel = relativo.strip().replace("\\", "/")
    # ':' recusa unidade e fluxo alternativo do NTFS (arq.md:fluxo); ponto/espaço no fim do nome o Windows apaga em silêncio
    # (docs/negocio./x vira docs/negocio/x), o que contornaria a checagem de área.
    if (not rel or rel.startswith("/") or ":" in rel or ".." in Path(rel).parts
            or any(p != p.rstrip(". ") for p in Path(rel).parts if p not in (".",))):
        raise ValueError(f"caminho recusado: {relativo!r}")
    destino = (raiz / rel).resolve()
    if raiz.resolve() not in destino.parents:
        raise ValueError(f"caminho fora do workspace: {relativo!r}")
    return destino


def area_permitida(norm: str, permitidos: Tuple[str, ...]) -> bool:
    """Entrada terminada em '/' é prefixo de pasta; sem '/' no fim é o caminho EXATO de um arquivo (ex.: 'README.md'),
    de modo que permitir um arquivo da raiz não abre a raiz nem nomes parecidos ('README.mdx', 'readme.md')."""
    return any(norm.startswith(p) if p.endswith("/") else norm == p for p in permitidos)


def escrever_arquivos(resposta: str, raiz: Path, prefixos_permitidos: Tuple[str, ...] = ()) -> Tuple[List[str], List[str]]:
    """
    Extrai blocos '### ARQUIVO:' da resposta do modelo e grava no workspace.
    Devolve (gravados, recusados). `prefixos_permitidos` restringe a área: pastas terminadas em '/' (ex.: 'src/', 'tests/')
    e arquivos exatos da raiz (ex.: 'README.md').
    """
    gravados, recusados = [], []
    for i, m in enumerate(RE_BLOCO.finditer(resposta or "")):
        caminho, corpo = m.group("caminho"), m.group("corpo")
        if i >= MAX_ARQUIVOS:
            recusados.append(f"{caminho}: excedeu {MAX_ARQUIVOS} arquivos")
            continue
        try:
            destino = caminho_seguro(raiz, caminho)
            norm = caminho.strip().replace("\\", "/")
            if prefixos_permitidos and not area_permitida(norm, prefixos_permitidos):
                raise ValueError(f"fora da área permitida {prefixos_permitidos}: {caminho!r}")
            if len(corpo.encode("utf-8")) > MAX_BYTES_ARQUIVO:
                raise ValueError(f"{caminho}: maior que {MAX_BYTES_ARQUIVO} bytes")
        except ValueError as e:
            recusados.append(str(e))
            continue
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(corpo + "\n", encoding="utf-8", newline="\n")
        gravados.append(norm)
    return gravados, recusados


def executar(comando: str, cwd: Path, timeout_s: int = TIMEOUT_PADRAO_S) -> Tuple[int, str]:
    """Roda `comando` sem shell. Devolve (código, stdout+stderr). Timeout e executável fora da lista viram falha."""
    partes = shlex.split(comando, posix=(os.name != "nt"))
    if not partes or Path(partes[0]).stem.lower() not in EXECUTAVEIS_PERMITIDOS:
        return 126, f"executável não permitido: {partes[:1]}"
    try:
        r = subprocess.run(partes, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=timeout_s, shell=False)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, f"timeout após {timeout_s}s: {comando}"
    except OSError as e:
        return 127, f"não foi possível executar {partes[0]}: {e}"


def tem_projeto_dotnet(raiz: Path) -> bool:
    return any(raiz.rglob("*.sln")) or any(raiz.rglob("*.slnx")) or any(raiz.rglob("*.csproj"))

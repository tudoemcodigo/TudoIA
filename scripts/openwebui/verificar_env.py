"""Confere o runtime/open-webui/env.py (cópia alterada) contra o env.py da imagem fixada no compose.

O arquivo substitui o módulo de configuração da imagem (volume somente leitura). Ao subir o digest do Open WebUI, o
env.py da imagem muda e a cópia fica para trás em silêncio. Este comando extrai o env.py da imagem fixada, calcula o
diff da cópia contra ele e compara com runtime/open-webui/env.py.aprovado.diff (o diff que um humano revisou).

Uso (na raiz do repositório):
    python -m scripts.openwebui.verificar_env              # confere
    python -m scripts.openwebui.verificar_env --aprovar    # grava o diff atual como aprovado (depois de revisar!)

Códigos de saída: 0 igual ao aprovado | 1 diferente (imagem mudou ou a cópia foi editada) | 2 não deu para conferir.
"""

from __future__ import annotations

import argparse
import difflib
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

RAIZ = Path(__file__).resolve().parents[2]
CAMINHO_NA_IMAGEM = "/app/backend/open_webui/env.py"
IMAGEM = re.compile(r"image:\s*(ghcr\.io/open-webui/open-webui:\S+@sha256:[0-9a-f]{64})")


class ErroVerificacao(Exception):
    pass


def imagem_do_compose(texto: str) -> str:
    achada = IMAGEM.search(texto)
    if not achada:
        raise ErroVerificacao("imagem do open-webui com digest não encontrada em runtime/docker-compose.yml")
    return achada.group(1)


def extrair_da_imagem(imagem: str, executar: Callable = subprocess.run) -> str:
    """env.py da imagem, sem subir o serviço (cat como entrypoint de um container descartável)."""
    try:
        r = executar(["docker", "run", "--rm", "--entrypoint", "cat", imagem, CAMINHO_NA_IMAGEM],
                     capture_output=True, timeout=300, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise ErroVerificacao(f"não consegui executar o docker ({type(e).__name__})") from e
    if r.returncode != 0 or not r.stdout:
        raise ErroVerificacao("docker não devolveu o env.py da imagem (imagem ausente? rode docker pull)")
    return r.stdout.decode("utf-8")


def diff_normalizado(upstream: str, local: str) -> str:
    """Diff unificado (upstream -> cópia), com fim de linha normalizado: CRLF do Windows não conta como mudança."""
    a = upstream.replace("\r\n", "\n").splitlines(keepends=True)
    b = local.replace("\r\n", "\n").splitlines(keepends=True)
    return "".join(difflib.unified_diff(a, b, "upstream/env.py", "tudoia/env.py", n=2))


def verificar(raiz: Path, extrair: Callable[[str], str] = extrair_da_imagem) -> tuple[bool, str]:
    """(igual ao aprovado?, diff atual)."""
    imagem = imagem_do_compose((raiz / "runtime" / "docker-compose.yml").read_text(encoding="utf-8"))
    atual = diff_normalizado(extrair(imagem), (raiz / "runtime" / "open-webui" / "env.py").read_text(encoding="utf-8"))
    aprovado_arq = raiz / "runtime" / "open-webui" / "env.py.aprovado.diff"
    aprovado = aprovado_arq.read_text(encoding="utf-8").replace("\r\n", "\n") if aprovado_arq.is_file() else None
    return aprovado == atual, atual


def principal(argv: list[str] | None = None, raiz: Path = RAIZ, extrair: Callable[[str], str] = extrair_da_imagem) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--aprovar", action="store_true", help="grava o diff atual como aprovado (revise antes)")
    args = ap.parse_args(argv)
    try:
        igual, atual = verificar(raiz, extrair)
    except ErroVerificacao as e:
        print(f"não foi possível conferir: {e}", file=sys.stderr)
        return 2
    arq = raiz / "runtime" / "open-webui" / "env.py.aprovado.diff"
    if args.aprovar:
        arq.write_text(atual, encoding="utf-8", newline="\n")
        print(f"diff aprovado gravado em {arq.relative_to(raiz)} ({atual.count(chr(10))} linhas)")
        return 0
    if igual:
        print("env.py: a cópia difere do upstream só no que já foi aprovado.")
        return 0
    print("env.py: a cópia ou a imagem mudou desde a última revisão. Diff atual (upstream -> cópia):\n")
    print(atual or "(sem diferenças: a cópia é idêntica ao upstream)")
    print("\nRevise o diff. Se estiver certo, rode: python -m scripts.openwebui.verificar_env --aprovar", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(principal())

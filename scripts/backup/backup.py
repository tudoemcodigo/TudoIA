"""Backup dos dados do TudoIA em dados/backups/<AAAAMMDD-HHMMSS>/ (só biblioteca padrão).

Uso (na raiz do repositório):
    python -m scripts.backup.backup [--manter N] [--destino PASTA]
    scripts\\tudoia.ps1 backup --manter 7

O que entra (cada item é independente: se um falha, os outros continuam):
    litellm-db.sql.gz   pg_dump do Postgres do LiteLLM (docker exec litellm-db), em streaming para o gzip
    cerebro.db          cópia consistente de dados/cerebro/cerebro.db pela API de backup do SQLite
    n8n.tar.gz          volume Docker tudoia_n8n (somente leitura, container alpine descartável)
    open-webui.tar.gz   volume Docker tudoia_open-webui (idem)
    manifesto.json      o que foi salvo, tamanho e sha256 de cada arquivo, e o que falhou

O .env NÃO é copiado (segredos); o painel já guarda cópias dele em dados/backups/env.
Restauração: scripts/backup/restaurar.md.

Rotação: depois de um backup sem falhas, mantém os N mais recentes (padrão 7) e apaga os mais antigos. Só pastas
com nome AAAAMMDD-HHMMSS entram na conta (dados/backups/env e afins nunca são tocados). Se algo falhou, nada é
apagado: um backup quebrado não pode empurrar um bom para fora.

Códigos de saída: 0 tudo salvo | 1 algum item falhou (resumo no fim) | 2 uso indevido.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable, Sequence

RAIZ = Path(__file__).resolve().parents[2]
DESTINO_PADRAO = RAIZ / "dados" / "backups"
MANTER_PADRAO = 7
# Imagem fixada por versão: o tar roda nela com o volume montado só para leitura.
IMAGEM_ALPINE = "alpine:3.20.3"
# Nomes reais: projeto compose (TUDOIA_COMPOSE_PROJETO do .env, padrão "tudoia") + volumes de runtime/docker-compose.yml.
CONTAINER_POSTGRES = "litellm-db"
VOLUMES = (("n8n.tar.gz", "n8n"), ("open-webui.tar.gz", "open-webui"))   # sufixo; o prefixo é o projeto compose
TIMEOUT_ETAPA = 2 * 3600.0       # teto por item: um docker travado não segura o backup para sempre
TIMEOUT_CURTO = 60.0
BLOCO = 1024 * 1024
_RE_PASTA = re.compile(r"\d{8}-\d{6}")


def _projeto_compose(raiz: Path) -> str:
    """TUDOIA_COMPOSE_PROJETO do .env (padrão tudoia). Leitura mínima: este script só usa a biblioteca padrão."""
    try:
        for linha in (raiz / ".env").read_text(encoding="utf-8").splitlines():
            if linha.startswith("TUDOIA_COMPOSE_PROJETO="):
                return linha.split("=", 1)[1].strip() or "tudoia"
    except OSError:
        pass
    return "tudoia"


class ErroEtapa(Exception):
    """Falha de um item. A mensagem é segura para exibir (sem segredos)."""


# ----------------------------------------------------------------- utilitários
def _sha256(caminho: Path) -> str:
    digest = hashlib.sha256()
    with open(caminho, "rb") as arq:
        for bloco in iter(lambda: arq.read(BLOCO), b""):
            digest.update(bloco)
    return digest.hexdigest()


def _fim_do_erro(bruto: bytes) -> str:
    """Só o fim do stderr, numa linha: o bastante para diagnosticar, sem despejar saída longa."""
    texto = bruto[-4000:].decode("utf-8", "replace")
    return " ".join(texto.split())[-300:]


def _transmitir(cmd: Sequence[str], destino: Path, *, comprimir: bool, timeout: float = TIMEOUT_ETAPA) -> None:
    """Roda `cmd` e grava o stdout em `destino` em blocos (gzip opcional), sem guardar tudo em memória."""
    estourou = threading.Event()
    with tempfile.TemporaryFile() as erros:
        proc = subprocess.Popen(list(cmd), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=erros)

        def matar() -> None:
            estourou.set()
            proc.kill()

        relogio = threading.Timer(timeout, matar)
        relogio.start()
        try:
            abrir = gzip.open if comprimir else open
            with abrir(destino, "wb") as saida:
                shutil.copyfileobj(proc.stdout, saida, BLOCO)
            codigo = proc.wait()
        finally:
            relogio.cancel()
            proc.stdout.close()
            if proc.poll() is None:  # erro ao gravar (disco cheio...): não deixa o processo órfão
                proc.kill()
                proc.wait()
        if estourou.is_set():
            raise ErroEtapa(f"tempo limite de {timeout:.0f} s excedido")
        if codigo != 0:
            erros.seek(0)
            raise ErroEtapa(f"terminou com código {codigo}: {_fim_do_erro(erros.read())}")


# ----------------------------------------------------------------- etapas
def backup_postgres(pasta: Path, docker: Sequence[str]) -> Path:
    destino = pasta / "litellm-db.sql.gz"
    _transmitir([*docker, "exec", CONTAINER_POSTGRES, "pg_dump", "-U", "litellm", "litellm"],
                destino, comprimir=True)
    return destino


def backup_sqlite(origem: Path, destino: Path) -> Path:
    """Cópia consistente (API de backup do SQLite), mesmo com o Cérebro gravando. Nunca cria a origem."""
    if not origem.is_file():
        raise ErroEtapa(f"banco não encontrado: {origem}")
    fonte = sqlite3.connect(f"{origem.resolve().as_uri()}?mode=ro", uri=True)
    try:
        alvo = sqlite3.connect(destino)
        try:
            fonte.backup(alvo)
            resultado = alvo.execute("PRAGMA quick_check").fetchone()[0]
        finally:
            alvo.close()
    finally:
        fonte.close()
    if resultado != "ok":
        raise ErroEtapa(f"cópia do SQLite falhou no quick_check: {resultado[:200]}")
    return destino


def backup_volume(pasta: Path, arquivo: str, volume: str, docker: Sequence[str]) -> Path:
    # Sem esta checagem, `docker run -v nome:/v` criaria um volume vazio e o backup "daria certo" vazio.
    try:
        r = subprocess.run([*docker, "volume", "inspect", volume], stdin=subprocess.DEVNULL,
                           capture_output=True, timeout=TIMEOUT_CURTO)
    except subprocess.TimeoutExpired:
        raise ErroEtapa("docker volume inspect excedeu o tempo limite") from None
    if r.returncode != 0:
        raise ErroEtapa(f"volume {volume} não existe ou o Docker não respondeu: {_fim_do_erro(r.stderr)}")
    destino = pasta / arquivo
    # tar vai para o stdout e é gravado aqui: nada de bind mount do host (no Linux o arquivo sairia com dono root).
    _transmitir([*docker, "run", "--rm", "--network", "none", "-v", f"{volume}:/v:ro", IMAGEM_ALPINE,
                 "tar", "czf", "-", "-C", "/v", "."], destino, comprimir=False)
    return destino


# ----------------------------------------------------------------- rotação
def pastas_de_backup(base: Path) -> list[Path]:
    """Backups (pastas AAAAMMDD-HHMMSS) do mais antigo para o mais novo."""
    if not base.is_dir():
        return []
    return sorted(p for p in base.iterdir() if p.is_dir() and _RE_PASTA.fullmatch(p.name))


def rotacionar(base: Path, manter: int) -> list[Path]:
    """Apaga os backups além dos `manter` mais recentes. Retorna o que foi apagado."""
    if manter < 1:
        raise ValueError("manter deve ser >= 1")
    antigos = pastas_de_backup(base)[:-manter]
    for pasta in antigos:
        shutil.rmtree(pasta)
    return antigos


# ----------------------------------------------------------------- orquestração
def executar_backup(destino_base: Path = DESTINO_PADRAO, *, manter: int = MANTER_PADRAO,
                    docker: Sequence[str] = ("docker",), raiz: Path = RAIZ,
                    agora: datetime | None = None, saida: Callable[[str], None] = print) -> int:
    """Faz o backup completo. Retorna o código de saída (0 tudo salvo, 1 algum item falhou)."""
    if manter < 1:
        raise ValueError("manter deve ser >= 1")
    momento = agora or datetime.now()
    projeto = _projeto_compose(raiz)
    pasta = destino_base / momento.strftime("%Y%m%d-%H%M%S")
    pasta.mkdir(parents=True, exist_ok=False)  # dois backups no mesmo segundo: o segundo falha, não sobrescreve

    etapas: list[tuple[str, Callable[[], Path]]] = [
        ("litellm-db.sql.gz", lambda: backup_postgres(pasta, docker)),
        ("cerebro.db", lambda: backup_sqlite(raiz / "dados" / "cerebro" / "cerebro.db", pasta / "cerebro.db")),
        *((arq, (lambda a=arq, v=f"{projeto}_{vol}": backup_volume(pasta, a, v, docker))) for arq, vol in VOLUMES),
    ]
    itens: list[dict] = []
    falhas: list[dict] = []
    for nome, etapa in etapas:
        try:
            arquivo = etapa()
            itens.append({"arquivo": arquivo.name, "bytes": arquivo.stat().st_size, "sha256": _sha256(arquivo)})
            saida(f"[ok]    {nome} ({itens[-1]['bytes']} bytes)")
        except Exception as e:  # noqa: BLE001 - cada item é independente; o erro vai para o resumo
            (pasta / nome).unlink(missing_ok=True)  # nada de arquivo pela metade no backup
            motivo = str(e) if isinstance(e, ErroEtapa) else f"{type(e).__name__}: {e}"
            if isinstance(e, FileNotFoundError) and nome != "cerebro.db":  # Popen sem o executável
                motivo = "docker não encontrado no PATH"
            falhas.append({"arquivo": nome, "erro": motivo})
            saida(f"[falha] {nome}: {motivo}")

    manifesto = {
        "versao": 1,
        "criado_em": momento.isoformat(timespec="seconds"),
        "itens": itens,
        "falhas": falhas,
        "env_incluido": False,
        "observacao": ".env não é copiado (segredos); cópias dele ficam em dados/backups/env.",
        "restauracao": "scripts/backup/restaurar.md",
    }
    (pasta / "manifesto.json").write_text(json.dumps(manifesto, ensure_ascii=False, indent=2) + "\n",
                                          encoding="utf-8")

    saida(f"\nbackup: {pasta}")
    saida("o .env NÃO foi copiado (segredos); cópias dele ficam em dados/backups/env.")
    if falhas:
        saida(f"FALHOU {len(falhas)} de {len(etapas)} itens: {', '.join(f['arquivo'] for f in falhas)}.")
        saida("rotação não executada: nenhum backup antigo foi apagado.")
        return 1
    apagados = rotacionar(destino_base, manter)
    saida(f"todos os {len(etapas)} itens salvos; rotação: mantidos {manter}, apagados {len(apagados)}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    for fluxo in (sys.stdout, sys.stderr):
        if hasattr(fluxo, "reconfigure"):
            fluxo.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="Backup dos dados do TudoIA (o .env não entra).")
    parser.add_argument("--manter", type=int, default=MANTER_PADRAO,
                        help=f"quantos backups manter depois de um backup sem falhas (padrão {MANTER_PADRAO})")
    parser.add_argument("--destino", type=Path, default=DESTINO_PADRAO,
                        help=f"pasta dos backups (padrão {DESTINO_PADRAO})")
    args = parser.parse_args(argv)
    if args.manter < 1:
        parser.error("--manter deve ser >= 1")
    try:
        return executar_backup(args.destino, manter=args.manter)
    except FileExistsError:
        print("erro: já existe um backup com este horário; espere um segundo e rode de novo", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

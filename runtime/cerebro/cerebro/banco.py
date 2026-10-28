import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

import numpy as np

from .vetores import de_blob, para_blob

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS fatos(
    id INTEGER PRIMARY KEY, texto TEXT NOT NULL, etiquetas TEXT NOT NULL,
    vetor BLOB NOT NULL, criado TEXT NOT NULL, atualizado TEXT NOT NULL, origem TEXT);
CREATE TABLE IF NOT EXISTS trechos(
    id INTEGER PRIMARY KEY, arquivo TEXT NOT NULL, ordem INT NOT NULL,
    texto TEXT NOT NULL, vetor BLOB NOT NULL);
CREATE INDEX IF NOT EXISTS ix_trechos_arquivo ON trechos(arquivo);
CREATE TABLE IF NOT EXISTS arquivos(
    arquivo TEXT PRIMARY KEY, mtime REAL NOT NULL, tamanho INT NOT NULL, indexado TEXT NOT NULL);
"""


def _agora() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class Banco:
    def __init__(self, caminho: Path):
        caminho = Path(caminho)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        # o servidor MCP atende de várias threads; o lock serializa o acesso
        self._con = sqlite3.connect(caminho, check_same_thread=False)
        self._lock = threading.Lock()
        # sobe a cada escrita; os caches de matriz (memória e índice) comparam para saber se relêem
        self._versoes = {"fatos": 0, "trechos": 0}
        with self._lock, self._con:
            self._con.executescript(_ESQUEMA)
            colunas = {linha[1] for linha in self._con.execute("PRAGMA table_info(fatos)")}
            if "origem" not in colunas:
                # banco criado antes da coluna existir: fatos antigos ficam com origem nula
                self._con.execute("ALTER TABLE fatos ADD COLUMN origem TEXT")

    def versao(self, tabela: str) -> int:
        return self._versoes[tabela]

    def inserir_fato(self, texto: str, etiquetas: list[str], vetor: np.ndarray, origem: str | None = None) -> int:
        agora = _agora()
        with self._lock, self._con:
            cur = self._con.execute(
                "INSERT INTO fatos(texto, etiquetas, vetor, criado, atualizado, origem) VALUES(?,?,?,?,?,?)",
                (texto, json.dumps(etiquetas, ensure_ascii=False), para_blob(vetor), agora, agora, origem),
            )
            self._versoes["fatos"] += 1
            return cur.lastrowid

    def atualizar_etiquetas(self, id: int, etiquetas: list[str]) -> None:
        with self._lock, self._con:
            self._con.execute(
                "UPDATE fatos SET etiquetas=?, atualizado=? WHERE id=?",
                (json.dumps(etiquetas, ensure_ascii=False), _agora(), id),
            )
            self._versoes["fatos"] += 1

    def listar_fatos(self) -> list[dict]:
        with self._lock:
            linhas = self._con.execute(
                "SELECT id, texto, etiquetas, vetor, criado, atualizado, origem FROM fatos ORDER BY id"
            ).fetchall()
        return [
            {"id": i, "texto": t, "etiquetas": json.loads(e), "vetor": de_blob(v),
             "criado": c, "atualizado": a, "origem": o}
            for i, t, e, v, c, a, o in linhas
        ]

    def apagar_fato(self, id: int) -> bool:
        with self._lock, self._con:
            cur = self._con.execute("DELETE FROM fatos WHERE id=?", (id,))
            self._versoes["fatos"] += 1
            return cur.rowcount > 0

    def substituir_arquivo(
        self, arquivo: str, mtime: float, tamanho: int, trechos: list[tuple[str, np.ndarray]]
    ) -> None:
        with self._lock, self._con:
            self._con.execute("DELETE FROM trechos WHERE arquivo=?", (arquivo,))
            self._con.executemany(
                "INSERT INTO trechos(arquivo, ordem, texto, vetor) VALUES(?,?,?,?)",
                [(arquivo, i, t, para_blob(v)) for i, (t, v) in enumerate(trechos)],
            )
            self._con.execute(
                "INSERT OR REPLACE INTO arquivos(arquivo, mtime, tamanho, indexado) VALUES(?,?,?,?)",
                (arquivo, mtime, tamanho, _agora()),
            )
            self._versoes["trechos"] += 1

    def remover_arquivo(self, arquivo: str) -> None:
        with self._lock, self._con:
            self._con.execute("DELETE FROM trechos WHERE arquivo=?", (arquivo,))
            self._con.execute("DELETE FROM arquivos WHERE arquivo=?", (arquivo,))
            self._versoes["trechos"] += 1

    def arquivos_indexados(self) -> dict[str, tuple[float, int]]:
        with self._lock:
            linhas = self._con.execute("SELECT arquivo, mtime, tamanho FROM arquivos").fetchall()
        return {a: (m, t) for a, m, t in linhas}

    def listar_trechos(self) -> list[dict]:
        with self._lock:
            linhas = self._con.execute(
                "SELECT arquivo, ordem, texto, vetor FROM trechos ORDER BY id"
            ).fetchall()
        return [{"arquivo": a, "ordem": o, "texto": t, "vetor": de_blob(v)} for a, o, t, v in linhas]

    def contagens(self) -> dict:
        with self._lock:
            return {
                nome: self._con.execute(f"SELECT COUNT(*) FROM {nome}").fetchone()[0]
                for nome in ("fatos", "trechos", "arquivos")
            }

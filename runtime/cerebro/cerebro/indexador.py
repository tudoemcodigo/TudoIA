import asyncio
import itertools
import logging
import os
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from .banco import Banco
from .embeddings import Embedder
from .vetores import CacheMatriz, ranquear

EXTENSOES = {".md", ".txt", ".pdf", ".docx", ".html"}
MAX_BYTES = 20 * 1024 * 1024
MAX_PAGINAS_PDF = 500
MAX_CARACTERES = 2_000_000  # texto extraído de PDF/DOCX; o resto do arquivo fica fora do índice
PRAZO_EXTRACAO = 120.0  # segundos por arquivo
_SEPS = chr(92) + "/"
log = logging.getLogger("cerebro.indexador")


def _juntar_limitado(partes: Iterable[str]) -> str:
    # para de consumir o gerador no limite: as páginas seguintes nem são extraídas
    saida, total = [], 0
    for parte in partes:
        saida.append(parte)
        total += len(parte) + 1
        if total >= MAX_CARACTERES:
            break
    return "\n".join(saida)[:MAX_CARACTERES]


def fatiar(texto: str, tamanho: int = 1000, sobreposicao: int = 150) -> list[str]:
    trechos: list[str] = []
    pos, total = 0, len(texto)
    while pos < total:
        fim = min(pos + tamanho, total)
        if fim < total:
            # prefere cortar numa quebra de linha ou espaço na metade final do trecho
            corte = max(texto.rfind("\n", pos + tamanho // 2, fim), texto.rfind(" ", pos + tamanho // 2, fim))
            if corte > pos:
                fim = corte + 1
        trecho = texto[pos:fim].strip()
        if trecho:
            trechos.append(trecho)
        if fim >= total:
            break
        # garante avanço mesmo com sobreposição grande
        pos = max(fim - sobreposicao, pos + 1)
    return trechos


def extrair_texto(caminho: Path) -> str:
    ext = caminho.suffix.lower()
    if ext in (".txt", ".md"):
        dados = caminho.read_bytes()
        try:
            return dados.decode("utf-8")
        except UnicodeDecodeError:
            return dados.decode("cp1252")
    if ext == ".html":
        import trafilatura

        return trafilatura.extract(caminho.read_text(encoding="utf-8", errors="replace")) or ""
    if ext == ".pdf":
        from pypdf import PdfReader

        paginas = itertools.islice(PdfReader(str(caminho)).pages, MAX_PAGINAS_PDF)
        return _juntar_limitado((p.extract_text() or "") for p in paginas)
    if ext == ".docx":
        from docx import Document

        return _juntar_limitado(p.text for p in Document(str(caminho)).paragraphs)
    raise ValueError(f"Extensão não suportada: {ext}")


class Indexador:
    def __init__(self, banco: Banco, embedder: Embedder, raiz: Path, raiz_host: str = ""):
        self.banco = banco
        self.embedder = embedder
        self.raiz = Path(raiz)
        self.raiz_host = raiz_host
        self.ultimo_resultado: dict | None = None
        self._cache = CacheMatriz(lambda: banco.versao("trechos"), banco.listar_trechos)
        # (arquivo, mtime, tamanho) cuja extração estourou o prazo: a thread presa não pode ser morta,
        # então o arquivo só é tentado de novo quando mudar (senão cada volta prenderia mais uma thread)
        self._estourados: set[tuple[str, float, int]] = set()

    def _varrer(self) -> dict[str, tuple[Path, float, int]]:
        achados = {}
        for pasta, subs, nomes in os.walk(self.raiz):
            subs[:] = [d for d in subs if not d.startswith(".")]
            for nome in nomes:
                p = Path(pasta) / nome
                if p.suffix.lower() not in EXTENSOES:
                    continue
                try:
                    st = p.stat()
                except OSError:
                    continue
                if st.st_size > MAX_BYTES:
                    continue
                achados[p.relative_to(self.raiz).as_posix()] = (p, st.st_mtime, st.st_size)
        return achados

    async def indexar(self) -> dict:
        r = {"novos": 0, "atualizados": 0, "removidos": 0, "inalterados": 0, "erros": 0}
        achados = await asyncio.to_thread(self._varrer)
        antigos = self.banco.arquivos_indexados()
        for rel in set(antigos) - set(achados):
            self.banco.remover_arquivo(rel)
            r["removidos"] += 1
        for rel, (p, mtime, tamanho) in sorted(achados.items()):
            if antigos.get(rel) == (mtime, tamanho):
                r["inalterados"] += 1
                continue
            if (rel, mtime, tamanho) in self._estourados:
                r["erros"] += 1
                continue
            try:
                try:
                    texto = await asyncio.wait_for(asyncio.to_thread(extrair_texto, p), PRAZO_EXTRACAO)
                except TimeoutError:
                    self._estourados.add((rel, mtime, tamanho))
                    log.warning("extração passou de %.0f s, arquivo ignorado até mudar: %r", PRAZO_EXTRACAO, rel)
                    raise
                pedacos = fatiar(texto)
                if not pedacos:
                    raise ValueError("arquivo sem texto extraível")
                vetores = await self.embedder.embed(pedacos)
                self.banco.substituir_arquivo(rel, mtime, tamanho, list(zip(pedacos, vetores, strict=True)))   # faltar vetor = erro do arquivo, não trecho sem busca
            except Exception:
                # um arquivo ruim não pode parar a varredura; fica fora de `arquivos` para nova tentativa
                r["erros"] += 1
                if rel in antigos:
                    # não deixa conteúdo velho aparecer na busca
                    self.banco.remover_arquivo(rel)
                continue
            r["atualizados" if rel in antigos else "novos"] += 1
        r["ultimo"] = datetime.now().astimezone().isoformat(timespec="seconds")
        self.ultimo_resultado = r
        return r

    async def buscar(self, consulta: str, n: int = 5) -> list[dict]:
        if not consulta or not consulta.strip():
            raise ValueError("A consulta está vazia. Diga o que você quer procurar.")
        # ler o banco e montar a matriz bloqueia: fica fora do event loop (e só acontece quando o índice muda)
        trechos, matriz = await asyncio.to_thread(self._cache.obter)
        if not trechos:
            return []
        (q,) = await self.embedder.embed([consulta])
        saida = []
        for i, score in await asyncio.to_thread(ranquear, q, matriz, n):
            t = trechos[i]
            caminho = (
                self.raiz_host.rstrip(_SEPS) + "\\" + t["arquivo"].replace("/", "\\")
                if self.raiz_host
                else t["arquivo"]
            )
            saida.append({"arquivo": t["arquivo"], "caminho": caminho, "trecho": t["texto"], "score": score})
        return saida

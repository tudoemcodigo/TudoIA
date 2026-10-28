import asyncio
import threading

import numpy as np

from .banco import Banco
from .embeddings import Embedder
from .vetores import CacheMatriz, ranquear

# acima disso o fato novo é marcado como parecido com um já guardado. Só marca, nunca substitui:
# "prefere X" e "não prefere X" passam fácil desse limiar.
LIMIAR_PARECIDO = 0.95
MAX_FATO = 2000  # caracteres: fato é uma frase durável, não um documento
MAX_ORIGEM = 500


def _validar(texto: str) -> str:
    texto = (texto or "").strip()
    if not texto:
        raise ValueError("o texto não pode ser vazio")
    return texto


def _normalizar(texto: str) -> str:
    return " ".join(texto.split()).casefold()


class Memoria:
    def __init__(self, banco: Banco, embedder: Embedder):
        self.banco = banco
        self.embedder = embedder
        self._cache = CacheMatriz(lambda: banco.versao("fatos"), banco.listar_fatos)
        # comparar e gravar sob a mesma trava: dois `lembrar` iguais ao mesmo tempo não viram dois fatos
        self._trava = threading.Lock()

    async def lembrar(self, fato: str, etiquetas: list[str] | None = None, origem: str | None = None) -> dict:
        fato = _validar(fato)
        if len(fato) > MAX_FATO:
            raise ValueError(f"o fato tem {len(fato)} caracteres; o limite é {MAX_FATO}. Resuma antes de guardar.")
        origem = (origem or "").strip() or None
        if origem is not None and len(origem) > MAX_ORIGEM:
            raise ValueError(f"a origem passa de {MAX_ORIGEM} caracteres")
        vetor = (await self.embedder.embed([fato]))[0]
        return await asyncio.to_thread(self._gravar, fato, etiquetas or [], origem, vetor)

    def _gravar(self, fato: str, etiquetas: list[str], origem: str | None, vetor: np.ndarray) -> dict:
        with self._trava:
            fatos, matriz = self._cache.obter()
            chave = _normalizar(fato)
            for existente in fatos:
                if _normalizar(existente["texto"]) == chave:
                    # mesmo texto: só junta as etiquetas
                    uniao = list(dict.fromkeys(existente["etiquetas"] + etiquetas))
                    self.banco.atualizar_etiquetas(existente["id"], uniao)
                    return {"id": existente["id"], "atualizado": True, "parecido_com": None}
            parecido = None
            if fatos:
                [(i, score)] = ranquear(vetor, matriz, 1)
                if score >= LIMIAR_PARECIDO:
                    parecido = fatos[i]["id"]
            novo = self.banco.inserir_fato(fato, etiquetas, vetor, origem)
            return {"id": novo, "atualizado": False, "parecido_com": parecido}

    async def recordar(self, consulta: str, n: int = 5) -> list[dict]:
        consulta = _validar(consulta)
        fatos, matriz = await asyncio.to_thread(self._cache.obter)
        if not fatos:
            return []
        vetor = (await self.embedder.embed([consulta]))[0]
        return [
            {"id": fatos[i]["id"], "fato": fatos[i]["texto"], "etiquetas": fatos[i]["etiquetas"],
             "origem": fatos[i]["origem"], "data": fatos[i]["atualizado"], "score": round(score, 3)}
            for i, score in await asyncio.to_thread(ranquear, vetor, matriz, n)
        ]

    def esquecer(self, id: int) -> bool:
        return self.banco.apagar_fato(id)

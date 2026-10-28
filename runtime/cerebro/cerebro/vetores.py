from collections.abc import Callable

import numpy as np

# teto de n nas buscas: n grande devolveria o banco inteiro, e n negativo vira slice invertido (quase tudo)
MAX_RESULTADOS = 20


def ranquear(consulta: np.ndarray, matriz: np.ndarray, n: int) -> list[tuple[int, float]]:
    if matriz.shape[0] == 0:
        return []
    n = min(max(n, 1), MAX_RESULTADOS)
    # vetores já normalizados: produto escalar = cosseno
    scores = matriz @ consulta
    ordem = np.argsort(-scores)[:n]
    return [(int(i), float(scores[i])) for i in ordem]


class CacheMatriz:
    """Itens e matriz de vetores em memória; só relê o banco quando a versão da tabela muda."""

    def __init__(self, versao: Callable[[], int], listar: Callable[[], list[dict]]):
        self._versao = versao
        self._listar = listar
        self._atual: tuple[int, list[dict], np.ndarray] | None = None

    def obter(self) -> tuple[list[dict], np.ndarray]:
        # versão lida ANTES de listar: escrita no meio só causa uma releitura a mais, nunca dado velho preso
        versao = self._versao()
        atual = self._atual
        if atual is None or atual[0] != versao:
            itens = self._listar()
            # o vetor sai do item para não ficar duplicado em memória (já está na matriz)
            matriz = np.stack([i.pop("vetor") for i in itens]) if itens else np.empty((0, 0), np.float32)
            atual = self._atual = (versao, itens, matriz)
        return atual[1], atual[2]


def para_blob(v: np.ndarray) -> bytes:
    return np.asarray(v, dtype=np.float32).tobytes()


def de_blob(b: bytes) -> np.ndarray:
    return np.frombuffer(b, dtype=np.float32).copy()

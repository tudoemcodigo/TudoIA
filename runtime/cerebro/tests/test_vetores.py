import numpy as np

from cerebro.vetores import CacheMatriz, de_blob, para_blob, ranquear


def test_ranquear_ordena_e_corta():
    matriz = np.array([[1, 0], [0, 1], [0.8, 0.6]], dtype=np.float32)
    r = ranquear(np.array([1, 0], dtype=np.float32), matriz, 2)
    assert [i for i, _ in r] == [0, 2]
    assert r[0][1] > r[1][1]


def test_ranquear_matriz_vazia():
    assert ranquear(np.array([1, 0], dtype=np.float32), np.empty((0, 2), dtype=np.float32), 5) == []


def test_ranquear_limita_n_a_faixa_1_a_20():
    matriz = np.eye(30, dtype=np.float32)
    consulta = np.ones(30, dtype=np.float32)
    assert len(ranquear(consulta, matriz, -1)) == 1  # antes: argsort[:-1] devolvia 29
    assert len(ranquear(consulta, matriz, 0)) == 1
    assert len(ranquear(consulta, matriz, 100)) == 20


def test_cache_so_rele_quando_a_versao_muda():
    versao, leituras = [0], []

    def listar():
        leituras.append(1)
        return [{"id": versao[0], "vetor": np.array([1.0, 0.0], dtype=np.float32)}]

    cache = CacheMatriz(lambda: versao[0], listar)
    itens, matriz = cache.obter()
    cache.obter()
    assert len(leituras) == 1 and matriz.shape == (1, 2) and "vetor" not in itens[0]
    versao[0] = 1
    itens, _ = cache.obter()
    assert len(leituras) == 2 and itens[0]["id"] == 1


def test_cache_vazio_devolve_matriz_vazia():
    itens, matriz = CacheMatriz(lambda: 0, list).obter()
    assert itens == [] and matriz.shape[0] == 0


def test_blob_ida_e_volta():
    v = np.array([0.5, -1.0, 2.0], dtype=np.float32)
    assert np.allclose(de_blob(para_blob(v)), v)

import pytest

from cerebro.banco import Banco
from cerebro.memoria import Memoria


async def test_lembrar_e_recordar_acha_o_fato_pelo_sentido(banco, embedder):
    m = Memoria(banco, embedder)
    await m.lembrar(r"o projeto Reversa fica em D:\Reversa")
    await m.lembrar("receita de bolo de cenoura com cobertura")
    r = await m.recordar("onde fica o Reversa")
    assert r[0]["fato"] == r"o projeto Reversa fica em D:\Reversa"
    assert r[0]["score"] > 0


async def test_lembrar_texto_igual_so_junta_etiquetas(banco, embedder):
    m = Memoria(banco, embedder)
    a = await m.lembrar("usuário prefere respostas curtas", ["estilo"])
    b = await m.lembrar("  Usuário  prefere respostas CURTAS ", ["chat"])
    assert a == {"id": a["id"], "atualizado": False, "parecido_com": None}
    assert b == {"id": a["id"], "atualizado": True, "parecido_com": None}
    [f] = banco.listar_fatos()
    assert f["texto"] == "usuário prefere respostas curtas" and f["etiquetas"] == ["estilo", "chat"]


async def test_negacao_parecida_vira_fato_novo_e_nao_apaga_o_antigo(banco, embedder):
    """'prefere X' e 'não prefere X' passam de 0,95 de similaridade; antes o segundo sobrescrevia o primeiro."""
    m = Memoria(banco, embedder)
    base = "o usuário prefere respostas curtas e diretas em português sem rodeios nem listas longas demais hoje"
    a = await m.lembrar(base)
    b = await m.lembrar("não " + base)
    assert b["atualizado"] is False and b["id"] != a["id"] and b["parecido_com"] == a["id"]
    assert [f["texto"] for f in banco.listar_fatos()] == [base, "não " + base]


async def test_fato_acima_do_limite_e_recusado(banco, embedder):
    m = Memoria(banco, embedder)
    with pytest.raises(ValueError, match="limite é 2000"):
        await m.lembrar("a" * 2001)
    assert banco.listar_fatos() == []
    assert (await m.lembrar("b" * 2000))["atualizado"] is False


async def test_origem_e_gravada_e_devolvida_em_recordar(banco, embedder):
    m = Memoria(banco, embedder)
    await m.lembrar("a cotação do dólar fechou em alta", origem="https://noticias.teste/dolar")
    await m.lembrar("o usuário mora em Campinas")
    r = {x["fato"]: x["origem"] for x in await m.recordar("dólar Campinas", n=5)}
    assert r == {"a cotação do dólar fechou em alta": "https://noticias.teste/dolar", "o usuário mora em Campinas": None}
    with pytest.raises(ValueError, match="origem"):
        await m.lembrar("outro fato", origem="x" * 501)


async def test_lembrar_concorrente_do_mesmo_texto_grava_uma_vez(banco, embedder):
    import asyncio

    m = Memoria(banco, embedder)
    resultados = await asyncio.gather(*(m.lembrar("gosto de café sem açúcar", [f"e{i}"]) for i in range(10)))
    assert len(banco.listar_fatos()) == 1
    assert len({r["id"] for r in resultados}) == 1
    assert sorted(banco.listar_fatos()[0]["etiquetas"]) == sorted(f"e{i}" for i in range(10))


async def test_recordar_limita_n(banco, embedder):
    m = Memoria(banco, embedder)
    for i in range(25):
        await m.lembrar(f"fato numero {i} sobre o projeto x{i}")
    assert len(await m.recordar("projeto", n=-1)) == 1  # antes: argsort[:-1] devolvia 24
    assert len(await m.recordar("projeto", n=1000)) == 20


async def test_recordar_enxerga_escritas_depois_do_cache(banco, embedder):
    m = Memoria(banco, embedder)
    await m.lembrar("alfa beta gama")
    assert [x["fato"] for x in await m.recordar("alfa")] == ["alfa beta gama"]
    novo = await m.lembrar("delta epsilon")
    assert "delta epsilon" in [x["fato"] for x in await m.recordar("delta")]
    m.esquecer(novo["id"])
    assert "delta epsilon" not in [x["fato"] for x in await m.recordar("delta")]


def test_banco_antigo_sem_coluna_origem_e_migrado(tmp_path):
    import sqlite3

    import numpy as np

    caminho = tmp_path / "antigo.db"
    con = sqlite3.connect(caminho)
    con.executescript(
        "CREATE TABLE fatos(id INTEGER PRIMARY KEY, texto TEXT NOT NULL, etiquetas TEXT NOT NULL,"
        " vetor BLOB NOT NULL, criado TEXT NOT NULL, atualizado TEXT NOT NULL);"
        "INSERT INTO fatos(texto, etiquetas, vetor, criado, atualizado) VALUES('velho', '[]', x'0000803f', 'c', 'a');"
    )
    con.commit()
    con.close()
    b = Banco(caminho)
    b.inserir_fato("novo", [], np.ones(1, dtype=np.float32), origem="usuário")
    assert [(f["texto"], f["origem"]) for f in b.listar_fatos()] == [("velho", None), ("novo", "usuário")]
    Banco(caminho)  # reabrir não tenta adicionar a coluna de novo


async def test_lembrar_vazio_da_erro_claro(banco, embedder):
    m = Memoria(banco, embedder)
    with pytest.raises(ValueError, match="vazio"):
        await m.lembrar("   ")
    with pytest.raises(ValueError, match="vazio"):
        await m.recordar("")


async def test_esquecer_remove(banco, embedder):
    m = Memoria(banco, embedder)
    r = await m.lembrar("algo")
    assert m.esquecer(r["id"]) is True
    assert banco.listar_fatos() == []
    assert m.esquecer(999) is False


def test_banco_persiste_entre_aberturas(tmp_path):
    import numpy as np

    caminho = tmp_path / "x.db"
    b = Banco(caminho)
    b.inserir_fato("oi", ["a"], np.ones(4, dtype=np.float32))
    b.substituir_arquivo("a.txt", 1.5, 10, [("trecho", np.ones(4, dtype=np.float32))])
    b2 = Banco(caminho)
    f = b2.listar_fatos()
    assert f[0]["texto"] == "oi" and f[0]["etiquetas"] == ["a"]
    assert b2.arquivos_indexados() == {"a.txt": (1.5, 10)}
    assert b2.contagens() == {"fatos": 1, "trechos": 1, "arquivos": 1}

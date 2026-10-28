import asyncio
import os

import pytest

from cerebro import indexador as ix
from cerebro.indexador import Indexador, fatiar


def test_fatiar_respeita_tamanho_e_sobreposicao():
    texto = " ".join(f"palavra{i}" for i in range(400))[:2500]
    trechos = fatiar(texto)
    assert len(trechos) >= 3
    assert all(len(t) <= 1000 for t in trechos)
    assert trechos[1][:30] in trechos[0]


def test_fatiar_descarta_espacos_e_texto_vazio():
    assert fatiar("   \n\n  ") == []
    assert fatiar("curto") == ["curto"]


async def test_indexar_so_reprocessa_o_que_mudou(banco, embedder, tmp_path):
    (tmp_path / "a.md").write_text("alpha beta", encoding="utf-8")
    (tmp_path / "b.txt").write_text("gamma delta", encoding="utf-8")
    idx = Indexador(banco, embedder, tmp_path)
    assert (await idx.indexar())["novos"] == 2
    r = await idx.indexar()
    assert r["inalterados"] == 2 and r["novos"] == 0
    a = tmp_path / "a.md"
    a.write_text("alpha beta novo", encoding="utf-8")
    st = a.stat()
    os.utime(a, (st.st_atime, st.st_mtime + 10))
    assert (await idx.indexar())["atualizados"] == 1
    (tmp_path / "b.txt").unlink()
    r = await idx.indexar()
    assert r["removidos"] == 1
    assert idx.ultimo_resultado == r and r["ultimo"]


async def test_arquivos_ruins_contam_erro_e_nao_param(banco, embedder, tmp_path):
    (tmp_path / "latin.txt").write_bytes("ação importante".encode("cp1252"))
    (tmp_path / "ruim.pdf").write_bytes(b"isto nao e um pdf \xff\xfe")
    (tmp_path / "ok.md").write_text("tudo certo aqui", encoding="utf-8")
    idx = Indexador(banco, embedder, tmp_path)
    r = await idx.indexar()
    assert r["erros"] == 1 and r["novos"] == 2
    assert set(banco.arquivos_indexados()) == {"latin.txt", "ok.md"}
    assert any("ação" in t["texto"] for t in banco.listar_trechos())
    # arquivo com erro é tentado de novo
    assert (await idx.indexar())["erros"] == 1


async def test_buscar_devolve_caminho_windows(banco, embedder, tmp_path):
    (tmp_path / "entrada").mkdir()
    (tmp_path / "entrada" / "a.md").write_text("receita de bolo de cenoura", encoding="utf-8")
    (tmp_path / "b.md").write_text("manual da impressora", encoding="utf-8")
    idx = Indexador(banco, embedder, tmp_path, raiz_host="D:\\TudoIA\\docs")
    await idx.indexar()
    r = await idx.buscar("bolo de cenoura", n=1)
    assert r[0]["arquivo"] == "entrada/a.md"
    assert r[0]["caminho"] == "D:\\TudoIA\\docs\\entrada\\a.md"
    assert "bolo" in r[0]["trecho"] and r[0]["score"] > 0
    idx2 = Indexador(banco, embedder, tmp_path)
    assert (await idx2.buscar("bolo", n=1))[0]["caminho"] == "entrada/a.md"
    with pytest.raises(ValueError):
        await idx.buscar("   ")


async def test_ignora_extensao_desconhecida_e_arquivo_gigante(banco, embedder, tmp_path, monkeypatch):
    (tmp_path / "x.exe").write_bytes(b"MZ")
    (tmp_path / "grande.txt").write_text("a" * 100, encoding="utf-8")
    (tmp_path / "ok.txt").write_text("ok", encoding="utf-8")
    (tmp_path / ".oculto").mkdir()
    (tmp_path / ".oculto" / "s.md").write_text("segredo", encoding="utf-8")
    monkeypatch.setattr(ix, "MAX_BYTES", 50)
    r = await Indexador(banco, embedder, tmp_path).indexar()
    assert r["novos"] == 1 and r["erros"] == 0
    assert set(banco.arquivos_indexados()) == {"ok.txt"}


async def test_arquivo_indexado_que_passa_a_falhar_sai_do_indice(banco, embedder, tmp_path, monkeypatch):
    f = tmp_path / "a.txt"
    f.write_text("conteudo antigo unico", encoding="utf-8")
    idx = Indexador(banco, embedder, tmp_path)
    assert (await idx.indexar())["novos"] == 1

    def quebrado(_):
        raise OSError("travado")

    monkeypatch.setattr(ix, "extrair_texto", quebrado)
    st = f.stat()
    os.utime(f, (st.st_atime, st.st_mtime + 10))
    r = await idx.indexar()
    assert r["erros"] == 1
    assert banco.arquivos_indexados() == {}
    assert await idx.buscar("conteudo antigo unico") == []


class _Pagina:
    def __init__(self, lidas, texto):
        self.lidas, self.texto = lidas, texto

    def extract_text(self):
        self.lidas.append(1)
        return self.texto


def test_pdf_para_no_limite_de_paginas(monkeypatch, tmp_path):
    import pypdf

    lidas = []
    monkeypatch.setattr(pypdf, "PdfReader", lambda _: type("L", (), {"pages": [_Pagina(lidas, "x") for _ in range(2000)]}))
    texto = ix.extrair_texto(tmp_path / "grande.pdf")
    assert len(lidas) == ix.MAX_PAGINAS_PDF == 500
    assert texto.count("x") == 500


def test_pdf_e_docx_param_no_limite_de_caracteres(monkeypatch, tmp_path):
    import docx
    import pypdf

    monkeypatch.setattr(ix, "MAX_CARACTERES", 55)
    lidas = []
    monkeypatch.setattr(pypdf, "PdfReader", lambda _: type("L", (), {"pages": [_Pagina(lidas, "a" * 10) for _ in range(100)]}))
    assert 50 <= len(ix.extrair_texto(tmp_path / "a.pdf")) <= 55
    assert len(lidas) == 5  # as páginas depois do limite nem são extraídas

    paragrafos = [type("P", (), {"text": "b" * 10})() for _ in range(100)]
    monkeypatch.setattr(docx, "Document", lambda _: type("D", (), {"paragraphs": paragrafos}))
    assert 50 <= len(ix.extrair_texto(tmp_path / "a.docx")) <= 55


async def test_extracao_que_trava_estoura_o_prazo_e_nao_prende_a_indexacao(banco, embedder, tmp_path, monkeypatch):
    import threading

    (tmp_path / "trava.pdf").write_bytes(b"%PDF")
    (tmp_path / "ok.md").write_text("tudo certo aqui", encoding="utf-8")
    solta, chamadas = threading.Event(), []
    original = ix.extrair_texto

    def extrair(p):
        if p.suffix == ".pdf":
            chamadas.append(p.name)
            solta.wait(5)  # simula pypdf em laço infinito
            return "texto que chegou tarde"
        return original(p)

    monkeypatch.setattr(ix, "extrair_texto", extrair)
    monkeypatch.setattr(ix, "PRAZO_EXTRACAO", 0.2)
    idx = Indexador(banco, embedder, tmp_path)
    try:
        r = await asyncio.wait_for(idx.indexar(), 3)
        assert r["erros"] == 1 and r["novos"] == 1
        # a volta seguinte não prende outra thread no mesmo arquivo
        r = await asyncio.wait_for(idx.indexar(), 3)
        assert r["erros"] == 1 and chamadas == ["trava.pdf"]
        # arquivo mudou: tenta de novo
        st = (tmp_path / "trava.pdf").stat()
        os.utime(tmp_path / "trava.pdf", (st.st_atime, st.st_mtime + 10))
        await asyncio.wait_for(idx.indexar(), 3)
        assert chamadas == ["trava.pdf", "trava.pdf"]
    finally:
        solta.set()


async def test_buscar_limita_n_e_ve_reindexacao(banco, embedder, tmp_path):
    for i in range(25):
        (tmp_path / f"{i}.md").write_text(f"documento numero {i} sobre bolo", encoding="utf-8")
    idx = Indexador(banco, embedder, tmp_path)
    await idx.indexar()
    assert len(await idx.buscar("bolo", n=-1)) == 1
    assert len(await idx.buscar("bolo", n=1000)) == 20
    (tmp_path / "novo.md").write_text("manual da geladeira frost free", encoding="utf-8")
    await idx.indexar()
    assert (await idx.buscar("geladeira frost free", n=1))[0]["arquivo"] == "novo.md"

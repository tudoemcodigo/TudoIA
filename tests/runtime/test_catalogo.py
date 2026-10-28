from pathlib import Path

import pytest

from tudoia_painel.catalogo import carregar_catalogo, carregar_roteamento, provedores_ligados

FIX = Path(__file__).parent / "fixtures"
REAL = Path(__file__).parents[2] / "config"


def test_carrega_campos():
    cat = carregar_catalogo(FIX / "catalogo-mini.yaml")
    nv = cat.provedor("nvidia")
    assert nv.tier == "FREE" and nv.chave == "NVIDIA_NIM_API_KEY" and nv.limites == {"rpm": 40}
    assert nv.modelos[0].papeis == ("chat", "codigo", "agente", "rapido")
    assert nv.modelos[0].contexto == 131072 and nv.modelos[1].contexto is None
    assert nv.modelos[2].ativo is False and nv.modelos[0].ativo is True
    assert cat.provedor("anthropic").tier == "PAID"
    assert cat.provedor("cloudflare").chaves_extras == ("CLOUDFLARE_ACCOUNT_ID",)


def test_ligados_so_com_chave():
    cat = carregar_catalogo(FIX / "catalogo-mini.yaml")
    assert [p.chave_id for p in provedores_ligados(cat, {"NVIDIA_NIM_API_KEY": "x"})] == ["nvidia"]


def test_chave_extra_obrigatoria():
    cat = carregar_catalogo(FIX / "catalogo-mini.yaml")
    assert provedores_ligados(cat, {"CLOUDFLARE_API_KEY": "x"}) == []
    env = {"CLOUDFLARE_API_KEY": "x", "CLOUDFLARE_ACCOUNT_ID": "y"}
    assert [p.chave_id for p in provedores_ligados(cat, env)] == ["cloudflare"]


def test_chave_so_com_espacos_e_desligado():
    cat = carregar_catalogo(FIX / "catalogo-mini.yaml")
    assert provedores_ligados(cat, {"NVIDIA_NIM_API_KEY": "   "}) == []


def test_roteamento_sem_limiar_e_erro(tmp_path):
    p = tmp_path / "r.yaml"
    p.write_text("pesos: {}\nordem: {}\n")
    with pytest.raises(ValueError, match="limiar"):
        carregar_roteamento(p)


def test_catalogo_real_valido():
    cat = carregar_catalogo(REAL / "catalogo-modelos.yaml")
    nomes = [m.nome for p in cat.provedores for m in p.modelos]
    assert len(nomes) == len(set(nomes))
    assert {p.tier for p in cat.provedores} == {"FREE", "PAID"}
    assert "github" not in {p.chave_id for p in cat.provedores}


def test_roteamento_real_valido():
    rot = carregar_roteamento(REAL / "roteamento.yaml")
    assert rot["limiar"] == 3
    assert set(rot["ordem"]) == {"tudoia-nuvem", "tudoia-codigo", "tudoia-codigo-reserva", "tudoia-max", "tudoia-visao"}


def test_roteamento_limiar_texto_e_erro(tmp_path):
    p = tmp_path / "r.yaml"
    p.write_text("limiar: 3,5\npesos: {longo: 3}\nordem: {tudoia-nuvem: [a]}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="limiar"):
        carregar_roteamento(p)


def test_roteamento_palavras_sem_colchetes_e_erro(tmp_path):
    p = tmp_path / "r.yaml"
    p.write_text("limiar: 3\npesos: {longo: 3}\npalavras_dificeis: refator, analise\nordem: {tudoia-nuvem: [a]}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="palavras_dificeis"):
        carregar_roteamento(p)

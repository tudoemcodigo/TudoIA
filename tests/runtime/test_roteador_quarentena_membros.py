"""O hook usa os membros gravados no quarentena.json quando o limites.json (120 s) está velho ou ausente."""
from datetime import datetime, timedelta, timezone

import pytest

from tudoia_painel import caminhos
from tudoia_painel.catalogo import carregar_roteamento
from tudoia_painel.regras import carregar_modulo_regras

R = carregar_modulo_regras()
AGORA = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)
MEMBROS = {"tudoia-nuvem": ["groq/a", "nim/b"], "tudoia-codigo": ["nim/b"]}


def _quarentena(modelos, ts=AGORA, membros=MEMBROS):
    ate = (AGORA + timedelta(minutes=20)).isoformat()
    d = {"ts": ts.isoformat(), "modelos": {n: {"motivo": "t", "ate": ate} for n in modelos}}
    if membros is not None:
        d["membros"] = membros
    return d


def test_quarentena_membros_fresco_devolve_so_o_formato_valido():
    d = _quarentena([], membros={"tudoia-nuvem": ["a", 3, None], "x": "lixo"})
    assert R.quarentena_membros(d, AGORA) == {"tudoia-nuvem": ["a"]}


def test_quarentena_membros_velho_ou_malformado_e_ignorado():
    velho = _quarentena([], ts=AGORA - timedelta(hours=2))
    assert R.quarentena_membros(velho, AGORA) is None
    for lixo in (None, [], "x", {}, {"ts": "lixo", "membros": MEMBROS}, {"membros": MEMBROS}, {"ts": AGORA.isoformat(), "membros": [1]}):
        assert R.quarentena_membros(lixo, AGORA) is None


def test_combinar_usa_membros_da_quarentena_quando_limites_esta_velho():
    q = _quarentena(["groq/a", "nim/b"])
    esg, mem = R.combinar_limites({"ts": (AGORA - timedelta(minutes=10)).isoformat(), "esgotados": ["x"], "membros": {"g": ["x"]}}, q, AGORA)
    assert esg == {"groq/a", "nim/b"} and mem == MEMBROS


def test_combinar_prefere_os_membros_do_limites_fresco():
    lim = {"ts": AGORA.isoformat(), "esgotados": ["z"], "membros": {"tudoia-nuvem": ["z"]}}
    esg, mem = R.combinar_limites(lim, _quarentena(["groq/a"]), AGORA)
    assert esg == {"z", "groq/a"} and mem == {"tudoia-nuvem": ["z"]}


@pytest.mark.parametrize("lim,q", [(None, None), ([], "x"), ({"ts": 1}, {"modelos": 3}), ({}, {"modelos": {"a": {"ate": "lixo"}}, "membros": 7})])
def test_combinar_nunca_levanta_com_entrada_patologica(lim, q):
    esg, mem = R.combinar_limites(lim, q, AGORA)
    assert esg == set() and mem is None


def test_combinar_com_todos_em_quarentena_e_limites_velho_manda_para_o_local():
    """O bug visto ao vivo: sem limites.json fresco, `ordem` do roteamento.yaml (com membros sem chave) nunca fechava."""
    regras = carregar_roteamento(caminhos.raiz() / "config" / "roteamento.yaml")
    esg, mem = R.combinar_limites(None, _quarentena(["groq/a", "nim/b"]), AGORA)
    dados = {"model": "tudoia-auto", "messages": [{"role": "user", "content": "#nuvem diga ok"}]}
    d = R.decidir(dados, regras, esgotados=esg, membros=mem)
    assert d.grupo == "tudoia-local" and "provedores esgotados" in d.motivos
    # com um só membro fora, o grupo continua na nuvem (efeito de grupo)
    esg1, mem1 = R.combinar_limites(None, _quarentena(["groq/a"]), AGORA)
    dados = {"model": "tudoia-auto", "messages": [{"role": "user", "content": "#nuvem diga ok"}]}
    assert R.decidir(dados, regras, esgotados=esg1, membros=mem1).grupo == "tudoia-nuvem"

"""Falha de operação sai com status HTTP de erro no modelo único {"erro": {...}}, sem texto cru de exceção."""
import httpx

from tests.painel.test_painel import cenario  # noqa: F401  (fixture)


class _Quebrado:
    """httpx.Client cuja conexão falha com uma exceção que carrega um segredo no texto."""

    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        raise RuntimeError("token-interno-que-nao-pode-vazar")

    def __exit__(self, *a):
        return False


def test_chat_sem_motores_devolve_502_sem_vazar_a_excecao(cenario, monkeypatch):  # noqa: F811
    monkeypatch.setattr(httpx, "Client", _Quebrado)
    r = cenario.post("/api/chat/completions", json={"messages": [{"role": "user", "content": "oi"}]})
    assert r.status_code == 502
    erro = r.json()["erro"]
    assert erro["codigo"] == "modelo_indisponivel" and erro["extras"]["model"] == "tudoia-auto"
    assert "token-interno" not in r.text


def test_cancelar_com_comfyui_fora_devolve_502_sem_vazar_a_excecao(cenario, monkeypatch):  # noqa: F811
    monkeypatch.setattr(httpx, "Client", _Quebrado)
    r = cenario.post("/api/estudio/cancelar", json={})
    assert r.status_code == 502
    assert r.json()["erro"]["codigo"] == "falha_motor" and "token-interno" not in r.text


def test_extras_aparecem_no_corpo_de_erro_e_somem_quando_vazios():
    from tudoia_painel.erros import corpo_erro

    assert corpo_erro("x", "m")["erro"] == {"codigo": "x", "mensagem": "m"}
    assert corpo_erro("x", "m", extras={"servico_offline": "comfyui"})["erro"]["extras"] == {"servico_offline": "comfyui"}

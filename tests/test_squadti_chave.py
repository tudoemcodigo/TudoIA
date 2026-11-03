"""Chave virtual da SquadTI: o que o script pede ao LiteLLM, o que grava no .env e o que nunca mostra. Seam: httpx.MockTransport."""
import json

import httpx
import pytest

from scripts.squadti import chave

MESTRE = "sk-mestre-de-teste-123"
GERADA = "sk-squadti-gerada-abcdef"


@pytest.fixture
def cenario(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(f"LITELLM_MASTER_KEY={MESTRE}\nSQUADTI_API_KEY=\nTZ=UTC\n", encoding="utf-8")
    pedidos = []
    resposta = {"status": 200, "json": {"key": GERADA}}

    def tratar(request: httpx.Request) -> httpx.Response:
        pedidos.append((request.url.path, request.headers.get("authorization"),
                        json.loads(request.content) if request.content else None))
        return httpx.Response(resposta["status"], json=resposta["json"])

    monkeypatch.setattr(chave, "TRANSPORTE", httpx.MockTransport(tratar))
    return tmp_path, pedidos, resposta


def _env(raiz):
    linhas = (raiz / ".env").read_text(encoding="utf-8").splitlines()
    return dict(l.split("=", 1) for l in linhas if "=" in l)


def test_gera_com_alias_tag_validade_e_so_os_perfis_da_squad(cenario):
    raiz, pedidos, _ = cenario
    assert chave.gerar(raiz) == "criada"
    (caminho, auth, corpo), = pedidos
    assert caminho == "/key/generate" and auth == f"Bearer {MESTRE}"
    assert corpo["key_alias"] == "squadti" and corpo["metadata"] == {"tags": ["squadti"]} and corpo["duration"] == "90d"
    assert "tudoia-max" not in corpo["models"]   # o pago nunca entra na chave da Squad
    assert "tudoia-local-estrito" in corpo["models"] and "tudoia-auto" in corpo["models"]
    assert _env(raiz)["SQUADTI_API_KEY"] == GERADA and _env(raiz)["TZ"] == "UTC"
    assert list((raiz / "dados" / "backups" / "env").iterdir())   # backup do .env antes de gravar


def test_nao_troca_uma_chave_existente_nem_chama_o_litellm(cenario):
    raiz, pedidos, _ = cenario
    (raiz / ".env").write_text(f"LITELLM_MASTER_KEY={MESTRE}\nSQUADTI_API_KEY=sk-antiga-0123456789\n", encoding="utf-8")
    assert chave.gerar(raiz) == "ja-existe"
    assert pedidos == [] and _env(raiz)["SQUADTI_API_KEY"] == "sk-antiga-0123456789"


def test_rotacionar_apaga_o_alias_e_gera_outra(cenario):
    raiz, pedidos, _ = cenario
    (raiz / ".env").write_text(f"LITELLM_MASTER_KEY={MESTRE}\nSQUADTI_API_KEY=sk-antiga-0123456789\n", encoding="utf-8")
    assert chave.gerar(raiz, rotacionar=True) == "rotacionada"
    assert [p[0] for p in pedidos] == ["/key/delete", "/key/generate"] and pedidos[0][2] == {"key_aliases": ["squadti"]}
    assert _env(raiz)["SQUADTI_API_KEY"] == GERADA


def test_sem_master_key_falha_sem_chamar_a_rede(cenario):
    raiz, pedidos, _ = cenario
    (raiz / ".env").write_text("SQUADTI_API_KEY=\n", encoding="utf-8")
    with pytest.raises(chave.ErroChave) as e:
        chave.gerar(raiz)
    assert e.value.codigo == 2 and pedidos == []


def test_recusa_do_litellm_nao_vaza_o_corpo_e_nao_grava(cenario):
    raiz, _, resposta = cenario
    resposta.update(status=400, json={"error": {"message": "alias duplicado sk-vazamento-do-corpo"}})
    with pytest.raises(chave.ErroChave) as e:
        chave.gerar(raiz)
    assert e.value.codigo == 1 and "sk-vazamento" not in str(e.value) and "--rotacionar" in str(e.value)
    assert _env(raiz)["SQUADTI_API_KEY"] == ""


def test_litellm_fora_do_ar_vira_erro_de_conexao(cenario, monkeypatch):
    raiz, _, _ = cenario

    def cai(request):
        raise httpx.ConnectError("recusado", request=request)

    monkeypatch.setattr(chave, "TRANSPORTE", httpx.MockTransport(cai))
    with pytest.raises(chave.ErroChave) as e:
        chave.gerar(raiz)
    assert e.value.codigo == 2


def test_url_fora_do_loopback_e_recusada(cenario, monkeypatch):
    raiz, pedidos, _ = cenario
    monkeypatch.setenv("TUDOIA_LITELLM_URL", "http://evil.example:4000")
    with pytest.raises(chave.ErroChave):
        chave.gerar(raiz)
    assert pedidos == []


def test_main_nao_imprime_a_chave_e_devolve_codigo(cenario, monkeypatch, capsys):
    raiz, _, _ = cenario
    monkeypatch.setattr(chave, "RAIZ", raiz)
    assert chave.main([]) == 0
    saida = capsys.readouterr()
    assert GERADA not in saida.out + saida.err and "criada" in saida.out
    assert chave.main([]) == 0   # segunda vez: já existe, sem nova chamada
    assert "já existe" in capsys.readouterr().out

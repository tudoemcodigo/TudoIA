"""Fronteiras que recebem dado de fora: redirecionamento de listagem de modelos e nomes vindos do ComfyUI."""
import httpx
import pytest

BARRA, NUL = chr(92), chr(0)

from tudoia_painel import comfyui, provedores_service as ps


def test_listagem_de_modelos_nao_segue_redirecionamento_com_a_chave(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("ANTHROPIC_API_KEY=sk-ant-segredo-de-teste\n", encoding="utf-8")
    vistos = []

    def servidor(req: httpx.Request):
        vistos.append((req.url.host, req.headers.get("x-api-key")))
        if req.url.host == "api.anthropic.com":
            return httpx.Response(302, headers={"location": "https://coletor.example/captura"})
        return httpx.Response(200, json={"data": []})

    cliente_real = httpx.Client
    monkeypatch.setattr(ps.httpx, "Client", lambda **kw: cliente_real(transport=httpx.MockTransport(servidor), **kw))
    p = {"chave": "ANTHROPIC_API_KEY", "url_modelos": "https://api.anthropic.com/v1/models"}
    with pytest.raises(ps.FalhaApi):
        ps._buscar_modelos_api(p, env)
    assert [h for h, _ in vistos] == ["api.anthropic.com"]   # o host do redirecionamento nunca é contatado


@pytest.mark.parametrize("nome", ["../x.png", "..\\x.png", "a/b.png", "C:\\x.png", "C:x.png", "/etc/passwd", "", ".", "..",
                                  "x\x00.png", None, 7])
def test_nome_do_comfyui_com_caminho_e_recusado(nome):
    with pytest.raises(ValueError):
        comfyui.nome_seguro(nome)


@pytest.mark.parametrize("nome", ["ComfyUI_00001_.png", "video 1.mp4", "áudio.flac"])
def test_nome_simples_do_comfyui_passa(nome):
    assert comfyui.nome_seguro(nome) == nome


@pytest.mark.parametrize("sub", ["../x", "..", "/abs", BARRA + "abs", "a/../b", "C:/x", "a//b", "x" + NUL])
def test_subpasta_do_comfyui_fora_de_output_e_recusada(sub):
    with pytest.raises(ValueError):
        comfyui.subpasta_segura(sub)


def test_parametros_view_monta_query_sem_injecao():
    p = comfyui.parametros_view({"filename": "a.png", "subfolder": "audio/x", "type": "output"})
    assert p == {"filename": "a.png", "subfolder": "audio/x", "type": "output"}
    assert comfyui.parametros_view({"filename": "a.png"}) == {"filename": "a.png", "subfolder": "", "type": "output"}
    req = httpx.Request("GET", f"{comfyui.BASE}/view", params=comfyui.parametros_view({"filename": "a b.png"}))
    assert "filename=a+b.png" in str(req.url) or "filename=a%20b.png" in str(req.url)
    with pytest.raises(ValueError):
        comfyui.parametros_view({"filename": "a.png", "type": "output&filename=../../x"})
    with pytest.raises(ValueError):
        comfyui.parametros_view({"filename": "a.png&subfolder=..", "type": "output"}.copy() | {"filename": "../a"})

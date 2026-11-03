"""Estúdio: reescrita de prompt só quando pedida, seed 0 respeitada, inpaint sem máscara cinza, quadros do Wan 4n+1,
erro de nó do ComfyUI detectado e cancelamento por trabalho."""
import pytest
from pydantic import ValidationError

from tests.painel.test_painel import cenario  # noqa: F401  (fixture)
from tudoia_painel import estudio_servico
from tudoia_painel.rotas import estudio_musica
from tudoia_painel.schemas import CancelarEstudioReq, GerarMusicaReq, GerarVideoReq, InpaintImagemReq


# ------------------------------------------------------------ schemas
def test_otimizar_prompt_e_desligado_por_padrao():
    assert GerarMusicaReq(style="x").otimizar_prompt is False
    assert GerarVideoReq(prompt="x").otimizar_prompt is False
    assert InpaintImagemReq(imagem_base="a.png", mascara_base64="eA==", prompt="x").otimizar_prompt is False


@pytest.mark.parametrize("seed", [-1, 2**32])
def test_seed_fora_da_faixa_e_recusada(seed):
    with pytest.raises(ValidationError):
        GerarMusicaReq(style="x", seed=seed)


def test_modo_off_nao_existe_no_yue2():
    with pytest.raises(ValidationError):
        GerarMusicaReq(style="x", modo="off")


@pytest.mark.parametrize("pid", ["../../etc", "abc", "x" * 65])
def test_cancelar_recusa_prompt_id_estranho(pid):
    with pytest.raises(ValidationError):
        CancelarEstudioReq(prompt_id=pid)


# ------------------------------------------------------------ rota de música
@pytest.fixture
def musica_falsa(monkeypatch):
    chamadas = {}
    monkeypatch.setattr(estudio_musica, "_arbitrar_vram_para_estudio", lambda: None)
    monkeypatch.setattr(estudio_musica.infra, "porta_aberta", lambda porta: True)

    def otimizar(*a, **k):
        chamadas["otimizou"] = True
        return ("estilo reescrito", True, "ok")

    def executar(**k):
        chamadas["exec"] = k
        return {"ok": True, "nome_arquivo": "teste.flac", "prompt_id": "abc"}

    monkeypatch.setattr(estudio_musica, "_otimizar_prompt_musica", otimizar)
    monkeypatch.setattr(estudio_musica, "_executar_comfyui_musica", executar)
    monkeypatch.setattr(estudio_musica, "_registrar_historico_visual", lambda *a, **k: None)
    return chamadas


def test_sem_pedir_o_estilo_vai_como_foi_escrito_e_seed_zero_vale(cenario, musica_falsa):  # noqa: F811
    r = cenario.post("/api/estudio/gerar-musica", json={"style": "calm guitar", "seed": 0})
    assert r.status_code == 200, r.text
    assert "otimizou" not in musica_falsa
    assert musica_falsa["exec"]["style_texto"] == "calm guitar"
    assert musica_falsa["exec"]["seed"] == 0


def test_pedindo_a_reescrita_o_otimizador_e_usado(cenario, musica_falsa):  # noqa: F811
    r = cenario.post("/api/estudio/gerar-musica", json={"style": "violão calmo", "otimizar_prompt": True})
    assert r.status_code == 200, r.text
    assert musica_falsa.get("otimizou") is True
    assert musica_falsa["exec"]["style_texto"] == "estilo reescrito"


# ------------------------------------------------------------ grafos e histórico do ComfyUI
@pytest.mark.parametrize("duracao,esperado", [(5, 121), (3, 73), (10, 121)])
def test_wan_5b_usa_4n_mais_1_quadros_ate_o_comprimento_de_treino(tmp_path, duracao, esperado):
    grafo, _nome, _minimax = estudio_servico._preparar_grafo_video(
        tmp_path, "local:wan2.2_ti2v_5B_fp16.safetensors", "barco", 1, "720p", duracao, 24, None, tmp_path)
    comprimentos = [n["inputs"]["length"] for n in grafo.values() if "length" in n.get("inputs", {})]
    assert comprimentos == [esperado]
    assert (esperado - 1) % 4 == 0


def test_erro_do_historico_traz_o_no_e_a_mensagem():
    entrada = {"status": {"status_str": "error", "messages": [
        ["execution_start", {}],
        ["execution_error", {"node_type": "KSampler", "exception_message": "CUDA out of memory"}],
    ]}}
    assert estudio_servico.erro_do_historico(entrada) == "KSampler: CUDA out of memory"
    assert estudio_servico.erro_do_historico({"status": {"status_str": "success"}}) is None
    assert estudio_servico.erro_do_historico({}) is None


def test_inpaint_nao_usa_o_no_que_pinta_a_mascara_de_cinza():
    import pathlib
    codigo = (pathlib.Path(estudio_servico.__file__).parent / "rotas" / "estudio_imagem.py").read_text(encoding="utf-8")
    assert "VAEEncodeForInpaint" not in codigo
    assert "SetLatentNoiseMask" in codigo

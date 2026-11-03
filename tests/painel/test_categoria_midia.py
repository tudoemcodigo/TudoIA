"""Categoria dos modelos do ComfyUI: a pasta diz como o arquivo é carregado; o nome desempata música e vídeo."""
import pytest

from tudoia_painel.modelos_service import categoria_do_arquivo


@pytest.mark.parametrize("pasta,arquivo,esperado", [
    ("checkpoints", "yue2_3b_int8_convrot.safetensors", "Modelo de música"),
    ("checkpoints", "ace_step_v1_3.5b.safetensors", "Modelo de música"),
    ("checkpoints", "Juggernaut-XL_v9_RunDiffusionPhoto_v2.safetensors", "Checkpoint de imagem (SDXL/Flux)"),
    ("diffusion_models", "wan2.2_ti2v_5B_fp16.safetensors", "Modelo de vídeo"),
    ("diffusion_models", "flux1-dev.safetensors", "Modelo de difusão (vídeo e imagem)"),
    ("vae", "wan2.2_vae.safetensors", "VAE (autoencoder)"),
    ("text_encoders", "umt5_xxl_fp8_e4m3fn_scaled.safetensors", "Codificador de texto (T5/Qwen)"),
])
def test_categoria_pelo_nome_e_pela_pasta(pasta, arquivo, esperado):
    assert categoria_do_arquivo(pasta, arquivo) == esperado


def test_nome_de_musica_fora_das_pastas_de_modelo_nao_muda_a_categoria():
    # Um VAE com "yue" no nome continua VAE: só checkpoints/difusão/unet são reclassificados.
    assert categoria_do_arquivo("vae", "yue_vae.safetensors") == "VAE (autoencoder)"


def test_pasta_desconhecida_usa_o_proprio_nome():
    assert categoria_do_arquivo("pasta_nova", "x.safetensors") == "pasta_nova"

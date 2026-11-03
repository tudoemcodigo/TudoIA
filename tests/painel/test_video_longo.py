"""Vídeo longo: plano de clipes, grafos com a duração pedida, LTX-2.3, corpo do pedido à nuvem, deployments do
LiteLLM, executor (encadeamento, repetição, retomada sem pagar duas vezes, cancelamento, reinício do painel),
rotas (confirmação, chave, teto, travessia) e a montagem real com o PyAV do ComfyUI quando ele existe."""
import json
import subprocess
import time
from pathlib import Path

import httpx
import pytest

from tests.painel.test_painel import cenario  # noqa: F401  (fixture)
from tudoia_painel import estudio_servico as es
from tudoia_painel import video_longo as vl
from tudoia_painel import video_midia
from tudoia_painel import video_nuvem as vn
from tudoia_painel.gerador import gerar_config
from tudoia_painel.catalogo import carregar_catalogo, carregar_roteamento

REPO = Path(__file__).resolve().parents[2]
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


# ------------------------------------------------------------ plano de clipes
@pytest.mark.parametrize("total,validas,esperado", [
    (60, tuple(range(1, 6)), [5] * 12),
    (23, tuple(range(1, 11)), [8, 8, 7]),
    (25, tuple(range(5, 16)), [13, 12]),
    (7, (6, 8, 10, 12, 14, 16, 18, 20), [8]),          # duração fixa do provedor: sobra é cortada na montagem
    (3, tuple(range(5, 16)), [5]),                      # pedido menor que o mínimo do provedor
    (60, tuple(range(2, 31)), [30, 30]),
])
def test_plano_usa_o_menor_numero_de_clipes_validos(total, validas, esperado):
    plano = vl.planejar_segmentos(total, validas)
    assert plano == esperado
    assert sum(plano) >= total
    assert all(d in validas for d in plano)


@pytest.mark.parametrize("total,validas", [(0, (5,)), (10, ())])
def test_plano_recusa_entrada_invalida(total, validas):
    with pytest.raises(ValueError):
        vl.planejar_segmentos(total, validas)


# ------------------------------------------------------------ quadros e grafos locais
@pytest.mark.parametrize("chave,duracao,quadros", [
    ("wan14b", 5, 81), ("wan14b", 3, 49), ("wan14b", 30, 81),
    ("wan5b", 5, 121), ("wan5b", 3, 73),
    ("minimax", 5, 124), ("minimax", 10, 243), ("minimax", 60, 243),
    ("ltx23", 5, 121), ("ltx23", 20, 481), ("ltx23", 1, 25),
])
def test_quadros_na_grade_de_cada_modelo(chave, duracao, quadros):
    perfil = es.PERFIS_VIDEO_LOCAL[chave]
    q = es.quadros_video(perfil, duracao)
    assert q == quadros
    if chave == "minimax":
        assert q % 17 == 5
    else:
        assert (q - 1) % (8 if chave == "ltx23" else 4) == 0


def _comprimentos(grafo):
    return [n["inputs"]["length"] for n in grafo.values() if "length" in n.get("inputs", {})]


def _fps(grafo):
    return [n["inputs"]["fps"] for n in grafo.values() if n["class_type"] == "CreateVideo"]


def test_wan_14b_i2v_respeita_a_duracao_e_grava_em_16_fps(tmp_path):
    img = tmp_path / "ref.png"
    img.write_bytes(PNG)
    grafo, nome, _ = es._preparar_grafo_video(tmp_path, "video-wan14b-i2v", "barco", 1, "720p", 3, 24, img, tmp_path)
    assert nome == "video-wan14b-i2v"
    assert _comprimentos(grafo) == [49]          # antes: 81 fixo, qualquer duração
    assert _fps(grafo) == [16.0]


def test_wan_14b_t2v_nao_mistura_24_fps_com_saida_de_16(tmp_path):
    grafo, nome, _ = es._preparar_grafo_video(tmp_path, "video-wan14b-t2v", "barco", 1, "720p", 5, 24, None, tmp_path)
    assert nome == "video-wan14b-t2v"
    assert _comprimentos(grafo) == [81]          # antes: 120 a 16 fps = 7,3 s para um pedido de 5 s
    assert _fps(grafo) == [16.0]


def test_minimax_grava_em_24_fps_mesmo_com_outro_fps_pedido(tmp_path):
    grafo, _, minimax = es._preparar_grafo_video(tmp_path, "video-minimax-h3", "barco", 1, "720p", 10, 30, None, tmp_path)
    assert minimax is True
    assert _comprimentos(grafo) == [243]
    assert _fps(grafo) == [24]


def test_ltx23_texto_tem_audio_e_sem_quadro_inicial(tmp_path):
    grafo, nome, minimax = es._preparar_grafo_video(tmp_path, "video-ltx23", "barco", 7, "480p", 20, 24, None, tmp_path)
    assert (nome, minimax) == ("video-ltx23", False)
    tipos = {n["class_type"] for n in grafo.values()}
    assert {"UnetLoaderGGUF", "DualCLIPLoaderGGUF", "VAELoaderKJ", "LTXVAudioVAEDecode", "SaveVideo"} <= tipos
    assert "LTXVImgToVideoInplace" not in tipos
    assert grafo["8"]["inputs"]["length"] == 481 and grafo["9"]["inputs"]["frames_number"] == 481
    assert (grafo["8"]["inputs"]["width"], grafo["8"]["inputs"]["height"]) == (832, 480)
    assert grafo["11"]["inputs"]["noise_seed"] == 7


def test_ltx23_em_720p_limita_o_clipe_a_10_s(tmp_path):
    grafo, _, _ = es._preparar_grafo_video(tmp_path, "video-ltx23", "barco", 1, "720p", 20, 24, None, tmp_path)
    assert grafo["8"]["inputs"]["length"] == 241


def test_ltx23_com_quadro_inicial_condiciona_o_latente(tmp_path):
    img = tmp_path / "ref.png"
    img.write_bytes(PNG)
    grafo, _, _ = es._preparar_grafo_video(tmp_path, "video-ltx23", "barco", 1, "480p", 5, 24, img, tmp_path)
    assert grafo["33"]["class_type"] == "LTXVImgToVideoInplace"
    assert grafo["10"]["inputs"]["video_latent"] == ["33", 0]
    assert grafo["30"]["inputs"]["image"].startswith("ref_")
    assert (tmp_path / grafo["30"]["inputs"]["image"]).is_file()   # copiado para o input do ComfyUI


def test_video_do_historico_acha_o_mp4():
    entrada = {"outputs": {"9": {"images": [{"filename": "a.png"}]}, "20": {"videos": [{"filename": "x.mp4", "subfolder": "video"}]}}}
    assert es.video_do_historico(entrada)["filename"] == "x.mp4"
    assert es.video_do_historico({"outputs": {}}) is None


# ------------------------------------------------------------ catálogo e pedido à nuvem
@pytest.fixture
def catalogo():
    return {m.nome: m for m in vn.carregar_catalogo_video(REPO / "config" / "video-nuvem.yaml")}


def test_catalogo_do_repo_carrega_todos_os_modelos(catalogo):
    assert set(catalogo) == {"wan-3", "minimax-h3", "kling-3", "seedance-2-fast", "ltx-23-fast"}
    assert catalogo["wan-3"].duracoes_validas()[-1] == 30
    assert catalogo["ltx-23-fast"].duracoes_validas() == (6, 8, 10, 12, 14, 16, 18, 20)
    assert all(m.preco("720p") > 0 for m in catalogo.values())


def test_catalogo_recusa_provedor_sem_suporte(tmp_path):
    arq = tmp_path / "v.yaml"
    arq.write_text("modelos:\n  - {nome: x, provedor: outro, chave: K, t2v: a/b, duracao: {min: 1, max: 5}}\n", encoding="utf-8")
    with pytest.raises(ValueError):
        vn.carregar_catalogo_video(arq)


def test_corpo_texto_tem_tipos_do_provedor_e_nao_usa_campos_openai(catalogo):
    corpo = vn.corpo_pedido(catalogo["kling-3"], "cena", 10, "720p", 5, None)
    assert corpo["model"] == "video/kling-3"
    extra = corpo["extra_body"]
    assert extra["duration"] == "10"                     # Kling: enum de string
    assert extra["aspect_ratio"] == "16:9" and extra["generate_audio"] is True and extra["seed"] == 5
    assert "resolution" not in extra and "seconds" not in corpo and "input_reference" not in corpo

    wan = vn.corpo_pedido(catalogo["wan-3"], "cena", 30, "480p", None, None)["extra_body"]
    assert wan["duration"] == 30 and wan["resolution"] == "480p" and "seed" not in wan


def test_corpo_com_quadro_vai_para_o_endpoint_i2v_como_data_uri(tmp_path, catalogo):
    img = tmp_path / "q.jpg"
    img.write_bytes(b"\xff\xd8\xff" + b"0" * 100)
    corpo = vn.corpo_pedido(catalogo["minimax-h3"], "cena", 5, "720p", 1, img)
    assert corpo["model"] == "video/minimax-h3-i2v"
    extra = corpo["extra_body"]
    assert extra["image_url"].startswith("data:image/jpeg;base64,")
    assert extra["resolution"] == "768P" and "aspect_ratio" not in extra   # i2v segue o quadro
    assert vn.corpo_pedido(catalogo["wan-3"], "c", 5, "720p", 1, img)["extra_body"]["start_image_url"].startswith("data:")


def test_imagem_grande_demais_nao_vai(tmp_path, monkeypatch):
    img = tmp_path / "g.jpg"
    img.write_bytes(b"0" * 10)
    monkeypatch.setattr(vn, "LIMITE_IMAGEM", 5)
    with pytest.raises(ValueError):
        vn.imagem_data_uri(img)


def test_deployments_so_com_chave_e_sem_segredo_no_config(catalogo):
    modelos = list(catalogo.values())
    assert vn.deployments_video(modelos, {}) == []
    deps = vn.deployments_video(modelos, {"FAL_AI_API_KEY": "fal-segredo-123"})
    nomes = {d["model_name"] for d in deps}
    assert {"video/wan-3", "video/wan-3-i2v", "video/kling-3", "video/ltx-23-fast-i2v"} <= nomes
    assert "fal-segredo-123" not in json.dumps(deps)
    wan = next(d for d in deps if d["model_name"] == "video/wan-3")
    assert wan["litellm_params"]["model"] == "fal_ai/alibaba/wan-3.0/text-to-video"
    assert wan["litellm_params"]["api_key"] == "os.environ/FAL_AI_API_KEY"
    assert wan["model_info"]["output_cost_per_second_480p"] == 0.05


def test_config_do_litellm_tem_video_fora_de_grupos_e_fallbacks(catalogo):
    cat = carregar_catalogo(REPO / "config" / "catalogo-modelos.yaml")
    rot = carregar_roteamento(REPO / "config" / "roteamento.yaml")
    env = {"FAL_AI_API_KEY": "x"}
    cfg = gerar_config(cat, env, rot, vn.deployments_video(list(catalogo.values()), env))
    nomes = [m["model_name"] for m in cfg["model_list"]]
    assert "video/seedance-2-fast" in nomes
    texto_fallbacks = json.dumps(cfg["router_settings"]["fallbacks"])
    assert "video/" not in texto_fallbacks


# ------------------------------------------------------------ cliente do LiteLLM
def _cliente(handler):
    return vn.ClienteVideoLiteLLM("sk-mestra", base="http://litellm.teste", transporte=httpx.MockTransport(handler))


def test_cliente_cria_consulta_e_baixa(tmp_path):
    vistos = []

    def handler(req: httpx.Request):
        vistos.append(req)
        assert req.headers["authorization"] == "Bearer sk-mestra"
        if req.method == "POST":
            corpo = json.loads(req.content)
            assert corpo["extra_body"]["duration"] == 5
            return httpx.Response(200, json={"id": "vid_1", "status": "queued"})
        if req.url.path.endswith("/content"):
            return httpx.Response(200, content=b"mp4" * 1000)
        return httpx.Response(200, json={"id": "vid_1", "status": "completed"})

    c = _cliente(handler)
    assert c.criar({"model": "video/wan-3", "prompt": "p", "extra_body": {"duration": 5}}) == "vid_1"
    assert c.status("vid_1") == ("pronto", None)
    destino = tmp_path / "c.mp4"
    assert c.baixar("vid_1", destino) == 3000 and destino.read_bytes().startswith(b"mp4")
    assert not (tmp_path / "c.mp4.parcial").exists()


def test_cliente_falha_do_provedor_e_429():
    def handler(req):
        if req.method == "POST":
            return httpx.Response(429, json={"error": {"message": "rate limit"}})
        return httpx.Response(200, json={"status": "failed", "error": {"message": "conteúdo bloqueado"}})

    c = _cliente(handler)
    with pytest.raises(vn.ErroNuvem) as e:
        c.criar({"model": "m", "prompt": "p"})
    assert e.value.transitorio and "rate limit" in str(e.value)
    assert c.status("x") == ("erro", "conteúdo bloqueado")


def test_cliente_timeout_no_envio_nao_e_repetido():
    def handler(req):
        raise httpx.ReadTimeout("lento", request=req)

    with pytest.raises(vn.ErroNuvem) as e:
        _cliente(handler).criar({"model": "m", "prompt": "p"})
    assert e.value.transitorio is False   # pode ter chegado ao provedor: repetir pagaria duas vezes


def test_cliente_recusa_download_acima_do_limite(tmp_path, monkeypatch):
    monkeypatch.setattr(vn, "LIMITE_DOWNLOAD", 10)
    c = _cliente(lambda req: httpx.Response(200, content=b"x" * 100))
    with pytest.raises(vn.ErroNuvem):
        c.baixar("v", tmp_path / "a.mp4")
    assert not list(tmp_path.iterdir())


# ------------------------------------------------------------ roteiro de cenas
def test_cenas_do_ollama_validas(monkeypatch):
    monkeypatch.setattr(vl, "_chamar_ollama_prompt", lambda *a: 'ok ["um barco", "o porto"] fim')
    assert vl.dividir_em_cenas("barco", 2) == ["um barco", "o porto"]


@pytest.mark.parametrize("resposta", ["", "nada", '["só uma"]', '[1, 2]', '{"a": 1}', '["' + "x" * 3000 + '", "b"]'])
def test_cenas_com_saida_ruim_viram_o_prompt_numerado(monkeypatch, resposta):
    monkeypatch.setattr(vl, "_chamar_ollama_prompt", lambda *a: resposta)
    assert vl.dividir_em_cenas("barco", 2) == ["barco. Scene 1 of 2.", "barco. Scene 2 of 2."]


# ------------------------------------------------------------ executor
class MidiaFalsa:
    ErroMidia = video_midia.ErroMidia

    def __init__(self):
        self.montagens = []
        self.quadros = []

    def info(self, raiz, video):
        return {"largura": 832, "altura": 480, "fps": 24.0, "tem_audio": True, "duracao_s": 5}

    def ultimo_quadro(self, raiz, video, destino):
        self.quadros.append(Path(video).name)
        Path(destino).write_bytes(b"\xff\xd8\xff")
        return {}

    def primeiro_quadro(self, raiz, video, destino):
        Path(destino).write_bytes(b"\xff\xd8\xff")
        return {}

    def montar(self, raiz, saida, entradas, largura, altura, fps, duracao_max_s=None, trilha=None):
        self.montagens.append({"entradas": [Path(e).name for e in entradas], "duracao_max_s": duracao_max_s, "trilha": trilha})
        Path(saida).write_bytes(b"final")
        return {}


class MotorFalso:
    def __init__(self, nuvem=False, falhas_envio=(), consultas_ate_pronto=1, estados=None):
        self.nuvem = nuvem
        self.envios = []
        self.falhas_envio = list(falhas_envio)   # ErroMotor a levantar nos primeiros envios
        self.consultas_ate_pronto = consultas_ate_pronto
        self.estados = estados or {}            # ref -> lista de respostas de consultar
        self.consultas = {}
        self.cancelados = []

    def submeter(self, prompt, duracao_s, imagem, seed):
        if self.falhas_envio:
            raise self.falhas_envio.pop(0)
        ref = f"ref{len(self.envios)}"
        self.envios.append({"prompt": prompt, "duracao_s": duracao_s, "imagem": imagem.name if imagem else None, "seed": seed})
        return ref

    def consultar(self, ref):
        if ref in self.estados and self.estados[ref]:
            return self.estados[ref].pop(0)
        self.consultas[ref] = self.consultas.get(ref, 0) + 1
        return ("pronto", None) if self.consultas[ref] >= self.consultas_ate_pronto else ("andamento", None)

    def baixar(self, ref, destino):
        Path(destino).write_bytes(b"clipe-" + ref.encode())

    def cancelar(self, ref):
        self.cancelados.append(ref)


def _executor(tmp_path, motor, midia=None, **kw):
    pasta_videos = tmp_path / "videos"
    pasta_videos.mkdir(parents=True, exist_ok=True)
    return vl.ExecutorVideoLongo(tmp_path, pasta_videos, lambda pedido: motor, intervalo_s=0,
                                 midia=midia or MidiaFalsa(), dormir=lambda s: None, **kw)


def _pedido(**kw):
    p = {"prompt": "um barco no mar", "motor": "comfyui", "modelo": "video-wan14b-t2v", "resolucao": "480p",
         "duracao_total_s": 12, "modo": "continuo", "cenas": [], "seed": 100, "referencia": None, "trilha": None}
    p.update(kw)
    return p


def _esperar_final(ex, tid, limite=10.0):
    fim = time.time() + limite
    while time.time() < fim:
        t = ex.obter(tid)
        if t["estado"] in vl.ESTADOS_FINAIS:
            return t
        time.sleep(0.02)
    raise AssertionError(f"trabalho não terminou: {ex.obter(tid)}")


def test_executor_encadeia_o_ultimo_quadro_e_monta_no_total(tmp_path):
    motor, midia = MotorFalso(consultas_ate_pronto=2), MidiaFalsa()
    ex = _executor(tmp_path, motor, midia)
    t = _esperar_final(ex, ex.criar(_pedido(), [5, 5, 2], None)["id"])
    assert t["estado"] == "concluido", t
    assert [e["imagem"] for e in motor.envios] == [None, "quadro_00.jpg", "quadro_01.jpg"]
    assert midia.quadros == ["clipe_00.mp4", "clipe_01.mp4"]
    assert [e["seed"] for e in motor.envios] == [100, 101, 102]
    assert midia.montagens == [{"entradas": ["clipe_00.mp4", "clipe_01.mp4", "clipe_02.mp4"], "duracao_max_s": 12.0, "trilha": None}]
    assert (tmp_path / "videos" / f"video_longo_{t['id']}.mp4").read_bytes() == b"final"
    salvo = json.loads((tmp_path / "dados" / "estudio" / "video-longo" / t["id"] / "trabalho.json").read_text(encoding="utf-8"))
    assert salvo["estado"] == "concluido" and all(s["estado"] == "concluido" for s in salvo["segmentos"])


def test_executor_modo_cenas_nao_encadeia_quadros(tmp_path):
    motor, midia = MotorFalso(), MidiaFalsa()
    ex = _executor(tmp_path, motor, midia)
    t = _esperar_final(ex, ex.criar(_pedido(modo="cenas", cenas=["cena A", "cena B"]), [5, 5], None)["id"])
    assert t["estado"] == "concluido"
    assert [(e["prompt"], e["imagem"]) for e in motor.envios] == [("cena A", None), ("cena B", None)]
    assert midia.quadros == []


def test_executor_referencia_de_video_usa_o_primeiro_quadro(tmp_path):
    ref = tmp_path / "ref.mp4"
    ref.write_bytes(b"v")
    motor = MotorFalso()
    ex = _executor(tmp_path, motor)
    t = _esperar_final(ex, ex.criar(_pedido(referencia=str(ref)), [5], None)["id"])
    assert t["estado"] == "concluido"
    assert motor.envios[0]["imagem"] == "referencia.jpg"


def test_executor_repete_falha_transitoria_e_desiste_da_permanente(tmp_path):
    motor = MotorFalso(falhas_envio=[vl.ErroMotor("rede", transitorio=True), vl.ErroMotor("rede", transitorio=True)])
    ex = _executor(tmp_path, motor)
    assert _esperar_final(ex, ex.criar(_pedido(), [5], None)["id"])["estado"] == "concluido"

    motor2 = MotorFalso(falhas_envio=[vl.ErroMotor("prompt recusado pelo provedor")])
    ex2 = _executor(tmp_path / "b", motor2)
    t = _esperar_final(ex2, ex2.criar(_pedido(), [5], None)["id"])
    assert t["estado"] == "erro" and "recusado" in t["erro"]
    assert motor2.envios == []


def test_retomar_refaz_so_o_clipe_que_falhou(tmp_path):
    motor = MotorFalso(estados={"ref1": [("erro", "CUDA out of memory")]})
    ex = _executor(tmp_path, motor)
    tid = ex.criar(_pedido(), [5, 5, 2], None)["id"]
    t = _esperar_final(ex, tid)
    assert t["estado"] == "erro" and "out of memory" in t["erro"]
    assert [s["estado"] for s in t["segmentos"]] == ["concluido", "erro", "pendente"]
    ex.retomar(tid)
    t = _esperar_final(ex, tid)
    assert t["estado"] == "concluido"
    assert len(motor.envios) == 4   # 2 da 1ª rodada + o clipe 2 refeito + o 3º; o 1º não foi gerado de novo


def test_reinicio_do_painel_interrompe_e_retomar_consulta_o_clipe_ja_enviado(tmp_path):
    pasta = tmp_path / "dados" / "estudio" / "video-longo" / "vl_0123456789ab"
    pasta.mkdir(parents=True)
    (pasta / "clipe_00.mp4").write_bytes(b"pronto")
    trabalho = {"id": "vl_0123456789ab", "criado": "2026-10-30T10:00:00", "estado": "executando", "fase": "Gerando",
                "pedido": _pedido(motor="nuvem", modelo="wan-3"), "custo_estimado_usd": 1.0, "video_final": None, "erro": None,
                "segmentos": [
                    {"indice": 0, "duracao_s": 6, "prompt": "p", "estado": "concluido", "ref": "a", "arquivo": "clipe_00.mp4", "erro": None},
                    {"indice": 1, "duracao_s": 6, "prompt": "p", "estado": "enviado", "ref": "ja-pago", "arquivo": None, "erro": None},
                ]}
    (pasta / "trabalho.json").write_text(json.dumps(trabalho), encoding="utf-8")
    motor = MotorFalso(nuvem=True)
    ex = _executor(tmp_path, motor)
    assert ex.obter("vl_0123456789ab")["estado"] == "interrompido"   # nada recomeça sozinho
    ex.retomar("vl_0123456789ab")
    t = _esperar_final(ex, "vl_0123456789ab")
    assert t["estado"] == "concluido"
    assert motor.envios == []                       # o clipe enviado antes do reinício não foi pago de novo
    assert motor.consultas.get("ja-pago") == 1


def test_cancelar_durante_a_geracao(tmp_path):
    motor = MotorFalso(consultas_ate_pronto=10**9)
    ex = _executor(tmp_path, motor)
    tid = ex.criar(_pedido(), [5, 5], None)["id"]
    fim = time.time() + 5
    while not motor.envios and time.time() < fim:
        time.sleep(0.01)
    ex.cancelar(tid)
    t = _esperar_final(ex, tid)
    assert t["estado"] == "cancelado"
    assert motor.cancelados == ["ref0"]


def test_comfyui_que_esqueceu_o_trabalho_refaz_o_clipe_uma_vez(tmp_path):
    motor = MotorFalso(estados={"ref0": [("sumiu", None)]})
    ex = _executor(tmp_path, motor)
    t = _esperar_final(ex, ex.criar(_pedido(), [5], None)["id"])
    assert t["estado"] == "concluido" and len(motor.envios) == 2


def test_falha_inesperada_nao_deixa_o_trabalho_preso_em_executando(tmp_path):
    def fabrica(pedido):
        raise KeyError("modelo sumiu do catálogo")

    pasta_videos = tmp_path / "videos"
    pasta_videos.mkdir()
    ex = vl.ExecutorVideoLongo(tmp_path, pasta_videos, fabrica, intervalo_s=0, midia=MidiaFalsa(), dormir=lambda s: None)
    t = _esperar_final(ex, ex.criar(_pedido(), [5], None)["id"])
    assert t["estado"] == "erro" and "KeyError" in t["erro"]


def test_falha_na_montagem_vira_erro_legivel(tmp_path):
    class MidiaQuebrada(MidiaFalsa):
        def montar(self, *a, **k):
            raise video_midia.ErroMidia("libx264 indisponível")

    ex = _executor(tmp_path, MotorFalso(), MidiaQuebrada())
    t = _esperar_final(ex, ex.criar(_pedido(), [5], None)["id"])
    assert t["estado"] == "erro" and "libx264" in t["erro"]


# ------------------------------------------------------------ rotas
@pytest.fixture
def rotas_video(cenario, monkeypatch):  # noqa: F811
    from tudoia_painel.rotas import estudio_video_longo as rota
    portas = {"8188": True, "4000": True}
    monkeypatch.setattr(rota.infra, "porta_aberta", lambda porta: portas[str(porta)])
    monkeypatch.setattr(rota.video_midia, "disponivel", lambda raiz: True)
    criados = []
    monkeypatch.setattr(rota.ExecutorVideoLongo, "criar",
                        lambda self, pedido, duracoes, custo: criados.append((pedido, duracoes, custo)) or {
                            "id": "vl_aaaaaaaaaaaa", "estado": "na_fila", "pedido": pedido, "custo_estimado_usd": custo,
                            "segmentos": [{"indice": i, "duracao_s": d, "estado": "pendente"} for i, d in enumerate(duracoes)]})
    cenario.portas, cenario.criados = portas, criados
    return cenario


def _com_chave_fal(c):
    env = c.raiz / ".env"
    env.write_text(env.read_text(encoding="utf-8") + "FAL_AI_API_KEY=fal-teste\n", encoding="utf-8")


def test_estimar_local_e_nuvem(rotas_video):
    r = rotas_video.post("/api/estudio/video-longo/estimar", json={"prompt": "p", "modelo": "video-wan14b-t2v", "duracao_segundos": 60})
    assert r.status_code == 200, r.text
    assert r.json()["segmentos"] == [5] * 12 and r.json()["custo_estimado_usd"] == 0.0
    r = rotas_video.post("/api/estudio/video-longo/estimar", json={"prompt": "p", "motor": "nuvem", "modelo": "wan-3",
                                                                    "duracao_segundos": 60, "resolucao": "720p"})
    d = r.json()
    assert d["segmentos"] == [30, 30] and d["custo_estimado_usd"] == 6.0 and d["chave_presente"] is False


def test_nuvem_exige_chave_confirmacao_e_respeita_o_teto(rotas_video):
    corpo = {"prompt": "p", "motor": "nuvem", "modelo": "kling-3", "duracao_segundos": 30}
    r = rotas_video.post("/api/estudio/video-longo", json=corpo)
    assert r.status_code == 422 and r.json()["erro"]["codigo"] == "chave_ausente"
    _com_chave_fal(rotas_video)
    r = rotas_video.post("/api/estudio/video-longo", json=corpo)
    assert r.status_code == 422 and r.json()["erro"]["codigo"] == "confirmacao_necessaria"
    env = rotas_video.raiz / ".env"
    env.write_text(env.read_text(encoding="utf-8") + "TUDOIA_VIDEO_NUVEM_TETO_USD=1,50\n", encoding="utf-8")
    r = rotas_video.post("/api/estudio/video-longo", json={**corpo, "confirmar_nuvem": True})
    assert r.status_code == 422 and r.json()["erro"]["codigo"] == "acima_do_teto"
    assert rotas_video.criados == []


def test_nuvem_confirmada_cria_o_trabalho(rotas_video):
    _com_chave_fal(rotas_video)
    r = rotas_video.post("/api/estudio/video-longo", json={"prompt": "p", "motor": "nuvem", "modelo": "minimax-h3",
                                                            "duracao_segundos": 20, "confirmar_nuvem": True, "seed": 0})
    assert r.status_code == 200, r.text
    pedido, duracoes, custo = rotas_video.criados[0]
    assert duracoes == [10, 10] and custo == pytest.approx(1.2) and pedido["seed"] == 0


def test_nuvem_com_litellm_fora_do_ar(rotas_video):
    _com_chave_fal(rotas_video)
    rotas_video.portas["4000"] = False
    r = rotas_video.post("/api/estudio/video-longo", json={"prompt": "p", "motor": "nuvem", "modelo": "wan-3",
                                                            "duracao_segundos": 10, "confirmar_nuvem": True})
    assert r.status_code == 503 and r.json()["erro"]["extras"]["servico_offline"] == "litellm"


def test_local_com_comfyui_desligado(rotas_video):
    rotas_video.portas["8188"] = False
    r = rotas_video.post("/api/estudio/video-longo", json={"prompt": "p", "modelo": "video-wan14b-t2v", "duracao_segundos": 20})
    assert r.status_code == 503


@pytest.mark.parametrize("ref", ["../../.env", "C:/Windows/win.ini", "/api/estudio/uploads/../../.env"])
def test_referencia_fora_da_pasta_de_uploads_e_recusada(rotas_video, ref):
    r = rotas_video.post("/api/estudio/video-longo", json={"prompt": "p", "modelo": "video-wan14b-t2v",
                                                            "duracao_segundos": 20, "arquivo_referencia": ref})
    assert r.status_code == 404
    assert rotas_video.criados == []


def test_ltx_nao_instalado_e_recusado(rotas_video):
    r = rotas_video.post("/api/estudio/video-longo/estimar", json={"prompt": "p", "modelo": "video-ltx23", "duracao_segundos": 40})
    assert r.status_code == 422


@pytest.mark.parametrize("corpo", [
    {"prompt": "p", "modelo": "m", "duracao_segundos": 61},
    {"prompt": "p", "modelo": "m", "duracao_segundos": 10, "cenas": ["x"] * 13},
    {"prompt": "p", "modelo": "m", "duracao_segundos": 10, "motor": "outro"},
    {"prompt": "p", "modelo": "m", "duracao_segundos": 10, "resolucao": "1080p"},
    {"prompt": "p", "modelo": "m", "duracao_segundos": 10, "campo_estranho": 1},
])
def test_entrada_fora_dos_limites_e_recusada(rotas_video, corpo):
    assert rotas_video.post("/api/estudio/video-longo/estimar", json=corpo).status_code == 422


def test_id_invalido_e_404_e_publico_esconde_caminhos(rotas_video):
    assert rotas_video.get("/api/estudio/video-longo/../../etc").status_code == 404
    assert rotas_video.get("/api/estudio/video-longo/vl_ffffffffffff").status_code == 404
    from tudoia_painel.rotas.estudio_video_longo import _publico
    t = {"id": "vl_0", "estado": "concluido", "pedido": {"referencia": "D:/TudoIA/dados/estudio/uploads/a.png", "trilha": None},
         "segmentos": [{"indice": 0, "duracao_s": 5, "estado": "concluido", "ref": "segredo-do-provedor"}], "video_final": "v.mp4"}
    pub = _publico(t)
    assert pub["pedido"]["referencia"] == "a.png" and "ref" not in pub["segmentos"][0]
    assert pub["video_url"] == "/api/estudio/videos/v.mp4"


def test_catalogo_lista_modelos_de_nuvem_e_clipe_maximo(rotas_video):
    _com_chave_fal(rotas_video)
    d = rotas_video.get("/api/estudio/catalogo-modelos").json()
    nuvem = {m["id"]: m for m in d["video"]["nuvem"]}
    assert nuvem["wan-3"]["disponivel"] is True and nuvem["wan-3"]["max_segmento_s"]["720p"] == 30
    assert "fal-teste" not in json.dumps(d)


# ------------------------------------------------------------ mídia real (PyAV do ComfyUI portable)
PY_COMFY = video_midia.python_comfy(REPO)
GERADOR = r'''
import sys, av, numpy as np
from fractions import Fraction
def clipe(path, fps, segundos, w, h, audio):
    with av.open(path, "w") as out:
        vs = out.add_stream("libx264", rate=fps); vs.width = w; vs.height = h; vs.pix_fmt = "yuv420p"
        aus = out.add_stream("aac", rate=44100, layout="mono") if audio else None
        for i in range(int(fps * segundos)):
            f = av.VideoFrame.from_ndarray(np.full((h, w, 3), (i * 9) % 255, dtype=np.uint8), format="rgb24")
            f.pts = i; f.time_base = Fraction(1, fps)
            for p in vs.encode(f): out.mux(p)
        for p in vs.encode(None): out.mux(p)
        if aus:
            t, total = 0, int(44100 * segundos)
            while t < total:
                k = min(1024, total - t)
                x = (0.2 * np.sin(2 * np.pi * 440 * np.arange(t, t + k) / 44100)).astype(np.float32).reshape(1, -1)
                fr = av.AudioFrame.from_ndarray(x, format="fltp", layout="mono"); fr.sample_rate = 44100
                fr.pts = t; fr.time_base = Fraction(1, 44100)
                for p in aus.encode(fr): out.mux(p)
                t += k
            for p in aus.encode(None): out.mux(p)
d = sys.argv[1]
clipe(d + "/a.mp4", 16, 2, 320, 240, True)
clipe(d + "/b.mp4", 24, 1.5, 640, 480, True)
clipe(d + "/m.mp4", 24, 1, 320, 240, False)
'''


@pytest.mark.skipif(not PY_COMFY.is_file(), reason="ComfyUI portable (PyAV) não instalado nesta máquina")
def test_montagem_real_reamostra_corta_e_mantem_o_audio(tmp_path):
    gerador = tmp_path / "gerar.py"
    gerador.write_text(GERADOR, encoding="utf-8")
    subprocess.run([str(PY_COMFY), "-I", str(gerador), str(tmp_path)], check=True, timeout=120)
    a, b, m = tmp_path / "a.mp4", tmp_path / "b.mp4", tmp_path / "m.mp4"

    saida = tmp_path / "final.mp4"
    r = video_midia.montar(REPO, saida, [a, b], 320, 240, 24)
    assert r["quadros"] == 48 + 36 and r["tem_audio"] is True        # 2 s a 16 fps viram 48 quadros a 24 fps
    info = video_midia.info(REPO, saida)
    assert (info["largura"], info["altura"], info["fps"]) == (320, 240, 24.0)
    assert info["duracao_s"] == pytest.approx(3.5, abs=0.1) and info["tem_audio"]

    cortado = tmp_path / "cortado.mp4"
    assert video_midia.montar(REPO, cortado, [a, b], 320, 240, 24, duracao_max_s=2.5)["quadros"] == 60

    mudo = tmp_path / "mudo.mp4"
    assert video_midia.montar(REPO, mudo, [a, m], 320, 240, 24)["tem_audio"] is False   # um clipe sem som: sem buraco

    com_trilha = tmp_path / "trilha.mp4"
    assert video_midia.montar(REPO, com_trilha, [m, m], 320, 240, 24, trilha=a)["tem_audio"] is True

    quadro = tmp_path / "q.jpg"
    assert video_midia.ultimo_quadro(REPO, saida, quadro) == {"largura": 320, "altura": 240} and quadro.stat().st_size > 0


@pytest.mark.skipif(not PY_COMFY.is_file(), reason="ComfyUI portable (PyAV) não instalado nesta máquina")
def test_midia_com_arquivo_inexistente_da_erro_legivel(tmp_path):
    with pytest.raises(video_midia.ErroMidia, match="No such file"):
        video_midia.info(REPO, tmp_path / "nao.mp4")

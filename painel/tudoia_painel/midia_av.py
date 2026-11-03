"""Operações de mídia do vídeo longo, executadas com o python_embeded do ComfyUI portable (que já traz o PyAV).

Este arquivo roda num subprocesso (`python -I midia_av.py ...`) e por isso só usa a biblioteca padrão e o `av`:
não importa nada do painel. O painel chama pelas funções de video_midia.py.

Comandos (saída: uma linha JSON no stdout; erro: código 1 e a mensagem no stderr):
  info <video>                       duração, dimensões, fps e se há áudio
  ultimo-quadro <video> <imagem>     grava o último quadro (.jpg ou .png)
  primeiro-quadro <video> <imagem>   grava o primeiro quadro
  montar <spec.json>                 emenda clipes num MP4 H.264/AAC (ver montar())
"""
import json
import sys
from fractions import Fraction

TAXA_AUDIO = 48000
AMOSTRAS_POR_QUADRO_AAC = 1024


def info(caminho: str) -> dict:
    import av
    with av.open(caminho) as c:
        v = next((s for s in c.streams if s.type == "video"), None)
        if v is None:
            raise ValueError("arquivo sem faixa de vídeo")
        fps = float(v.average_rate or v.guessed_rate or 0)
        if c.duration:
            dur = c.duration / 1_000_000
        elif v.duration and v.time_base:
            dur = float(v.duration * v.time_base)
        else:
            dur = 0.0
        return {"duracao_s": round(dur, 3), "largura": v.codec_context.width, "altura": v.codec_context.height,
                "fps": round(fps, 3), "tem_audio": any(s.type == "audio" for s in c.streams)}


def _salvar_imagem(quadro, destino: str) -> dict:
    img = quadro.to_image()
    if destino.lower().endswith((".jpg", ".jpeg")):
        img.convert("RGB").save(destino, quality=92)
    else:
        img.save(destino)
    return {"largura": img.width, "altura": img.height}


def ultimo_quadro(caminho: str, destino: str) -> dict:
    import av
    ultimo = None
    with av.open(caminho) as c:
        for f in c.decode(video=0):
            ultimo = f
    if ultimo is None:
        raise ValueError("vídeo sem quadros")
    return _salvar_imagem(ultimo, destino)


def primeiro_quadro(caminho: str, destino: str) -> dict:
    import av
    with av.open(caminho) as c:
        for f in c.decode(video=0):
            return _salvar_imagem(f, destino)
    raise ValueError("vídeo sem quadros")


def _quadros_no_ritmo(caminho: str, fps: int):
    """Quadros do clipe reamostrados para `fps` (repete ou pula quadros pelo tempo de cada um)."""
    import av
    with av.open(caminho) as c:
        stream = c.streams.video[0]
        inicio = None
        atual = None
        k = 0
        fim = 0.0
        for f in c.decode(stream):
            t = float(f.time) if f.time is not None else k / fps
            if inicio is None:
                inicio = t
            t -= inicio
            if atual is None:
                atual = f
            while atual is not None and k / fps < t:
                yield atual
                k += 1
            atual = f
            passo = float(1 / stream.average_rate) if stream.average_rate else 1 / fps
            fim = t + passo
        while atual is not None and k / fps < fim - 1e-6:
            yield atual
            k += 1


def _audio_do_clipe(caminho: str, resampler_fabrica):
    """Áudio do clipe em fltp estéreo 48 kHz, como blocos AudioFrame (vazio se o clipe não tem áudio)."""
    import av
    with av.open(caminho) as c:
        if not c.streams.audio:
            return
        res = resampler_fabrica()
        for f in c.decode(audio=0):
            f.pts = None
            yield from res.resample(f)
        yield from res.resample(None)


def _silencio(amostras: int):
    import av
    import numpy as np
    quadro = av.AudioFrame.from_ndarray(np.zeros((2, amostras), dtype=np.float32), format="fltp", layout="stereo")
    quadro.sample_rate = TAXA_AUDIO
    return quadro


def montar(spec: dict) -> dict:
    """spec: {saida, entradas: [mp4...], largura, altura, fps, duracao_max_s?, trilha?}

    Vídeo: cada clipe é redimensionado para largura×altura e reamostrado para `fps`; o total para em duracao_max_s
    (clipes de nuvem vêm em durações fixas e podem passar do pedido). Áudio: a trilha, se houver, substitui o som dos
    clipes; sem trilha, o som dos clipes entra só se TODOS tiverem áudio (senão o vídeo sai mudo, sem buracos). Cada
    clipe ganha silêncio ou corte no áudio para não perder a sincronia com a imagem.
    """
    import av
    entradas = list(spec["entradas"])
    if not entradas:
        raise ValueError("nenhum clipe para montar")
    largura, altura, fps = int(spec["largura"]), int(spec["altura"]), int(spec["fps"])
    if largura % 2 or altura % 2:
        largura, altura = largura - largura % 2, altura - altura % 2
    limite = spec.get("duracao_max_s")
    max_quadros = round(float(limite) * fps) if limite else None
    trilha = spec.get("trilha")
    audio_dos_clipes = not trilha and all(info(e)["tem_audio"] for e in entradas)

    def novo_resampler():
        return av.AudioResampler(format="fltp", layout="stereo", rate=TAXA_AUDIO)

    with av.open(spec["saida"], "w") as out:
        vs = out.add_stream("libx264", rate=fps)
        vs.width, vs.height, vs.pix_fmt = largura, altura, "yuv420p"
        vs.options = {"crf": "18", "preset": "medium"}
        tb_video = Fraction(1, fps)
        aus = None
        if trilha or audio_dos_clipes:
            aus = out.add_stream("aac", rate=TAXA_AUDIO, layout="stereo")
        fifo = av.AudioFifo() if aus else None
        escritos = 0
        amostras_escritas = 0

        def gravar_audio(ate_amostras: int) -> None:
            nonlocal amostras_escritas
            while amostras_escritas < ate_amostras:
                n = min(AMOSTRAS_POR_QUADRO_AAC, ate_amostras - amostras_escritas)
                bloco = fifo.read(n) if fifo.samples >= n else None
                if bloco is None:
                    bloco = _silencio(n)
                bloco.pts = amostras_escritas
                bloco.time_base = Fraction(1, TAXA_AUDIO)
                for p in aus.encode(bloco):
                    out.mux(p)
                amostras_escritas += n

        for caminho in entradas:
            inicio_clipe = escritos
            for quadro in _quadros_no_ritmo(caminho, fps):
                if max_quadros is not None and escritos >= max_quadros:
                    break
                novo = quadro.reformat(width=largura, height=altura, format="yuv420p")
                novo.pts = escritos
                novo.time_base = tb_video
                for p in vs.encode(novo):
                    out.mux(p)
                escritos += 1
            if audio_dos_clipes:
                alvo = round(escritos / fps * TAXA_AUDIO)
                # o áudio do clipe começa onde o vídeo do clipe começou; sobra é descartada, falta vira silêncio
                inicio_amostras = round(inicio_clipe / fps * TAXA_AUDIO)
                gravar_audio(inicio_amostras)
                fifo = av.AudioFifo()
                for bloco in _audio_do_clipe(caminho, novo_resampler):
                    fifo.write(bloco)
                    if fifo.samples >= alvo - amostras_escritas:
                        break
                gravar_audio(alvo)
            if max_quadros is not None and escritos >= max_quadros:
                break

        if trilha:
            alvo = round(escritos / fps * TAXA_AUDIO)
            for bloco in _audio_do_clipe(trilha, novo_resampler):
                fifo.write(bloco)
                if fifo.samples >= alvo:
                    break
            gravar_audio(alvo)

        for p in vs.encode(None):
            out.mux(p)
        if aus:
            for p in aus.encode(None):
                out.mux(p)

    return {"quadros": escritos, "duracao_s": round(escritos / fps, 3), "tem_audio": aus is not None}


def main(argv: list[str]) -> int:
    try:
        if len(argv) == 2 and argv[0] == "info":
            r = info(argv[1])
        elif len(argv) == 3 and argv[0] == "ultimo-quadro":
            r = ultimo_quadro(argv[1], argv[2])
        elif len(argv) == 3 and argv[0] == "primeiro-quadro":
            r = primeiro_quadro(argv[1], argv[2])
        elif len(argv) == 2 and argv[0] == "montar":
            with open(argv[1], encoding="utf-8") as f:
                r = montar(json.load(f))
        else:
            print("uso: midia_av.py info|ultimo-quadro|primeiro-quadro|montar ...", file=sys.stderr)
            return 2
    except Exception as e:  # noqa: BLE001 — o painel lê a mensagem do stderr
        print(f"{type(e).__name__}: {e}"[:500], file=sys.stderr)
        return 1
    print(json.dumps(r))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

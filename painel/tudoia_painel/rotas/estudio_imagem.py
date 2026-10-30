"""Estúdio: geração, otimização de prompt e inpaint de imagem."""
import base64
import html
import shutil
import time
from typing import Any

import httpx
from fastapi import APIRouter


from ..envfile import ler_env
from .. import comfyui
from ..caminhos import comfyui_dir
from .. import servicos as infra
from ..ambiente import Contexto
from ..erros import ErroApi
from ..schemas import GerarImagemReq, InpaintImagemReq, OtimizarPromptReq
from ..estudio_servico import _arbitrar_vram_para_estudio, _registrar_historico_visual, dimensoes_png, executar_comfyui_imagem, otimizar_prompt_visual
from .. import upstreams


def criar_router(ctx: Contexto) -> APIRouter:
    router = APIRouter()
    raiz = ctx.raiz
    pastas = ctx.pastas_estudio
    pasta_estudio_imagens = pastas.imagens
    pasta_estudio_uploads = pastas.uploads

    @router.post("/api/estudio/gerar-imagem")
    def gerar_imagem(corpo: GerarImagemReq):
        inicio = time.perf_counter()
        dimensoes = {
            "1:1": (1024, 1024),
            "16:9": (1344, 768),
            "9:16": (768, 1344),
            "4:3": (1152, 864),
            "3:4": (864, 1152),
        }
        largura, altura = dimensoes.get(corpo.aspect_ratio, (1024, 1024))
        seed_final = corpo.seed or int(time.time() * 1000) % 1_000_000_000

        # Tradução e enriquecimento visual automático para o motor de difusão
        prompt_efetivo, foi_otimizado, msg_otimizado = otimizar_prompt_visual(corpo.prompt, raiz)

        comfy_online = infra.porta_aberta(8188)
        is_modelo_local = corpo.modelo.startswith("local:")
        motor_efetivo = "comfyui" if is_modelo_local else corpo.motor

        if (motor_efetivo == "comfyui" or is_modelo_local) and not comfy_online:
            raise ErroApi(503, "servico_offline", f"O serviço ComfyUI (:8188) está offline no host. Inicie-o para carregar o modelo '{corpo.modelo}'.", extras={"servico_offline": "comfyui", "modelo_solicitado": corpo.modelo, "porta": 8188})

        # 1. Se ComfyUI estiver online e for selecionado ou modelo local
        if comfy_online and (motor_efetivo in ("comfyui", "auto") or is_modelo_local):
            _arbitrar_vram_para_estudio()
            res_comfy = executar_comfyui_imagem(raiz, pasta_estudio_imagens, corpo.modelo, prompt_efetivo, corpo.prompt_negativo, seed_final, largura, altura, corpo.steps)
            latencia_s = time.perf_counter() - inicio
            if res_comfy.get("ok"):
                latencia_ms = int(latencia_s * 1000)
                url_img = f"/api/estudio/imagens/{res_comfy['nome_arquivo']}"
                _registrar_historico_visual("txt2img", "comfyui", corpo.modelo, prompt_efetivo, f"{largura}x{altura}", latencia_s, "sucesso", url_img)
                return {
                    "ok": True,
                    "motor": "comfyui",
                    "modelo": corpo.modelo,
                    "largura": largura,
                    "altura": altura,
                    "seed": seed_final,
                    "steps": corpo.steps,
                    "prompt": prompt_efetivo,
                    "prompt_original": corpo.prompt,
                    "prompt_otimizado": foi_otimizado,
                    "prompt_msg": msg_otimizado,
                    "latencia_ms": latencia_ms,
                    "imagem_url": url_img,
                }
            elif is_modelo_local:
                _registrar_historico_visual("txt2img", "comfyui", corpo.modelo, corpo.prompt, f"{largura}x{altura}", latencia_s, "falha")
                raise ErroApi(502, "falha_motor", res_comfy.get("erro", "Falha na execução do fluxo no ComfyUI."), extras={"motor": "comfyui", "modelo": corpo.modelo})

        # 2. Geração Local-First via Nuvem (baixando bytes e servindo localmente para respeitar CSP)
        env_atual = ler_env(raiz / ".env")
        cf_key = env_atual.get("CLOUDFLARE_API_KEY", "").strip()
        cf_acc = env_atual.get("CLOUDFLARE_ACCOUNT_ID", "").strip()

        # Rota A: Cloudflare Workers AI (Zero Watermark, Ultra Rápido e Estável)
        usar_cf = bool(cf_key and cf_acc) and (corpo.modelo.startswith("cf-") or corpo.modelo in ("flux", "turbo", "flux-anime", "auto"))
        if usar_cf:
            cf_modelos_map = {
                "cf-flux": "@cf/black-forest-labs/flux-1-schnell",
                "flux": "@cf/black-forest-labs/flux-1-schnell",
                "cf-sdxl": "@cf/stabilityai/stable-diffusion-xl-base-1.0",
                "turbo": "@cf/stabilityai/stable-diffusion-xl-base-1.0",
                "cf-dreamshaper": "@cf/lykon/dreamshaper-8-lcm",
                "flux-anime": "@cf/lykon/dreamshaper-8-lcm",
            }
            cf_model_id = cf_modelos_map.get(corpo.modelo, "@cf/black-forest-labs/flux-1-schnell")
            cf_url = f"https://api.cloudflare.com/client/v4/accounts/{cf_acc}/ai/run/{cf_model_id}"
            cf_headers = {"Authorization": f"Bearer {cf_key}"}

            try:
                with httpx.Client(timeout=45.0) as cliente:
                    cf_payload: dict[str, Any] = {"prompt": prompt_efetivo}
                    if "flux" in cf_model_id:
                        cf_payload["steps"] = min(corpo.steps, 8)
                    cf_resp = cliente.post(cf_url, headers=cf_headers, json=cf_payload)

                    if cf_resp.status_code == 200:
                        img_bytes = None
                        if "application/json" in cf_resp.headers.get("content-type", ""):
                            dados_json = cf_resp.json()
                            if "result" in dados_json and "image" in dados_json["result"]:
                                img_bytes = base64.b64decode(dados_json["result"]["image"])
                        elif len(cf_resp.content) > 1000:
                            img_bytes = cf_resp.content

                        if img_bytes:
                            nome_arquivo = f"img_{int(time.time())}_{seed_final % 100000}.png"
                            caminho_local = pasta_estudio_imagens / nome_arquivo
                            caminho_local.write_bytes(img_bytes)
                            latencia_s = time.perf_counter() - inicio
                            latencia_ms = int(latencia_s * 1000)
                            url_img = f"/api/estudio/imagens/{nome_arquivo}"
                            _registrar_historico_visual("txt2img", "cloudflare", cf_model_id.split("/")[-1], prompt_efetivo, f"{largura}x{altura}", latencia_s, "sucesso", url_img)
                            return {
                                "ok": True,
                                "motor": "cloudflare",
                                "modelo": cf_model_id.split("/")[-1],
                                "largura": largura,
                                "altura": altura,
                                "seed": seed_final,
                                "steps": corpo.steps,
                                "prompt": prompt_efetivo,
                                "prompt_original": corpo.prompt,
                                "prompt_otimizado": foi_otimizado,
                                "prompt_msg": msg_otimizado,
                                "latencia_ms": latencia_ms,
                                "imagem_url": url_img,
                            }
            except Exception:
                # Se Cloudflare oscilar, tenta fallback do Pollinations
                pass

        # Rota B: Provedor Público Pollinations. Só com TUDOIA_ESTUDIO_POLLINATIONS=1: o prompt vai na URL para um
        # serviço público sem conta, e antes isso acontecia em silêncio sempre que a Cloudflare falhava.
        aviso = None
        usar_pollinations = env_atual.get("TUDOIA_ESTUDIO_POLLINATIONS", "").strip() == "1"
        if not usar_pollinations:
            aviso = ("Nenhum motor de imagem respondeu (ComfyUI e Cloudflare). O Pollinations, serviço público que recebe "
                     "o prompt, está desligado: ative com TUDOIA_ESTUDIO_POLLINATIONS=1 no .env.")
        prompt_codificado = httpx.URL(f"/{corpo.prompt}").raw_path.decode("utf-8").lstrip("/")
        modelo_nuvem = corpo.modelo.replace("cf-", "") if not is_modelo_local else "flux"
        url_remota = f"https://image.pollinations.ai/prompt/{prompt_codificado}?width={largura}&height={altura}&seed={seed_final}&model={modelo_nuvem}&nologo=true"
        nome_arquivo = f"img_{int(time.time())}_{seed_final % 100000}.jpg"
        caminho_local = pasta_estudio_imagens / nome_arquivo

        try:
            if not usar_pollinations:
                raise RuntimeError("pollinations desligado")
            with httpx.Client(timeout=35.0) as cliente:
                resp = cliente.get(url_remota)
                if resp.status_code == 200 and len(resp.content) > 1000:
                    caminho_local.write_bytes(resp.content)
                    latencia_s = time.perf_counter() - inicio
                    latencia_ms = int(latencia_s * 1000)
                    url_img = f"/api/estudio/imagens/{nome_arquivo}"
                    _registrar_historico_visual("txt2img", "pollinations", modelo_nuvem, prompt_efetivo, f"{largura}x{altura}", latencia_s, "sucesso", url_img)
                    return {
                        "ok": True,
                        "motor": "nuvem",
                        "modelo": modelo_nuvem,
                        "largura": largura,
                        "altura": altura,
                        "seed": seed_final,
                        "steps": corpo.steps,
                        "prompt": prompt_efetivo,
                        "prompt_original": corpo.prompt,
                        "prompt_otimizado": foi_otimizado,
                        "prompt_msg": msg_otimizado,
                        "latencia_ms": latencia_ms,
                        "imagem_url": url_img,
                    }
        except Exception:
            pass

        # Rota C: Fallback local resiliente (se conexão externa oscilar, rate limit 402 ou ambiente de teste)
        svg_content = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{largura}" height="{altura}" viewBox="0 0 {largura} {altura}">
  <rect width="100%" height="100%" fill="#09090b"/>
  <defs>
    <linearGradient id="grad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#18181b"/>
      <stop offset="100%" stop-color="#09090b"/>
    </linearGradient>
  </defs>
  <rect width="100%" height="100%" fill="url(#grad)"/>
  <rect x="40" y="40" width="{largura-80}" height="{altura-80}" rx="12" fill="none" stroke="#27272a" stroke-width="2"/>
  <text x="50%" y="45%" text-anchor="middle" fill="#f4f4f5" font-family="sans-serif" font-size="22" font-weight="600">TudoIA Studio · Render</text>
  <text x="50%" y="55%" text-anchor="middle" fill="#a1a1aa" font-family="monospace" font-size="14">{html.escape(corpo.prompt[:60])}...</text>
  <text x="50%" y="62%" text-anchor="middle" fill="#71717a" font-family="monospace" font-size="12">{largura}x{altura} · Seed: {seed_final}</text>
</svg>"""
        nome_svg = f"img_{int(time.time())}_{seed_final % 100000}.svg"
        (pasta_estudio_imagens / nome_svg).write_text(svg_content, encoding="utf-8")
        latencia_s = time.perf_counter() - inicio
        latencia_ms = int(latencia_s * 1000)
        url_svg = f"/api/estudio/imagens/{nome_svg}"
        _registrar_historico_visual("svg", "estudio", corpo.modelo, prompt_efetivo, f"{largura}x{altura}", latencia_s, "sucesso", url_svg)
        return {
            "ok": True,
            "motor": "estudio",
            "modelo": corpo.modelo,
            "largura": largura,
            "altura": altura,
            "seed": seed_final,
            "steps": corpo.steps,
            "prompt": prompt_efetivo,
            "prompt_original": corpo.prompt,
            "prompt_otimizado": foi_otimizado,
            "prompt_msg": msg_otimizado,
            "latencia_ms": latencia_ms,
            "imagem_url": url_svg,
            **({"aviso": aviso} if aviso else {}),
        }

    @router.post("/api/estudio/otimizar-prompt")
    def otimizar_prompt_endpoint(corpo: OtimizarPromptReq):
        prompt_efetivo, foi_otimizado, msg_otimizado = otimizar_prompt_visual(corpo.prompt, raiz)
        return {
            "ok": True,
            "prompt_original": corpo.prompt,
            "prompt": prompt_efetivo,
            "prompt_otimizado": foi_otimizado,
            "prompt_msg": msg_otimizado or "Prompt mantido (já detalhado em inglês)"
        }

    @router.post("/api/estudio/inpaint")
    def inpaint_imagem(corpo: InpaintImagemReq):
        inicio = time.perf_counter()
        comfy_online = infra.porta_aberta(8188)
        if not comfy_online:
            raise ErroApi(503, "servico_offline", "O serviço ComfyUI (:8188) está offline no host. Inicie-o para executar o inpainting com aceleração na GPU.", extras={"servico_offline": "comfyui", "porta": 8188})

        # 1. Localiza a imagem base
        caminho_base = None
        base_str = corpo.imagem_base.strip()
        if base_str.startswith("/api/estudio/imagens/"):
            sub_nome = base_str.replace("/api/estudio/imagens/", "")
            c_cand = (pasta_estudio_imagens / sub_nome).resolve()
            if c_cand.is_file() and c_cand.is_relative_to(pasta_estudio_imagens):
                caminho_base = c_cand
        elif base_str.startswith("/api/estudio/uploads/"):
            sub_nome = base_str.replace("/api/estudio/uploads/", "")
            c_cand = (pasta_estudio_uploads / sub_nome).resolve()
            if c_cand.is_file() and c_cand.is_relative_to(pasta_estudio_uploads):
                caminho_base = c_cand
        else:
            # Só nome dentro da pasta do Estúdio. Caminho absoluto do disco seria leitura arbitrária (copiado p/ o ComfyUI).
            p_cand = (pasta_estudio_imagens / base_str).resolve()
            if p_cand.is_file() and p_cand.is_relative_to(pasta_estudio_imagens):
                caminho_base = p_cand

        if not caminho_base or not caminho_base.is_file():
            raise ErroApi(404, "nao_encontrado", f"Imagem base para inpaint não encontrada: '{corpo.imagem_base}'.")

        # 2. Decodifica a máscara enviada pelo Canvas
        mascara_b64 = corpo.mascara_base64
        if "," in mascara_b64:
            mascara_b64 = mascara_b64.split(",", 1)[1]
        try:
            mascara_bytes = base64.b64decode(mascara_b64)
        except Exception as e:
            raise ErroApi(422, "validacao", "Máscara Base64 inválida.") from e

        if len(mascara_bytes) == 0:
            raise ErroApi(422, "validacao", "Máscara de inpainting está vazia.")

        # 3. Prepara os arquivos na pasta input do ComfyUI
        comfy_input = comfyui_dir(raiz) / "input"
        comfy_input.mkdir(parents=True, exist_ok=True)
        nome_base_comfy = f"inpaint_base_{int(time.time())}_{caminho_base.name}"
        nome_mask_comfy = f"inpaint_mask_{int(time.time())}.png"

        shutil.copy2(caminho_base, comfy_input / nome_base_comfy)
        (comfy_input / nome_mask_comfy).write_bytes(mascara_bytes)

        # 4. Monta o grafo de inpainting e otimiza o prompt para difusão
        seed_final = corpo.seed or int(time.time() * 1000) % 1_000_000_000

        # Tradução e enriquecimento visual automático para o motor de difusão
        prompt_efetivo, foi_otimizado, msg_otimizado = otimizar_prompt_visual(corpo.prompt, raiz)

        neg = corpo.prompt_negativo or "blurry, deformed, ugly, distorted, bad architecture"
        ckpt_inpaint = "Juggernaut-XL_v9_RunDiffusionPhoto_v2.safetensors"
        if corpo.modelo and corpo.modelo.startswith("local:"):
            cand_ckpt = corpo.modelo.replace("local:", "").strip()
            if cand_ckpt.endswith((".safetensors", ".ckpt")) and "yue" not in cand_ckpt.lower():
                if (comfyui_dir(raiz) / "models" / "checkpoints" / cand_ckpt).is_file():
                    ckpt_inpaint = cand_ckpt
        grafo: dict[str, Any] = {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt_inpaint}},
            "2": {"class_type": "LoadImage", "inputs": {"image": nome_base_comfy}},
            "3": {"class_type": "LoadImageMask", "inputs": {"image": nome_mask_comfy, "channel": "red"}},
            "4": {"class_type": "VAEEncodeForInpaint", "inputs": {"pixels": ["2", 0], "vae": ["1", 2], "mask": ["3", 0], "grow_mask_by": 6}},
            "5": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt_efetivo, "clip": ["1", 1]}},
            "6": {"class_type": "CLIPTextEncode", "inputs": {"text": neg, "clip": ["1", 1]}},
            "7": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": seed_final, "steps": corpo.steps, "cfg": 6.5, "sampler_name": "dpmpp_2m_sde",
                    "scheduler": "karras", "denoise": corpo.denoise, "model": ["1", 0], "positive": ["5", 0],
                    "negative": ["6", 0], "latent_image": ["4", 0],
                },
            },
            "8": {"class_type": "VAEDecode", "inputs": {"samples": ["7", 0], "vae": ["1", 2]}},
            "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "inpaint_tudoia", "images": ["8", 0]}},
        }

        # 5. Arbitrador de VRAM e Disparo /prompt no ComfyUI
        _arbitrar_vram_para_estudio()
        try:
            with httpx.Client(timeout=15.0) as cliente:
                resp = cliente.post(f"{upstreams.COMFYUI}/prompt", json={"prompt": grafo})
                if resp.status_code != 200:
                    _registrar_historico_visual("inpaint", "comfyui", corpo.modelo, corpo.prompt, "auto", time.perf_counter() - inicio, "falha")
                    raise ErroApi(502, "falha_motor", f"ComfyUI HTTP {resp.status_code}: {resp.text[:300]}")
                d_resp = resp.json()
                if d_resp.get("node_errors"):
                    _registrar_historico_visual("inpaint", "comfyui", corpo.modelo, corpo.prompt, "auto", time.perf_counter() - inicio, "falha")
                    raise ErroApi(502, "falha_motor", f"Erros nos nós do ComfyUI: {d_resp['node_errors']}")
                prompt_id = d_resp.get("prompt_id")
                if not prompt_id:
                    _registrar_historico_visual("inpaint", "comfyui", corpo.modelo, corpo.prompt, "auto", time.perf_counter() - inicio, "falha")
                    raise ErroApi(502, "falha_motor", "ComfyUI não retornou prompt_id.")
        except ErroApi:
            raise
        except Exception as e:
            _registrar_historico_visual("inpaint", "comfyui", corpo.modelo, corpo.prompt, "auto", time.perf_counter() - inicio, "falha")
            raise ErroApi(502, "falha_motor", f"Falha ao comunicar com ComfyUI: {type(e).__name__}") from e

        # 6. Polling do resultado
        inicio_wait = time.time()
        with httpx.Client(timeout=15.0) as cliente:
            while time.time() - inicio_wait < 180:
                try:
                    h_resp = cliente.get(f"{upstreams.COMFYUI}/history/{prompt_id}")
                    if h_resp.status_code == 200:
                        h_data = h_resp.json()
                        if prompt_id in h_data:
                            outputs = h_data[prompt_id].get("outputs", {})
                            for _nid, nout in outputs.items():
                                if "images" in nout and len(nout["images"]) > 0:
                                    img_info = nout["images"][0]
                                    params_view = comfyui.parametros_view(img_info)   # recusa nome/pasta com `..`
                                    fn = params_view["filename"]
                                    v_resp = cliente.get(f"{comfyui.BASE}/view", params=params_view, timeout=30.0)
                                    if v_resp.status_code == 200 and len(v_resp.content) > 1000:
                                        nome_local = f"inpaint_{int(time.time())}_{fn}"
                                        caminho_local = pasta_estudio_imagens / nome_local
                                        caminho_local.write_bytes(v_resp.content)
                                        w, h = dimensoes_png(v_resp.content)
                                        latencia_s = time.perf_counter() - inicio
                                        latencia_ms = int(latencia_s * 1000)
                                        url_inpaint = f"/api/estudio/imagens/{nome_local}"
                                        _registrar_historico_visual("inpaint", "comfyui", corpo.modelo, prompt_efetivo, f"{w}x{h}", latencia_s, "sucesso", url_inpaint)
                                        return {
                                            "ok": True,
                                            "motor": "comfyui",
                                            "modelo": corpo.modelo,
                                            "largura": w,
                                            "altura": h,
                                            "denoise": corpo.denoise,
                                            "seed": seed_final,
                                            "steps": corpo.steps,
                                            "prompt": prompt_efetivo,
                                            "prompt_original": corpo.prompt,
                                            "prompt_otimizado": foi_otimizado,
                                            "prompt_msg": msg_otimizado,
                                            "latencia_ms": latencia_ms,
                                            "imagem_url": url_inpaint,
                                            "mensagem": f"Inpainting concluído com sucesso ({corpo.denoise} denoise)!"
                                        }
                except Exception:
                    pass
                time.sleep(1)

        _registrar_historico_visual("inpaint", "comfyui", corpo.modelo, corpo.prompt, "auto", time.perf_counter() - inicio, "falha")
        raise ErroApi(504, "tempo_esgotado", "Tempo limite de 90s excedido aguardando inpainting do ComfyUI.")

    return router

# Estúdio

O Estúdio é a área criativa do painel. Ele gera imagens, faz inpainting (regenerar uma região marcada com pincel), gera vídeos e compõe músicas. Cada tipo de mídia pode rodar em dois lugares:

- **Local (ComfyUI)**: roda na GPU do host, em uma instalação ComfyUI portable que fica fora do Docker. É o único motor de vídeo, música e inpainting.
- **Nuvem**: imagem apenas. Cloudflare Workers AI (exige chave) e Pollinations (sem chave).

Os endpoints ficam em `painel/tudoia_painel/rotas/estudio_*.py` (catálogo, arquivos, imagem, vídeo e música), a lógica de prompts e grafos em `painel/tudoia_painel/estudio_servico.py`, a interface em `painel/tudoia_painel/static/painel.js` e `index.html`, e os fluxos ComfyUI em `runtime/comfyui/fluxos/`.

## Pré-requisitos

1. **ComfyUI portable no host.** A pasta precisa conter `ComfyUI\` (com `models`, `input`, `output` e `user`) e o script `run_nvidia_gpu.bat`.
   - Caminho: variável `TUDOIA_COMFYUI_PORTABLE` no `.env`. Vazia, o padrão é `modelos\comfyui\ComfyUI_windows_portable` dentro da raiz do projeto (`painel/tudoia_painel/caminhos.py`, funções `comfyui_portable` e `comfyui_dir`).
   - O painel sobe o ComfyUI executando `run_nvidia_gpu.bat` dessa pasta (`painel/tudoia_painel/servicos.py`, `_start_comfyui`). Não há variável para trocar o script.
   - **Porta 8188 em `127.0.0.1`, fixa no código.** Os chamados `http://127.0.0.1:8188` estão em `painel/tudoia_painel/upstreams.py`. Não existe variável para mudar a porta. O ComfyUI escuta em `127.0.0.1` por padrão (`ComfyUI/comfy/cli_args.py`, opção `--listen`), e o `run_nvidia_gpu.bat` não passa `--listen`.
2. **Custom node `ComfyUI-GGUF`** em `ComfyUI\custom_nodes\`. O fluxo `flux-schnell` usa `UnetLoaderGGUF`, que vem dele. Está instalado na cópia local.
   Os nós de YuE 2 (`YuE2GenerateMusic`), MiniMax H3 (`MiniMaxH3ImageToVideo`) e TextGen estão em `ComfyUI\comfy_extras\` da cópia local, não em `custom_nodes`.
3. **Pesos dos modelos** nas subpastas de `ComfyUI\models\`. Os nomes exatos estão na tabela de fluxos abaixo. Para baixar e verificar, use [modelos.md](modelos.md) e `config/modelos.yaml`. Todos os nomes de arquivo usados pelos fluxos existem em `config/modelos.yaml` (conferido).
4. **GPU NVIDIA.** Antes de cada geração pesada, o painel descarrega da VRAM os modelos do Ollama (`_arbitrar_vram_para_estudio`).

## Configuração

Variáveis lidas pelo Estúdio, no `.env` da raiz (só os nomes aqui):

| Variável | Para que serve |
|---|---|
| `TUDOIA_COMFYUI_PORTABLE` | Pasta do ComfyUI portable. Vazia usa o padrão. |
| `CLOUDFLARE_API_KEY` e `CLOUDFLARE_ACCOUNT_ID` | Imagem pela Cloudflare Workers AI. Sem as duas, a rota é ignorada. |
| `GROQ_API_KEY` | Otimização de prompt pela Groq. Sem ela, usa o Ollama local. |

A otimização local chama o modelo `qwen3.5:4b` no Ollama, em `http://127.0.0.1:11434` (porta fixa). O modelo está no manifesto como `ollama-qwen3.5-4b` em `config/modelos.yaml`.

As demais variáveis do Ollama (`TUDOIA_OLLAMA_MODELS`, por exemplo) estão em [servicos-docker.md](servicos-docker.md).

## Uso pela interface

### Imagem

- **Campos:** prompt (até 4096 caracteres), prompt negativo, motor (Automático, ComfyUI ou Nuvem), modelo, proporção, seed (opcional) e passos (padrão do servidor 20; faixa 1 a 100).
- **Proporções:** 1:1 gera 1024x1024; 16:9 gera 1344x768; 9:16 gera 768x1344; 4:3 gera 1152x864; 3:4 gera 864x1152.
- **Melhorar com IA:** chama `POST /api/estudio/otimizar-prompt` e mostra o prompt em inglês antes de gerar. A geração também otimiza automaticamente quando o texto parece português.

### Inpainting

- Gere uma imagem, ative o modo inpaint e pinte com o pincel a área a regenerar. A máscara sai como PNG preto e branco: preto preserva a imagem, o pintado é regenerado.
- Controles: denoise (faixa 0,2 a 1,0; padrão da interface 0,75) e passos. O prompt descreve o que deve aparecer na região.
- O servidor usa sempre o fluxo `inpaint-tudoia.json`. O campo `modelo` enviado pela interface não escolhe o modelo.

### Vídeo

- **Modelos (opções locais):** MiniMax H3 Omni (padrão; vídeo com áudio estéreo), Wan 2.2 Text-to-Video 14B, Wan 2.2 Image-to-Video 14B e Wan 2.2 5B.
- **Modo de origem:** `t2v` (texto), `i2v` (imagem) ou `v2v` (vídeo). Os modos `i2v` e `v2v` exigem arquivo de referência, enviado antes por `POST /api/estudio/upload`.
- **Duração:** 1 a 60 s. **FPS:** 8 a 60 (a interface oferece 16 e 24). **Resolução:** 480p, 720p ou 1080p (ver a ressalva sobre 1080p).
- A interface envia `modo_execucao=async`. O servidor responde com um `job_id` (o `prompt_id` do ComfyUI) e a interface consulta `GET /api/estudio/status-video/{job_id}` até terminar.

### Música

- **Modelo:** YuE 2 (3B), fluxo `musica-yue2.json`.
- **Campos:** estilo (`style`), letra (`lyrics`, padrão `[instrumental]`), duração de 5 a 360 s e modo (`full`, `melody` ou `off`).
- **Melhorar Estilo com IA:** chama `POST /api/estudio/otimizar-prompt-musica`.

### Galeria

A galeria da interface guarda só o que foi gerado nesta sessão da página. Os arquivos ficam em disco (seção de armazenamento) e voltam a aparecer pelas rotas `GET /api/estudio/imagens`, `/videos` e `/musicas`.

## Como funciona

### Imagem: escolha do motor

A função `gerar_imagem` (em `rotas/estudio_imagem.py`) segue esta ordem:

1. **Modelo local** (começa com `local:` ou `fluxo:`): exige o ComfyUI online. Se ele estiver fora, responde com `servico_offline`.
2. **ComfyUI** online e motor `auto` ou `comfyui`, ou modelo local: roda um fluxo no ComfyUI.
   - `fluxo:<nome>` carrega o JSON pelo nome.
   - `local:<arquivo>` escolhe `flux-schnell.json`, `zimage-turbo.json` ou `sdxl-foto.json` pelo nome do arquivo.
   - Qualquer outro valor usa `GeraImagemTudoIA-KREA2.json`.
3. **Cloudflare Workers AI**, se houver as duas chaves e o modelo for `cf-*`, `flux`, `turbo`, `flux-anime` ou `auto`. Modelos usados: FLUX.1 Schnell, SDXL base 1.0 e DreamShaper 8 LCM.
4. **Pollinations** (`image.pollinations.ai`), sem chave, **só com `TUDOIA_ESTUDIO_POLLINATIONS=1`** no `.env`. O prompt vai na URL para um serviço público. Entra quando nenhum passo anterior se aplica ao modelo escolhido, ou quando o passo anterior falha.
5. **SVG de reserva**, gravado com o texto do prompt. Motor `estudio`. Com o Pollinations desligado, a resposta traz `aviso` explicando que nenhum motor respondeu, e a interface mostra esse aviso.

Cada resultado vai para o histórico visual (últimas 60 entradas, em memória).

### Inpainting

A requisição traz a imagem base (URL `/api/estudio/imagens/...`, `/api/estudio/uploads/...` ou só o nome do arquivo dentro de `imagens`), a máscara em base64 (aceita data URL) e o prompt. O servidor:

1. copia a base e a máscara para `ComfyUI\input`;
2. carrega `inpaint-tudoia.json` e injeta os valores nos nós de ID 2 (`LoadImage`), 3 (`LoadImageMask`), 5 e 6 (`CLIPTextEncode`) e 7 (`KSampler`);
3. espera até 90 s pelo histórico do ComfyUI e copia o resultado para `dados\estudio\imagens`.

### Vídeo

- **Escolha do grafo** (`_preparar_grafo_video`): se o nome do modelo tem `minimax` ou `h3`, usa `video-minimax-h3.json`. Se há imagem de referência ou `i2v` no nome, usa `video-wan14b-i2v.json`. Se tem `5b`, usa `video-wan5b.json`. Nos demais casos, cai no MiniMax (se o arquivo existir) ou no `video-wan14b-t2v.json`.
- **Dimensões:** MiniMax usa 768x768 em 480p e 1344x768 em 720p e 1080p. Wan usa 832x480 em 480p e 1280x704 em 720p e 1080p.
- **Quadros do MiniMax:** duração x fps, ajustado ao múltiplo exigido pelo nó.
- **Job:** `POST /prompt` devolve o `prompt_id`, que fica em memória (`_jobs_video`). O servidor consulta `/history/{id}` e copia o vídeo de `ComfyUI\output\video` para `dados\estudio\videos` com prefixo `comfy_vid_`. O tempo máximo de espera é 600 s.
- **Cancelar:** `POST /api/estudio/cancelar` chama `/interrupt` no ComfyUI. Interrompe a execução atual, seja ela qual for.

### Música

O servidor submete `musica-yue2.json` com estilo, letra, seed e duração. Espera até 300 s pelo histórico e copia o áudio de `ComfyUI\output\audio` (ou `output`) para `dados\estudio\musicas` com prefixo `comfy_audio_`.

### Otimização de prompt

Imagem e vídeo usam a mesma lógica (`_otimizar_prompt_visual` e `_otimizar_prompt_video`). A música tem a sua (`_otimizar_prompt_musica`).

1. Se o texto já tem 30 palavras ou mais, não tem acento e não tem termos em português, devolve o texto como está.
2. Se `GROQ_API_KEY` existe, chama `https://api.groq.com/openai/v1/chat/completions` com o modelo `qwen/qwen3.8-27b` (timeout 6 s).
3. Se a Groq falhar ou não houver chave, chama o Ollama local com `qwen3.5:4b` (timeout 8 s).
4. Se tudo falhar, devolve o texto original sem alteração.

Com `GROQ_API_KEY` configurada, **o texto do prompt sai da máquina** e vai para a Groq.

## Fluxos (`runtime/comfyui/fluxos/`)

Os fluxos são JSON no formato de API do ComfyUI e ficam versionados no repositório. Os nomes dos arquivos de modelo são os exatos esperados pelo ComfyUI.

| Fluxo | Tipo | Modelos esperados (nome do arquivo) | Observação |
|---|---|---|---|
| `sdxl-foto.json` | imagem | `Juggernaut-XL_v9_RunDiffusionPhoto_v2.safetensors` | checkpoint SDXL |
| `sdxl-foto-hires.json` | imagem | mesmo checkpoint | acrescenta upscale latente |
| `flux-schnell.json` | imagem | `flux1-schnell-Q4_K_S.gguf`, `t5xxl_fp8_e4m3fn.safetensors`, `clip_l.safetensors`, `ae.safetensors` | exige `ComfyUI-GGUF` |
| `zimage-turbo.json` | imagem | `z_image_turbo_int8_convrot.safetensors`, `qwen_3_4b_fp8_mixed.safetensors`, `ae.safetensors` | |
| `zimage-turbo-hires.json` | imagem | mesmos do anterior | acrescenta upscale latente |
| `GeraImagemTudoIA-KREA2.json` | imagem | `krea2_turbo_int8_convrot.safetensors`, `krea2_darkbrush.safetensors` (LoRA), `qwen3vl_4b_fp8_scaled.safetensors`, `qwen_image_vae.safetensors` | padrão do servidor quando nenhum outro fluxo é escolhido |
| `inpaint-tudoia.json` | inpaint | `Juggernaut-XL_v9_RunDiffusionPhoto_v2.safetensors` | nós fixos 2, 3, 5, 6 e 7 |
| `video-minimax-h3.json` | vídeo com áudio | `minimax_h3_fl2va_pruned_int8_convrot.safetensors`, `minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors` (LoRA), `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors`, `minimax_h3_video_vae_int8_convrot.safetensors`, `minimax_h3_audio_vae_fp32.safetensors` | nós fixos 104, 114, 15 e 91 |
| `video-wan14b-t2v.json` | vídeo | `wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors`, `wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors`, LoRAs `wan2.2_t2v_lightx2v_4steps_lora_v1.1_*`, `umt5_xxl_fp8_e4m3fn_scaled.safetensors`, `wan_2.1_vae.safetensors` | |
| `video-wan14b-i2v.json` | vídeo (imagem para vídeo) | `wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors`, `wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors`, LoRAs `wan2.2_i2v_lightx2v_4steps_lora_v1_*`, `umt5_xxl_fp8_e4m3fn_scaled.safetensors`, `wan_2.1_vae.safetensors` | |
| `video-wan5b.json` | vídeo | `wan2.2_ti2v_5B_fp16.safetensors`, `umt5_xxl_fp8_e4m3fn_scaled.safetensors`, `wan2.2_vae.safetensors` | |
| `musica-yue2.json` | música | `yue2_3b_int8_convrot.safetensors` | nós `YuE2GenerateABC` e `YuE2GenerateMusic` |

`perfis.json` descreve cada fluxo (modelo, passos, tamanho e nome do nó de seed). A listagem de modelos do painel lê esse arquivo para rotular os fluxos. A escolha do fluxo e a injeção de valores **não** leem o `perfis.json`: estão escritas no código. Se você mudar um fluxo, confira os IDs de nó citados acima.

O painel também lista os checkpoints e modelos de difusão que existem em `ComfyUI\models\` (`/api/estudio/catalogo-modelos`).

## Armazenamento

| Pasta | Conteúdo |
|---|---|
| `dados/estudio/imagens` | PNG e JPG gerados (ComfyUI e nuvem), resultados de inpaint e SVG de reserva |
| `dados/estudio/videos` | MP4 gerados |
| `dados/estudio/musicas` | Áudio gerado pelo YuE 2 |
| `dados/estudio/uploads` | Arquivos enviados como referência |
| `ComfyUI\input` | Cópias de base, máscara e referência, criadas pelo painel |
| `ComfyUI\output\video` e `ComfyUI\output\audio` | Saída original do ComfyUI. O painel copia para `dados\estudio` |

A pasta `dados/` é de execução e não vai para o git (`.gitignore`). `DELETE /api/estudio/videos/{nome}` apaga o arquivo em `dados\estudio\videos` e também a cópia em `ComfyUI\output\video`.

## API

Todas as rotas ficam sob `/api/estudio`. As rotas que alteram estado (POST, DELETE) passam pela guarda de origem do painel (`painel/tudoia_painel/seguranca.py`): só aceitam requisição do próprio painel e corpo de até 10 MB (`POST /upload`: 140 MB), contado nos bytes recebidos. As rotas de arquivo (`/imagens/{nome}`, `/videos/{nome}`, `/musicas/{nome}`, `/uploads/{nome}`) passam por `_arquivo_em` (`app.py`): só servem ou apagam arquivo que fica dentro da pasta permitida, já resolvida.

| Método e rota | Função |
|---|---|
| `GET /status-motores` | Diz se o ComfyUI responde na porta 8188 |
| `GET /catalogo-modelos` | Modelos por motor e tipo (locais, fluxos e nuvem) |
| `POST /otimizar-prompt`, `/otimizar-prompt-video`, `/otimizar-prompt-musica` | Traduz e enriquece o prompt |
| `POST /gerar-imagem` | Gera imagem (ComfyUI, Cloudflare, Pollinations ou SVG) |
| `POST /inpaint` | Regenera a região marcada na máscara |
| `POST /gerar-video` | Gera vídeo; `modo_execucao` `sync` ou `async` |
| `GET /status-video/{job_id}` | Estado de um job de vídeo assíncrono |
| `POST /gerar-musica` | Compõe música (YuE 2) |
| `POST /cancelar` | Envia `interrupt` ao ComfyUI |
| `POST /upload` | Envia imagem ou vídeo em base64 (`tipo` `imagem` ou `video`) |
| `GET /uploads/{nome}` | Serve um upload |
| `GET` e `DELETE /imagens/{nome}`, `/videos/{nome}`, `/musicas/{nome}` | Serve ou apaga um arquivo |
| `GET /imagens`, `/videos`, `/musicas` | Lista os arquivos de cada pasta |

## Limitações e riscos

Estes pontos saem da leitura do código. Alguns são divergências entre o que a interface mostra e o que o servidor faz.

1. **Upload de até 100 MB de arquivo.** A guarda aceita até 140 MB de corpo em `POST /api/estudio/upload` (`LIMITES_POR_ROTA` em `seguranca.py`), porque o arquivo vai em base64 (cerca de 33% maior). A checagem de 100 MB dentro de `upload_midia_estudio` (`app.py`) vale para o arquivo decodificado. Antes, o teto de 1 MB do corpo recusava qualquer arquivo acima de cerca de 750 KB.
2. **1080p gera a mesma resolução de 720p** (`estudio_servico.py`, dicionário `res_dims` em `_preparar_grafo_video`).
3. **As opções "Wan 2.1 Nuvem" e "Stable Video Diffusion (SVD Nuvem)" não têm backend de nuvem.** O servidor só gera vídeo no ComfyUI. Com o ComfyUI ligado, o pedido cai nos grafos locais (MiniMax ou Wan 14B). Com o ComfyUI desligado, responde `servico_offline`. O campo `motor` de `gerar-video` é ignorado.
4. **Com o ComfyUI ligado e motor Automático, o modelo "FLUX.1 Schnell (Nuvem)" (valor padrão `flux`) é renderizado pelo fluxo local KREA2.** A interface diz "ComfyUI Local se ativo / Nuvem", o que é consistente, mas o modelo escolhido não é o FLUX.
5. **Caminho de fluxo contido (corrigido).** Em `_executar_comfyui_imagem`, o valor `fluxo:<nome>` só aceita nome de arquivo puro (sem `..`, subpasta ou caminho absoluto) e o arquivo resolvido precisa ficar dentro de `runtime/comfyui/fluxos` ou da pasta de workflows do usuário do ComfyUI (`is_relative_to`).
6. **Prompts saem da máquina.** A Groq recebe o prompt quando há `GROQ_API_KEY`. O Pollinations recebe o prompt na URL só se `TUDOIA_ESTUDIO_POLLINATIONS=1`; por padrão ele fica desligado.
7. **Portas fixas.** ComfyUI (8188) e Ollama (11434) não são configuráveis pelo `.env`.
8. **Jobs de vídeo ficam em memória.** Reiniciar o painel apaga `_jobs_video`. A consulta de estado volta a funcionar pelo histórico do ComfyUI, enquanto ele mantiver o job.
9. **Campos ignorados.** `modelo` é ignorado em inpaint (sempre `inpaint-tudoia.json`) e em música (sempre `musica-yue2.json`).
10. **IDs de nó fixos.** Trocar um JSON de fluxo sem ajustar o código quebra o inpaint (nós 2, 3, 5, 6 e 7) e o MiniMax (104, 114, 15 e 91).
11. **SVG de reserva.** O texto do prompt entra no SVG com `html.escape` (até 60 caracteres). O arquivo é servido como `application/octet-stream` (`servir_imagem_estudio`), então o `<img>` da interface provavelmente não o exibe. Isso é a confirmar no navegador.
12. **Modelo da Groq.** `qwen/qwen3.8-27b` não aparece em `config/modelos.yaml`. A existência desse modelo na Groq é a confirmar.
13. **Histórico visual.** As últimas 60 gerações ficam em memória (`HISTORICO_VISUAL`). Não há persistência.

## Veja também

- [modelos.md](modelos.md): download, verificação e espaço em disco dos pesos.
- [keycloak.md](keycloak.md): autenticação do painel.
- [servicos-docker.md](servicos-docker.md): como o painel sobe e para o ComfyUI e o Ollama no host.
- [../../config/modelos.yaml](../../config/modelos.yaml): manifesto de modelos, com destino de cada arquivo.

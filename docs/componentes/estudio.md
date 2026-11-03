# Estúdio

O Estúdio é a área criativa do painel. Ele gera imagens, faz inpainting (regenerar uma região marcada com pincel), gera vídeos e compõe músicas. Cada tipo de mídia pode rodar em dois lugares:

- **Local (ComfyUI)**: roda na GPU do host, em uma instalação ComfyUI portable que fica fora do Docker. É o único motor de música e inpainting.
- **Nuvem**: imagem pela Cloudflare Workers AI (exige chave) e pelo Pollinations (sem chave); vídeo longo pela fal.ai, através do LiteLLM (exige `FAL_AI_API_KEY`, pago por segundo, só com confirmação a cada pedido).

Os endpoints ficam em `painel/tudoia_painel/rotas/estudio_*.py` (catálogo, arquivos, imagem, vídeo e música), a lógica de prompts e grafos em `painel/tudoia_painel/estudio_servico.py`, e a interface em `painel/tudoia_painel/static/painel.js` e `index.html`.

## Pré-requisitos

1. **ComfyUI portable no host.** A pasta precisa conter `ComfyUI\` (com `models`, `input`, `output` e `user`) e o script `run_nvidia_gpu.bat`.
   - Caminho: variável `TUDOIA_COMFYUI_PORTABLE` no `.env`. Vazia, o padrão é `modelos\comfyui\ComfyUI_windows_portable` dentro da raiz do projeto (`painel/tudoia_painel/caminhos.py`, funções `comfyui_portable` e `comfyui_dir`).
   - O painel sobe o ComfyUI executando `run_nvidia_gpu.bat` dessa pasta (`painel/tudoia_painel/servicos.py`, `_start_comfyui`). Não há variável para trocar o script.
   - **Porta 8188 em `127.0.0.1`, fixa no código.** Os chamados `http://127.0.0.1:8188` estão em `painel/tudoia_painel/upstreams.py`. Não existe variável para mudar a porta. O ComfyUI escuta em `127.0.0.1` por padrão (`ComfyUI/comfy/cli_args.py`, opção `--listen`), e o `run_nvidia_gpu.bat` não passa `--listen`.
2. **Custom nodes** em `ComfyUI\custom_nodes\` (instalados na cópia local em 30/10/2026, com o commit fixo):
   - `ComfyUI-GGUF` (city96, Apache-2.0, commit `6ea2651e7df66d7585f6ffee804b20e92fb38b8a`) e o pacote `gguf==0.19.0` no `python_embeded`. Dá `UnetLoaderGGUF` e `DualCLIPLoaderGGUF`, usados pelo LTX-2.3 e pelo fluxo `flux-schnell`. Antes de 30/10/2026 a pasta não existia, e o `flux-schnell` falhava.
   - `ComfyUI-KJNodes` (kijai, GPL-3.0, commit `ab72eda7ffad6280422d71ab7d54d3fb87c0ba18`). Dá `VAELoaderKJ`, que carrega os VAEs de vídeo e áudio separados do LTX-2.3. Os outros requisitos dele (opencv, matplotlib, mss, color-matcher) não foram instalados: só os nós que os usam falham, e o LTX não usa nenhum.
   - Para atualizar: `git -C <pasta> fetch` e `git checkout <commit>` revisado, e reinicie o ComfyUI.
   Os nós de YuE 2 (`YuE2GenerateMusic`), MiniMax H3 (`MiniMaxH3ImageToVideo`), LTX (`EmptyLTXVLatentVideo` e afins) e TextGen vêm no próprio ComfyUI (`comfy_extras`).
3. **Pesos dos modelos** nas subpastas de `ComfyUI\models\`. Os nomes exatos estão na tabela de fluxos abaixo. Para baixar e verificar, use [modelos.md](modelos.md) e `config/modelos.yaml`. Todos os nomes de arquivo usados pelos fluxos existem em `config/modelos.yaml` (conferido).
4. **GPU NVIDIA.** Antes de cada geração pesada, o painel descarrega da VRAM os modelos do Ollama (`_arbitrar_vram_para_estudio`).

## Configuração

Variáveis lidas pelo Estúdio, no `.env` da raiz (só os nomes aqui):

| Variável | Para que serve |
|---|---|
| `TUDOIA_COMFYUI_PORTABLE` | Pasta do ComfyUI portable. Vazia usa o padrão. |
| `CLOUDFLARE_API_KEY` e `CLOUDFLARE_ACCOUNT_ID` | Imagem pela Cloudflare Workers AI. Sem as duas, a rota é ignorada. |
| `GROQ_API_KEY` | Otimização de prompt pela Groq. Sem ela, usa o Ollama local. |
| `FAL_AI_API_KEY` | Vídeo na nuvem (fal.ai) pelo LiteLLM. Sem ela, os modelos de nuvem aparecem como indisponíveis. Depois de gravar, gere o config do LiteLLM e recrie o container (`docker compose up -d litellm`, em `runtime/`). |
| `TUDOIA_VIDEO_NUVEM_TETO_USD` | Opcional. Teto em US$ por vídeo longo na nuvem; vazio, não há teto. |

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

- **Modelos locais:** MiniMax H3 Omni (padrão; vídeo com áudio estéreo), Wan 2.2 Text-to-Video 14B, Wan 2.2 Image-to-Video 14B, Wan 2.2 5B e LTX-2.3 distilled GGUF (vídeo com áudio; aparece quando os pesos e os custom nodes existem).
- **Modelos de nuvem:** os de `config/video-nuvem.yaml` (Wan 3.0, MiniMax H3, Kling 3.0, Seedance 2.0 Fast e LTX-2.3 Fast, todos na fal.ai).
- **Modo de origem:** `t2v` (texto), `i2v` (imagem) ou `v2v` (vídeo, usa o primeiro quadro). Os modos `i2v` e `v2v` exigem arquivo de referência, enviado antes por `POST /api/estudio/upload`.
- **Duração:** 3 a 60 s na interface. **Resolução:** 480p ou 720p.
- **Clipe único:** quando a duração cabe num clipe do modelo local, a interface usa `POST /gerar-video` com `modo_execucao=async` e consulta `GET /status-video/{job_id}`, como antes.
- **Vídeo longo:** quando a duração passa do clipe máximo do modelo, ou o modelo é de nuvem, aparece o bloco "Vídeo longo". Ele mostra o plano (quantos clipes e de quantos segundos) e, na nuvem, o custo estimado e a caixa de autorização. Opções: continuidade (plano contínuo ou várias cenas com roteiro, uma por linha), e áudio (o som dos próprios clipes ou uma trilha do Estúdio de música). Se o trabalho parar (erro, cancelamento, painel reiniciado), aparece o botão **Retomar**.

### Música

- **Modelo:** YuE 2 (3B), fluxo `musica-yue2.json`.
- **Campos:** estilo (`style`), letra (`lyrics`, padrão `[instrumental]`), duração de 5 a 360 s e modo (`full`, `melody` ou `off`).
- **Melhorar Estilo com IA:** chama `POST /api/estudio/otimizar-prompt-musica`.

### Galeria

A galeria da interface guarda só o que foi gerado nesta sessão da página. Os arquivos ficam em disco (seção de armazenamento) e voltam a aparecer pelas rotas `GET /api/estudio/imagens`, `/videos` e `/musicas`.

## Como funciona

### Imagem: escolha do motor

A função `gerar_imagem` (em `rotas/estudio_imagem.py`) segue esta ordem:

1. **Modelo local** (começa com `local:`): exige o ComfyUI online. Se ele estiver fora, responde com `servico_offline`.
2. **ComfyUI** online e motor `auto` ou `comfyui`, ou modelo local: monta o grafo ComfyUI em memória e submete ao ComfyUI (`executar_comfyui_imagem`).
3. **Cloudflare Workers AI**, se houver as duas chaves e o modelo for `cf-*`, `flux`, `turbo`, `flux-anime` ou `auto`. Modelos usados: FLUX.1 Schnell, SDXL base 1.0 e DreamShaper 8 LCM.
4. **Pollinations** (`image.pollinations.ai`), sem chave, **só com `TUDOIA_ESTUDIO_POLLINATIONS=1`** no `.env`. O prompt vai na URL para um serviço público. Entra quando nenhum passo anterior se aplica ao modelo escolhido, ou quando o passo anterior falha.
5. **SVG de reserva**, gravado com o texto do prompt. Motor `estudio`. Com o Pollinations desligado, a resposta traz `aviso` explicando que nenhum motor respondeu, e a interface mostra esse aviso.

Cada resultado vai para o histórico visual (últimas 60 entradas, em memória).

### Inpainting

A requisição traz a imagem base (URL `/api/estudio/imagens/...`, `/api/estudio/uploads/...` ou só o nome do arquivo dentro de `imagens`), a máscara em base64 (aceita data URL) e o prompt. O servidor:

1. copia a base e a máscara para `ComfyUI\input`;
2. monta o grafo de inpainting em memória (`LoadImage`, `LoadImageMask`, `CLIPTextEncode`, `KSampler` e `VAEDecode`);
3. espera até 90 s pelo histórico do ComfyUI e copia o resultado para `dados\estudio\imagens`.

### Vídeo

- **Escolha do grafo** (`_preparar_grafo_video`): monta o grafo em memória conforme o modelo (`ltx`, `minimax`/`h3`, `i2v`, `5b` ou `wan14b-t2v`).
- **Dimensões:** MiniMax usa 768x768 em 480p e 1344x768 em 720p e 1080p. Wan e LTX usam 832x480 em 480p e 1280x704 em 720p e 1080p. Wan 14B I2V usa 640x640.
- **Quadros por modelo** (`PERFIS_VIDEO_LOCAL` e `quadros_video` em `estudio_servico.py`). O grafo grava sempre no fps do modelo; o `fps` pedido não muda mais a duração:

  | Modelo | fps | Grade de quadros | Clipe máximo | 5 s viram |
  |---|---|---|---|---|
  | Wan 2.2 5B | 24 | 4n+1 | 5 s (121) | 121 |
  | Wan 2.2 14B (T2V e I2V) | 16 | 4n+1 | 5 s (81) | 81 |
  | MiniMax H3 | 24 | 17k+5, para cima | 10 s (243) | 124 |
  | LTX-2.3 | 24 | 8n+1 | 20 s em 480p (481), 10 s em 720p (241) | 121 |

  Antes de 30/10/2026 o Wan 14B I2V tinha 81 quadros fixos (qualquer duração dava 5 s) e o T2V calculava com 24 fps mas gravava a 16 (um pedido de 5 s saía com 7,3 s).
- **LTX-2.3** (`_grafo_ltx23`): distilled 1.1 Q4_K_S em GGUF, num estágio de 8 passos com CFG 1 (sigmas do template oficial `video_ltx2_3_t2v`), sem o upscaler de latente, que não cabe com ele em 8 GB. Vídeo e áudio saem juntos. Com quadro inicial, a imagem passa por `ImageScale`, `LTXVPreprocess` e `LTXVImgToVideoInplace`. Base: o fluxo publicado em `unsloth/LTX-2.3-GGUF`. O fp8 oficial (29 GB) não cabe nos 32 GB de RAM da máquina.
- **Job:** `POST /prompt` devolve o `prompt_id`, que fica em memória (`_jobs_video`). O servidor consulta `/history/{id}` e copia o vídeo de `ComfyUI\output\video` para `dados\estudio\videos` com prefixo `comfy_vid_`. O tempo máximo de espera é 600 s.
- **Cancelar:** `POST /api/estudio/cancelar` chama `/interrupt` no ComfyUI. Interrompe a execução atual, seja ela qual for.

### Vídeo longo

Arquivos: `video_longo.py` (plano, motores e executor), `video_nuvem.py` (catálogo de nuvem e cliente do LiteLLM), `video_midia.py` e `midia_av.py` (mídia), `rotas/estudio_video_longo.py` (API).

1. **Plano** (`planejar_segmentos`): o menor número de clipes, os mais parecidos possíveis, cada um numa duração que o motor aceita. Exemplos: 60 s no Wan 14B são 12 clipes de 5 s; 23 s até 10 s por clipe são 8 + 8 + 7; 7 s no LTX Fast da nuvem (6, 8, …, 20 s) são um clipe de 8 s. Quando a soma passa do pedido, a montagem corta no total pedido, mas a nuvem cobra o clipe inteiro.
2. **Roteiro:** no modo contínuo todos os clipes usam a mesma descrição. No modo cenas, vale o roteiro digitado (uma cena por linha, até 12); sem roteiro, o Ollama local divide a descrição em cenas (o texto não sai da máquina). A resposta do modelo só é aceita se for uma lista JSON com o número certo de textos curtos; senão, cada cena vira a descrição com "Scene N of M".
3. **Continuidade:** no modo contínuo, o último quadro de cada clipe (JPEG) vira o quadro inicial do seguinte. Referência em vídeo usa o primeiro quadro, como no `v2v`. Modelo de nuvem sem endpoint de imagem continua só pelo texto, e a interface avisa. A seed de cada clipe é a do pedido mais o índice do clipe.
4. **Execução:** uma thread do painel roda um trabalho por vez (a GPU é uma só). Cada clipe é enviado, consultado a cada 3 s e baixado. Falha transitória (rede, 429, 5xx) é repetida até 4 vezes com espera exponencial e jitter. Timeout no envio à nuvem **não** é repetido: o pedido pode ter chegado ao provedor, e repetir pagaria duas vezes. Se o ComfyUI reiniciar e esquecer o clipe, ele é refeito uma vez. Limite por clipe: 60 min no local, 30 min na nuvem.
5. **Estado em disco:** `dados/estudio/video-longo/<id>/trabalho.json` é gravado a cada passo (escrita atômica), junto com os clipes e os quadros. Ao subir, o painel lê esses arquivos; o que estava em andamento volta como `interrompido`, e nada recomeça sozinho. **Retomar** pula os clipes prontos, consulta pelo id o clipe que já tinha sido enviado (sem novo pagamento) e refaz só o que falhou. Ficam guardados os 50 trabalhos mais recentes; os mais antigos perdem os clipes intermediários, e o MP4 final fica.
6. **Montagem** (`midia_av.py`): roda com o `python_embeded` do ComfyUI (`-I`), que já tem o PyAV; o painel não instala FFmpeg. Cada clipe é redimensionado para as dimensões do primeiro e reamostrado para o fps dele (por exemplo, clipes de 16 fps viram 24 fps repetindo quadros pelo tempo). Saída H.264 (CRF 18) com AAC 48 kHz estéreo em `dados/estudio/videos/video_longo_<id>.mp4`. A trilha, quando escolhida, substitui o som dos clipes. Sem trilha, o som dos clipes entra só se todos tiverem áudio; o áudio de cada clipe é cortado ou completado com silêncio para não perder a sincronia.
7. **Nuvem:** o painel chama `POST /v1/videos` do LiteLLM com o modelo fixado em `video/<nome>` (ou `video/<nome>-i2v` com quadro inicial), nunca pelo `tudoia-auto`. Os parâmetros do provedor vão em `extra_body`, com o tipo que o esquema da fal exige (o `seconds` do formato OpenAI viraria string e a fal recusaria nos campos inteiros). O quadro inicial vai como data URI JPEG. Depois o painel consulta `GET /v1/videos/{id}` e baixa `GET /v1/videos/{id}/content` (até 1 GB). O contrato foi conferido em 30/10/2026 com o LiteLLM 1.106.2 do container e um servidor falso da fila da fal: o corpo chegou com `duration` inteiro no Wan e texto no Kling, `start_image_url` em data URI, e a chave no cabeçalho `Authorization: Key`. Uma geração paga de verdade não foi testada.
8. **Deployments:** `config/video-nuvem.yaml` vira entradas `video/*` no config do LiteLLM (`gerador.py`), só para modelos com a chave no `.env`, fora de grupos e de fallbacks (um pedido pago nunca troca de provedor sozinho). O `model_info` leva o preço por segundo por resolução, para o LiteLLM registrar o gasto.
9. **Confirmação e teto:** sem `confirmar_nuvem: true`, a API recusa com `confirmacao_necessaria` e devolve a estimativa. Retomar na nuvem pede a confirmação de novo. Com `TUDOIA_VIDEO_NUVEM_TETO_USD`, estimativa acima do teto é recusada com `acima_do_teto`.

### Música

O servidor monta o grafo YuE 2 em memória com estilo, letra, seed e duração. Espera até 300 s pelo histórico e copia o áudio de `ComfyUI\output\audio` (ou `output`) para `dados\estudio\musicas` com prefixo `comfy_audio_`.

### Otimização de prompt

Imagem e vídeo usam a mesma lógica (`_otimizar_prompt_visual` e `_otimizar_prompt_video`). A música tem a sua (`_otimizar_prompt_musica`).

1. Se o texto já tem 30 palavras ou mais, não tem acento e não tem termos em português, devolve o texto como está.
2. Se `GROQ_API_KEY` existe, chama `https://api.groq.com/openai/v1/chat/completions` com o modelo `qwen/qwen3.8-27b` (timeout 6 s).
3. Se a Groq falhar ou não houver chave, chama o Ollama local com `qwen3.5:4b` (timeout 8 s).
4. Se tudo falhar, devolve o texto original sem alteração.

Com `GROQ_API_KEY` configurada, **o texto do prompt sai da máquina** e vai para a Groq.

## Modelos locais do ComfyUI

O painel lista os checkpoints e modelos de difusão que existem em `ComfyUI\models\` (`/api/estudio/catalogo-modelos`).

## Armazenamento

| Pasta | Conteúdo |
|---|---|
| `dados/estudio/imagens` | PNG e JPG gerados (ComfyUI e nuvem), resultados de inpaint e SVG de reserva |
| `dados/estudio/videos` | MP4 gerados (inclusive `video_longo_<id>.mp4`) |
| `dados/estudio/video-longo/<id>` | Estado do vídeo longo (`trabalho.json`), clipes e quadros intermediários |
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
| `POST /video-longo/estimar` | Plano de clipes e custo estimado, sem gerar nada |
| `POST /video-longo` | Cria um vídeo longo (até 60 s); na nuvem exige `confirmar_nuvem` |
| `GET /video-longo` e `GET /video-longo/{id}` | Lista os trabalhos recentes ou mostra um (fase, clipes prontos, URL do vídeo) |
| `POST /video-longo/{id}/cancelar` e `/retomar` | Cancela (o clipe já enviado à nuvem é cobrado) ou retoma do clipe que faltou |
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
3. **`POST /gerar-video` continua só local.** A nuvem entra pelo vídeo longo. O campo `motor` de `gerar-video` é ignorado.
4. **Prompts saem da máquina.** A Groq recebe o prompt quando há `GROQ_API_KEY`. O Pollinations recebe o prompt na URL só se `TUDOIA_ESTUDIO_POLLINATIONS=1`; por padrão ele fica desligado. No vídeo longo na nuvem, a fal.ai recebe a descrição de cada clipe e os quadros de referência (a imagem enviada e os últimos quadros dos clipes), só depois da confirmação.
4a. **Custo da nuvem é estimativa.** Os preços de `config/video-nuvem.yaml` foram copiados das páginas da fal em 30/10/2026 e mudam sem aviso. Cancelar não devolve o clipe já enviado. No Seedance, o preço de 480p não é publicado e fica igual ao de 720p.
4b. **Emendas no modo contínuo.** O último quadro garante a posição inicial, mas o movimento recomeça a cada clipe, e cor e identidade podem ir se desviando ao longo de muitos clipes. Clipes nativos mais longos (Wan 3.0 até 30 s, LTX-2.3 até 20 s) têm menos emendas.
5. **Portas fixas.** ComfyUI (8188) e Ollama (11434) não são configuráveis pelo `.env`.
6. **Jobs de vídeo ficam em memória.** Reiniciar o painel apaga `_jobs_video`. A consulta de estado volta a funcionar pelo histórico do ComfyUI, enquanto ele mantiver o job.
7. **Campos ignorados.** `modelo` é ignorado em inpaint e em música (sempre YuE 2).
8. **SVG de reserva.** O texto do prompt entra no SVG com `html.escape` (até 60 caracteres). O arquivo é servido como `application/octet-stream` (`servir_imagem_estudio`), então o `<img>` da interface provavelmente não o exibe. Isso é a confirmar no navegador.
9. **Modelo da Groq.** `qwen/qwen3.8-27b` não aparece em `config/modelos.yaml`. A existência desse modelo na Groq é a confirmar.
10. **Histórico visual.** As últimas 60 gerações ficam em memória (`HISTORICO_VISUAL`). Não há persistência.

## Veja também

- [modelos.md](modelos.md): download, verificação e espaço em disco dos pesos.
- [keycloak.md](keycloak.md): autenticação do painel.
- [servicos-docker.md](servicos-docker.md): como o painel sobe e para o ComfyUI e o Ollama no host.
- [../../config/modelos.yaml](../../config/modelos.yaml): manifesto de modelos, com destino de cada arquivo.

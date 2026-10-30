# Modelos de IA: manifesto, download e verificação

Este documento explica como o TudoIA obtém os pesos dos modelos de IA (Ollama e ComfyUI) sem guardá-los no projeto.
Os arquivos de referência são:

- `config/modelos.yaml`: o manifesto, com os modelos que o projeto usa.
- `scripts/modelos/baixar.py`: o baixador (listar, baixar, verificar).
- `tests/modelos/test_baixar.py`: testes do baixador.

## 1. Por que os modelos não estão no repositório

Os pesos somam cerca de 196 GB dentro da pasta do projeto (`modelos\`), quase tudo em ComfyUI portable e nos modelos do Ollama.
Pesos não são código-fonte: são grandes, têm licenças próprias (algumas exigem aceite em conta), mudam de versão e não
podem ir para uma cópia ou instalação do projeto. Por isso:

- Cada máquina baixa os próprios modelos a partir do manifesto.
- O projeto guarda só o manifesto (texto, poucos KB), o script e a documentação.
- `modelos/` continua sendo a pasta padrão de destino, mas o conteúdo dela não é parte do projeto.

## 2. Onde cada coisa fica

A pasta base é `<repositório>\modelos` por padrão. Para mudar, use `--base-dir DIR` ou a variável
`TUDOIA_MODELOS_DIR`. Os `destino` do manifesto são relativos a essa pasta.

| Componente | Pasta (com base em `modelos\`) | Como o TudoIA aponta para ela |
|---|---|---|
| Ollama | `ollama\models` | `OLLAMA_MODELS` do servidor. `scripts\tudoia.ps1 up` usa `TUDOIA_OLLAMA_MODELS` do `.env` ou, sem ela, `<raiz>\modelos\ollama\models` |
| ComfyUI | `comfyui\ComfyUI_windows_portable\ComfyUI\models\<categoria>\` | O Estúdio referencia os modelos instalados nessa pasta |

Importante sobre o Ollama: `ollama pull` é enviado ao **servidor** Ollama, que grava no `OLLAMA_MODELS` **dele**, e não no
do cliente. Se o servidor usar outra pasta, o baixador vai reportar o modelo como `ausente` mesmo após o pull. Mantenha
`OLLAMA_MODELS` apontando para `<base>\ollama\models`.

Categorias do ComfyUI usadas pelo manifesto: `checkpoints`, `clip`, `text_encoders`, `diffusion_models`, `unet`, `vae`, `loras`.

## 3. Formato do manifesto

Cada entrada tem estes campos (todos obrigatórios, exceto `arquivo` e `revisao`):

| Campo | Significado |
|---|---|
| `id` | Identificador único (minúsculas, dígitos, `.`, `_`, `-`; até 80 caracteres). |
| `tipo` | `ollama`, `url`, `huggingface` ou `comfyui-node-asset` (arquivo baixado para uma pasta do ComfyUI). |
| `destino` | Caminho relativo à pasta base. Sem `..`, sem caminho absoluto, sem `:`. |
| `origem` | `ollama`: `nome:tag`. `url` e `comfyui-node-asset`: URL `https://...`. `huggingface`: `dono/repositorio`. `null` = PENDENTE. |
| `arquivo` | Só `huggingface`: caminho do arquivo dentro do repositório. |
| `revisao` | Só `huggingface`: branch, tag ou commit (padrão `main`; prefira fixar um commit). |
| `tamanho_aprox_gb` | Estimativa usada para checar espaço livre antes do download. `null` = desconhecido. |
| `licenca` | `{nome, url}`. `null` quando não foi confirmado. |
| `obrigatorio` | `true` entra em `--obrigatorios`. |
| `usado_por` | Onde o TudoIA usa o modelo. |
| `sha256` | 64 caracteres hexadecimais minúsculos, quando conhecido. `null` = só presença e tamanho são verificados. |
| `notas` | Texto livre. Origem `null` exige `PENDENTE: informar origem` nas notas. |

Exemplo (modelo Ollama, já no manifesto):

```yaml
  - id: "ollama-qwen3.5-9b"
    tipo: "ollama"
    destino: "ollama/models"
    origem: "qwen3.5:9b"
    tamanho_aprox_gb: 6.6
    licenca: {nome: null, url: "https://ollama.com/library/qwen3.5"}
    obrigatorio: true
    usado_por: "Ollama: base de tudoia-chat, tudoia-agente, assistente, programador, revisor, tradutor"
    sha256: null
    notas: "Modelo do dia a dia. Licenca a confirmar na pagina do modelo."
```

Exemplo de entrada por URL com integridade declarada:

```yaml
  - id: "exemplo-modelo-url"
    tipo: "url"
    destino: "comfyui/ComfyUI_windows_portable/ComfyUI/models/vae/exemplo.safetensors"
    origem: "https://exemplo.org/arquivos/exemplo.safetensors"
    tamanho_aprox_gb: 0.3
    licenca: {nome: "Apache-2.0", url: "https://www.apache.org/licenses/LICENSE-2.0"}
    obrigatorio: false
    usado_por: "Estudio ComfyUI: fluxo X"
    sha256: "<64 hex minusculos, obtido de fonte confiavel>"
    notas: ""
```

O carregador recusa o manifesto inteiro se houver: id duplicado, `destino` com `..` ou absoluto, `origem` em `http://`,
URL com credenciais embutidas, `sha256` malformado, chave desconhecida (erro de digitação), ou `origem: null` sem o
marcador `PENDENTE`. Essa falha é intencional (fail closed).

## 4. Comandos

Rode a partir da raiz do repositório, com o Python do projeto:

```powershell
D:\TudoIA\.venv\Scripts\python.exe scripts\modelos\baixar.py --listar
D:\TudoIA\.venv\Scripts\python.exe scripts\modelos\baixar.py --obrigatorios
D:\TudoIA\.venv\Scripts\python.exe scripts\modelos\baixar.py --modelo ollama-qwen3.5-9b comfy-ae
D:\TudoIA\.venv\Scripts\python.exe scripts\modelos\baixar.py --verificar --obrigatorios
D:\TudoIA\.venv\Scripts\python.exe scripts\modelos\baixar.py --verificar
```

- `--listar`: tabela com `STATUS` (`presente`, `ausente`, `pendente-origem`). Não lê nem calcula hash de nenhum arquivo.
- `--obrigatorios` / `--modelo ID ...`: baixa. Modelos já presentes são pulados (`ja-presente`). Um download
  interrompido é retomado a partir do `.part`.
- `--verificar`: sem ids, verifica todos. Com `sha256` declarado, calcula o hash (pode levar minutos em arquivos grandes).
  Sem `sha256`, só confere a presença. Entradas `ollama` são confiadas ao próprio Ollama (que valida os digests no pull).

Códigos de saída: `0` ok; `1` validação, verificação, entrada PENDENTE ou dependência ausente; `2` rede ou disco.

Variáveis de ambiente:

- `TUDOIA_MODELOS_DIR`: pasta base alternativa.
- `HF_TOKEN`: token do Hugging Face. Só é enviado a `huggingface.co` e subdomínios. Nunca é gravado no manifesto, nem impresso.

Uso pela API Python (para ligar ao CLI do TudoIA depois):

```python
import importlib.util, sys
spec = importlib.util.spec_from_file_location("baixar", r"D:\TudoIA\scripts\modelos\baixar.py")
baixar = importlib.util.module_from_spec(spec); sys.modules["baixar"] = baixar; spec.loader.exec_module(baixar)
modelos = baixar.carregar_manifesto()
status = baixar.status_modelos(modelos, baixar.resolver_base())
```

Funções públicas: `carregar_manifesto`, `status_modelos`, `status_modelo`, `selecionar_modelos`, `baixar_modelo`,
`verificar_modelo`, `resolver_base`, `caminho_local`, `validar_destino`, `validar_url_https`.

## 5. Como o download é feito

- Escreve em `<destino>.part` e só renomeia para o nome final quando o conteúdo está completo e (se houver) o sha256 confere.
  Nunca existe arquivo parcial com o nome final.
- Retomada: se o `.part` existe, pede o restante com `Range` e `If-Range`. O validador do `If-Range` é o `ETag` forte
  da primeira resposta ou, sem ele, o `Last-Modified`, guardado em `<destino>.part.meta`. `ETag` fraco (`W/`) não vale
  (RFC 9110). Se o arquivo mudou no servidor, ou o servidor ignorou o `Range`, a resposta é 200 e o download recomeça do
  zero.
- Faixa conferida: numa resposta 206, o início do `Content-Range` precisa ser o tamanho do `.part`. Se não for, o
  download não junta os pedaços (o arquivo sairia corrompido).
- Tamanho: o total esperado vem do `Content-Range` (206) ou do `Content-Length` (200). Menos bytes que o esperado é falha
  transitória e é repetido.
- Sem tamanho declarado (sem `Content-Length`, por exemplo `chunked`) e sem `sha256` no manifesto, o download falha:
  o fim da conexão não prova que o arquivo veio inteiro. Com `sha256`, o hash decide.
- Repetição: até 4 tentativas com backoff (2, 4, 8 s) para erros transitórios (timeout, 429, 5xx, conexão caída).
  Erros permanentes (401, 403, 404) não são repetidos.
- Trava: um arquivo `<destino>.part.lock` impede dois downloads simultâneos do mesmo arquivo. Se nenhum download estiver rodando
  e a trava sobrou de uma queda, apague o `.lock`.
- Espaço: antes de baixar, compara o `tamanho_aprox_gb` com o espaço livre.
- sha256 divergente: o `.part` é apagado e o comando falha com código 1. Um arquivo final antigo nunca é substituído por
  conteúdo não verificado.
- Só `https://`. Redirecionamentos são refeitos um a um: se qualquer salto for `http://`, o download para antes de conectar.
- Ollama: roda `ollama pull <origem>` com lista de argumentos (sem shell). Se `ollama` não estiver no PATH, o script
  informa o comando a rodar manualmente.

## 6. Como adicionar um modelo

1. Confirme a origem na fonte oficial (página do modelo, repositório Hugging Face, URL direta).
2. Acrescente a entrada em `config/modelos.yaml` com um `id` novo. Para Hugging Face, use `tipo: huggingface`, `origem` com
   `dono/repositorio`, `arquivo` e, se possível, `revisao` com commit fixo.
3. Se souber o sha256 por fonte confiável, declare-o. Não calcule a partir de cópia local sem conferir a origem.
4. Rode `--listar` e confira o status. Depois `--modelo ID` e `--verificar --modelo ID`.
5. Rode `D:\TudoIA\.venv\Scripts\python.exe -m pytest -q tests\modelos` para garantir que o manifesto continua válido.

Para um modelo Ollama personalizado (como `tudoia-chat`), o manifesto guarda só a base (`FROM`). Depois do pull da base, crie o
modelo local com `ollama create tudoia-chat -f runtime\ollama\modelfiles\Modelfile.tudoia-chat` (o mesmo para os outros `Modelfile.*`).

## 7. Espaço em disco por perfil

Valores aproximados, calculados a partir de `tamanho_aprox_gb` (cada arquivo contado uma vez; componentes compartilhados,
como o `umt5_xxl` do Wan, entram só na primeira vez).

| Perfil | Modelos | GB aprox. |
|---|---|---|
| Stack de texto (mínimo) | Ollama: qwen3.5:9b, qwen3.5:4b, bge-m3 (obrigatórios) | 11,1 |
| + código e raciocínio | + qwen2.5-coder:7b, deepseek-r1:7b | 20,5 |
| Estúdio: SDXL foto | Juggernaut XL v9 | 6,6 |
| Estúdio: Z-Image turbo | z-image turbo, qwen3 4B, ae | 11,3 |
| Estúdio: Flux schnell | flux1 schnell GGUF, t5xxl, clip_l, ae | 11,4 |
| Estúdio: KREA2 | krea2 turbo, qwen3vl 4B, VAE, LoRA | 18,1 |
| Estúdio: música (YuE) | yue2 3B | 3,7 |
| Vídeo: Wan 2.2 5B | ti2v 5B, umt5, VAE | 16,9 |
| Vídeo: Wan 2.2 14B (t2v ou i2v) | 2 UNets, umt5, VAE, 4 LoRAs | 35,4 |
| Vídeo: MiniMax H3 | UNet, qwen3vl 32B, 2 VAEs, LoRA | 39,1 |
| Todos os ComfyUI do manifesto | (inclui os acima) | 165,0 |

Não entram no total: `qwen3:8b` e `qwen3-coder:30b` do Ollama (não medidos),
e os binários do ComfyUI portable e do Ollama, que são aplicativos e não modelos. Reserve espaço extra para `.part` durante
downloads grandes.

## 8. Licenças e modelos com acesso restrito

- Cada entrada tem `licenca`. `null` significa que a licença ainda não foi confirmada no repositório. Confirme na
  página do modelo antes de usar comercialmente.
- Modelos hospedados no Hugging Face podem exigir aceitar a licença na conta. Sem isso, o download responde 401 ou 403 e o
  baixador explica o motivo. Para esses casos:
  1. Entre em `huggingface.co`, abra a página do modelo e aceite a licença.
  2. Crie um token em `https://huggingface.co/settings/tokens` (leitura basta).
  3. Defina `HF_TOKEN` no ambiente (no PowerShell: `$env:HF_TOKEN = "hf_..."`). Não cole o token no manifesto nem em logs.
- O token só vai para `huggingface.co` e subdomínios. Hosts de CDN que não sejam do Hugging Face recebem a requisição sem o token.
- O `.env` da raiz não é lido pelo baixador. Se quiser usar `HF_TOKEN` por lá, exporte a variável antes de rodar o script.

## 9. Nova máquina: passo a passo

1. Clone ou copie o projeto. A pasta `modelos\` não deve vir junto (está no `.gitignore`).
2. Instale o Ollama e confirme que `ollama` está no PATH (`ollama --version`).
3. Defina a pasta de modelos do Ollama. Pelo `scripts\tudoia.ps1`, `OLLAMA_MODELS` aponta para `TUDOIA_OLLAMA_MODELS` ou,
   sem ela, para `<raiz>\modelos\ollama\models`. Se quiser outro disco, defina `TUDOIA_MODELOS_DIR` e
   `TUDOIA_OLLAMA_MODELS=<essa pasta>\ollama\models`.
4. Suba o servidor Ollama (o `tudoia.ps1` faz isso) e rode:
   `D:\TudoIA\.venv\Scripts\python.exe scripts\modelos\baixar.py --listar` para ver o que falta.
5. Baixe os obrigatórios: `D:\TudoIA\.venv\Scripts\python.exe scripts\modelos\baixar.py --obrigatorios`.
6. Crie os modelos locais do TudoIA a partir dos Modelfiles em `runtime\ollama\modelfiles\` (`ollama create tudoia-chat -f ...`, e os outros), se for usá-los.
7. Para o Estúdio, baixe os modelos ComfyUI desejados (`--modelo ID ...`) depois que as origens estiverem preenchidas (seção 10).
   Hoje nenhuma origem ComfyUI está no manifesto, então esse passo depende do preenchimento.
8. Confira com `--verificar --obrigatorios`.

## 10. Entradas PENDENTE (o dono precisa preencher)

Estas 29 entradas existem no manifesto, mas `origem` é `null`: o baixador as lista como `pendente-origem` e não baixa nada.
O repositório não diz de onde esses arquivos vieram, então nenhuma URL foi inventada. Para cada uma, informe:

- o repositório de origem (ex.: `dono/repositorio` no Hugging Face, com `arquivo` = caminho exato) **ou** uma URL `https://` direta;
- se for Hugging Face com acesso restrito, se a licença foi aceita na conta;
- a revisão (commit) usada, se souber;
- o sha256 de uma fonte confiável, se houver (não calcule a partir do arquivo local sem conferir a origem);
- a licença (nome e URL).

Depois, troque `origem: null` por `origem: "..."`, ajuste `tipo` para `huggingface` (se for HF), remova `PENDENTE` das notas e rode `--listar`.

**ComfyUI (29 entradas, todas presentes localmente, origem desconhecida)**

- Checkpoints: `comfy-juggernaut-xl-v9` (Juggernaut-XL_v9_RunDiffusionPhoto_v2.safetensors), `comfy-yue2-3b-int8`
- CLIP: `comfy-clip-l`, `comfy-t5xxl-fp8`
- Text encoders: `comfy-qwen3vl-4b-fp8`, `comfy-qwen3vl-32b-minimax`, `comfy-qwen3-4b-fp8-mixed`, `comfy-umt5-xxl-fp8`
- Diffusion models: `comfy-krea2-turbo-int8`, `comfy-minimax-h3-fl2va-int8`, `comfy-wan22-i2v-high-fp8`, `comfy-wan22-i2v-low-fp8`,
  `comfy-wan22-t2v-high-fp8`, `comfy-wan22-t2v-low-fp8`, `comfy-wan22-ti2v-5b-fp16`, `comfy-z-image-turbo-int8`
- UNet: `comfy-flux1-schnell-gguf` (exige o custom node ComfyUI-GGUF, presente em `custom_nodes\ComfyUI-GGUF`)
- VAE: `comfy-ae`, `comfy-minimax-h3-audio-vae`, `comfy-minimax-h3-video-vae`, `comfy-qwen-image-vae`, `comfy-wan22-vae`, `comfy-wan21-vae`
- LoRA: `comfy-krea2-darkbrush-lora`, `comfy-minimax-h3-turbo-8step-lora`, `comfy-wan22-i2v-lightx2v-high-lora`,
  `comfy-wan22-i2v-lightx2v-low-lora`, `comfy-wan22-t2v-lightx2v-high-lora`, `comfy-wan22-t2v-lightx2v-low-lora`

## 11. Solução de problemas

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| `erro: ... https` ao carregar | Manifesto com `http://` ou URL sem host | Use `https://` |
| `destino ... '..'` ou absoluto | Caminho fora da pasta base | Use caminho relativo a `modelos` |
| `'ollama' nao encontrado no PATH` | Ollama não instalado ou PATH sem ele | Instale e reabra o terminal; ou rode o `ollama pull` indicado |
| Pull feito, mas `--listar` mostra `ausente` | Servidor Ollama usa outro `OLLAMA_MODELS` | Corrija `OLLAMA_MODELS` do servidor (seção 2) e reinicie o Ollama |
| `acesso negado (HTTP 401/403)` | Modelo restrito ou token ausente | Aceite a licença no Hugging Face e defina `HF_TOKEN` (seção 8) |
| `sha256 divergente` | Arquivo corrompido, ou origem mudou | O `.part` foi apagado. Tente de novo; se persistir, confira o sha256 e a revisão |
| `outro download ... em andamento` | Trava de um download anterior interrompido | Se nenhum download estiver rodando, apague `<arquivo>.part.lock` |
| `espaco livre insuficiente` | Disco cheio em relação ao `tamanho_aprox_gb` | Libere espaço, ou aponte `--base-dir`/`TUDOIA_MODELOS_DIR` para outro disco |
| Download para no meio (código 2) | Rede instável ou timeout | Rode de novo: o `.part` é retomado |
| `certificado TLS nao confiavel` | Proxy ou antivírus com certificado próprio | Instale a CA corporativa no Windows e tente de novo |
| `PyYAML nao instalado` | Ambiente sem as dependências do projeto | `D:\TudoIA\.venv\Scripts\python.exe -m pip install pyyaml` (ou rode com o venv do projeto) |

## 12. Decisões em aberto (o dono confirma)

1. **Quais modelos são obrigatórios por perfil.** Hoje `obrigatorio: true` só para `qwen3.5:9b`, `qwen3.5:4b` e `bge-m3`
   (o Cérebro e o classificador semântico do roteador usam o `bge-m3`; o painel usa o `qwen3.5:4b`). Todos os ComfyUI são opcionais.
2. **`qwen3-coder:30b`** (base do `Modelfile.opencode-coder`) é grande e não está no disco. Confirme se entra no perfil padrão.
3. **Modelos presentes sem referência.** `gemma4:e4b-it-qat` e `qwen2.5-coder:1.5b` estão no disco do Ollama, mas nenhum
   Modelfile nem código do repositório os usa. Não entraram no manifesto. Remova do disco ou inclua.
4. **Modelfiles e fluxos fora de `modelos\`.** Já há uma movimentação em curso (`modelos\ollama\Modelfile.*` para
   `runtime\ollama\modelfiles\`, e `modelos\comfyui\fluxos\` para `runtime\comfyui\fluxos\`), feita por outro trabalho no
   working tree. Esta documentação usa os caminhos novos; confirme que a movimentação foi concluída e que o painel acompanha.
5. **Instalação do ComfyUI portable.** Hoje fica dentro de `modelos\comfyui\`. O manifesto não instala o ComfyUI, só os modelos.
   Decida onde ele fica, para que a pasta `modelos\` possa ser só de dados.
6. **Empacotamento.** Quem gera a cópia/instalação do projeto precisa excluir `modelos\` (o `.gitignore` já exclui os pesos
   para o git, mas não para cópias de pasta).
7. **Revisões fixadas e sha256.** Para cada origem preenchida, recomendo fixar commit e sha256 vindos da fonte.

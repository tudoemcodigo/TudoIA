# Serviços Docker e processos do host

O TudoIA mistura containers Docker e processos do Windows. Os containers estão definidos em `runtime/docker-compose.yml`. Ollama e ComfyUI rodam direto no host, porque precisam da GPU e ficam fora do compose. Este documento descreve os dois grupos, como subir e parar, e o que vale saber antes de mexer.

## Visão geral

- **Arquivo:** `runtime/docker-compose.yml`, nome de projeto `tudoia` (`name: tudoia`).
- **Variáveis:** o compose lê o `.env` da raiz com `--env-file` só para substituir `${VAR}`. Nenhum serviço recebe o `.env` inteiro (não há `env_file`). Cada um recebe só as variáveis listadas na tabela.
- **Portas:** todas publicadas em `127.0.0.1`. Nenhum container fica acessível pela rede local.
- **Healthcheck:** `litellm-db`, `litellm`, `searxng`, `cerebro` e `n8n`.
- **Imagens:** seis das sete imagens estão fixadas por digest (`@sha256:`). O `cerebro` é construído localmente a partir de `runtime/cerebro/Dockerfile` e a base dele não tem digest (ver riscos).

## Containers

| Serviço | Container | Imagem | Porta no host | Variáveis (nomes) | Volumes | Depende de | Healthcheck |
|---|---|---|---|---|---|---|---|
| `litellm-db` | `litellm-db` | `postgres:17.6-alpine` | `127.0.0.1:5433` para `5432` | `POSTGRES_USER`, `POSTGRES_PASSWORD` (de `LITELLM_DB_PASSWORD`), `POSTGRES_DB`, `TZ` | volume `litellm-db` | nada | `pg_isready`, a cada 5 s, 10 tentativas |
| `litellm` | `litellm` | `ghcr.io/berriai/litellm:main-latest` | `127.0.0.1:4000` | `DATABASE_URL`, `LITELLM_MASTER_KEY`, `OLLAMA_URL` (padrão `http://host.docker.internal:11434`), `TZ` e as chaves de provedor: `NVIDIA_NIM_API_KEY`, `NVIDIA_NIM_API_BASE`, `OPENROUTER_API_KEY`, `GROQ_API_KEY`, `GEMINI_API_KEY`, `CLOUDFLARE_API_KEY`, `CLOUDFLARE_ACCOUNT_ID`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, `XAI_API_KEY`, `HF_TOKEN` | `config/` (leitura), `runtime/litellm/*.py` (leitura), `runtime/litellm/config.yaml` (leitura), `dados/logs` | `litellm-db` saudável | `GET /health/liveliness`, a cada 30 s (início: 60 s) |
| `searxng` | `searxng` | `searxng/searxng:2026.10.19-81371861f` | `127.0.0.1:8080` | `SEARXNG_SECRET` | `runtime/searxng` para `/etc/searxng` | nada | `GET /healthz` responde `OK`, a cada 30 s |
| `cerebro` | `cerebro` | construído de `runtime/cerebro/Dockerfile` | `127.0.0.1:8765` | `OLLAMA_URL`, `SEARXNG_URL`, `CEREBRO_DOCS`, `CEREBRO_DOCS_HOST` (opcional), `CEREBRO_DADOS`, `CEREBRO_OIDC_ISSUER`, `CEREBRO_OIDC_JWKS_URL`, `CEREBRO_OIDC_CLIENT_ID`, `CEREBRO_TOKEN_ESTATICO` | `dados/documentos` para `/docs` (leitura), `dados/cerebro` para `/dados` | `searxng` (só ordem de início) | `GET /saude`, a cada 30 s |
| `kokoro` | `kokoro` | `ghcr.io/remsky/kokoro-fastapi-cpu:v0.9.0` | `127.0.0.1:8880` | nenhuma | nenhum | nada | nenhum |
| `open-webui` | `open-webui` | `ghcr.io/open-webui/open-webui:main` | `127.0.0.1:3000` para `8080` | `OLLAMA_BASE_URL`, `WEBUI_NAME`, `WEBUI_SECRET_KEY`, `ENABLE_API_KEYS`, `TZ` | volume `open-webui` em `/app/backend/data`, `runtime/open-webui/env.py` e nove imagens de `runtime/open-webui/static` (leitura) | `searxng`, `kokoro` (só ordem de início) | nenhum |
| `n8n` | `n8n` | `docker.n8n.io/n8nio/n8n:latest` (digest fixo; o container em execução respondeu `n8n --version` = 2.44.6) | `127.0.0.1:5678` | `GENERIC_TIMEZONE`, `TZ`, `N8N_HOST`, `N8N_WEBHOOK_URL`, `N8N_RESTRICT_FILE_ACCESS_TO`, `N8N_ENCRYPTION_KEY`, `N8N_BLOCK_ENV_ACCESS_IN_NODE=true` | volume `n8n` em `/home/node/.n8n`, `dados/documentos` em `/data/docs` | nada | `GET /healthz`, a cada 30 s (início: 60 s) |

Todas as imagens de terceiros, exceto `cerebro`, têm digest no compose. Os nomes das imagens estão também em [../terceiros.md](../terceiros.md).

### Ordem de início

O compose respeita só o que está em `depends_on`:

1. `litellm-db` sobe e fica saudável (`pg_isready`).
2. `litellm` sobe depois que o banco está saudável.
3. `searxng` sobe. Em seguida, `cerebro`, `kokoro` e `open-webui` sobem, nessa ordem de dependência. Nada garante que o `searxng` esteja pronto, só que o container foi iniciado.
4. `n8n` não tem dependências.

O `litellm` é o único serviço com dependência condicionada a saúde. Os demais dependem só de o container ter iniciado.
Os healthchecks de `litellm`, `searxng`, `cerebro` e `n8n` só marcam o estado (`healthy` ou `unhealthy`). Nenhum
`depends_on` espera por eles.

### Open WebUI e o arquivo `env.py`

O arquivo `runtime/open-webui/env.py` é montado sobre `/app/backend/open_webui/env.py` (volumes do serviço `open-webui` no compose). Não é um arquivo novo: é uma **cópia completa** do `env.py` original do Open WebUI, com duas mudanças. A comparação foi feita contra o `env.py` extraído da imagem `ghcr.io/open-webui/open-webui:main@sha256:4860ba...`, que traz o Open WebUI 0.12.3 (`/app/package.json`). Só 11 linhas diferem:

| Trecho | Upstream | No TudoIA |
|---|---|---|
| `WEBUI_NAME` | padrão `Open WebUI`, com a regra que acrescenta ` (Open WebUI)` ao nome | padrão `TudoIA` |
| `WEBUI_FAVICON_URL` | fixo em `https://openwebui.com/favicon.png` | lido da variável, com padrão `/static/favicon.png` |

Com `WEBUI_NAME=TudoIA` no compose, o nome final é o mesmo nos dois casos. O efeito prático das mudanças é o padrão do favicon servido localmente.

Além do `env.py`, o compose monta nove imagens de `runtime/open-webui/static/` sobre os ícones de `/app/build/static/`. Nenhuma delas tem o mesmo hash do arquivo original da imagem. `logo.png`, `splash.png` e `splash-dark.png` são o mesmo arquivo. `favicon.png`, `favicon-96x96.png` e os dois `web-app-manifest` são outro arquivo, igual ao `painel/tudoia_painel/static/logo-512.png`. Isso indica que a marca foi substituída pela do TudoIA, o que tem implicação de licença (ver [../terceiros.md](../terceiros.md)).

Ao atualizar o digest do Open WebUI, extraia de novo o `env.py` da imagem, compare com o arquivo do repositório e reaplique as duas mudanças. Se a estrutura de `/app/build/static` mudar, os montes do compose precisam ser revistos.

## Processos do host

### Ollama

- **Início:** o painel (`painel/tudoia_painel/servicos.py`, `_start_ollama`) executa `ollama serve` com `OLLAMA_HOST=127.0.0.1:11434` e `OLLAMA_MODELS` apontando para `TUDOIA_OLLAMA_MODELS` ou, sem ela, `modelos\ollama\models`. O `scripts\tudoia.ps1 up` faz o mesmo e também lê `TUDOIA_OLLAMA_MODELS` do `.env`.
- **Parada:** o painel encerra o processo que escuta na porta 11434 e também `ollama.exe` e `ollama_llama_server.exe` (`taskkill`).
- **Bind:** no Windows e no Docker Desktop, só `127.0.0.1:11434`. Os containers chegam ao loopback do host por `host.docker.internal` (testado). No Linux com Docker Engine sem Docker Desktop, `host.docker.internal` (`host-gateway`) é o IP da bridge `docker0`, não o loopback. Por isso o `scripts/tudoia.sh` (`endereco_ollama`) faz o Ollama escutar no IPv4 da `docker0` (ex.: `172.17.0.1`), nunca em `0.0.0.0`. Nesse caso, a CLI do Ollama e o painel no host precisam de `OLLAMA_HOST=<esse IP>:11434`, e o firewall (ufw) precisa liberar a porta para as redes do Docker. Não testado em Linux.

### ComfyUI

- **Início:** o painel executa `cmd.exe /c run_nvidia_gpu.bat` dentro de `TUDOIA_COMFYUI_PORTABLE` (padrão `modelos\comfyui\ComfyUI_windows_portable`). A saída vai para `dados/logs/comfyui.log`.
- **Parada:** o painel encerra o processo que escuta na porta 8188 e os processos cuja linha de comando contém o caminho do portable.
- **Porta:** 8188, em `127.0.0.1` (padrão do ComfyUI). Não é configurável pelo `.env`.
- Detalhes do uso pelo Estúdio em [estudio.md](estudio.md).

### Como o painel controla os serviços

O painel (`painel/tudoia_painel/servicos.py`) faz três coisas:

- **Estado:** `docker ps` diz se um container está rodando. Para Ollama e ComfyUI, o painel testa se a porta responde em `127.0.0.1`.
- **Ação em um serviço:** `POST /api/servicos/{nome}/{acao}` com `start`, `stop` ou `restart`. Para containers, o painel roda `docker compose` com `up -d`, `stop` e `restart`. Para os processos do host, aplica a lógica descrita acima.
- **Ação em todos:** `POST /api/servicos/todos/{acao}`. No `start`, sobe Ollama e ComfyUI (se as portas estiverem fechadas), depois faz `up -d` do compose. Falhas ao subir os processos do host são ignoradas em silêncio: a resposta diz sucesso mesmo se o ComfyUI não iniciou. Confira o estado na aba de serviços ou em `dados/logs/comfyui.log`.

## Subir, parar e ver o estado

### Pelo script (recomendado)

Execute na raiz do repositório, no PowerShell (ou `scripts\tudoia.cmd`, que chama o `.ps1`):

```powershell
scripts\tudoia.ps1 up       # sobe Ollama (se a porta 11434 estiver livre), sincroniza a governança e roda compose up -d --build
scripts\tudoia.ps1 status   # docker compose ps
scripts\tudoia.ps1 down     # docker compose down (remove containers e rede; mantém os volumes)
scripts\tudoia.ps1 painel   # sobe o painel em http://127.0.0.1:3100/app/
```

Atenções:

- `up` **não** sobe o ComfyUI. Para ele, use o painel ou inicie `run_nvidia_gpu.bat` manualmente.
- `up` faz `--build`, então reconstrói o `cerebro`. O `start` do painel não faz `--build`.
- `down` remove os containers. O `stop` do painel só pausa os containers. Ambos preservam os volumes nomeados.
- O script para com o código de saída do primeiro comando nativo que falhar (função `Nativo`). Um `sync` que falha não deixa o `up` seguir para o `compose up`.

Os demais comandos do script (`sync`, `verificar`, `segredos`, `keycloak`, `modelos`, `n8n-credencial`, `backup`) são descritos em [../instalacao.md](../instalacao.md#comandos-disponíveis) e nos documentos de cada componente.

No Linux, o equivalente é `scripts/tudoia.sh`, com os mesmos comandos (ver [../instalacao.md](../instalacao.md#linux)).

### Direto pelo Docker Compose

Na raiz do repositório:

```powershell
docker compose -p tudoia -f runtime\docker-compose.yml --env-file .env up -d
docker compose -p tudoia -f runtime\docker-compose.yml ps
docker compose -p tudoia -f runtime\docker-compose.yml logs -f litellm
docker compose -p tudoia -f runtime\docker-compose.yml stop
docker compose -p tudoia -f runtime\docker-compose.yml down
```

Para um serviço só, acrescente o nome no fim: `up -d cerebro`, `restart n8n`, `logs -f cerebro`.

### Checar a saúde

- `litellm-db`, `litellm`, `searxng`, `cerebro`, `n8n`: `docker inspect --format "{{.State.Health.Status}}" <nome>` deve retornar `healthy`. O `tudoia.ps1 status` mostra o mesmo estado.
- Painel: `http://127.0.0.1:3100/saude` responde `{"ok": true}`, sem login.
- Cérebro: `http://127.0.0.1:8765/saude` retorna contagens e o estado da última indexação.
- LiteLLM: a interface em `http://localhost:4000/ui`.
- Ollama: `http://127.0.0.1:11434` responde (a resposta exata da raiz não foi conferida nesta versão; a confirmar).
- ComfyUI: `http://127.0.0.1:8188/system_stats`.

## Riscos e divergências

Itens verificados no código. Os de maior impacto vêm primeiro.

1. **Lista de variáveis do LiteLLM precisa acompanhar o catálogo** (antes: o LiteLLM recebia o `.env` inteiro; corrigido). Provedor novo em `config/catalogo-modelos.yaml` precisa da chave em `environment` do serviço `litellm`. Sem isso, o `config.yaml` referencia `os.environ/<CHAVE>` e o container não tem o valor. `tests/runtime/test_compose.py` falha nesse caso.
2. **O Open WebUI não passa pelo LiteLLM para o Ollama.** O comentário no topo do compose diz que o LiteLLM é o gateway de chat. Mas `OLLAMA_BASE_URL` do serviço `open-webui` aponta direto para o Ollama no host. Chamadas feitas pelo Open WebUI ao Ollama não passam pelo roteador, pela quarentena nem pelos limites do LiteLLM. A ligação do Open WebUI ao LiteLLM, se existir, é feita na interface (a confirmar).
3. **Ollama escuta só em loopback** (`127.0.0.1:11434`) no Windows e no Docker Desktop, como explicado acima.
4. **`N8N_ENCRYPTION_KEY` é parte do backup do n8n** (antes: a chave não chegava ao container; corrigido). O compose repassa a chave do `.env`. As credenciais do volume `n8n` só decifram com ela. O `tudoia.ps1 backup` não copia o `.env`: guarde a chave à parte. Uma instalação que já tinha credenciais cifradas com a chave gerada pelo próprio n8n, antes da mudança, pode precisar recriá-las (a confirmar na instância).
5. **`runtime/litellm/config.yaml` precisa existir antes do `up`.** O compose monta esse arquivo. Ele é gerado pelo painel (`POST /api/roteador/gerar`) e está no `.gitignore`. Em um clone limpo, ele não existe e o Docker cria um diretório no lugar, o que impede o `litellm` de subir (a confirmar em clone limpo). Gere o arquivo pelo painel antes do primeiro `up`.
6. **A base do Cérebro não tem digest.** O `runtime/cerebro/Dockerfile` usa `python:3.12-slim` e `ghcr.io/astral-sh/uv:0.13.0`, ambos por tag. Isso contradiz a política de imagens fixadas por digest. A versão do uv está fixada, mas não o conteúdo da imagem.
7. **Cérebro na rede Docker** (antes: sem autenticação; corrigido). `/mcp` e `/indexar` exigem token (JWT do cliente `tudoia-mcp` ou `CEREBRO_TOKEN_ESTATICO`). Só `/saude` é público. Ver [cerebro.md](cerebro.md#autenticação).
8. **Healthcheck não condiciona a ordem de início.** `litellm-db`, `litellm`, `searxng`, `cerebro` e `n8n` têm `healthcheck`; Kokoro e Open WebUI não. Só o `litellm` espera um deles (`litellm-db` saudável). `depends_on` sem condição só garante o início, não a prontidão.
9. **Reinicialização após reboot.** Os containers têm `restart: unless-stopped`. Ollama e ComfyUI não sobem sozinhos ao ligar a máquina (a confirmar). Use o `up` ou o painel.
10. **Imagens `main`, `latest` e `main-latest`.** A tag muda, mas o digest fixa o conteúdo. Atualizar exige trocar o digest no compose, e isso deve ser feito com conferência (ver o item do `env.py` do Open WebUI).
11. **`kokoro` sem ligação explícita.** O Open WebUI declara dependência de `kokoro`, mas nenhuma variável do compose aponta para ele. A configuração do TTS fica na interface (a confirmar).
12. **Kill por porta.** O painel encerra o processo que escuta na porta do serviço (8188 ou 11434), seja ele qual for. Se outro programa usar a porta, ele também é encerrado.

## Veja também

- [../instalacao.md](../instalacao.md): preparação da máquina.
- [../configuracao.md](../configuracao.md): variáveis do `.env`.
- [estudio.md](estudio.md): ComfyUI, fluxos e modelos.
- [automacao-n8n.md](automacao-n8n.md): workflows do n8n.
- [cerebro.md](cerebro.md): o serviço `cerebro` em detalhe.
- [painel.md](painel.md): a interface de controle dos serviços.
- [keycloak.md](keycloak.md): autenticação do painel.
- [../terceiros.md](../terceiros.md): imagens e licenças de terceiros.

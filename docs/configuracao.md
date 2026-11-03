---
titulo: Configuração (.env)
tipo: referencia
dono: TudoIA (mantenedor do repositório)
status: vigente
classificacao: publico
verificado-em: 2026-11-03
---

[🏠 TudoIA](../README.md) › [📚 Documentação](README.md) › ⚙️ Configuração

# ⚙️ Configuração (.env)

> Para quem instala, opera ou desenvolve o TudoIA: toda variável lida do `.env` (ou do ambiente), com padrão, efeito e onde é usada. O modelo versionado é o `.env.example`; nenhum valor real aparece aqui, só `<chave>`.

## 📑 Sumário

- [🎯 Visão geral](#-visão-geral)
- [⚙️ Variáveis](#️-variáveis)
  - [🔐 Identidade OIDC do painel](#-identidade-oidc-do-painel)
  - [🪪 Keycloak e clientes de serviço](#-keycloak-e-clientes-de-serviço)
  - [🔑 Segredos internos](#-segredos-internos)
  - [🐳 Stack Docker](#-stack-docker)
  - [📁 Caminhos](#-caminhos)
  - [🖥️ Local (host e containers)](#️-local-host-e-containers)
  - [☁️ Provedores gratuitos](#️-provedores-gratuitos)
  - [💳 Provedores pagos](#-provedores-pagos)
  - [🎨 Estúdio](#-estúdio)
  - [🏛️ Governança e MCP](#️-governança-e-mcp)
  - [🤖 SquadTI](#-squadti)
  - [🔒 Lidas só dentro de containers](#-lidas-só-dentro-de-containers)
  - [🛠️ Ferramentas de desenvolvimento](#️-ferramentas-de-desenvolvimento)
- [❌ Erros e diagnóstico](#-erros-e-diagnóstico)
- [🛡️ Segurança](#️-segurança)
- [❓ Perguntas frequentes](#-perguntas-frequentes)

---

## 🎯 Visão geral

Toda a configuração do TudoIA fica em um único arquivo, o `.env` da raiz do repositório. Ele nasce da cópia do `.env.example` (ou é escrito pelo instalador), tem os segredos internos preenchidos por `tudoia segredos` e pode ser editado à mão ou pela aba **Segredos** do painel.

Regras gerais, conferidas em `painel/tudoia_painel/envfile.py`:

- Formato `NOME=valor`, sem espaço em volta do `=`. A linha só vale se o nome casa `[A-Za-z_][A-Za-z0-9_]*`.
- **Não use aspas.** A gravação pelo painel remove aspas externas do valor (`limpar_valor`), mas a leitura (`ler_env`) devolve o texto como está, e o `docker compose` e os scripts PowerShell tratam o `.env` cada um a seu jeito.
- Chave vazia significa "não configurado". Um provedor de nuvem só entra no roteador se a chave dele estiver preenchida.
- O painel grava preservando comentários, ordem e fim de linha (CRLF ou LF). Antes de cada gravação, o arquivo anterior vai para `dados\backups\env\` (no máximo 10 cópias, as mais antigas são apagadas).
- A aba Segredos mostra os valores mascarados. Só o papel `tudoia-admin` revela um valor (`POST /api/segredos/{chave}/revelar`). Ver [segurança](seguranca.md).
- `TUDOIA_*` definidas no ambiente do processo vencem as do `.env` no login do painel (`carregar_config_auth`), no provisionamento do Keycloak e nos caminhos do ComfyUI e do Ollama.
- `.env` está no `.gitignore` (assim como `.env.*`, exceto `.env.example`). O `.env` não entra no backup do `tudoia backup`.

> [!IMPORTANT]
> Guarde uma cópia do `.env` fora do repositório: ele concentra os segredos, e a `N8N_ENCRYPTION_KEY` e as senhas dos bancos não podem ser recuperadas depois (ver [Segredos internos](#-segredos-internos)).

## ⚙️ Variáveis

### 🔐 Identidade OIDC do painel

Lidas por `painel/tudoia_painel/autenticacao.py` (`ConfigAuth.do_ambiente`).

| Variável | Obrigatória | Padrão no `.env.example` | Efeito |
|---|---|---|---|
| `TUDOIA_OIDC_ISSUER` | sim | `http://localhost:8180/realms/tudoia` | Issuer OIDC. Precisa começar com `http://` ou `https://`; o painel lê `<issuer>/.well-known/openid-configuration`. |
| `TUDOIA_OIDC_CLIENT_ID` | sim | `tudoia-painel` | Client ID registrado no IdP. |
| `TUDOIA_OIDC_CLIENT_SECRET` | sim | vazia | Segredo do client; gravado pelo `tudoia keycloak`. Nunca versionar. |
| `TUDOIA_OIDC_SCOPE` | não | `openid email profile` | Escopos pedidos no login (esse também é o padrão do código). |
| `TUDOIA_SESSAO_SEGREDO` | sim (gerada) | vazia | Assina o cookie de sessão; mínimo de 32 caracteres, senão a autenticação não é configurada. Se vazia e o issuer existe, o painel gera uma (48 bytes em base64url) e grava no `.env`. |
| `TUDOIA_COOKIE_SEGURO` | não | `0` | `1`, `true` ou `sim` faz o cookie trafegar só por HTTPS (atrás de um proxy com TLS). `0` serve para `http://127.0.0.1`. |
| `TUDOIA_API_BEARER_CLIENTES` | não | ausente | Lista de `azp` (clientes de serviço do Keycloak), separados por vírgula, que podem chamar `/api` com `Authorization: Bearer <JWT>`. Vazia, o Bearer fica desligado (401 `bearer_desativado`). |
| `TUDOIA_PAINEL_PORTA` | não | ausente | Porta do painel para o provisionamento do Keycloak montar os redirect URIs (padrão `3100`). O próprio painel recebe a porta por `tudoia painel --porta` e a exporta para si. |

Sem `TUDOIA_OIDC_ISSUER`, `TUDOIA_OIDC_CLIENT_ID` ou `TUDOIA_OIDC_CLIENT_SECRET`, ou com `TUDOIA_SESSAO_SEGREDO` curto, toda rota `/api` do painel responde 503. É intencional (fail-closed).

### 🪪 Keycloak e clientes de serviço

Lidas por `scripts/keycloak/provisionar.py`, `scripts/keycloak/token_mcp.py` e `scripts/n8n/credencial_cerebro.py`. O compose usa as três primeiras para o container `keycloak`.

| Variável | Padrão | Efeito |
|---|---|---|
| `TUDOIA_KEYCLOAK_URL` | `http://localhost:8180` | Endereço do Keycloak (API de administração). Precisa ser `http://` ou `https://`. |
| `TUDOIA_KEYCLOAK_ADMIN` | `admin` no template; pedido no terminal se vazia | Administrador do realm `master` (no compose, `KC_BOOTSTRAP_ADMIN_USERNAME`). |
| `TUDOIA_KEYCLOAK_ADMIN_PASSWORD` | vazia | Senha desse administrador (`KC_BOOTSTRAP_ADMIN_PASSWORD`). Gerada por `segredos` quando `COMPOSE_PROFILES` tem `keycloak`; sem ela e sem terminal interativo o provisionamento falha. |
| `TUDOIA_KEYCLOAK_REALM` | `tudoia` | Realm a provisionar e usado pelos scripts (fora do template). |
| `TUDOIA_IDP_*` | conforme o IdP | Variáveis referenciadas pelos arquivos de `infra/keycloak/idps/` (por exemplo `TUDOIA_IDP_ENTRA_TENANT_ID`, `TUDOIA_IDP_OIDC_ISSUER`). |

Variáveis que o provisionamento **grava** no `.env` (além de `TUDOIA_OIDC_*`):

| Variável | Efeito | Quem lê |
|---|---|---|
| `TUDOIA_MCP_CLIENT_ID` | Id do cliente de serviço do Cérebro (`tudoia-mcp`; padrão `tudoia-mcp` se vazia) | `token_mcp.py`, `credencial_cerebro.py` |
| `TUDOIA_MCP_CLIENT_SECRET` | Segredo desse cliente (`client_credentials`) | Os mesmos dois scripts. Nenhum container recebe esta variável: o n8n recebe o segredo no cofre dele, por `tudoia n8n-credencial`. |
| `TUDOIA_CAPTURAS_CLIENT_ID`, `TUDOIA_CAPTURAS_CLIENT_SECRET` | Cliente de serviço só leitura (`tudoia-capturas`), gravado quando o template do realm o define | Capturas de tela do Estúdio (`scripts/studio`) |

Detalhes do realm e dos IdPs: [Keycloak](componentes/keycloak.md).

### 🔑 Segredos internos

`.\scripts\tudoia.ps1 segredos` preenche **só as chaves vazias** e nunca troca uma existente (`SEGREDOS_INTERNOS` em `painel/tudoia_painel/cli.py`). Cada valor novo tem 32 bytes aleatórios em base64url; a `LITELLM_MASTER_KEY` ganha o prefixo `sk-`.

| Variável | Gerada | Efeito | Observação |
|---|---|---|---|
| `WEBUI_SECRET_KEY` | sempre | Segredo do Open WebUI (repassado pelo compose). | Trocar depois do primeiro uso pode invalidar sessões do Open WebUI (não verificado). |
| `SEARXNG_SECRET` | sempre | Segredo do SearXNG. | |
| `N8N_ENCRYPTION_KEY` | sempre | Cifra as credenciais salvas no n8n. | Trocar a chave, ou restaurar um volume do n8n com outra chave, torna as credenciais ilegíveis. |
| `LITELLM_MASTER_KEY` | sempre | Chave mestra do gateway (`general_settings.master_key`); o painel a usa no chat e no teste de conexão. | Quem usa a chave (clientes, `.aider.conf.yml`) precisa da nova depois de trocar. |
| `LITELLM_DB_PASSWORD` | sempre | Senha do Postgres do LiteLLM (`litellm-db`, role `litellm`), também na `DATABASE_URL` do `litellm`. | Vale só na criação do volume `litellm-db`; para trocar depois, ver [Trocar a senha de um banco](#trocar-a-senha-de-um-banco). |
| `KEYCLOAK_DB_PASSWORD` | só com o perfil `keycloak` | Senha do Postgres do Keycloak (`keycloak-db`, role `keycloak`; no `keycloak`, `KC_DB_PASSWORD`). | Igual à anterior, no volume `keycloak-db`. |
| `TUDOIA_SESSAO_SEGREDO` | sempre | Assina o cookie de sessão do painel. | Trocar derruba todas as sessões abertas. |
| `CEREBRO_TOKEN_ESTATICO` | sempre | Token sem expiração, papel de operador, que os clientes MCP locais mandam ao Cérebro (`Bearer ${CEREBRO_TOKEN_ESTATICO}` em `governanca/mcp.json`). O compose o repassa ao serviço `cerebro`. | Mínimo de 32 caracteres: abaixo disso o Cérebro desliga o caminho (`runtime/cerebro/cerebro/autenticacao.py`, `token_estatico_do_ambiente`). Revogar: trocar o valor, recriar o `cerebro` e rodar `tudoia.ps1 sync`. |
| `TUDOIA_KEYCLOAK_ADMIN_PASSWORD` | só com o perfil `keycloak` | Ver a seção do Keycloak. | |
| `TUDOIA_SQUADTI_TOKEN` | só com o perfil `squadti` | Token da API da SquadTI. | Ver [SquadTI](#-squadti). |

#### Trocar a senha de um banco

> [!WARNING]
> Mudar `LITELLM_DB_PASSWORD` ou `KEYCLOAK_DB_PASSWORD` no `.env` **não** muda a senha dentro do banco: a imagem do Postgres só lê `POSTGRES_PASSWORD` quando cria o volume. Altere o role e recrie o serviço dependente. Passo a passo e confirmação em [operação](operacao.md#senha-do-postgres-trocada-no-env-sem-mudar-no-banco).

### 🐳 Stack Docker

| Variável | Padrão | Efeito |
|---|---|---|
| `COMPOSE_PROFILES` | `cerebro,webui,n8n,keycloak` no template | Perfis do compose que sobem: `cerebro` (Cérebro e SearXNG), `webui` (Open WebUI, Kokoro e SearXNG), `n8n`, `keycloak` e `squadti`. LiteLLM e o Postgres dele (`litellm-db`) sempre sobem; o perfil `keycloak` traz o `keycloak-db`. O `segredos` consulta esta variável para gerar a senha do Keycloak e o token da SquadTI. |
| `TUDOIA_COMPOSE_PROJETO` | `tudoia` | Nome do projeto compose, prefixo dos volumes. Outro nome isola esta instalação de outra na mesma máquina. Lida pelo painel, por `tudoia.ps1` e `tudoia.sh`, por `_comum.ps1` e pelo backup. |

### 📁 Caminhos

Deixe vazias para usar os padrões do repositório.

| Variável | Padrão | Efeito |
|---|---|---|
| `TUDOIA_COMFYUI_PORTABLE` | `modelos\comfyui\ComfyUI_windows_portable` | Pasta do ComfyUI portable (`run_nvidia_gpu.bat`, `python_embeded`, `ComfyUI`). Usada pelo painel (`servicos.py`, `caminhos.py`), por `iniciar.ps1` e pelo Estúdio para achar as saídas em `ComfyUI\output\video` e `ComfyUI\output\audio`. |
| `TUDOIA_OLLAMA_MODELS` | `modelos\ollama\models` | Pasta de pesos do Ollama (vira `OLLAMA_MODELS`). Usada pelo painel, por `tudoia.ps1 up` e `tudoia.sh up` e por `iniciar.ps1`, que só inicia o Ollama se esta variável tiver valor. |
| `TUDOIA_RAIZ` | raiz do repositório | Troca a raiz usada por `painel/tudoia_painel/caminhos.py` (outra instalação ou testes). Só vale se a pasta existe. |
| `TUDOIA_MODELOS_DIR` | `modelos\` do repositório | Pasta base do baixador de modelos; `--base-dir` tem prioridade (`config/modelos.yaml`, `scripts/modelos/baixar.py`). |

### 🖥️ Local (host e containers)

| Variável | Padrão | Efeito |
|---|---|---|
| `OLLAMA_URL` | vazia no template | Endereço do Ollama visto de dentro do container do LiteLLM. O compose repassa `${OLLAMA_URL:-http://host.docker.internal:11434}`: vazia vira esse padrão. O `config.yaml` gerado usa `os.environ/OLLAMA_URL` nos modelos locais e o hook do roteador lê a mesma variável. O Cérebro e o Open WebUI têm o endereço fixo no compose. |
| `TZ` | vazia | Fuso dos containers (`litellm-db`, LiteLLM, Open WebUI, n8n; no Keycloak e no `keycloak-db`, `UTC` se vazia). Exemplo: `America/Sao_Paulo`. |
| `TUDOIA_ESTUDIO_POLLINATIONS` | vazia | `1` permite que o Estúdio gere a imagem no Pollinations (serviço público, sem conta, que recebe o prompt na URL) quando o ComfyUI e a Cloudflare falham. Vazia ou outro valor: o prompt nunca vai para lá e a resposta traz um aviso (`rotas/estudio_imagem.py`). |

### ☁️ Provedores gratuitos

Usados pelo roteador `tudoia-auto` e pelos grupos gratuitos. O texto dos pedidos sai da sua máquina mesmo nos planos gratuitos, e os limites mudam sem aviso; o painel mostra o uso contado pelo LiteLLM. Todas as chaves chegam ao container `litellm` pelo compose.

| Variável | Provedor | Onde obter | Observação |
|---|---|---|---|
| `NVIDIA_NIM_API_KEY` | NVIDIA NIM | build.nvidia.com | Chave `nvapi-`. |
| `NVIDIA_NIM_API_BASE` | NVIDIA NIM | build.nvidia.com | `api_base` dos modelos NIM no `config.yaml` gerado; o template deixa vazio e o valor esperado não está no repositório. Confirme antes de usar o NIM. |
| `OPENROUTER_API_KEY` | OpenRouter (modelos `:free`) | openrouter.ai/keys | Chave `sk-or-`. |
| `GROQ_API_KEY` | Groq | console.groq.com/keys | Chave `gsk_`. Também usada pelo otimizador de prompt do Estúdio (`estudio_servico.py`). |
| `GEMINI_API_KEY` | Google Gemini | aistudio.google.com/apikey | O plano gratuito usa os dados para treino (aviso do template). |
| `CLOUDFLARE_API_KEY` | Cloudflare Workers AI | dash.cloudflare.com | Precisa de `CLOUDFLARE_ACCOUNT_ID` também. |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare Workers AI | dash.cloudflare.com | Identificador da conta. |

### 💳 Provedores pagos

Só entram no roteamento por nome (por exemplo, o grupo `tudoia-max`); não substituem o gratuito sozinhos.

| Variável | Provedor | Onde obter |
|---|---|---|
| `ANTHROPIC_API_KEY` | Anthropic (Claude) | console.anthropic.com |
| `OPENAI_API_KEY` | OpenAI | platform.openai.com/api-keys |
| `DEEPSEEK_API_KEY` | DeepSeek | platform.deepseek.com/api_keys |
| `XAI_API_KEY` | xAI | console.x.ai |
| `HF_TOKEN` | Hugging Face (Inference Providers) | huggingface.co/settings/tokens; precisa de créditos. O baixador (`scripts/modelos/baixar.py`) também a usa nos downloads de huggingface.co. |

`SAMBANOVA_API_KEY` e `ZAI_API_KEY` aparecem comentadas no template como experimentais; nenhum provedor do `config/catalogo-modelos.yaml` as usa, então não têm efeito hoje.

### 🎨 Estúdio

| Variável | Efeito |
|---|---|
| `FAL_AI_API_KEY` | fal.ai, vídeo na nuvem pelo LiteLLM; **pago** por segundo gerado. Chega ao `litellm` pelo compose; o teste da aba Segredos só consulta preço. Ver [estúdio](componentes/estudio.md). |
| `TUDOIA_VIDEO_NUVEM_TETO_USD` | Teto opcional em US$ por vídeo longo na nuvem; vazio, sem teto. Aceita vírgula ou ponto. |
| `MUAPI_API_KEY` | Chave da MuAPI, listada na aba Segredos. Nenhum código versionado a lê hoje. |

O Estúdio usa o ComfyUI em `127.0.0.1:8188` e o Ollama em `127.0.0.1:11434` (`painel/tudoia_painel/upstreams.py`); a geração em nuvem usa as chaves dos provedores acima.

### 🏛️ Governança e MCP

| Variável | Obrigatória | Efeito |
|---|---|---|
| `CONTEXT7_API_KEY` | não | Usada como `${CONTEXT7_API_KEY:-}` no MCP `context7`; vazia não bloqueia o `sync`. |
| `GITHUB_PERSONAL_ACCESS_TOKEN` | só se o MCP `github` estiver ativo | Token do servidor remoto oficial do GitHub. Sem ela, o `sync` recusa e nada é escrito. |
| `SUPABASE_ACCESS_TOKEN`, `SUPABASE_PROJECT_REF` | só se o MCP `supabase` estiver ativo | Token e referência do projeto (o catálogo usa `--read-only` e `--project-ref=${SUPABASE_PROJECT_REF}`). Sem elas, o `sync` recusa. |
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | não | Nenhum MCP do catálogo as referencia; aparecem na aba Segredos como rótulos. |
| `DOUTRINA_TEC` | para o MCP `doutrina-tec` e a tela da Doutrina | Pasta da Doutrina (com `gerado/manifesto.json`). O instalador grava `<pasta de instalação>/doutrina` (a que vai no pacote); numa cópia de desenvolvimento aponte para o clone. Vazia ou ilegível, a skill, o MCP e a SquadTI falham fechado (ver [Doutrina](componentes/doutrina.md)). |
| `TUDOIA_PYTHON` | para o MCP `doutrina-tec` | Python que roda `tools/mcp_doutrina.py`. O instalador grava o `python.exe` do `.venv` da pasta de instalação; numa cópia de desenvolvimento aponte para o `.venv` do TudoIA. O MCP não usa `npx`. |

As variáveis obrigatórias são as que aparecem como `${VAR}` sem valor padrão em `governanca/mcp.json` **e** pertencem a um MCP ativo em `governanca/governanca.json`. Ver [governança](componentes/governanca.md).

### 🤖 SquadTI

Efetivas com o perfil de compose `squadti` (variáveis passadas ao container em `runtime/docker-compose.yml`).

| Variável | Padrão | Efeito |
|---|---|---|
| `TUDOIA_SQUADTI_TOKEN` | gerada por `segredos` com o perfil `squadti` | Token da API da Squad; mínimo de 32 caracteres, senão a API não sobe e o painel responde 503. O painel e o container leem o mesmo valor. |
| `SQUADTI_API_KEY` | criada por `tudoia squadti-chave` | Chave virtual do LiteLLM só da Squad (alias e tag `squadti`); vira `TUDOIA_API_KEY` no container. `--rotacionar` troca por outra. |
| `TUDOIA_SQUADTI_URL` | `http://127.0.0.1:8790` | Endereço da API para o painel; só `http://` com `127.0.0.1` ou `localhost` é aceito. |
| `TUDOIA_LITELLM_URL` | `http://127.0.0.1:4000` | Só para `tudoia squadti-chave`; precisa apontar para o próprio computador. |
| `SQUADTI_TIMEOUT_S` | `300` | Prazo de uma chamada ao modelo (5 a 3600; fora disso volta a 300). Fora do template. |
| `SQUADTI_CONTEXTO_TOKENS` | `32768` | Janela de contexto que a Squad assume. Fora do template. |
| `SQUADTI_MEMORIA` | `6g` | Teto de memória do container. |
| `SQUADTI_CPUS` | `4` | Teto de CPUs do container. |
| `SQUADTI_TEMPLATE_DIR` | `../dados/squadti-template` (relativo ao compose) | Pasta do TemplateTEC montada em `/template`, somente leitura. |
| `SQUADTI_DOUTRINA_SHA` | commit em `governanca/doutrina.json` (repetido no compose) | Commit da Doutrina embutida na imagem (argumento de build). Não edite à mão: use os comandos de [Desenvolvimento](desenvolvimento.md). |
| `TUDOIA_NUGET_FEED_URL` | vazia | Feed NuGet público das bibliotecas `TEC.*`, sem credencial. |
| `TUDOIA_NUGET_USER`, `TUDOIA_NUGET_PAT` | vazias | Feed NuGet privado (GitHub Packages, PAT com `read:packages`). Só por ambiente; segredo. |

### 🔒 Lidas só dentro de containers

Definidas pelo compose ou pelo Dockerfile; **não** defina no `.env` (a maioria nem chegaria ao container).

| Variável | Onde | Efeito |
|---|---|---|
| `CEREBRO_DOCS`, `CEREBRO_DADOS`, `SEARXNG_URL`, `OLLAMA_URL` | Cérebro (`runtime/cerebro/cerebro/__main__.py`) | Pastas montadas e endereços internos. |
| `CEREBRO_DOCS_HOST` | compose, a partir do `.env` | Caminho do Windows da pasta de documentos. Só afeta o campo `caminho` dos resultados de `buscar_documentos`; vazia, o campo é o caminho relativo ao índice. Esta é a única do grupo que se define no `.env`. |
| `CEREBRO_OIDC_ISSUER`, `CEREBRO_OIDC_JWKS_URL`, `CEREBRO_OIDC_CLIENT_ID` | Cérebro (`ConfigOidc.do_ambiente`) | Emissores aceitos (`localhost` e `host.docker.internal`), URL do JWKS e cliente `tudoia-mcp`. Sem os três, `/mcp` e `/indexar` só aceitam o token estático; sem ele também, recusam tudo. Ver [Cérebro](componentes/cerebro.md). |
| `ROTEADOR_CONFIG`, `ROTEADOR_LOGS` | LiteLLM (`runtime/litellm/roteador.py`) | Caminhos do `config.yaml` e da pasta de logs. |
| `TUDOIA_GATEWAY_URL`, `TUDOIA_API_KEY`, `TUDOIA_TIMEOUT_S`, `TUDOIA_CONTEXTO_TOKENS` | SquadTI (`orquestrador/nodes.py`) | Montadas pelo compose a partir de `SQUADTI_API_KEY`, `SQUADTI_TIMEOUT_S` e `SQUADTI_CONTEXTO_TOKENS`. |
| `TUDOIA_MODEL`, `TUDOIA_PERMITIR_NUVEM` | SquadTI | Modelo padrão `tudoia-local-estrito`. Um modelo que pode ir à nuvem só é aceito com `TUDOIA_PERMITIR_NUVEM=1`, que o compose não repassa. |
| `DOUTRINA_TEC`, `DOUTRINA_FAMILIAS`, `DOUTRINA_REGRAS_MAX_TOKENS` | SquadTI (`orquestrador/doutrina_tec.py`) | Doutrina embutida em `/doutrina`; famílias lidas (padrão `arquitetura`, `ia`, `ecossistema`); orçamento de regras em tokens (500 a 200000). |
| `TUDOIA_SQUADTI_HOST`, `TUDOIA_SQUADTI_PORTA`, `SQUADTI_DB`, `SQUADTI_STACK_CONFIG` | SquadTI (`orquestrador/api.py`) | Bind (`127.0.0.1` ou `0.0.0.0`), porta (8790), banco de checkpoint e configuração da stack. |

### 🛠️ Ferramentas de desenvolvimento

| Variável | Onde | Efeito |
|---|---|---|
| `TUDOIA_KEYCLOAK_IT` | `tests/conftest.py`, `tests/keycloak/` | `1` liga o teste de integração com um Keycloak vivo e libera a rede nos testes. |
| `PESSOAIS_EXTRA` | `scripts/empacotar/payload.py` | Lista separada por vírgula de termos que o empacotador procura no payload (além do usuário e do nome do computador) e recusa se achar. |

## ❌ Erros e diagnóstico

| Sintoma | Causa provável | Ação |
|---|---|---|
| Toda rota `/api` do painel responde 503 | Falta `TUDOIA_OIDC_ISSUER`, `TUDOIA_OIDC_CLIENT_ID` ou `TUDOIA_OIDC_CLIENT_SECRET`, ou `TUDOIA_SESSAO_SEGREDO` tem menos de 32 caracteres | Rode `tudoia keycloak` (grava as três) e `tudoia segredos`; reinicie o painel. |
| `litellm` ou `keycloak` não ficam saudáveis; log com `password authentication failed` | `LITELLM_DB_PASSWORD` ou `KEYCLOAK_DB_PASSWORD` vazia ou diferente da gravada no volume do banco (o compose não as exige) | `.\scripts\tudoia.ps1 segredos`; com o volume já criado, ver [operação](operacao.md#senha-do-postgres-trocada-no-env-sem-mudar-no-banco) |
| Provedor não aparece no roteador | Chave vazia, ou chave preenchida depois sem recriar o `litellm` | Preencha, gere a configuração pela aba Roteador e use `restart` do serviço (recria o container e relê o `.env`). |
| `sync` recusa e escreve nada | Variável obrigatória de um MCP ativo está vazia (por exemplo `GITHUB_PERSONAL_ACCESS_TOKEN`) | Preencha a variável ou desative o MCP em `governanca.json`. |
| Cérebro responde 401 ao cliente MCP | `CEREBRO_TOKEN_ESTATICO` vazio, curto (< 32) ou diferente do que o cliente recebeu no último `sync` | Gere o segredo, recrie o `cerebro` e rode `tudoia.ps1 sync`. |
| Aba da SquadTI mostra "SquadTI não configurado" | `TUDOIA_SQUADTI_TOKEN` ausente ou com menos de 32 caracteres | `segredos` com `squadti` em `COMPOSE_PROFILES`, depois `squadti-chave`. |
| Credenciais do n8n ilegíveis depois de restaurar | `N8N_ENCRYPTION_KEY` diferente da usada ao criar o volume | Restaure o `.env` original com a chave antiga. |

## 🛡️ Segurança

- Nenhum segredo pertence ao repositório: o `.env` está no `.gitignore`, e a aba Segredos nunca devolve o valor sem o papel `tudoia-admin`.
- Os containers não recebem o `.env` inteiro; cada um recebe só as variáveis listadas no compose.
- O instalador restringe o acesso ao `.env` recém-criado ao usuário (`_restringir_acesso` em `instalador/tudoia_instalador/etapas.py`).
- Segredos de MCP vão para os arquivos dos clientes só em destinos sob a home; em workspace, a governança escreve `${VAR}` literal ([governança](componentes/governanca.md)).
- Para reportar uma falha de configuração que exponha segredo, siga [segurança](seguranca.md).

## ❓ Perguntas frequentes

**Posso usar aspas nos valores?** Não. O painel remove aspas externas ao gravar, mas a leitura do `.env` não as remove, e o compose e os scripts podem interpretá-las de outro jeito.

**Qual variável vence, a do ambiente ou a do `.env`?** Para `TUDOIA_*` no login do painel, no provisionamento do Keycloak e nos caminhos do ComfyUI e do Ollama, a do ambiente. O compose lê o `.env` pelo `--env-file` que os scripts passam.

**Onde está o modelo do arquivo?** Em `.env.example`, na raiz. As variáveis de `Segredos internos` ficam vazias de propósito.

---

[🏠 README](../README.md) · ⬅️ [Arquitetura](arquitetura.md) · [Desenvolvimento](desenvolvimento.md) ➡️

# Configuração

Toda a configuração do TudoIA fica em um único arquivo: `.env`, na raiz do repositório. O modelo é o `.env.example`.
Este documento descreve cada variável. Nenhum valor real aparece aqui; os exemplos usam `<chave>`.

## Regras gerais

- Formato: `NOME=valor`, sem aspas e sem espaço ao redor do `=`. A leitura não é uniforme entre os módulos: o
  `governanca` remove aspas em volta do valor, e o `ler_env` do painel (`painel/tudoia_painel/envfile.py`) não remove.
  Escreva sem aspas.
- Chave vazia significa "não configurado". Um provedor de nuvem só entra no roteador se todas as suas chaves estiverem
  preenchidas.
- O painel grava no `.env` preservando comentários e a ordem. Antes de cada gravação, o arquivo anterior vai para
  `dados\backups\env\` (no máximo 10 cópias).
- A aba **Segredos** do painel mostra as chaves mascaradas. Quem tem o papel admin pode revelar um valor
  (`POST /api/segredos/{chave}/revelar`). Ver [seguranca.md](seguranca.md#segredos).
- Variáveis `TUDOIA_*` que estão no ambiente do processo têm prioridade sobre o `.env`. Isso vale para o painel
  (`carregar_config_auth`) e para o script do Keycloak.
- `.env` está no `.gitignore`. `.env.example` é versionado.

## Identidade OIDC (login do painel)

| Variável | Obrigatória | Valor no template ou padrão do código | Uso |
|---|---|---|---|
| `TUDOIA_OIDC_ISSUER` | sim | `http://localhost:8180/realms/tudoia` | URL do issuer OIDC. O painel lê `<issuer>/.well-known/openid-configuration`. Precisa começar com `http://` ou `https://`. |
| `TUDOIA_OIDC_CLIENT_ID` | sim | `tudoia-painel` | Client ID registrado no IdP. |
| `TUDOIA_OIDC_CLIENT_SECRET` | sim | vazia | Segredo do client. Gravado pelo `keycloak` (provisionamento). Nunca versionar. |
| `TUDOIA_OIDC_SCOPE` | não | `openid email profile` | Escopos pedidos no login. |
| `TUDOIA_SESSAO_SEGREDO` | sim (gerado) | vazia | Chave que assina o cookie de sessão. Precisa ter pelo menos 32 caracteres; abaixo disso, o painel não configura a autenticação. Gerada por `segredos`. |
| `TUDOIA_COOKIE_SEGURO` | não | `0` | `1` faz o cookie de sessão trafegar só por HTTPS. Use `1` atrás de um proxy com TLS. `0` serve para `http://127.0.0.1`. |
| `TUDOIA_API_BEARER_CLIENTES` | não | vazia (não está no template) | Lista de `azp` (clientes de serviço do Keycloak), separados por vírgula, que podem chamar `/api` com `Authorization: Bearer <JWT>`. Vazia, o Bearer fica desligado (401 `bearer_desativado`). Lida em `painel/tudoia_painel/autenticacao.py` (`ConfigAuth.do_ambiente`). |

Sem `TUDOIA_OIDC_ISSUER`, `TUDOIA_OIDC_CLIENT_ID`, `TUDOIA_OIDC_CLIENT_SECRET` ou com `TUDOIA_SESSAO_SEGREDO` curto,
toda rota `/api` do painel responde 503. Isso é intencional.

Variáveis que o provisionamento do Keycloak lê e que não estão no `.env.example`:

| Variável | Padrão | Uso |
|---|---|---|
| `TUDOIA_KEYCLOAK_URL` | `http://localhost:8180` | Endereço do Keycloak (admin API). Precisa ser `http://` ou `https://`. |
| `TUDOIA_KEYCLOAK_REALM` | `tudoia` | Nome do realm a provisionar. Só letras, números, `-` e `_`. |
| `TUDOIA_KEYCLOAK_ADMIN` | pedido no terminal | Usuário admin do realm `master`. |
| `TUDOIA_KEYCLOAK_ADMIN_PASSWORD` | pedida no terminal | Senha desse admin. Prefira não gravá-la no `.env`. |
| `TUDOIA_IDP_*` | conforme o IdP | Variáveis referenciadas pelos arquivos em `infra/keycloak/idps/`. |
| `TUDOIA_PAINEL_PORTA` | `3100` | Porta do painel. Usada também para montar os redirect URIs do Keycloak. |

Variáveis que o provisionamento **grava** no `.env`, além de `TUDOIA_OIDC_*` (`scripts/keycloak/provisionar.py`):

| Variável | Uso | Quem lê |
|---|---|---|
| `TUDOIA_MCP_CLIENT_ID` | Id do cliente de serviço do Cérebro (`tudoia-mcp`) | `scripts/keycloak/token_mcp.py`, `scripts/n8n/credencial_cerebro.py` (padrão `tudoia-mcp` se vazia) |
| `TUDOIA_MCP_CLIENT_SECRET` | Segredo desse cliente (`client_credentials`) | Os mesmos dois scripts. Nenhum container recebe esta variável: o n8n recebe o segredo no cofre dele, pelo `tudoia.ps1 n8n-credencial` |
| `TUDOIA_CAPTURAS_CLIENT_ID`, `TUDOIA_CAPTURAS_CLIENT_SECRET` | Cliente de serviço só leitura (`tudoia-capturas`), gravado quando o template o define | Capturas de tela do Studio (`scripts/studio`) |

Detalhes do realm e dos IdPs: [keycloak.md](componentes/keycloak.md).

## Segredos internos

Gerados por `.\scripts\tudoia.ps1 segredos`, que preenche só as chaves vazias. Não edite à mão a não ser que saiba o
impacto.

| Variável | Uso | Observação |
|---|---|---|
| `WEBUI_SECRET_KEY` | Segredo do Open WebUI (repassado pelo compose). | Trocar depois do primeiro uso pode invalidar sessões existentes (a confirmar). |
| `SEARXNG_SECRET` | Segredo do SearXNG (repassado pelo compose). | Sem observação específica no repositório. |
| `N8N_ENCRYPTION_KEY` | Chave que cifra as credenciais salvas no n8n. O compose a repassa ao serviço `n8n`. | Ver nota abaixo. |
| `LITELLM_MASTER_KEY` | Chave mestra do gateway LiteLLM (`general_settings.master_key`). O painel a usa no chat e no teste de conexão. | Clientes que a usam precisam da nova chave. |
| `LITELLM_DB_PASSWORD` | Senha do Postgres do LiteLLM (`litellm-db`), usada também na `DATABASE_URL` do serviço `litellm`. | `POSTGRES_PASSWORD` só vale na criação do volume. Trocar a variável depois não altera a senha dentro do banco. |
| `TUDOIA_SESSAO_SEGREDO` | Assina o cookie de sessão do painel (ver acima). | Trocar derruba todas as sessões abertas. |
| `CEREBRO_TOKEN_ESTATICO` | Token sem expiração, com papel de operador, que os clientes MCP locais mandam ao Cérebro (`Bearer ${CEREBRO_TOKEN_ESTATICO}` em `governanca/mcp.json`). O compose o repassa ao serviço `cerebro`. | Mínimo de 32 caracteres: abaixo disso o Cérebro desliga esse caminho (`runtime/cerebro/cerebro/autenticacao.py`, `token_estatico_do_ambiente`). Revogar: trocar o valor, reiniciar o `cerebro` e rodar `tudoia.ps1 sync`. |

Nota sobre `N8N_ENCRYPTION_KEY`: o serviço `n8n` recebe a variável (`environment` em `runtime/docker-compose.yml`). As
credenciais salvas no n8n, inclusive a do Cérebro gravada pelo `tudoia.ps1 n8n-credencial`, só decifram com a mesma
chave. Trocar a chave, ou restaurar um backup do volume `n8n` com outra chave, torna essas credenciais ilegíveis.
Guarde a chave junto com o `.env` (o backup do TudoIA não copia o `.env`). Veja
[arquitetura.md](arquitetura.md#serviços-docker).

## Local (host e containers)

| Variável | Padrão | Uso |
|---|---|---|
| `OLLAMA_URL` | vazia no template | Endereço do Ollama visto de dentro do container do LiteLLM. O compose repassa `${OLLAMA_URL:-http://host.docker.internal:11434}`, então vazia ou ausente vira `http://host.docker.internal:11434`. O `config.yaml` gerado usa `os.environ/OLLAMA_URL` nos modelos locais, e o hook do roteador lê a mesma variável. Cérebro e Open WebUI têm o endereço fixo no compose. |
| `TZ` | vazia | Fuso horário dos containers (Postgres, LiteLLM, Open WebUI, n8n). Exemplo: `America/Sao_Paulo`. |
| `TUDOIA_ESTUDIO_POLLINATIONS` | vazia | `1` permite que o Estúdio gere a imagem no Pollinations (serviço público, sem conta, que recebe o prompt na URL) quando ComfyUI e Cloudflare falham. Vazia ou outro valor: nunca envia o prompt para lá, e a resposta traz um aviso. Lida em `painel/tudoia_painel/app.py` (`gerar-imagem`). |

## Provedores gratuitos (nuvem)

Usados pelo roteador `tudoia-auto` e pelos grupos gratuitos. O texto dos pedidos sai da sua máquina, mesmo nos planos
gratuitos. Os limites mudam sem aviso; o painel mostra o uso contado pelo LiteLLM.

| Variável | Provedor | Onde obter | Observação |
|---|---|---|---|
| `NVIDIA_NIM_API_KEY` | NVIDIA NIM | build.nvidia.com | Chave `nvapi-`. Provedor só entra se a chave estiver preenchida. |
| `NVIDIA_NIM_API_BASE` | NVIDIA NIM | a confirmar | Usada como `api_base` dos modelos NIM no `config.yaml` gerado. O template deixa vazio e o valor esperado não está documentado no repositório. Confirme antes de usar NIM. |
| `OPENROUTER_API_KEY` | OpenRouter (modelos `:free`) | openrouter.ai/keys | Chave `sk-or-`. |
| `GROQ_API_KEY` | Groq | console.groq.com/keys | Chave `gsk_`. Também usada pelo otimizador de prompt do Estúdio (`painel/tudoia_painel/estudio_servico.py`). |
| `GEMINI_API_KEY` | Google Gemini | aistudio.google.com/apikey | O plano gratuito usa os dados para treino (aviso do próprio template). |
| `CLOUDFLARE_API_KEY` | Cloudflare Workers AI | dash.cloudflare.com | Precisa de `CLOUDFLARE_ACCOUNT_ID` também. |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare Workers AI | dash.cloudflare.com | Identificador da conta, usado junto com a chave. |

## Provedores pagos

Só entram no roteamento por nome (por exemplo, no grupo `tudoia-max`). Não substituem o gratuito sozinhos.

| Variável | Provedor | Onde obter |
|---|---|---|
| `ANTHROPIC_API_KEY` | Anthropic (Claude) | console.anthropic.com (chave `sk-ant-`) |
| `OPENAI_API_KEY` | OpenAI | platform.openai.com/api-keys |
| `DEEPSEEK_API_KEY` | DeepSeek | platform.deepseek.com/api_keys |
| `XAI_API_KEY` | xAI | console.x.ai |
| `HF_TOKEN` | Hugging Face (Inference Providers) | huggingface.co/settings/tokens. Precisa de créditos para Inference Providers. `scripts/modelos/baixar.py` também a usa nos downloads de huggingface.co. |

## Experimentais (comentados no template)

`SAMBANOVA_API_KEY` e `ZAI_API_KEY` aparecem comentados no `.env.example`. Nenhum dos dois tem provedor no
`config/catalogo-modelos.yaml`, então hoje não têm efeito.

## Estúdio

| Variável | Uso |
|---|---|
| `MUAPI_KEY`, `MUAPI_API_KEY` | Presentes no `.env.example` com o nome "Muapi / TudoEstudio". Nenhum código versionado lê essas variáveis. A integração a confirmar; pode ser removida do template. |

O Estúdio de imagem e vídeo usa o ComfyUI em `127.0.0.1:8188` (variável de caminho abaixo) e o Ollama em
`127.0.0.1:11434`. A geração em nuvem usa as chaves de provedores acima.

## Caminhos

Deixe vazias para usar os padrões do repositório.

| Variável | Padrão | Uso |
|---|---|---|
| `TUDOIA_COMFYUI_PORTABLE` | `modelos\comfyui\ComfyUI_windows_portable` | Pasta do ComfyUI portable (com `run_nvidia_gpu.bat`). Usada pelo painel (`servicos.py`) para iniciar e parar o ComfyUI, e pelo Estúdio para achar as saídas em `ComfyUI\output\video` e `ComfyUI\output\audio`. |
| `TUDOIA_OLLAMA_MODELS` | `modelos\ollama\models` | Pasta de pesos do Ollama (`OLLAMA_MODELS`). Usada pelo painel ao iniciar o Ollama. |
| `TUDOIA_RAIZ` | raiz do repositório | Lida por `painel/tudoia_painel/caminhos.py`, para outra instalação ou testes. |
| `TUDOIA_MODELOS_DIR` | `modelos\` do repositório | Pasta base do baixador (`scripts/modelos/baixar.py`). `--base-dir` tem prioridade. |

O `.\scripts\tudoia.ps1 up` e o `scripts/tudoia.sh up` leem `TUDOIA_OLLAMA_MODELS` do `.env` para o `OLLAMA_MODELS`
do Ollama que iniciam. Sem valor, usam `modelos\ollama\models`. O painel faz o mesmo.

## Governança e MCP

| Variável | Obrigatória? | Uso |
|---|---|---|
| `CONTEXT7_API_KEY` | não | Usada por `${CONTEXT7_API_KEY:-}` no MCP `context7`. Vazia não bloqueia o sync. |
| `SUPABASE_ACCESS_TOKEN` | sim, se o MCP `supabase` estiver ativo | Token do MCP `supabase`. Sem ela, o sync recusa e nada é escrito. |
| `GITHUB_PERSONAL_ACCESS_TOKEN` | sim, se o MCP `github` estiver ativo | Token do MCP `github`. Mesmo comportamento. |
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | não | Não são lidas por nenhum MCP do catálogo. Aparecem na aba Segredos como rótulos. |

As variáveis obrigatórias são as que aparecem como `${VAR}` sem default em `governanca/mcp.json`. Ver
[governanca.md](componentes/governanca.md).

## Variáveis lidas pelo código que não estão no template

| Variável | Onde | Uso |
|---|---|---|
| `CEREBRO_DOCS_HOST` | `runtime/docker-compose.yml` | Caminho do Windows da pasta de documentos (ex.: `D:\TudoIA\dados\documentos`). Só afeta o campo `caminho` nos resultados de `buscar_documentos`. Vazia, o campo `caminho` é o caminho relativo ao índice (ex.: `notas/x.md`). |
| `ROTEADOR_CONFIG`, `ROTEADOR_LOGS` | dentro do container do LiteLLM | Caminhos do `config.yaml` e da pasta de logs. Os padrões são `/app/config.yaml` e `/app/logs`. Não defina no `.env`. |
| `CEREBRO_DOCS`, `CEREBRO_DADOS`, `OLLAMA_URL`, `SEARXNG_URL` | dentro do container do Cérebro | Definidos no compose. Não defina no `.env`. |
| `CEREBRO_OIDC_ISSUER`, `CEREBRO_OIDC_JWKS_URL`, `CEREBRO_OIDC_CLIENT_ID` | dentro do container do Cérebro (`runtime/cerebro/cerebro/autenticacao.py`, `ConfigOidc.do_ambiente`) | Fixos no compose: emissores aceitos (`localhost` e `host.docker.internal`), URL do JWKS e cliente `tudoia-mcp`. Sem os três, `/mcp` e `/indexar` só aceitam o `CEREBRO_TOKEN_ESTATICO`; sem ele também, respondem 503. Não defina no `.env`. Ver [cerebro.md](componentes/cerebro.md#configuração). |
| `TUDOIA_KEYCLOAK_IT` | testes (`tests/conftest.py`, `tests/keycloak/`) | `1` liga o teste de integração com o Keycloak e libera a rede nos testes. |

## Exemplo mínimo de `.env` (valores fictícios)

```dotenv
TUDOIA_OIDC_ISSUER=http://localhost:8180/realms/tudoia
TUDOIA_OIDC_CLIENT_ID=tudoia-painel
TUDOIA_OIDC_CLIENT_SECRET=<gerado pelo keycloak>
TUDOIA_COOKIE_SEGURO=0
OLLAMA_URL=http://host.docker.internal:11434
GROQ_API_KEY=<sua chave>
GITHUB_PERSONAL_ACCESS_TOKEN=<seu token>
SUPABASE_ACCESS_TOKEN=<seu token>
TZ=<seu fuso>
```

Os segredos internos (`WEBUI_SECRET_KEY`, `LITELLM_MASTER_KEY` etc.) são gerados pelo `segredos`. Não precisa
escrevê-los.

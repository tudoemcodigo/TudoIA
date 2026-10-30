# Painel

O painel é o ponto de controle do TudoIA. É uma aplicação FastAPI que serve uma SPA estática e uma API em `/api`.
Pelo painel você sobe e para serviços, testa chaves de provedores, vê o uso de modelos, edita o roteamento, distribui a
governança e gera o `config.yaml` do LiteLLM. Ele também tem o Estúdio (chat, imagens, vídeos e músicas).

Código: `painel/tudoia_painel/`. Configuração: [configuracao.md](../configuracao.md).

## Como rodar

```powershell
.\scripts\tudoia.ps1 painel
```

Esse comando executa `python -m tudoia_painel painel` dentro do ambiente do projeto. O painel sobe em
`http://127.0.0.1:3100/app/`. O uvicorn escuta só em `127.0.0.1`, com log em nível `warning`.

Outras formas de chamar, equivalentes:

- `scripts\tudoia.cmd painel`. O `.cmd` só repassa os argumentos para o `tudoia.ps1`.
- `uv run --project . python -m tudoia_painel painel --porta 3100` com `PYTHONPATH` apontando para a raiz e para
  `painel\`. O `--porta` existe no `cli.py` (padrão 3100), mas o `tudoia.ps1 painel` não o repassa.

O painel não é iniciado pelo `tudoia.ps1 up`. Você sobe o painel separadamente.

## Seções da interface

A navegação está em `painel/tudoia_painel/static/index.html`:

| Grupo | Seção (`data-view`) | Para que serve |
|---|---|---|
| Estúdio de criação | `chat` | Chat com modelos. Usa o LiteLLM (`/api/chat/completions`). |
| Estúdio de criação | `imagens` | Geração de imagens, pelo ComfyUI ou por motor de nuvem. Inclui otimização de prompt e inpaint. |
| Estúdio de criação | `videos` | Geração de vídeo pelo ComfyUI (fluxos Wan e MiniMax). |
| Estúdio de criação | `musicas` | Geração de música pelo ComfyUI (fluxo YuE). |
| Plataforma | `servicos` | Estado e ações (start, stop, restart) dos containers e dos processos do host. |
| Plataforma | `hardware` | Uso de GPU, VRAM e fila do ComfyUI. Permite descarregar modelos da VRAM. |
| Roteamento e modelos | `modelos` | Catálogo de modelos, testes de chave e modelos locais (Ollama). |
| Roteamento e modelos | `roteador` | Grupos do roteador `tudoia-auto`, membros de cada grupo e geração do `config.yaml`. |
| Governança e segurança | `governanca` | Regras, skills, MCP e instâncias dos clientes. Dispara o `sync`. |
| Governança e segurança | `segredos` | Chaves do `.env`, mascaradas, com teste e edição. |
| Governança e segurança | `limites` | Limites e consumo de tokens por provedor (`/api/limites-tokens`). |
| Governança e segurança | `telemetria` | Tráfego e ao vivo, a partir de `eventos.jsonl` e do LiteLLM. |

Os textos da interface estão em português. Os nomes técnicos (`tudoia-auto`, `LITELLM_MASTER_KEY`) aparecem como estão.

## Autenticação

Login por OpenID Connect contra o IdP configurado (Keycloak por padrão). Detalhes do fluxo e dos controles estão em
[seguranca.md](../seguranca.md#autenticação-oidc). Resumo:

- `GET /auth/login` redireciona ao IdP. `GET /auth/callback` recebe o código, troca por tokens e cria a sessão.
- `POST /auth/logout` encerra a sessão e leva ao logout do IdP.
- `GET /api/sessao` diz à SPA se a autenticação está configurada, se há sessão e quais papéis ela tem. Essa rota não exige
  login.
- `GET /saude` responde `{"ok": true}` sem login e fora da guarda. Serve para launcher e healthcheck.
- Cliente de serviço: com `TUDOIA_API_BEARER_CLIENTES`, o painel aceita `Authorization: Bearer <JWT>` do Keycloak em
  `/api` (ver [seguranca.md](../seguranca.md#autenticação-oidc)).

### Papéis

| Papel | Pode | Não pode |
|---|---|---|
| `tudoia-leitor` | Ver as telas (`GET`), inclusive a governança | Alterar qualquer coisa. Não vê segredos, provedores nem o catálogo MCP. |
| `tudoia-operador` | Alterar o que não é administrativo: serviços, roteamento, modelos, Estúdio | Segredos, provedores, qualquer alteração na governança (regras, skills, MCP, instâncias, `sincronizar`), baixar modelo local |
| `tudoia-admin` | Tudo, inclusive segredos, provedores, governança e download de modelos | Nada: é o papel com mais acesso |

A regra está em `decidir` (`painel/tudoia_painel/autenticacao.py`): `PREFIXOS_SO_ADMIN` vale para qualquer método, e
`PREFIXOS_ESCRITA_SO_ADMIN = ("/api/governanca",)` deixa todos lerem a governança e só o admin alterá-la.

O papel vem de `groups` ou de `realm_access.roles` do token. Um usuário pode ter mais de um papel. Sem nenhum papel do
painel, o login é recusado com 403.

### Sem OIDC configurado

Se `TUDOIA_OIDC_ISSUER`, `TUDOIA_OIDC_CLIENT_ID` ou `TUDOIA_OIDC_CLIENT_SECRET` faltarem, ou se
`TUDOIA_SESSAO_SEGREDO` tiver menos de 32 caracteres, toda rota `/api` responde **503** com código
`auth_nao_configurada`. A exceção é `GET /api/sessao`, que responde `configurado: false`. A SPA carrega, mas não consegue
mostrar dados. Isso é fail-closed de propósito.

## Formato de erro

Todas as respostas de erro da API seguem este formato (`painel/tudoia_painel/erros.py`):

```json
{"erro": {"codigo": "validacao", "mensagem": "texto em português", "campo": "valor", "detalhes": []}}
```

`campo`, `detalhes` e `extras` só aparecem quando há. `extras` é contexto legível por máquina (por exemplo `{"servico_offline": "comfyui"}`); o `painel.js` lê `erro.extras` para mostrar "ComfyUI offline". Operação que falha (upload recusado, geração que não rodou, chat sem motor) responde com status HTTP de erro e este corpo, nunca `200` com `ok: false`. As rotas de **teste** (`/api/modelos/testar`, `/api/roteador/testar`, `/api/governanca/mcp/{id}/testar`, `/api/segredos/{chave}/testar`) continuam respondendo `200` com o resultado do teste, porque "o teste deu negativo" é o resultado, não uma falha da rota. Códigos usados:

| HTTP | `codigo` | Quando |
|---|---|---|
| 400 | `requisicao_invalida` | Requisição mal formada (ex.: `Content-Length` inválido) |
| 401 | `nao_autenticado` | Sem sessão válida em `/api` |
| 403 | `papel_insuficiente` | Papel não permite a ação |
| 403 | `host_recusado` | `Host` diferente de `127.0.0.1` ou `localhost` |
| 403 | `origem_recusada` | `Origin`, `Referer` ou `Sec-Fetch-Site` de outro site |
| 404 | `nao_encontrado` | Recurso ou arquivo inexistente |
| 409 | `duplicado` ou `conflito` | Já existe (ex.: instância com o mesmo id) |
| 413 | `corpo_grande_demais` | Corpo acima de 10 MB (140 MB em `POST /api/estudio/upload`), declarado ou contado nos bytes recebidos |
| 415 | `tipo_de_conteudo` | `POST`, `PUT` ou `PATCH` (ou `DELETE` com corpo) sem `application/json` |
| 422 | `validacao` | Campo inválido. `campo` aponta qual |
| 500 | `falha_interna` | Exceção não tratada. A mensagem diz só o tipo da exceção e o id do pedido. O traceback fica no log do servidor |
| 503 | `auth_nao_configurada` | OIDC não configurado |
| 503 | `indisponivel` | Dependência fora do ar (ex.: ComfyUI) |

Alguns erros do fluxo de login usam outros códigos: `login_recusado` (401) e `sem_papel` (403). O Bearer usa
`bearer_desativado` e `token_invalido` (401) e `identidade_indisponivel` (503).

Toda resposta de `/api`, `/app` e `/auth/*` traz o cabeçalho `X-Request-ID`. O mesmo id aparece na mensagem do erro 500,
no log do servidor e em `dados\logs\auditoria.jsonl`. Use-o para achar o pedido.

## API

As rotas ficam em `painel/tudoia_painel/rotas/`, um `APIRouter` por domínio (`servicos`, `segredos`, `governanca`, `modelos`, `roteador`, `telemetria`, `provedores`, `hardware`, `estudio_catalogo`, `estudio_arquivos`, `estudio_imagem`, `estudio_video`, `estudio_musica`, `chat`, `ui`). `app.py` só monta o `Contexto` (`ambiente.py`: raiz, home, serviços e a trava de escrita em arquivos de configuração), inclui os routers e liga a autenticação e a guarda. Modelos de entrada: `schemas.py`. Regra de negócio fora das rotas: `estudio_servico.py`, `skills_servico.py`, `mcp_teste.py` e `comfyui.py`. Endereços do LiteLLM, Ollama e ComfyUI: `upstreams.py`. A lista abaixo agrupa por prefixo. Consulte
o código para a assinatura de cada rota. A OpenAPI está desligada (`openapi_url=None`).

| Prefixo | Papel mínimo para alterar | O que faz |
|---|---|---|
| `/api/sessao` | nenhum | Estado da sessão e papéis |
| `/api/servicos` | operador | Lista serviços. `POST /api/servicos/{nome}/{acao}` (start, stop, restart). `POST /api/servicos/todos/{acao}` |
| `/api/hardware` | operador | Estado da GPU e da fila. `POST /api/hardware/limpar-vram` descarrega modelos do Ollama |
| `/api/modelos` | operador (só `/api/modelos/local/baixar` exige admin) | Catálogo, teste de modelos (`/api/modelos/testar`), modelos locais, mídia do Estúdio |
| `/api/roteador` | operador | Detalhes dos grupos, `POST /api/roteador/gerar`, `POST /api/roteador/testar`, edição de grupos e auto-vínculo |
| `/api/telemetria` | leitor | Eventos ao vivo e totais do LiteLLM |
| `/api/limites-tokens` | leitor | Uso por provedor. `periodo` aceita `24h`, `7d`, `total` etc. |
| `/api/provedores` | admin | Cadastro de provedor, descoberta de modelos (`/api/provedores/{id}/descobrir-modelos`) |
| `/api/segredos` | admin | Listar (mascarado), gravar (`PUT /api/segredos/{chave}`), revelar, testar |
| `/api/governanca` | admin (leitura: qualquer papel, exceto `/api/governanca/mcp`, só admin) | Estado, `sincronizar`, instâncias, regras, skills, MCP e edição de arquivos |
| `/api/estudio` | operador | Geração (imagem, vídeo, música, inpaint), otimização de prompt, galeria, cancelamento e upload |
| `/api/chat/completions` | operador | Chat pelo LiteLLM (usa `LITELLM_MASTER_KEY`) |

O `POST /api/roteador/gerar` grava `runtime/litellm/config.yaml` e não reinicia o LiteLLM. O LiteLLM lê esse arquivo na
inicialização. Para aplicar, reinicie o serviço `litellm` (pela aba Serviços ou com `docker compose restart litellm`).

### Teste e sincronização de modelos

Código: `painel/tudoia_painel/provedores_service.py` e a rota `POST /api/modelos/testar` em `rotas/modelos.py`.

- O botão "Testar" só desativa um modelo do catálogo (e o tira dos grupos do roteador) quando o provedor diz que ele não
  existe mais: HTTP 404, ou 400/410 com sinais como `decommissioned`, `deprecated`, `does not exist`,
  `no longer supported` ou `model not found` (`falha_definitiva`).
- Conexão recusada, timeout, 429, 5xx e 401 não desativam nada. Essas falhas dizem algo do ambiente, não do modelo.
- `Invalid model name` (ou `ProxyModelNotFound`) vem do próprio LiteLLM: o `config.yaml` foi regenerado e o LiteLLM
  ainda não foi reiniciado. Não desativa, e a resposta traz `dica` pedindo para reiniciar o LiteLLM
  (`litellm_sem_o_modelo`).
- A sincronização do catálogo segue a paginação de cada API: Anthropic (`has_more` e `after_id`), Gemini
  (`nextPageToken`) e Cloudflare (`result_info`). Uma listagem que não termina em 20 páginas (`MAX_PAGINAS`) é tratada
  como incompleta e não inativa nenhum modelo.
- A consulta às APIs dos provedores é feita fora da trava do painel. Antes, toda gravação do painel esperava as
  listagens.
- Telemetria e limites pedem ao LiteLLM só o período: a telemetria pede as últimas 24 h (`rotas/telemetria.py`, `/api/telemetria`) e
  os limites o período escolhido (`limites.py`). Antes, cada atualização da tela baixava o histórico inteiro, cerca de
  27 MB.

## Serviços

O painel controla dois tipos de serviço:

- **Docker** (`litellm`, `litellm-db`, `cerebro`, `searxng`, `open-webui`, `kokoro`, `n8n`): ações via
  `docker compose -p tudoia -f runtime\docker-compose.yml --env-file .env`.
- **Host** (`ollama`, `comfyui`): ações via processo. Para parar, o painel encerra o processo que escuta na porta
  (11434 ou 8188). Para iniciar, usa `ollama serve` e `run_nvidia_gpu.bat` dentro da pasta do ComfyUI portable.

Implementação: `painel/tudoia_painel/servicos.py`. Esse módulo é Windows-only em vários pontos (`cmd.exe`,
`taskkill`, `powershell`).

Ao iniciar o Ollama, o painel define `OLLAMA_HOST=127.0.0.1:11434` (só loopback; ver [seguranca.md](../seguranca.md)).

## Estúdio

Documentação completa do Estúdio: [estudio.md](estudio.md). Rotas em `/api/estudio/*`. O fluxo de imagem está descrito em [arquitetura.md](../arquitetura.md#fluxos). Pontos
importantes:

- O ComfyUI é acessado em `127.0.0.1:8188`. Se o pedido exige o ComfyUI (motor `comfyui` ou modelo local `local:`) e a porta 8188 não responde, o painel devolve erro e não tenta outro motor (`gerar-imagem` em `rotas/estudio_imagem.py`).
- Antes de algumas gerações visuais (imagem, inpaint, vídeo e música), o painel descarrega da VRAM os modelos do Ollama
  (`keep_alive: 0`). Isso libera a GPU para o ComfyUI.
- O otimizador de prompt usa `GROQ_API_KEY` quando existe, senão um modelo local.
- Saídas: `dados\estudio\imagens`, `dados\estudio\videos` e `dados\estudio\musicas`. Uploads ficam em
  `dados\estudio\uploads`.
- Caminhos de arquivo passam por `arquivo_em` (`estudio_servico.py`): a pasta permitida e o alvo são resolvidos, e só vale arquivo
  dentro da pasta resolvida (`is_relative_to`). Vale para ler e apagar imagens, vídeos, músicas e uploads.
- O Pollinations só é usado com `TUDOIA_ESTUDIO_POLLINATIONS=1` (ver [configuracao.md](../configuracao.md#local-host-e-containers)).

## O que o painel grava

| Arquivo | Quando |
|---|---|
| `.env` (com backup em `dados\backups\env\`) | Edição de segredo, `segredos`, provisionamento do Keycloak |
| `runtime\litellm\config.yaml` | `POST /api/roteador/gerar`. Guarda o anterior em `config.yaml.anterior`. A gravação só ocorre se o código do gerador não mudou desde que o painel abriu |
| `config\roteamento.yaml` | Edição de grupos do roteador (gravação atômica) |
| `governanca\governanca.json`, `governanca\mcp.json`, `governanca\regras\*.md`, `governanca\skills\*\SKILL.md` | Edições na aba Governança |
| Arquivos dos clientes (`~\.claude\`, `~\.claude.json`, `~\.gemini\`, `opencode.json` etc.) | Quando a governança ou o MCP mudam e em `sincronizar` (`aplicar_tudo`). Backups em `~\.tudoia\backups\`. Veja [governanca.md](governanca.md) |
| `dados\logs\auditoria.jsonl` | Uma linha por `POST`, `PUT`, `PATCH` ou `DELETE` em `/api` (ver [seguranca.md](../seguranca.md#auditoria)) |
| `dados\logs\comfyui.log` | Ao iniciar o ComfyUI pelo painel |

## Testes

Os testes do painel estão em `tests\painel\` (`test_painel.py`, `test_autenticacao.py`, `test_bearer.py`,
`test_cli.py`, `test_mcp_stdio.py`). Rodam com `uv run pytest -q`. Ver [desenvolvimento.md](../desenvolvimento.md).

### Sessão

O login usa o Keycloak. O painel reconfirma a conta a cada 30 s: desativar o usuário no Keycloak encerra o acesso
no próximo ciclo, e trocar o papel vale no mesmo ciclo. Sem resposta do Keycloak, o acesso é negado (503). A sessão
dura 8 h. O token do cliente `tudoia-painel` também dura 8 h (`access.token.lifespan = 28800` no template do realm);
com o padrão de 300 s do Keycloak, a sessão caía em 5 min. Rode o provisionamento para o valor valer no Keycloak em
execução. Detalhes em [seguranca.md](../seguranca.md#autenticação-oidc).

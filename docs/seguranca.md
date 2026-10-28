# Segurança

Este documento descreve o que o TudoIA faz para se proteger, o que ainda não faz e os riscos que o dono precisa
decidir. Tudo aqui foi conferido no código. Quando a afirmação vem de uma leitura do código e não de uma execução,
isso está dito. Os riscos estão em [Riscos residuais](#riscos-residuais), cada um com o estado: **corrigido**,
**em aberto** (o dono decide) ou **segue** (aceito, sem mudança prevista).

As referências usam nome de arquivo e de função ou rota, não número de linha.

O projeto foi desenhado para uma máquina, acessada só localmente. Não é desenhado para ser exposto à internet.

## Escopo e ativos

| Ativo | Onde está | Sensibilidade |
|---|---|---|
| Chaves de provedores (NIM, Groq, Anthropic etc.) | `.env`; no container do LiteLLM, só as chaves listadas no compose | Alta: custo financeiro e acesso às contas |
| Chaves internas (`LITELLM_MASTER_KEY`, `TUDOIA_SESSAO_SEGREDO`, `CEREBRO_TOKEN_ESTATICO` etc.) | `.env` | Alta: `LITELLM_MASTER_KEY` dá acesso ao gateway; `CEREBRO_TOKEN_ESTATICO` dá escrita na memória do Cérebro |
| Segredo do cliente `tudoia-mcp` | `.env` (`TUDOIA_MCP_CLIENT_SECRET`) e cofre do n8n | Alta: emite token de operador para o Cérebro |
| Tokens de MCP (GitHub, Supabase, Context7) | `.env`; gravados em `~\.claude.json` e `~\.gemini\config\mcp_config.json` pela governança | Alta |
| Sessão do painel | Cookie `tudoia_sessao` no navegador | Média |
| Memória e documentos do Cérebro | `dados\cerebro\cerebro.db`, `dados\documentos\` | Média a alta (pode conter dados pessoais) |
| Prompts e respostas | Enviados aos provedores; metadados em `dados\logs\` | Alta (ver [Privacidade](#privacidade)) |
| Backups | `dados\backups\` (dados) e `~\.tudoia\backups\` (JSON de MCP com tokens) | Alta |
| Host e GPU | Windows do usuário | Alta: o painel controla processos e pastas |

Atores considerados:

1. Outro processo ou usuário na mesma máquina.
2. Página web aberta no navegador do usuário (CSRF e DNS rebinding).
3. Máquina na mesma rede local, se a porta do Ollama estiver exposta.
4. Conteúdo externo lido pelo agente: páginas da web e documentos indexados (injeção de prompt).
5. Operador do painel (papel `tudoia-operador`), que não é admin.
6. Administrador do painel (papel `tudoia-admin`).
7. Provedores de nuvem, que recebem os prompts dos modelos gratuitos e pagos.
8. Autor de uma skill ou de um servidor MCP de terceiros.

Fora de escopo: acesso de administrador ao próprio Windows e exposição deliberada à internet.

## Controles implementados

### Autenticação OIDC

Arquivo: `painel/tudoia_painel/autenticacao.py`.

- Fluxo Authorization Code com PKCE `S256`. O `client_kwargs` tem `code_challenge_method: S256`. O authlib 1.9.1
  (versão travada no `uv.lock`) gera o `code_verifier` e o guarda na sessão. Conferido em
  `.venv/Lib/site-packages/authlib/integrations/base_client/sync_app.py`.
- O parâmetro `retorno` só aceita caminhos dentro de `/app`. Bloqueia `//`, `\` e URLs absolutas (`retorno_seguro`).
- Papéis vêm do claim `groups` ou de `realm_access.roles` (`papeis_do_token`). Só valem `tudoia-admin`,
  `tudoia-operador` e `tudoia-leitor`. Conta sem papel recebe 403 `sem_papel` no callback.
- Erros do IdP não são devolvidos ao navegador (a descrição pode ecoar parâmetros).
- Fail-closed: sem `TUDOIA_OIDC_*` completo ou com `TUDOIA_SESSAO_SEGREDO` de menos de 32 caracteres, toda rota
  `/api` responde 503 (`ConfigAuth.do_ambiente`). Só `/api/sessao` responde, para o SPA saber que a autenticação não
  está configurada.
- Sessão: cookie `tudoia_sessao`, `HttpOnly`, `SameSite=lax`, validade de 8 h (`IDADE_MAXIMA_SESSAO`), com
  `expira_em` dentro do payload. Com `TUDOIA_COOKIE_SEGURO=1`, o cookie também é `Secure`.
- `expira_em` vencido, ausente ou mais de 8 h no futuro invalida a sessão (`_papeis_validos`). O painel nunca emite um
  cookie assim, então ele é tratado como forjado.
- A sessão é reconfirmada no Keycloak (`userinfo`, `consultar_userinfo`) quando `verificado_em` tem mais de 30 s
  (`TTL_REVALIDACAO_S`). Valor no futuro, negativo ou que não é número (`_numero` devolve 0) também força a
  confirmação (`GuardaAutorizacao`). Assim um cookie com `verificado_em` adiantado não escapa da checagem. Conta
  desativada, sessão revogada ou sem papel do painel derrubam a sessão na hora. Se o Keycloak não responde, a
  requisição é negada com 503 (fail-closed). Papel alterado no Keycloak vale no próximo ciclo de confirmação.
- A confirmação usa o `access_token` guardado na sessão. O cliente `tudoia-painel` tem `access.token.lifespan = 28800`
  (8 h) em `infra/keycloak/realm-tudoia.json`. Antes valia o padrão de 300 s do Keycloak: o token vencia, o `userinfo`
  respondia 401 e a sessão caía em 5 min. O valor só vale no Keycloak em execução depois de rodar o provisionamento
  (`.\scripts\tudoia.ps1 keycloak`).
- A sessão é assinada, não cifrada. O conteúdo é JSON em base64 e inclui `id_token` e `access_token`. Quem tem o cookie
  consegue ler os claims dele (o próprio usuário). `HttpOnly` impede acesso por JavaScript.
- Token de API (opcional): com `TUDOIA_API_BEARER_CLIENTES` preenchido (lista de `azp` separados por vírgula), o painel
  aceita `Authorization: Bearer <JWT>` em `/api`. O token é validado localmente: RS256 fixo, emissor, `exp`, `azp` na
  lista e `aud` contendo o `client_id` do painel (`validar_token_bearer`). O cliente de serviço precisa de um mapper de
  audiência `tudoia-painel` (o template já o define em `tudoia-capturas`). Chaves do JWKS do realm em cache de 600 s
  (`CacheJwks`); um `kid` desconhecido (rotação de chaves) renova o cache no máximo a cada 30 s, com uma busca por vez.
  Sem as chaves, 503.
  Vazio (padrão), qualquer Bearer recebe 401 `bearer_desativado`.
- Logout (`POST /auth/logout`) passa pela checagem de origem, limpa a sessão e leva ao `end_session_endpoint` do IdP
  com `id_token_hint`.

### Autorização

Arquivo: `painel/tudoia_painel/autenticacao.py`, função `decidir`, listas `PREFIXOS_SO_ADMIN` e
`PREFIXOS_ESCRITA_SO_ADMIN`.

| Ação | Leitor | Operador | Admin |
|---|---|---|---|
| `GET` em `/api/*` (fora de `PREFIXOS_SO_ADMIN`) | sim | sim | sim |
| `POST`, `PUT`, `PATCH`, `DELETE` em `/api/*` (fora das listas abaixo) | não | sim | sim |
| `GET` em `/api/governanca/*` (estado, instâncias, regras, skills, MCP) | sim | sim | sim |
| `POST`, `PUT`, `PATCH`, `DELETE` em `/api/governanca` e `/api/governanca/*` (inclui instâncias e `sincronizar`) | não | não | sim |
| `/api/segredos`, `/api/provedores`, `/api/governanca/skills/importar`, `/api/governanca/mcp`, `/api/modelos/local/baixar` (qualquer método) | não | não | sim |

Observação: `/api/governanca/mcp` está em `PREFIXOS_SO_ADMIN`, então nem a leitura do catálogo MCP é liberada ao leitor
e ao operador.

### Guarda de Host, Origem e CSRF

Arquivo: `painel/tudoia_painel/seguranca.py`, classe `GuardaApi` (middleware ASGI, o mais externo da aplicação) e
função `checar`.

Aplica-se a `/api`, `/app` e `/auth/*`. Regras, na ordem em que o código as avalia:

1. `Host` tem de ser exatamente `127.0.0.1:<porta>` ou `localhost:<porta>`, em toda requisição a `/api`, `/app` e
   `/auth/*` (inclusive `GET` e SSE). Caso contrário, 403 `host_recusado`. Isso barra DNS rebinding.
2. Em `/api`, métodos que mudam estado (`POST`, `PUT`, `PATCH`, `DELETE`):
   - `Origin`, se presente, precisa ser local (esquema, host e porta exatos). `null` é recusado.
   - Sem `Origin`, o `Referer`, se presente, precisa ser local.
   - `Sec-Fetch-Site`, se presente, só pode ser `same-origin` ou `none`.
   - `POST`, `PUT` e `PATCH` exigem `Content-Type: application/json`. Quem não tem corpo envia `{}`. `DELETE` com
     corpo também.
   - Corpo de até 10 MB (`LIMITE_CORPO`). Exceção: `POST /api/estudio/upload`, até 140 MB (`LIMITES_POR_ROTA`; o
     upload vai em base64 no JSON). `Content-Length` declarado acima do limite recebe 413 antes da leitura. Além disso,
     `_receive_limitado` conta os bytes que chegam de fato e responde 413 ao passar do limite. Isso vale para corpo
     `chunked` (sem `Content-Length`) e para `Content-Length` menor que o corpo real.
3. Em `/auth/*`, só a regra de Host. Login e callback usam `state` e PKCE. O logout tem a própria checagem de origem.
4. Cabeçalhos em toda resposta: `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`,
   `X-Frame-Options: DENY`, `Cross-Origin-Resource-Policy: same-origin`. Na API, também `Cache-Control: no-store`. A SPA
   recebe uma Content-Security-Policy restrita e `Cross-Origin-Opener-Policy: same-origin`.
5. Toda resposta de `/api`, `/app` e `/auth/*` traz `X-Request-ID`, um id de 16 caracteres hexadecimais gerado por
   pedido. O mesmo id vai para o log e para a auditoria.
6. Exceção não tratada em rota `/api` vira 500 `falha_interna`, com o tipo da exceção e o id do pedido. A mensagem e o
   traceback nunca vão ao cliente. O traceback vai só para o log do servidor (`log.warning(..., exc_info=True)`), com
   o mesmo id.
7. Não há CORS. A SPA é servida pela mesma origem.

`GET /saude` fica fora da guarda e do login. Responde só `{"ok": true}`, para launcher e healthcheck (`rotas/ui.py`, rota
`saude`).

### Auditoria

Arquivo: `painel/tudoia_painel/auditoria.py`, classe `Auditoria`. Ligada em `registrar_autenticacao`, com o arquivo
`dados\logs\auditoria.jsonl`.

- Uma linha JSON por `POST`, `PUT`, `PATCH` ou `DELETE` em `/api/`, inclusive os negados pela autorização (401 e 403).
- Campos: `instante`, `id` (o `X-Request-ID`), `usuario` (e-mail, login ou `sub`; para Bearer, `cliente:<azp>`),
  `papeis`, `metodo`, `rota` e `status`. O corpo nunca entra: ele pode ter segredo (`PUT /api/segredos/...`) ou texto
  de prompt.
- Ao passar de 5 MB, o arquivo vira `auditoria.jsonl.1` (sobrescreve a cópia anterior).
- Disco cheio ou arquivo preso não derrubam o pedido. O aviso vai para o log.
- O middleware fica dentro da `GuardaApi`. Pedidos recusados pela `GuardaApi` (Host, origem, tipo de conteúdo,
  `Content-Length` declarado grande demais) não chegam à auditoria.

### Validação de entrada

- Nome de chave de segredo: `^[A-Z][A-Z0-9_]{0,63}$` (`painel/tudoia_painel/rotas/segredos.py`, constante `CHAVE`).
- IDs de instância, grupo e skill: `^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$` (`skills_servico.py`, constante `ID`) e `_id_seguro` em
  `governanca/__init__.py`, que recusa `..` e separadores.
- Valores do `.env` com quebra de linha são recusados (`limpar_valor`, `envfile.py`), com 422.
- Estúdio: toda rota de arquivo (`/api/estudio/imagens/{p}`, `/videos/{p}`, `/musicas/{p}`, `/uploads/{p}`, leitura e
  exclusão) passa por `arquivo_em` (`estudio_servico.py`). A função resolve a pasta permitida e o alvo e só aceita arquivo que
  existe e fica dentro da pasta resolvida (`is_relative_to`). Isso fecha `..`, `%2F` e caminho absoluto (`C:/...`).
  Uploads aceitam só extensões por tipo (imagem ou vídeo).
- Mídia do ComfyUI: verificar ou excluir aceita só pesos `.safetensors`, `.gguf`, `.ckpt` e `.pt` (`EXT_PESOS`) e
  fluxos `.json` (`EXT_FLUXO`), em `painel/tudoia_painel/modelos_service.py`, `_resolver_caminho_midia`. Antes, a
  exclusão apagava qualquer arquivo dentro de `modelos\`.
- Modelos de entrada da API usam Pydantic. Erros de validação saem com código `validacao` e a lista de campos.
- Interface: texto vindo de fora (resposta de modelo, erro de provedor) passa por `esc()` antes de entrar em
  `innerHTML` (`painel/tudoia_painel/static/painel.js`). O resultado do teste do roteador usa essa função.

### Segredos

- `.env` está no `.gitignore` (`.env` e `.env.*`). Só `.env.example` é versionado, com valores vazios ou de exemplo.
- Segredos internos são gerados com `secrets.token_urlsafe(32)` (`cli.py`, `preencher_segredos`; lista em
  `SEGREDOS_INTERNOS`, que inclui `CEREBRO_TOKEN_ESTATICO`). Se o painel sobe com OIDC configurado e sem segredo de
  sessão, gera um com `secrets.token_urlsafe(48)` (`autenticacao.py`, `carregar_config_auth`).
- `segredos` só preenche chaves vazias. Não troca valores existentes.
- Gravação do `.env` é atômica: escreve em `.env.tmp` e faz `os.replace`. Antes, copia o arquivo para
  `dados\backups\env\` (no máximo 10 cópias, `envfile.py`).
- Na API, o nome de cada chave aparece com um valor mascarado: prefixo até o primeiro `-` ou `_` (no máximo 7
  caracteres), `…` e os últimos 4 caracteres. Valores com menos de 12 caracteres viram só `…`.
- Exceção a isso: `POST /api/segredos/{chave}/revelar` devolve o valor inteiro, só para admin. Cada chamada fica na
  auditoria (rota com o nome da chave, nunca o valor). Ver o risco 6.
- O botão "Testar" envia a chave só a um endereço fixo no código, do provedor correspondente. Para `LITELLM_MASTER_KEY`
  o endereço é o LiteLLM local (`127.0.0.1:4000`). A rota é `/api/segredos/{chave}/testar` (`rotas/segredos.py`).
- Erros de provedor no hook do roteador registram só a classe da exceção e o código HTTP
  (`roteador_eventos.resumir_erro`), sem a mensagem, porque provedores às vezes repetem trechos do pedido.

### Containers e variáveis

Arquivo: `runtime/docker-compose.yml`.

- O LiteLLM não recebe mais o `.env` inteiro (não há `env_file`). Recebe uma lista explícita: `DATABASE_URL`,
  `LITELLM_MASTER_KEY`, `OLLAMA_URL`, `TZ` e as chaves de provedor (`NVIDIA_NIM_API_KEY`, `NVIDIA_NIM_API_BASE`,
  `OPENROUTER_API_KEY`, `GROQ_API_KEY`, `GEMINI_API_KEY`, `CLOUDFLARE_API_KEY`, `CLOUDFLARE_ACCOUNT_ID`,
  `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, `XAI_API_KEY`, `HF_TOKEN`). Token do GitHub, senha do
  Keycloak e chaves do n8n ficam fora. `tests/runtime/test_compose.py` garante que toda chave do catálogo está na lista
  e que segredos que o LiteLLM não usa (por exemplo `TUDOIA_MCP_CLIENT_SECRET`) não estão.
- O n8n roda com `N8N_BLOCK_ENV_ACCESS_IN_NODE=true`: nenhum nó Code ou expressão lê variáveis do container (nem a
  `N8N_ENCRYPTION_KEY`). Ele não recebe mais `TUDOIA_MCP_CLIENT_ID` nem `TUDOIA_MCP_CLIENT_SECRET`. O segredo do cliente
  `tudoia-mcp` vai para o cofre do n8n pelo `scripts/n8n/credencial_cerebro.py` (`tudoia.ps1 n8n-credencial`), pelo
  stdin do `docker exec`, nunca por argumento.
- O formulário de ingestão (`automacao/n8n/ingerir-documento.json`) exige login no n8n (`authentication: n8nUserAuth`).
- Healthcheck em `litellm-db`, `litellm`, `searxng`, `cerebro` e `n8n`.
- Todas as portas são publicadas só em `127.0.0.1`.

### Cérebro: autenticação

Arquivo: `runtime/cerebro/cerebro/autenticacao.py`. Detalhes em [cerebro.md](componentes/cerebro.md#autenticação).

- `/mcp` e `/indexar` exigem `Authorization: Bearer`. Valem dois tipos de token: JWT RS256 do Keycloak (cliente
  `tudoia-mcp`, validado localmente contra o JWKS) e o `CEREBRO_TOKEN_ESTATICO` (comparado em tempo constante, papel
  de operador, mínimo de 32 caracteres).
- Sem configuração OIDC e sem token estático, `/mcp` e `/indexar` respondem 503 (fail-closed). `/saude` é público.
- `lembrar`, `esquecer` e `/indexar` exigem `tudoia-admin` ou `tudoia-operador`.
- Negação de autenticação e de ferramenta vai para o log só com rota, status e código do motivo
  (`auth negada rota=... status=... motivo=...`, `ferramenta negada ...`). Token e cabeçalhos nunca entram no log.

### Cérebro: leitura de páginas (SSRF)

Arquivo: `runtime/cerebro/cerebro/web.py`. Ferramenta `ler_pagina`.

- Aceita só `http` e `https`, com host presente. A URL é interpretada pelo próprio `httpx.URL`, o mesmo parser que
  monta a requisição.
- Resolve o host antes de conectar e exige que **todos** os endereços resolvidos sejam globais (`ip_publico`, com
  `is_global`). Isso recusa privado, loopback, link-local (inclui `169.254.169.254`, metadados de nuvem), CGNAT,
  reservado e não especificado. IPv6 mapeado em IPv4 é tratado. Endereço NAT64 (`64:ff9b::/96`) é avaliado pelo IPv4
  embutido. Multicast é recusado mesmo quando o `ipaddress` o considera global.
- A conexão vai para o IP já validado, com `Host` e SNI do nome original (`_baixar`). O `httpx` não resolve o nome de
  novo, então não há janela de DNS rebinding. O certificado TLS continua conferido contra o nome. `Connection: close`
  impede que um salto para outro nome reaproveite a conexão.
- O cliente usa `trust_env=False` (`servidor.py`, `ler_pagina`): variáveis de proxy do ambiente não desviam a conexão.
- Redirecionamentos não são seguidos automaticamente (`follow_redirects=False`). Cada `Location` passa de novo pela
  validação. No máximo 3 saltos.
- Corpo com teto de 2 MB, timeout de 15 s por leitura e prazo total de 20 s para a página inteira (`PRAZO_TOTAL`;
  segura servidor que goteja bytes). `max_caracteres` fica entre 500 e 20000 (padrão 8000).
- O texto volta dentro de um envelope "conteúdo externo, não confiável", com uma marca aleatória no início e no fim
  (`_envelopar`). A página não consegue forjar o fechamento do envelope.

### Cérebro: entradas e limites

- `pesquisar_web`, `buscar_documentos` e `recordar`: `n` limitado a 1..20 (`vetores.MAX_RESULTADOS`).
- `lembrar`: fato de até 2000 caracteres; `origem` opcional, até 500 (`memoria.py`).
- Indexação: PDF até 500 páginas; texto extraído de PDF e DOCX até 2 milhões de caracteres; prazo de 120 s por arquivo.
  Arquivo que estoura o prazo fica em quarentena até mudar de `mtime` ou tamanho (`indexador.py`, `_estourados`).
- `recordar` e `buscar_documentos` devolvem o texto dentro de um envelope "conteúdo não confiável" com marca aleatória
  (`cerebro/envelope.py`), como o `ler_pagina`. Memória e documentos podem carregar instruções plantadas por conteúdo
  externo; o envelope as marca como dado. Mitigação, não garantia.
- Os argumentos das ferramentas nunca entram no log. O log registra ferramenta, duração e resultado (`_registrada`).

### Cérebro: rede e container

- O endpoint MCP tem proteção de DNS rebinding do SDK `mcp`. Os hosts aceitos são `cerebro`, `127.0.0.1`, `localhost` e
  `host.docker.internal`, sempre com a porta 8765 (`runtime/cerebro/cerebro/servidor.py`, `SEGURANCA`).
- O container roda como usuário sem privilégios `cerebro` (uid 10001). Só `/dados` é gravável. O código fica no
  diretório da aplicação, e o usuário não o escreve (`runtime/cerebro/Dockerfile`).
- `dados\documentos` entra em `/docs` com `:ro`.
- A porta é publicada só em `127.0.0.1`.

### Imagens Docker

- As imagens do compose estão fixadas por digest (`@sha256:`). As tags continuam no arquivo, mas o digest é o que vale.
- O `uv` no Dockerfile do Cérebro está fixado em `0.13.0`.
- A imagem base do Cérebro, `python:3.12-slim`, **não** tem digest. Veja o risco 4.

### Governança e execução de código de terceiros

- Importar skill (`POST /api/governanca/skills/importar`, só admin) executa
  `npx --yes skills@<versão fixa> add <repositório> --skill <nome> -y` (`skills_servico.py`, `VERSAO_SKILLS_CLI`). O repositório precisa casar com `REPO_GITHUB`:
  `https://github.com/<dono>/<repo>`, ou `dono/repo`, que vira essa URL. Nenhum outro host nem caractere especial
  passa. Motivo: no Windows o `npx` é um `.cmd`, e o Python não escapa argumento de `.cmd` para o `cmd.exe`
  (`&`, `|`, `^`, `%` e `"` virariam comando).
- Skill importada com link simbólico (na pasta ou em qualquer arquivo dela) é recusada antes da cópia. O `copytree`
  seguiria o link e traria, por exemplo, `~\.ssh` para a governança.
- Teste de MCP stdio: `painel/tudoia_painel/mcp_stdio.py`, `handshake`. Prazo total de 30 s para a conversa inteira,
  stderr descartado (`DEVNULL`), no máximo 200 linhas lidas, e a árvore de processos encerrada no fim (`taskkill /T /F`
  no Windows, `killpg` no Linux).
- Skills são Markdown lido pelo agente como instrução. Uma skill hostil pode tentar injeção de prompt. As skills do
  repositório foram lidas por inteiro antes da cópia, segundo `governanca/ORIGEM.md`.
- Servidores MCP do catálogo são executados com `npx`. Vários usam `@latest` ou nenhuma versão. Veja o risco 5.
- Escrita da governança (`governanca/__init__.py`): destinos resolvidos (junction e symlink no meio do caminho não
  desviam a escrita); destino fora da home e dos workspaces é recusado; destino em workspace recebe `${VAR}` literal;
  JSON de MCP com backup em `~\.tudoia\backups\` (arquivos criados com modo `0600`; no Windows quem decide o acesso
  são as ACLs do perfil). Ver [governanca.md](componentes/governanca.md).

### Estúdio

- O Pollinations (serviço público, sem conta, que recebe o prompt na URL) só é usado com
  `TUDOIA_ESTUDIO_POLLINATIONS=1` no `.env`. Desligado por padrão. Antes, ele era chamado em silêncio sempre que a
  Cloudflare falhava (`rotas/estudio_imagem.py`, `gerar-imagem`, "Rota B").
- O prompt que aparece na imagem SVG de reserva passa por `html.escape`.
- Upload (`POST /api/estudio/upload`): além da extensão, os primeiros bytes precisam bater com o formato (`midia.py`);
  o tamanho é conferido antes de decodificar o base64; o nome ganha um sufixo aleatório (dois envios no mesmo segundo
  não se sobrescrevem).
- Nomes e pastas que o ComfyUI devolve no histórico (`filename`, `subfolder`, `type`) são validados antes de virar
  caminho em disco ou consulta de `/view` (`comfyui.py`): `..`, separador, unidade e byte nulo são recusados.

### Logs e observabilidade

- `eventos.jsonl` (aba "Ao vivo") usa lista branca de campos (`roteador_eventos.CAMPOS`). Não contém texto de pedido ou
  de resposta. Corte por idade (24 h) e tamanho (20 MB).
- `roteador.jsonl` e `correcoes.jsonl` viram `.1` ao passar de 5 MB (`roteador_eventos.girar_se_grande`).
  `correcoes.jsonl` guarda só rótulo, SHA-1 e tamanho do pedido (risco 12, corrigido).
- `auditoria.jsonl`: ver [Auditoria](#auditoria).
- O painel loga em nível `warning`. O traceback de erro 500 só vai para o log, com o id do pedido.

## Riscos residuais

Cada item diz o que é, onde está, o impacto e o estado.

### 1. Ollama exposto na rede (corrigido)

- Antes: `0.0.0.0:11434` em `scripts/tudoia.ps1`, `scripts/tudoia.sh` e `painel/tudoia_painel/servicos.py`.
- Agora: `127.0.0.1:11434` no Windows (`tudoia.ps1`, `servicos.py`) e no Docker Desktop. Testado: um container alcança
  o Ollama por `host.docker.internal` com o bind em loopback.
- Linux com Docker Engine sem Docker Desktop: `tudoia.sh` (`endereco_ollama`) usa o IP IPv4 da bridge `docker0`, que é
  o que `host-gateway` resolve. Nunca `0.0.0.0`. Não testado em Linux.
- Impacto se voltar a `0.0.0.0`: a API do Ollama não tem autenticação. Quem alcança a porta usa a GPU, lista modelos e
  pode baixar ou apagar modelos.

### 2. DNS rebinding no `ler_pagina` (corrigido)

- Antes: a validação resolvia o nome e o `httpx` resolvia de novo ao conectar. Um domínio que respondesse com IP
  público na validação e IP interno na conexão alcançava serviços locais.
- Agora: a conexão vai para o IP validado, com `Host` e SNI do nome original (`web.py`, `_validar_destino` e
  `_baixar`). Ver [Cérebro: leitura de páginas](#cérebro-leitura-de-páginas-ssrf).

### 3. `runtime/open-webui/env.py` é uma cópia alterada (em aberto)

- Onde: `runtime/docker-compose.yml`, serviço `open-webui`, volume
  `./open-webui/env.py:/app/backend/open_webui/env.py:ro`.
- Impacto: o arquivo substitui o módulo de configuração da imagem. Quando a imagem subir de versão, esse arquivo não
  acompanha as mudanças do upstream. Correções de segurança ou de configuração podem ficar de fora, em silêncio.
- Estado: a comparação com o `env.py` da imagem fixada (Open WebUI 0.12.3) está em
  [servicos-docker.md](componentes/servicos-docker.md#open-webui-e-o-arquivo-envpy). Não há comparação automática. A
  diferença precisa ser conferida a cada atualização do digest.

### 4. Atualizações de imagem são manuais (em aberto)

- As imagens estão fixadas por digest, então atualização de imagem não acontece sozinha. Isso é bom para
  reprodutibilidade e ruim para correções de segurança.
- Tags flutuantes continuam no compose: `open-webui:main`, `litellm:main-latest`, `n8n:latest`.
- `python:3.12-slim` do Cérebro não tem digest.
- Cuidado: atualizar o digest do Open WebUI sem revisar o `env.py` (risco 3) pode quebrar o serviço.

### 5. Supply chain dos servidores MCP (em aberto)

- Onde: `governanca/mcp.json`. Usam `@latest` ou nenhuma versão: `@supabase/mcp-server-supabase@latest`,
  `@playwright/mcp@latest`, `@wonderwhy-er/desktop-commander@latest`, `@modelcontextprotocol/server-github`,
  `@modelcontextprotocol/server-sequential-thinking`, `@tokenizin/mcp-npx-fetch` e `mcp-remote`. Só `context7` está
  fixado (`@upstash/context7-mcp@4.4.4`).
- Impacto: uma versão nova de um pacote roda com as credenciais do `.env` na próxima vez que o cliente iniciar o MCP.
- Sugestão para o dono: fixar versões no catálogo e revisar a cada atualização.

### 6. Revelação de segredo pela API (em aberto)

- Onde: `painel/tudoia_painel/rotas/segredos.py`, rota `POST /api/segredos/{chave}/revelar` (`revelar_segredo`). Devolve o valor
  completo.
- Controles: só admin (`PREFIXOS_SO_ADMIN`), resposta com `no-store`. Cada revelação fica em
  `dados\logs\auditoria.jsonl` com usuário, instante, id do pedido e a rota (que tem o nome da chave). O valor nunca é
  registrado.
- Risco: uma sessão de admin roubada, ou um navegador com a sessão aberta, vaza todos os segredos chave a chave. A
  auditoria mostra depois o que foi revelado, mas não impede.
- Decisão em aberto: manter a rota (necessária para edição) ou só mostrar mascarado.

### 7. Cérebro sem autenticação (corrigido)

- Antes: `/mcp` e `/indexar` não pediam credencial. Qualquer processo da máquina ou container da rede do compose
  gravava, lia e apagava a memória.
- Agora: JWT do Keycloak (OIDC/JWKS, cliente `tudoia-mcp`) ou `CEREBRO_TOKEN_ESTATICO`, com papéis por ferramenta. Ver
  [Cérebro: autenticação](#cérebro-autenticação) e [cerebro.md](componentes/cerebro.md#autenticação).
- Resíduo: o `CEREBRO_TOKEN_ESTATICO` não expira e tem papel de operador. Ele fica no `.env` e, depois do `sync`, em
  claro nos arquivos dos clientes (risco 15). Revogar é trocar o valor, reiniciar o `cerebro` e rodar o `sync`.

### 8. Limite de tamanho não cobria requisição sem `Content-Length` (corrigido)

- Antes: o teto (1 MB) comparava só o `Content-Length` declarado. Corpo `chunked` não era medido.
- Agora: 10 MB (140 MB no upload do Estúdio), contados nos bytes recebidos (`seguranca.py`, `_receive_limitado`).

### 9. Operador gravava segredos em caminhos escolhidos por ele (corrigido)

- Antes: o operador criava uma instância de governança apontando para uma pasta dele e disparava o `sync`. Os tokens de
  MCP eram escritos em claro nessa pasta.
- Agora: toda escrita em `/api/governanca` (inclusive instâncias e `sincronizar`) exige admin
  (`PREFIXOS_ESCRITA_SO_ADMIN`). Além disso, a governança recusa destino fora da home e dos workspaces, no caminho
  resolvido, e destino em workspace recebe `${VAR}` literal (`governanca/__init__.py`, `_destino` e
  `_servidores_para`).

### 10. Comentário de segurança citava camada inexistente (corrigido)

- O cabeçalho de `painel/tudoia_painel/seguranca.py` não cita mais um "OrigemLocal". `grep` não encontra o nome no
  painel.

### 11. `/auth/*` fora da guarda de Host (corrigido)

- Agora `GuardaApi` aplica a regra de Host a `/auth/*` (`eh_auth`).

### 12. `correcoes.jsonl` guardava texto de prompt (corrigido)

- Antes: `runtime/litellm/roteador.py` (`_gravar_correcao`) gravava até 500 caracteres do prompt quando o usuário escrevia
  `#local` ou `#nuvem`. Nenhum código lia o arquivo.
- Agora: grava `{ts, rotulo, sha1, caracteres}`. O texto não vai para o disco. Se um dia houver aprendizado a partir de
  correções, o texto precisa de decisão e de base legal própria (ver `lgpd-compliance`).
- Linhas antigas, com texto, podem continuar em `dados\logs\correcoes.jsonl*`. Apague-as se não quiser guardá-las.

### 13. Keycloak do autor em modo de desenvolvimento (segue)

- Informado pelo dono, sem verificação possível neste repositório: a instância de Keycloak que o autor usava roda em `start-dev`, fora
  deste repositório. O Keycloak embutido no compose usa `start` com HTTP só em `127.0.0.1`. Nenhum dos dois é para produção. O template do realm define
  `sslRequired=external` (ver [keycloak.md](componentes/keycloak.md)), mas o servidor em modo de desenvolvimento não
  é uma instalação de produção.
- Não use essa instância para nada além do uso local.

### 14. Variáveis de proxy do `httpx` (corrigido)

- O cliente do `ler_pagina` usa `trust_env=False`. `HTTP_PROXY` e `HTTPS_PROXY` do ambiente não são usados.

### 15. Segredos em texto claro nos arquivos dos clientes (segue, por design)

- Onde: `governanca/__init__.py` (`_servidores_para`, `aplicar_tudo`). O painel escreve em `~\.claude.json` (chave
  `mcpServers`), no `opencode.json` e em `~\.gemini\config\mcp_config.json` os valores reais das variáveis `${VAR}` do
  `mcp.json`, lidos do `.env`.
- Os backups desses arquivos ficam em `~\.tudoia\backups\{claude-json,opencode-json,antigravity-json}`, criados com
  modo `0600`, fora de todo workspace (10 cópias por arquivo). Eles também têm os tokens em claro.
- Impacto: qualquer processo ou pessoa com acesso de leitura ao perfil do usuário lê os tokens (GitHub, Supabase,
  Context7, `CEREBRO_TOKEN_ESTATICO` e os que você adicionar). Os clientes precisam desses valores para iniciar os MCP.
  Não há cofre intermediário.
- Mitigações práticas: tokens com escopo mínimo e revogáveis; perfil do Windows sem compartilhamento; não sincronizar
  `~\` em nuvem. Se o arquivo for copiado para outro lugar, trate como vazado.

### 16. Fallback de contexto do `tudoia-local` para a nuvem (aceito pelo dono)

- Onde: `painel/tudoia_painel/gerador.py`, `router_settings.context_window_fallbacks = [{"tudoia-local":
  ["tudoia-nuvem"]}]`.
- Impacto: um pedido marcado `#local` que não cabe no contexto do modelo local é reenviado pelo LiteLLM a
  `tudoia-nuvem`. O texto sai da máquina, embora o usuário tenha pedido local. O hook não roda de novo nessa troca, e
  `#local` não impede o fallback.
- Decisão do dono (27/10/2026): manter. Pedido que não cabe no contexto local vai para a nuvem; resposta vale mais que
  erro. Para um pedido que não pode sair da máquina em hipótese alguma, encurte o contexto ou use um cliente que fale
  direto com o Ollama.

### 17. Papel admin equivale a executar código no host e nos clientes de IA (segue)

- Onde: `POST /api/governanca/mcp` grava um `command` arbitrário em `governanca/mcp.json`; o `sync` o propaga para
  `~\.claude.json`, Cursor, Codex e demais, onde roda a cada início do cliente. `POST /api/governanca/mcp/{id}/testar`
  executa esse comando na hora. `skills/importar` executa `npx` com um repositório do GitHub escolhido por quem pede.
- Impacto: uma sessão de admin comprometida vira execução de código no Windows do usuário. É a mesma fronteira do risco 6
  (revelar segredos), só que maior.
- Controles: só `tudoia-admin`; repositório restrito ao GitHub (`REPO_GITHUB`); pacote `skills` com versão fixa; skill com
  link simbólico recusada; a troca de skill não apaga a anterior se a cópia falhar; toda chamada na auditoria.
- Não há confirmação em duas etapas nem lista de comandos permitidos. Mantenha poucos admins, com MFA no Keycloak.

### 18. `runtime/open-webui/env.py` muda o nome do produto (em aberto, verificável)

- A cópia troca `WEBUI_NAME` e `WEBUI_FAVICON_URL` e remove o aviso de licença do upstream (ver o diff em
  `runtime/open-webui/env.py.aprovado.diff`). A licença do Open WebUI restringe alterar essa marca fora do que ela permite
  (https://docs.openwebui.com/license). Confirme se o seu uso está dentro da licença.
- Mitigação do risco 3: `.\scripts\tudoia.ps1 verificar-openwebui` extrai o `env.py` da imagem fixada no compose, calcula o
  diff contra a cópia e reprova se ele for diferente do aprovado. Rode ao trocar o digest; depois de revisar o diff novo,
  `--aprovar`. O teste `tests/openwebui/test_verificar_env.py` faz a mesma conferência quando o docker e a imagem existem.

### 19. Resposta de modelo e conteúdo indexado continuam sendo instrução em potencial (segue)

- O envelope do Cérebro marca texto de fora como dado, mas o modelo é quem decide o que fazer com ele. `lembrar` aceita
  `origem` para o agente declarar de onde veio o fato; nada obriga o agente a informar.
- Mitigação prática: tratar a memória como não verificada; usar `esquecer` em fato suspeito; não indexar pasta que receba
  conteúdo de terceiros sem revisão.

### 20. Primeiro acesso ao Open WebUI e ao n8n (segue)

- Os dois criam o dono na primeira visita. Em `127.0.0.1` o risco é outro processo local chegar antes. Crie as contas logo
  depois do primeiro `up`.

## Privacidade

- Provedores gratuitos e pagos recebem o texto dos pedidos que o roteador envia a eles. Gratuito não é privado. O
  `.env.example` avisa disso e cita o plano gratuito do Gemini, que usa os dados para treino.
- `#local` não garante que o texto fica na máquina: ver o risco 16.
- Modelos locais (Ollama) não saem da máquina. Mesmo assim, o embedding de cada mensagem é calculado pelo `bge-m3` e
  guardado no cache `exemplos-vetores.json` (somente hashes e vetores, não o texto, segundo `roteador.py`).
- O Cérebro guarda documentos e fatos em `dados\cerebro\cerebro.db`. Não há criptografia em repouso. Use o BitLocker ou
  equivalente do Windows se isso for necessário. O backup (`tudoia.ps1 backup`) copia esse banco para
  `dados\backups\`, também sem criptografia.

## Como reportar uma vulnerabilidade

Não abra issue pública com detalhes de exploração.

Use o recurso de **security advisory privado** do repositório (no GitHub: aba **Security** > **Report a vulnerability**).
Se o projeto não estiver no GitHub, o canal é **a confirmar**. Não há e-mail de contato no repositório.

Inclua:

- o commit ou versão afetada (`pyproject.toml` diz 2.0.0; o commit é mais preciso);
- os passos para reproduzir, com o endpoint ou arquivo envolvido;
- o impacto esperado;
- se houver segredo exposto, diga qual, sem colar o valor. Rotacione o segredo antes de reportar.

## Checklist mínimo para uma máquina

- `.env` fora de qualquer pasta sincronizada (OneDrive, Dropbox). O mesmo vale para `~\.tudoia\backups\` e
  `dados\backups\`.
- `TUDOIA_COOKIE_SEGURO=1` se houver proxy com TLS. Sem TLS, mantenha `0`.
- Ollama só em loopback (Windows e Docker Desktop) ou no IP da `docker0` (Linux com Docker Engine). Ver o risco 1.
- Contas no Keycloak com senha forte e MFA quando o provedor permitir.
- Só admins que realmente precisam de acesso a segredos, skills e governança.
- Revisar `governanca/governanca.json` e `governanca/mcp.json` antes de cada `sync`.
- Rodar `.\scripts\tudoia.ps1 verificar-openwebui` ao trocar o digest do Open WebUI (risco 18).
- Não usar a instância de Keycloak em modo de desenvolvimento para nada além de uso local (risco 13).
- Ler `dados\logs\auditoria.jsonl` de vez em quando, sobretudo as linhas de `/revelar`.

## Política de senha do realm `tudoia`

O template (`infra/keycloak/realm-tudoia.json`) define `passwordPolicy = "length(12) and notUsername and notEmail"`: no
mínimo 12 caracteres, sem repetir o login nem o e-mail. Isso revoga a decisão anterior do dono de deixar a política
desligada (antes, qualquer senha era aceita). A proteção contra força bruta (brute force detection) continua ligada.

- A política vale para senhas **novas ou trocadas**. Contas que já existem mantêm a senha atual até a próxima troca;
  troque as dos admins agora.
- A senha temporária do primeiro administrador (`--admin-inicial`) tem 24 caracteres e cumpre a regra.
- Para mudar a regra, edite `passwordPolicy` no template e rode `.\scripts\tudoia.ps1 keycloak`. O provisionador
  aplica o template inteiro, inclusive a política.

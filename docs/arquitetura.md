---
titulo: Arquitetura
tipo: explicacao
dono: TudoIA (mantenedor do repositório)
status: vigente
classificacao: publico
verificado-em: 2026-11-03
---

[🏠 TudoIA](../README.md) › [📚 Documentação](README.md) › 🏗️ Arquitetura

# 🏗️ Arquitetura

> Para quem mantém ou audita o TudoIA: que peças existem, onde cada uma roda, em que porta escuta, com quem conversa e onde guarda os dados. Cada componente tem o seu guia; aqui está o que liga um ao outro.

## 📑 Sumário

- [🎯 Visão geral](#-visão-geral)
- [🧱 Componentes](#-componentes)
- [🔌 Portas](#-portas)
- [🔄 Fluxos](#-fluxos)
- [🐳 Serviços Docker](#-serviços-docker)
- [🗄️ Localização dos dados](#️-localização-dos-dados)
- [🛡️ Segurança em uma página](#️-segurança-em-uma-página)
- [📏 Ambiente de referência](#-ambiente-de-referência)

---

## 🎯 Visão geral

O TudoIA é uma máquina só. A GPU fica no host, então o Ollama e o ComfyUI rodam como processos do Windows. Os serviços de rede ficam em containers Docker, com as portas publicadas só em `127.0.0.1`. O painel é o ponto de controle: sobe e para serviços, edita a configuração, guarda o login e conversa com os demais.

```mermaid
---
title: Contêineres do TudoIA (C4 nível 2, só loopback)
---
flowchart LR
    subgraph Navegador
        UI[Painel SPA]
    end

    subgraph Host["Host Windows (processos)"]
        Painel["Painel FastAPI<br/>127.0.0.1:3100"]
        Ollama["Ollama<br/>127.0.0.1:11434"]
        ComfyUI["ComfyUI<br/>127.0.0.1:8188"]
    end

    subgraph Docker["Docker (projeto compose tudoia)"]
        LiteLLM["LiteLLM :4000<br/>+ hook do roteador"]
        PG[("Postgres único :5433<br/>bancos litellm e keycloak")]
        Cerebro["Cérebro MCP :8765"]
        SearXNG["SearXNG :8080"]
        OWUI["Open WebUI :3000"]
        Kokoro["Kokoro :8880"]
        N8N["n8n :5678"]
        KC["Keycloak :8180<br/>(perfil keycloak)"]
        Squad["SquadTI :8790<br/>(perfil squadti)"]
    end

    Nuvem[("Provedores de nuvem")]
    Clientes["Clientes de IA<br/>Claude Code, Cursor, Antigravity,<br/>Codex, OpenCode, Aider"]
    Web[("Páginas públicas")]

    UI -->|HTTP| Painel
    Painel -->|OIDC| KC
    Painel -->|chat, testes, métricas| LiteLLM
    Painel -->|compose up, stop| Docker
    Painel -->|iniciar, parar| Ollama
    Painel -->|/prompt, /history, /view| ComfyUI
    Painel -->|/api/tags, /api/generate| Ollama
    Painel -->|/api/squadti, Bearer| Squad

    Clientes -->|API OpenAI e Anthropic| LiteLLM
    Clientes -->|MCP /mcp| Cerebro
    OWUI -->|OLLAMA_BASE_URL| Ollama
    LiteLLM -->|embeddings bge-m3, modelos locais| Ollama
    LiteLLM -->|metadados e chaves| PG
    LiteLLM -->|HTTPS| Nuvem
    Cerebro -->|embeddings bge-m3| Ollama
    Cerebro -->|pesquisar_web| SearXNG
    Cerebro -->|ler_pagina| Web
    Cerebro -->|JWKS| KC
    N8N -->|POST /indexar| Cerebro
    N8N -->|token client_credentials| KC
    KC -->|banco keycloak| PG
    Squad -->|chat local| LiteLLM
```

Três observações que o desenho não mostra:

- O Kokoro não tem chamada em nenhum código deste repositório. O compose só faz o Open WebUI depender dele e do SearXNG; como o Open WebUI os usa fica na configuração interna dele, que não é versionada.
- O compose configura o Open WebUI só para o Ollama (`OLLAMA_BASE_URL`). Qualquer conexão dele com o LiteLLM é feita na interface do próprio Open WebUI.
- O Keycloak embutido é opcional. Quem tem um Keycloak próprio tira `keycloak` de `COMPOSE_PROFILES` e aponta `TUDOIA_OIDC_ISSUER` para ele (ver [Keycloak](componentes/keycloak.md)).

## 🧱 Componentes

| Componente | Tecnologia | Papel | Guia |
|---|---|---|---|
| Painel | FastAPI, SPA estática (`painel/tudoia_painel/static/`) | Controle, login, Estúdio, configuração, tela da governança e da SquadTI | [painel](componentes/painel.md) |
| LiteLLM e roteador | Imagem `ghcr.io/berriai/litellm` e hook `runtime/litellm/roteador*.py` | Gateway OpenAI e Anthropic, roteamento, quarentena, métricas | [roteador](componentes/roteador.md) |
| Cérebro | Python 3.12, `mcp`, SQLite, `numpy` | Busca web, leitura de páginas, documentos e memória | [cérebro](componentes/cerebro.md) |
| Governança | Python (biblioteca padrão), `governanca/` | Distribui regras, skills e MCP para os clientes de IA | [governança](componentes/governanca.md) |
| Doutrina | Pasta indicada por `DOUTRINA_TEC`, commit fixado em `governanca/doutrina.json` | Regras de engenharia consumidas pela skill, pelo MCP `doutrina-tec` e pela SquadTI | [doutrina](componentes/doutrina.md) |
| Keycloak | Imagem `quay.io/keycloak/keycloak`, tema em `infra/keycloak/tema/` | Identidade OIDC do painel, do Cérebro e do n8n | [keycloak](componentes/keycloak.md) |
| Modelos | Python, `config/modelos.yaml` | Baixa e verifica os pesos | [modelos](componentes/modelos.md) |
| Open WebUI, SearXNG, Kokoro, n8n, Postgres | Imagens fixadas por digest | Chat com interface própria, metabusca, voz, automação, banco | [serviços Docker](componentes/servicos-docker.md) |
| Automação | Fluxos JSON do n8n (`automacao/n8n/`) | Resumo, pesquisa, digest e ingestão no Cérebro | [automação n8n](componentes/automacao-n8n.md) |
| SquadTI | LangGraph, SDK .NET e Node numa imagem própria (`runtime/squadti/`) | Gera projetos novos seguindo a Doutrina | [squadti](componentes/squadti.md) |
| Estúdio | Parte do painel e fluxos do ComfyUI (`runtime/comfyui/workflows/`) | Imagens, vídeos e músicas | [estúdio](componentes/estudio.md) |
| Instalador | PyInstaller, tela web local (`instalador/`) | Instala o TudoIA no Windows | [instalador](instalador.md) |

## 🔌 Portas

Os valores vêm de `runtime/docker-compose.yml`, `painel/tudoia_painel/cli.py`, `painel/tudoia_painel/servicos.py`, `painel/tudoia_painel/upstreams.py` e `scripts/_comum.ps1`.

| Porta | Serviço | Onde escuta | Observação |
|---|---|---|---|
| 3100 | Painel | `127.0.0.1` (uvicorn) | Padrão de `tudoia painel --porta`. O redirect URI do login OIDC depende dela. |
| 4000 | LiteLLM | `127.0.0.1:4000` publicado | Único gateway; todos os clientes falam com ele. |
| 8765 | Cérebro (`/mcp`, `/indexar`, `/saude`) | `127.0.0.1:8765` publicado; `0.0.0.0` dentro do container | Endpoint MCP em `/mcp`. |
| 3000 | Open WebUI | `127.0.0.1:3000` publicado (container 8080) | |
| 8080 | SearXNG | `127.0.0.1:8080` publicado | Precisa de `formats: json`, já configurado em `runtime/searxng/settings.yml`. |
| 5678 | n8n | `127.0.0.1:5678` publicado | |
| 8880 | Kokoro | `127.0.0.1:8880` publicado | |
| 5433 | Postgres único | `127.0.0.1:5433` publicado (container 5432) | Bancos `litellm` e `keycloak`. |
| 8180 | Keycloak | `127.0.0.1:8180` publicado (container 8080) | Só com o perfil `keycloak`. HTTP puro: não exponha. |
| 8790 | SquadTI | `127.0.0.1:8790` publicado | Só com o perfil `squadti`. |
| 11434 | Ollama | `127.0.0.1:11434` (`OLLAMA_HOST` definido por quem o inicia) | Os containers chegam por `host.docker.internal`. |
| 8188 | ComfyUI | O painel e o `iniciar.ps1` o iniciam sem `--listen`; o código sempre o chama em `127.0.0.1` | O bind real é do próprio ComfyUI e não foi verificado aqui. |

## 🔄 Fluxos

### Login no painel (OIDC, Authorization Code com PKCE)

```mermaid
sequenceDiagram
    participant B as Navegador
    participant P as Painel
    participant K as Keycloak
    B->>P: GET /auth/login?retorno=/app/
    P->>P: guarda o estado no servidor; gera code_verifier (S256)
    P-->>B: 302 para o authorize (state, code_challenge); cookie tudoia_login_<state>
    B->>K: login
    K-->>B: 302 para /auth/callback?code=...&state=...
    B->>P: GET /auth/callback
    P->>K: troca code + code_verifier por tokens (servidor a servidor)
    K-->>P: id_token com claims (groups ou realm_access.roles)
    P->>P: mapeia tudoia-admin, tudoia-operador, tudoia-leitor
    P-->>B: 303 para o retorno; cookie tudoia_sessao (8 h)
```

Detalhes e limites: [painel](componentes/painel.md) e [segurança](seguranca.md).

### Chat pelo gateway

```mermaid
sequenceDiagram
    participant C as Cliente (ex.: Claude Code)
    participant L as LiteLLM
    participant H as Hook roteador.py
    participant O as Ollama (bge-m3)
    participant N as Membro do grupo (nuvem ou local)
    C->>L: POST /v1/messages ou /v1/chat/completions (model=tudoia-auto)
    L->>H: async_pre_call_hook
    H->>H: marcador (#local, #nuvem, #max); regras; visão; ferramentas
    alt pontuação ambígua
        H->>O: embedding da última mensagem (até 1,5 s)
        O-->>H: vetor; vizinhos mais próximos em exemplos-roteamento.yaml
    end
    H->>L: escolhe o grupo (tudoia-nuvem, tudoia-codigo, tudoia-local...)
    L->>N: membro escolhido (latency-based, cooldown de 60 s)
    N-->>L: resposta ou erro
    L->>H: eventos (só metadados) para eventos.jsonl
    L-->>C: resposta (nova tentativa em outro membro se falhar)
```

Em `/v1/messages` (Claude Code) o hook segura o stream até `message_stop` e só então o libera. Assim uma falha no meio da resposta pode ser refeita em outro modelo sem o cliente perceber (ver [roteador](componentes/roteador.md)).

### Geração de imagem no Estúdio (ComfyUI)

```mermaid
sequenceDiagram
    participant B as Navegador
    participant P as Painel
    participant G as Groq ou Ollama (prompt)
    participant O as Ollama
    participant C as ComfyUI :8188
    B->>P: POST /api/estudio/gerar-imagem
    P->>G: otimiza o prompt (GROQ_API_KEY ou modelo local)
    P->>O: descarrega modelos da VRAM (keep_alive 0) antes da inferência visual
    P->>C: POST /prompt (grafo do fluxo)
    loop até concluir
        P->>C: GET /history/{prompt_id}
    end
    P->>C: GET /view?filename=...
    P->>P: grava em dados\estudio\imagens
    P-->>B: JSON com a URL do arquivo
```

Quando o motor pedido não é o ComfyUI, ou ele está fora do ar, `gerar-imagem` segue outro caminho em `painel/tudoia_painel/rotas/estudio_imagem.py` e não passa por ele. Vídeos, músicas e vídeo longo: [estúdio](componentes/estudio.md).

### Leitura de página pelo Cérebro

```mermaid
sequenceDiagram
    participant A as Agente (MCP)
    participant C as Cérebro
    participant D as DNS
    participant W as Site público
    A->>C: ler_pagina(url)
    C->>C: aceita só http e https
    C->>D: resolve o host
    D-->>C: endereços
    C->>C: todos precisam ser globais
    C->>W: GET no IP validado, Host e SNI do nome (sem seguir redirecionamento sozinho)
    alt redirecionamento (máximo 3)
        W-->>C: 3xx Location
        C->>C: valida o novo destino de novo
    end
    W-->>C: corpo (máximo 2 MB, prazo total de 20 s)
    C-->>A: texto principal (trafilatura) num envelope de conteúdo externo, cortado em max_caracteres
```

Os detalhes de SSRF estão em [segurança](seguranca.md).

### Distribuição da governança

```mermaid
sequenceDiagram
    participant U as Usuário ou instalador
    participant G as governanca.sincronizar
    participant F as governanca/ (regras, skills, mcp.json, governanca.json)
    participant E as .env
    participant D as Clientes de IA (arquivos em ~ e nos workspaces)
    U->>G: tudoia sync (ou o painel: aplicar_tudo)
    G->>F: lê regras, skills, catálogo MCP e instâncias
    G->>E: lê as variáveis ${VAR} dos MCP ativos
    G->>G: valida tudo (destino, segredo, JSON, marcas); nada é escrito se algo falhar
    G->>D: bloco gerenciado, skills, MCP (atômico, com backup em ~/.tudoia/backups)
    G-->>U: {alvo: atualizado | igual | removido}
```

A interface pública está em [SPEC.md](../SPEC.md) e o comportamento por cliente em [governança](componentes/governanca.md).

## 🐳 Serviços Docker

Definidos em `runtime/docker-compose.yml`, projeto `tudoia` (ou o de `TUDOIA_COMPOSE_PROJETO`). Suba com `.\scripts\tudoia.ps1 up`.

- O Postgres e o LiteLLM sempre sobem. Os demais dependem de `COMPOSE_PROFILES`: `cerebro` (Cérebro e SearXNG), `webui` (Open WebUI, Kokoro e SearXNG), `n8n`, `keycloak` e `squadti`.
- Todas as imagens baixadas estão fixadas por digest (`@sha256:`). As tags continuam no arquivo, mas o digest é o que vale. As imagens base do Cérebro (`python:3.12-slim`) não têm digest; as da SquadTI têm.
- Nenhum serviço recebe o `.env` inteiro (não há `env_file`). O `litellm` recebe uma lista explícita de variáveis (chaves de provedor, `LITELLM_MASTER_KEY`, `DATABASE_URL`, `OLLAMA_URL`, `TZ`); `tests/runtime/test_compose.py` confere que toda chave do catálogo chega a ele.
- O `n8n` recebe a `N8N_ENCRYPTION_KEY`, que cifra as credenciais salvas nele; restaurar o volume `n8n` exige a mesma chave. Ele roda com `N8N_BLOCK_ENV_ACCESS_IN_NODE=true` e guarda o segredo do Cérebro no próprio cofre.
- Healthcheck em `postgres`, `litellm`, `searxng`, `cerebro`, `n8n`, `keycloak` e `squadti`. Kokoro e Open WebUI não têm.
- O `litellm` monta `runtime/litellm/config.yaml` (gerado pelo painel), os quatro arquivos Python do hook e `config/`, tudo somente leitura.
- O Cérebro monta `dados/documentos` como `/docs` (somente leitura) e `dados/cerebro` como `/dados`. O `n8n` monta `dados/documentos` como `/data/docs`, com `N8N_RESTRICT_FILE_ACCESS_TO=/data/docs`.
- A SquadTI roda sem root, com sistema de arquivos somente leitura, sem capabilities e com teto de CPU, memória e processos. **Monta o `docker.sock` do host** para os testes de integração dos projetos que gera (decisão registrada no compose): quem controla o socket controla o Docker do host, então o código que o modelo gera deixa de estar isolado do host. Ver [squadti](componentes/squadti.md).

## 🗄️ Localização dos dados

| Caminho | Conteúdo | Quem grava | Versionado | Backup |
|---|---|---|---|---|
| `.env` | Segredos e configuração | Você; `segredos`; `keycloak`; instalador; painel (aba Segredos) | Não (`.gitignore`) | Cópias em `dados\backups\env\`; não entra no `backup` |
| `dados\backups\env\` | Cópias do `.env` antes de cada gravação (máximo 10) | Painel e `segredos` | Não | É o backup |
| `dados\backups\<AAAAMMDD-HHMMSS>\` | `postgres-litellm.sql.gz`, `postgres-keycloak.sql.gz`, `cerebro.db`, `n8n.tar.gz`, `open-webui.tar.gz` e `manifesto.json` (sha256 de cada item) | `tudoia.ps1 backup` (`scripts/backup/backup.py`) | Não | É o backup; `--manter N` guarda os N mais recentes |
| `dados\cerebro\cerebro.db` | SQLite: fatos, trechos indexados e arquivos | Cérebro | Não | `backup` |
| `dados\documentos\` | Documentos que o Cérebro indexa (`.md`, `.txt`, `.pdf`, `.docx`, `.html`) | Você; n8n (`entrada`, `resumos`) | Não | Manual |
| `dados\estudio\` | Saídas do Estúdio (`imagens`, `videos`, `musicas`) e `uploads` | Painel | Não | Manual |
| `dados\squadti-template\` | Padrão de `SQUADTI_TEMPLATE_DIR`: o TemplateTEC montado em `/template` na SquadTI | Você | Não | Manual |
| `dados\logs\` | Do hook: `eventos.jsonl`, `roteador.jsonl`, `correcoes.jsonl`, `ratelimit.json`, `exemplos-vetores.json`. Do painel e dos scripts: `auditoria.jsonl`, `painel.out.log`, `painel.err.log`, `comfyui.log`, `comfyui.err.log`. Lidos pelo hook: `limites.json`, `quarentena.json` e `gpu.json` (nenhum código versionado que os escreva foi localizado). Os `.jsonl` de `roteador`, `correcoes` e `auditoria` giram para `.1` acima de 5 MB | Hook do roteador; painel; scripts | Não | Não |
| `modelos\ollama\models\` | Pesos do Ollama (padrão de `TUDOIA_OLLAMA_MODELS`) | Ollama | Não (`.gitignore`) | Não |
| `modelos\comfyui\ComfyUI_windows_portable\` | ComfyUI portable e pesos (padrão de `TUDOIA_COMFYUI_PORTABLE`) | Você; baixador | Não | Não |
| `runtime\litellm\config.yaml` | Configuração gerada do LiteLLM | Painel (`/api/roteador/gerar`) | Não | `config.yaml.anterior` |
| Volume `postgres` | Dados do Postgres único (bancos do LiteLLM e do Keycloak) | LiteLLM, Keycloak | Não | `backup` (`pg_dump` de cada banco) |
| Volume `open-webui` | Dados do Open WebUI | Open WebUI | Não | `backup` (tar) |
| Volume `n8n` | Fluxos e credenciais do n8n, cifradas com `N8N_ENCRYPTION_KEY` | n8n | Não | `backup` (tar); restaurar exige a mesma chave |
| Volume `squadti-dados` | Checkpoint, `workspace/<tarefa>` e caches NuGet e npm da SquadTI | SquadTI | Não | Não |
| `~\.claude\`, `~\.claude.json`, `~\.gemini\`, `~\.codex\`, `~\.cursor\mcp.json`, `opencode.json`, `~\.aider.conf.yml` | Arquivos gerados pela governança nos clientes | `sincronizar` e painel (`aplicar_tudo`) | Não | Não |
| `~\.tudoia\backups\` | Cópias dos arquivos de MCP antes de cada gravação (`claude-json`, `opencode-json`, `antigravity-json`, `cursor-json`, `codex-toml`; 10 por arquivo). Têm tokens em claro | Governança | Não | É o backup |

Os volumes levam o prefixo do projeto compose (`tudoia_postgres`, `tudoia_n8n` etc.). `dados\`, `modelos\` e `runtime\litellm\config.yaml*` estão no `.gitignore`. Os nomes de pasta e de arquivo foram conferidos em `painel/tudoia_painel/caminhos.py`, `scripts/backup/backup.py`, `scripts/_comum.ps1` e `runtime/litellm/roteador.py`.

## 🛡️ Segurança em uma página

- Todo serviço publica em `127.0.0.1`; nada escuta na rede local por padrão.
- O painel só atende `/api` com sessão OIDC (ou Bearer de cliente de serviço permitido); sem IdP configurado responde 503.
- Nenhum container recebe o `.env` inteiro; o LiteLLM é o mais exposto a texto de terceiros e recebe só o que o `config.yaml` referencia.
- A governança falha fechada: valida tudo antes de escrever e nunca grava segredo em workspace.
- A exceção declarada é o `docker.sock` da SquadTI, descrita acima.

O modelo de ameaças completo, os controles e os riscos residuais estão em [segurança](seguranca.md).

## 📏 Ambiente de referência

Os limites de contexto, os tempos de espera e os comentários de desempenho em `painel/tudoia_painel/gerador.py` foram medidos em uma RTX 5070 com 8 GB de VRAM. Com outra GPU, esses valores precisam ser medidos de novo.

---

[🏠 README](../README.md) · ⬅️ [Glossário](glossario.md) · [Configuração](configuracao.md) ➡️

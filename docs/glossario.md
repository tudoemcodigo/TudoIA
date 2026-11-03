---
titulo: Glossário
tipo: glossario
dono: TudoIA (mantenedor do repositório)
status: vigente
classificacao: publico
verificado-em: 2026-11-03
---

[🏠 TudoIA](../README.md) › [📚 Documentação](README.md) › 📖 Glossário

# 📖 Glossário

> Para quem lê ou escreve a documentação e o código do TudoIA: o termo canônico de cada conceito, em uma linha, e o sinônimo que não se usa. O termo é o mesmo no código, na API, na interface e nos documentos.

## 📑 Sumário

- [🧩 Produto e componentes](#-produto-e-componentes)
- [🔀 Roteamento de modelos](#-roteamento-de-modelos)
- [🏛️ Governança dos clientes de IA](#️-governança-dos-clientes-de-ia)
- [🔐 Identidade e acesso](#-identidade-e-acesso)
- [🐳 Execução e configuração](#-execução-e-configuração)
- [🤝 Ecossistema TEC](#-ecossistema-tec)

Dentro de cada seção os termos seguem a ordem alfabética.

---

## 🧩 Produto e componentes

| Termo | Definição | Evitar |
|---|---|---|
| Automação | Os fluxos do n8n versionados em `automacao/n8n/` (resumo de documentos, pesquisa, digest de notícias e ingestão no Cérebro). | workflow solto, robô |
| Backup | Cópia datada em `dados\backups\<AAAAMMDD-HHMMSS>\` do Postgres (bancos `litellm` e `keycloak`), do `cerebro.db` e dos volumes do n8n e do Open WebUI, com manifesto de sha256; o `.env` não entra. | snapshot |
| Cérebro | Servidor MCP local (`runtime/cerebro/`) com busca na web, leitura de páginas, busca nos documentos indexados e memória de fatos. | Cerebro (sem acento) em texto corrido, memória |
| Estúdio | Parte do painel que gera imagens, vídeos e músicas pelo ComfyUI ou por provedores de nuvem (`rotas/estudio_*.py`). | Studio (só no nome de `scripts/studio`) |
| Instalador | `TudoIA-Setup.exe`, assistente do Windows que prepara a máquina e instala o TudoIA (`instalador/`, `scripts/empacotar/`). | setup, wizard |
| Painel | Interface web e API de controle (FastAPI e SPA, `painel/`), em `http://127.0.0.1:3100/app/`. | dashboard, console |
| Payload | Zip reproduzível com o código do repositório que o instalador carrega (`instalador/dados/payload.zip`, manifesto em `payload.manifest.json`). | pacote do instalador |
| Serviço do host | Processo do Windows fora do Docker, por causa da GPU: Ollama (porta 11434) e ComfyUI (porta 8188). | serviço nativo |
| SquadTI | Equipe de agentes (LangGraph) que gera projetos novos seguindo a Doutrina; roda no container `squadti` (porta 8790) e aparece no menu SquadTI do painel. | Squad (só em texto corrido, depois de definida), esquadrão |
| TudoIA | O produto inteiro: o painel, o roteador, o Cérebro, a governança e os serviços que sobem por Docker ou no host. | TudoAI, Tudo IA |

## 🔀 Roteamento de modelos

| Termo | Definição | Evitar |
|---|---|---|
| Catálogo de modelos | `config/catalogo-modelos.yaml`: os provedores e os modelos que o painel pode oferecer ao roteador. | lista de modelos |
| Gateway | O LiteLLM na porta 4000, único ponto de entrada de chat dos clientes (APIs compatíveis com OpenAI e Anthropic). | proxy |
| Grupo de modelos | Nome de modelo (`model_name`) do LiteLLM que reúne vários membros equivalentes, como `tudoia-local`, `tudoia-nuvem` e `tudoia-codigo`; a ordem dos membros está em `config/roteamento.yaml`. | pool, cluster |
| Hook | O código em `runtime/litellm/roteador*.py`, montado no container do LiteLLM, que decide o grupo antes de cada chamada. | plugin |
| Manifesto de modelos | `config/modelos.yaml`: os pesos de IA que o baixador conhece (id, origem, tamanho, checksum). Os pesos ficam fora do repositório. | lista de downloads |
| Marcador | `#local`, `#nuvem` ou `#max` no fim da última mensagem; força o destino e é removido do texto antes de enviar. | tag, flag |
| Membro | Um modelo concreto (por exemplo `groq/gpt-oss-120b`) dentro de um grupo de modelos. | nó, backend |
| Perfil (do roteador) | Nome de modelo que o cliente escolhe e que fixa as regras de privacidade, como `tudoia-local-estrito` (nunca sai da máquina) e `tudoia-hibrido` (local primeiro, nuvem gratuita como apoio); seção `perfis` de `config/roteamento.yaml`. | modo |
| Provedor | Serviço que hospeda modelos na nuvem, gratuito (FREE) ou pago (PAID) no catálogo; a chave fica no `.env`. | vendor |
| Quarentena | Estado de um membro afastado do rodízio até um horário (`ate`) depois de falhar; o hook lê `dados\logs\quarentena.json`. | blacklist |
| Roteador | O hook que escolhe o grupo de modelos de cada pedido por regras e, se a pontuação for ambígua, por similaridade semântica. | router (só quando se fala do `Router` do LiteLLM) |
| tudoia-auto | Nome de modelo que aciona o roteador; ele resolve para um grupo (`tudoia-local`, `tudoia-nuvem`, `tudoia-codigo` etc.). Não garante execução local. | auto, roteador automático |
| tudoia-max | Grupo de modelos pagos, usado só quando o cliente o pede pelo nome ou com `#max`. | premium |

## 🏛️ Governança dos clientes de IA

| Termo | Definição | Evitar |
|---|---|---|
| Bloco gerenciado | Trecho de um arquivo entre as marcas `<!-- tudoia:inicio ... -->` e `<!-- tudoia:fim -->`, reescrito pela governança; o que fica fora das marcas é do usuário. | seção automática |
| Catálogo MCP | `governanca/mcp.json`: os servidores MCP que o TudoIA conhece, com `${VAR}` no lugar de segredos. Só os ids listados em `mcp[]` de `governanca.json` ficam ativos. | lista de MCPs |
| Cliente de IA | Ferramenta do usuário que recebe regras, skills e MCP: Claude Code, Cursor, Antigravity, Codex, OpenCode e Aider. | agente (reservado para os agentes da SquadTI) |
| Drift | Diferença entre o que a governança geraria e o que está no disco; `verificar` lista e nunca escreve. | divergência (só no sentido genérico) |
| Governança | Módulo Python `governanca/` e a pasta de mesmo nome: a fonte única de regras, skills e MCP e o código que a distribui. | sincronizador |
| Instância | Entrada de `instancias[]` em `governanca.json` (ou em `instancias.local.json`) que aponta um cliente de IA a uma pasta, por exemplo um perfil `~/.claude-*`. | perfil de cliente, conta |
| MCP | Model Context Protocol: protocolo pelo qual os clientes de IA chamam ferramentas, como as do Cérebro. | plugin |
| Regra | Arquivo Markdown de `governanca/regras/` que vira o bloco gerenciado de instruções nos clientes. | prompt do sistema |
| Seam pública | A interface única do módulo `governanca` descrita em [SPEC.md](../SPEC.md): `sincronizar`, `verificar`, `aplicar_mcp_claude`, `aplicar_mcp_opencode`, `aplicar_tudo` e `detectar_instancias`. | API interna |
| Skill | Pasta de `governanca/skills/<id>/` com um `SKILL.md`, copiada para os clientes que suportam skills. | habilidade, plugin |
| Skill órfã | Pasta de skill que tem o marcador `.tudoia` mas saiu de `skills[]`; `verificar` aponta e `sincronizar` remove. Pasta sem marcador nunca é apagada. | skill velha |
| Workspace | Raiz de um projeto do usuário listada em `workspaces[]` ou numa instância `cursor`/`workspace`; recebe `AGENTS.md` com `${VAR}` literal, nunca o valor do segredo. | pasta de projeto |

## 🔐 Identidade e acesso

| Termo | Definição | Evitar |
|---|---|---|
| Cliente de serviço | Cliente OIDC sem usuário (`client_credentials`), como `tudoia-mcp` (Cérebro e n8n) e `tudoia-capturas` (capturas de tela). | conta de máquina |
| Keycloak | Provedor de identidade OIDC do painel, do Cérebro e do n8n; sobe pelo perfil de compose `keycloak` na porta 8180 ou é um Keycloak próprio apontado por `TUDOIA_OIDC_ISSUER`. | SSO, servidor de login |
| Papel | Um dos três papéis do painel: `tudoia-admin` (tudo, inclusive segredos), `tudoia-operador` (altera o que não é administrativo) e `tudoia-leitor` (só leitura); vêm do claim `groups` ou de `realm_access.roles`. | permissão, role |
| Realm | Domínio de identidade do Keycloak; o TudoIA usa o realm `tudoia`, criado por `tudoia keycloak` a partir de `infra/keycloak/realm-tudoia.json`. | tenant |
| Token estático | Segredo sem expiração (`CEREBRO_TOKEN_ESTATICO`, mínimo de 32 caracteres) que os clientes MCP locais mandam ao Cérebro, com papel de operador. | chave de API do Cérebro |

## 🐳 Execução e configuração

| Termo | Definição | Evitar |
|---|---|---|
| `.env` | Arquivo único de configuração e de segredos na raiz do repositório; ignorado pelo git. O modelo versionado é o `.env.example`. | arquivo de ambiente |
| Perfil de compose | Grupo opcional de serviços do `docker-compose.yml` ligado por `COMPOSE_PROFILES`: `cerebro`, `webui`, `n8n`, `keycloak` e `squadti`. LiteLLM e Postgres sobem sempre. | profile (em texto corrido) |
| Projeto compose | Prefixo dos volumes e dos recursos do Docker, `tudoia` por padrão, trocado por `TUDOIA_COMPOSE_PROJETO` para isolar instalações. | namespace |
| Segredo interno | Valor que o TudoIA gera sozinho no `.env` quando está vazio (`tudoia segredos`), como `LITELLM_MASTER_KEY` e `TUDOIA_SESSAO_SEGREDO`. | senha automática |

## 🤝 Ecossistema TEC

| Termo | Definição | Evitar |
|---|---|---|
| Doutrina | A Doutrina TEC: o conjunto de regras de engenharia da Tudo em Código, em repositório próprio. O TudoIA a consome por `DOUTRINA_TEC` (skill, MCP `doutrina-tec` e SquadTI) e fixa o commit usado em `governanca/doutrina.json`. | padrão TEC (em texto corrido), guia de estilo |
| Doutrina fixada | O par repositório e commit (`sha`) registrado em `governanca/doutrina.json`; o Dockerfile da SquadTI e o compose repetem esse commit e o painel mostra se divergem. | pin (em texto corrido) |
| TEC.* | As bibliotecas .NET da Tudo em Código; a SquadTI gera projetos que as usam, a partir de um feed NuGet opcional. | libs TEC |

---

[🏠 README](../README.md) · [📚 Documentação](README.md) · ⬅️ [Índice](README.md) · [Arquitetura](arquitetura.md) ➡️

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
- [🤖 SquadTI](#-squadti)
- [🔐 Identidade e acesso](#-identidade-e-acesso)
- [🐳 Execução e configuração](#-execução-e-configuração)
- [🤝 Ecossistema TEC](#-ecossistema-tec)

Dentro de cada seção os termos seguem a ordem alfabética.

---

## 🧩 Produto e componentes

| Termo | Definição | Evitar |
|---|---|---|
| Automação | Os fluxos do n8n versionados em `automacao/n8n/` (resumo de documentos, pesquisa, digest de notícias e ingestão no Cérebro). | workflow solto, robô |
| Backup | Cópia datada em `dados\backups\<AAAAMMDD-HHMMSS>\` do Postgres do LiteLLM (`litellm-db.sql.gz`), do `cerebro.db` e dos volumes do n8n e do Open WebUI, com manifesto de sha256; o `.env` e o banco do Keycloak não entram (`scripts/backup/backup.py`). | snapshot |
| Cérebro | Servidor MCP local (`runtime/cerebro/`) com busca na web, leitura de páginas, busca nos documentos indexados e memória de fatos. | Cerebro (sem acento) em texto corrido, memória |
| Ecossistema | O que `scripts\parar.ps1` desliga e `iniciar.ps1` liga: painel, SquadTI, serviços Docker de qualquer perfil, Ollama e ComfyUI. `reiniciar.ps1` sem `-Tudo` reinicia só o painel (e a SquadTI, se estava ligada). | stack inteira |
| Estúdio | Parte do painel que gera imagens, vídeos e músicas pelo ComfyUI ou por provedores de nuvem (`rotas/estudio_*.py`). | Studio (só no nome de `scripts/studio`) |
| Instalador | `TudoIA-Setup.exe`, assistente do Windows que prepara a máquina e instala o TudoIA (`instalador/`, `scripts/empacotar/`). | setup, wizard |
| Painel | Interface web e API de controle (FastAPI e SPA, `painel/`), em `http://127.0.0.1:3100/app/`. | dashboard, console |
| Payload | Zip reproduzível com o código do repositório e o instantâneo da Doutrina (pasta `doutrina/`) que o instalador carrega (`instalador/dados/payload.zip`, manifesto em `payload.manifest.json`). | pacote do instalador |
| Serviço do host | Processo do Windows fora do Docker, por causa da GPU: Ollama (porta 11434) e ComfyUI (porta 8188). | serviço nativo |
| SquadTI | Equipe de agentes (LangGraph) que gera projetos novos seguindo a Doutrina; roda no container `squadti` (porta 8790) e aparece no menu SquadTI do painel. Os termos dela estão na seção [SquadTI](#-squadti). | Squad (só em texto corrido, depois de definida), esquadrão |
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

## 🤖 SquadTI

Os termos abaixo valem para `runtime/squadti/` e para o menu SquadTI do painel. A API e o fluxo estão em [SquadTI (componente)](componentes/squadti.md).

| Termo | Definição | Evitar |
|---|---|---|
| Aprovação humana | Decisão explícita do usuário amarrada ao conteúdo aprovado (`aprovacao.py`): vale para a especificação (`BUSINESS_SPEC`, antes da arquitetura) e para o pacote do release; se o arquivo muda depois, a aprovação deixa de valer. | OK automático |
| Briefing | A demanda que o usuário entrega ao CHEFE para iniciar uma tarefa; é dado, nunca instrução. | prompt |
| Caso dourado | Briefing sintético com respostas fixas, limites e verificadores, em `runtime/squadti/evals/casos/*.json` (`a-crud-tarefas`, `b-catalogo`, `c-autenticada`, `d-pedidos`). | teste de aceitação |
| Carga | Agente de DevOps/SRE que sobe usuários simultâneos em degraus (k6) até violar o SLO e aponta o gargalo; o número é capacidade relativa ao teto de CPU do sandbox, não de produção (`carga.py`). | teste de performance de produção |
| CHEFE | Tech Lead e orquestrador da SquadTI (`chefe.py`): único canal entre o usuário e os demais agentes; planeja, confere os critérios de pronto entre as fases e escreve o relatório de escalada. | gerente, coordenador |
| Cockpit | A tela da tarefa no painel (`static/squadti.js`): trilha dos nós, orçamento, log ao vivo, auditoria e conversa com o CHEFE. | dashboard |
| Escalada | Parada que exige decisão humana: limite de três passagens de QA ou revisão, estagnação, orçamento esgotado, critério de pronto não atendido ou saída de modelo inválida. O CHEFE escreve `docs/chefe/ESCALADA.md`. | erro, falha |
| Estagnação | A mesma falha duas vezes seguidas (mesma assinatura de erro): é tratada como loop sem progresso e escala antes de gastar o resto das tentativas (`auditoria.py`). | travamento |
| Eval | Execução de um caso dourado com modelo real, pela API HTTP, conferida por verificadores em código; mede se a Squad entrega código bom. Roda por `python -m evals.run`, consome tokens e não faz parte do `pytest`. Ver [evals](squadti/evals.md). | benchmark, teste unitário |
| Hacker | Agente de AppSec em execução: ataca o sistema gerado, já rodando no sandbox, com o kit de ataque (autenticação, injeção, vazamento de erro, CORS, atribuição em massa, limites, cabeçalhos). | pentest |
| Kit | Script determinístico, só biblioteca padrão e semente fixa, copiado para um container na rede do sandbox: `kit_api.py` (modos `ataque` e `macaco`) e `kit_ui.py` (macaco de interface, com Playwright). Cada achado traz um ID (`AUTH-01`, `INJ-01`, `IDOR-01`, `MAC-01`...) e o comando de reprodução. | scanner |
| Livro de Lições | Arquivo JSONL (`SQUADTI_LICOES_ARQUIVO`, padrão `licoes.jsonl`) em que os achados dos agentes viram lições com triagem de destino e aprovação humana (`licoes.py`). É uma API pura e **ainda não está ligada ao grafo, à API HTTP nem ao painel**. Ver [licoes](squadti/licoes.md). | base de conhecimento, memória |
| Macaco | Agente de QA em execução: usa o sistema à força, com entrada errada de todo jeito, texto hostil, JSON malformado e, se há tela, cliques e digitação aleatórios. | fuzzer (só no sentido genérico) |
| Mantenedor | Último portão antes do release (`qualidade.py`, "eu daqui a 1 ano"): lê o projeto como quem vai mantê-lo; se não se orienta, devolve à documentação (duas voltas, depois escala). | revisor de docs |
| Orçamento | Teto da tarefa em `tokens` (padrão 2.000.000), `tempo_s` (7200) e `chamadas` (300), editável no painel (`agentes.py`); estourou, a execução para e escala. `null` em um eixo é sem limite. | quota, cota |
| Papel | Função de um agente na Squad (requisitos, arquiteto, dba, backend, frontend, revisor...). Cada papel carrega o núcleo e as regras das famílias do perfil dele na Doutrina; sem perfil o papel não trabalha. | persona |
| Perfil (da SquadTI) | Destino do modelo da tarefa: `local-estrito` (padrão, nunca sai da máquina), `local`, `hibrido`, `nuvem` e `max`. `hibrido`, `nuvem` e `max` exigem `consentimento_nuvem`; o `tudoia-auto` é recusado. | modo |
| Portão | Verificação que bloqueia a fase seguinte: QA, revisor, Sênior Master, AppSec, validação em execução, DevOps, Mantenedor e as duas aprovações humanas. Nenhum nó aprova por omissão. | gate (em texto corrido) |
| Proveniência | `docs/proveniencia.json` da entrega: versão e hash da Doutrina, modelo e hash do prompt de cada chamada, tokens, tempo, hashes das aprovações e de cada arquivo gerado. Não contém prompt, resposta nem segredo (`proveniencia.py`). | log de auditoria (a auditoria é o registro por nó, no estado da tarefa) |
| Sandbox | Rede interna do Docker (`--internal`, sem rota para a internet nem porta publicada) onde o sistema gerado e o banco dele sobem para serem atacados, estressados e usados à força, com teto de CPU e memória, sem capabilities e desmontados sempre (`sandbox.py`). Com a validação em `auto` e sem Docker respondendo, a fase é pulada com o motivo registrado. | ambiente de teste |
| Sênior Master | Portão de qualidade de código dentro do desenvolvimento (`qualidade.py`): mede complexidade, função longa, duplicação, API pública sem documentação e gambiarras (IDs `QC-*`) e pede ao modelo a crítica dos pontos suspeitos; só bloqueia o que dá para conferir. Três voltas, depois escala. | linter |
| Stack | Adaptador de tecnologia do backend (`stacks.py`): `dotnet` (padrão) ou `python`. Define os comandos de build, teste e auditoria, as áreas onde cada papel escreve e as famílias da Doutrina que não se aplicam. O CHEFE grava o `stack_id`. Não confundir com perfil de compose. | tecnologia, linguagem |
| Tarefa | Uma conversa da Squad a partir de um briefing, com checkpoint em SQLite e `workspace/<tarefa>` no volume `squadti-dados`. A API executa uma por vez. | job, ticket |
| Validação em execução | Fase em que o sistema gerado roda no sandbox e Macaco, Hacker e Carga tentam quebrá-lo (`validacao.py`); modos `auto`, `sempre` e `nunca`. | teste de integração |
| Verificador | Função pura `(workspace, api, caso)` dos evals que confere um resultado e falha fechado: relatório ausente ou adulterado reprova (`evals/verificadores.py`). | assert |
| Workspace da tarefa | Pasta `workspace/<tarefa>` no volume da SquadTI onde o projeto gerado nasce. Diferente do workspace da governança (raiz de projeto do usuário). | workspace (sozinho) |

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
| Perfil de compose | Grupo opcional de serviços do `docker-compose.yml` ligado por `COMPOSE_PROFILES`: `cerebro`, `webui`, `n8n`, `keycloak` e `squadti`. `litellm-db` e `litellm` sobem sempre; o `keycloak-db` sobe com o perfil `keycloak`. | profile (em texto corrido) |
| Projeto compose | Prefixo dos volumes e dos recursos do Docker, `tudoia` por padrão, trocado por `TUDOIA_COMPOSE_PROJETO` para isolar instalações. | namespace |
| Segredo interno | Valor que o TudoIA gera sozinho no `.env` quando está vazio (`tudoia segredos`), como `LITELLM_MASTER_KEY` e `TUDOIA_SESSAO_SEGREDO`. | senha automática |

## 🤝 Ecossistema TEC

| Termo | Definição | Evitar |
|---|---|---|
| Doutrina | A Doutrina TEC: o conjunto de regras de engenharia da Tudo em Código, em repositório próprio. O TudoIA a consome por `DOUTRINA_TEC` (skill, MCP `doutrina-tec` e SquadTI) e fixa o commit usado em `governanca/doutrina.json`. | padrão TEC (em texto corrido), guia de estilo |
| Doutrina fixada | O par repositório e commit (`sha`, 40 caracteres) registrado em `governanca/doutrina.json`; o Dockerfile da SquadTI e o compose repetem esse commit e o painel mostra se divergem. O empacotador leva um instantâneo dela no payload e o instalador baixa a mesma versão quando o código vem do GitHub. | pin (em texto corrido) |
| Falha fechada | Sem a condição de segurança (Doutrina ilegível, login não configurado, nuvem sem consentimento) o componente se recusa a agir em vez de seguir sem proteção. | fail-open, degradar em silêncio |
| TEC.* | As bibliotecas .NET da Tudo em Código; a SquadTI gera projetos que as usam, a partir de um feed NuGet opcional. | libs TEC |

---

[🏠 README](../README.md) · [📚 Documentação](README.md) · ⬅️ [Índice](README.md) · [Arquitetura](arquitetura.md) ➡️

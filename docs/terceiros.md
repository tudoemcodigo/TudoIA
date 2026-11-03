---
titulo: Componentes de terceiros e licenças
tipo: referencia
dono: TudoIA (mantenedor do repositório)
status: vigente
classificacao: publico
verificado-em: 2026-11-03
---

[🏠 TudoIA](../README.md) › [📚 Documentação](README.md) › 📜 Terceiros

# 📜 Componentes de terceiros e licenças

> Para quem usa, redistribui ou audita o TudoIA: o que vem de terceiros, de onde, em que versão e sob qual licença, e quais dados saem da máquina para serviços externos. Onde a licença não pôde ser conferida nos arquivos disponíveis, está escrito **a confirmar**; nenhuma licença foi inferida de memória.

## 📑 Sumário

- [🎯 Visão geral](#-visão-geral)
- [🧠 Skills de governança](#-skills-de-governança)
- [🔌 Servidores MCP do catálogo](#-servidores-mcp-do-catálogo)
- [🐍 Dependências Python](#-dependências-python)
- [🐳 Imagens Docker](#-imagens-docker)
- [🖥️ Processos do host e ferramentas locais](#️-processos-do-host-e-ferramentas-locais)
- [🧬 Pesos de modelos de IA](#-pesos-de-modelos-de-ia)
- [🌐 Serviços externos chamados pelo código](#-serviços-externos-chamados-pelo-código)
- [🎨 Ícones do painel](#-ícones-do-painel)
- [❓ Perguntas frequentes](#-perguntas-frequentes)

---

## 🎯 Visão geral

O TudoIA é licenciado sob a **Apache License 2.0** (`LICENSE`, com o aviso em `NOTICE`). Os itens abaixo mantêm as licenças próprias. O repositório não redistribui imagens Docker, pesos de modelos, Ollama nem ComfyUI: cada máquina os baixa.

Como esta página foi conferida em 2026-11-03:

| Seção | Fonte da conferência |
|---|---|
| Skills | `governanca/ORIGEM.md`, `governanca/governanca.json`, arquivos `LICENSE*` das pastas |
| Servidores MCP | `governanca/mcp.json` e `governanca/ORIGEM.md` |
| Dependências Python | versões: `uv.lock` de cada projeto; licenças: `METADATA` das distribuições instaladas nos `.venv` desta máquina |
| Imagens Docker | `runtime/docker-compose.yml` e os `Dockerfile` |
| ComfyUI e nós | cópia local em `modelos\ComfyUI\` (fora do git) |
| Pesos | `config/modelos.yaml` |

## 🧠 Skills de governança

As 23 skills de `governanca/skills/` estão listadas em `governanca/governanca.json`. A origem de cada uma é registrada em `governanca/ORIGEM.md`, que também descreve as adaptações. A licença MIT das cópias de `addyosmani/agent-skills` está em `governanca/LICENSE-agent-skills` (Copyright (c) 2025 Addy Osmani); os `SKILL.md` não repetem o aviso, a atribuição vale pelo `ORIGEM.md` e pelo arquivo de licença.

| Skill | Origem (commit) | Licença | Adaptada |
|---|---|---|---|
| `using-agent-skills`, `spec-driven-development`, `planning-and-task-breakdown`, `incremental-implementation`, `debugging-and-error-recovery`, `code-review-and-quality`, `security-and-hardening`, `git-workflow-and-versioning` | `addyosmani/agent-skills`, commit `aeac41d4`, copiadas em 22/10/2026 | MIT (`LICENSE-agent-skills`) | Sim, notas de precedência da Doutrina (2026-11-01) |
| `observability-and-instrumentation` | `addyosmani/agent-skills`, `fe6f0811` | MIT (`LICENSE-agent-skills`) | Sim |
| `documentation-and-adrs` | `addyosmani/agent-skills`, `30f88627` | MIT (`LICENSE-agent-skills`) | Não |
| `mcp-builder` | `anthropics/skills`, `ef740771` | Apache-2.0 (`LICENSE.txt` na pasta) | Sim |
| `frontend-design` | Anthropic (commit não registrado no `ORIGEM.md`) | Apache-2.0 (`LICENSE.txt` na pasta) | Não registrado |
| `dotnet-aot-compat` | `dotnet/skills`, `05aeb657` | MIT (`LICENSE.txt` na pasta) | Sim |
| `security-threat-model` | `openai/skills`, `5c8f1e26` | Apache-2.0 (`LICENSE.txt` na pasta) | Sim |
| `advanced-evaluation` | `muratcankoylan/Agent-Skills-for-Context-Engineering`, `8fc51c7c` | MIT (`LICENSE.txt` na pasta) | Sim |
| `n8n-expression-syntax` | `czlonkowski/n8n-skills`, `2fb619a8` | MIT (`LICENSE.txt` na pasta) | Sim |
| `humanize-text`, `lgpd-compliance` | Criação própria do autor do TudoIA (a segunda cita referências no `ORIGEM.md`) | Apache-2.0, licença do projeto | Não se aplica |
| `doutrina-tec` | Criação própria do ecossistema TEC (repositório Doutrina), copiada em 01/11/2026 e atualizada em 02/11/2026 | Apache-2.0 (licença do repositório Doutrina, segundo o `ORIGEM.md`) | Sim |
| `disciplined-tdd`, `grill-me`, `improve-codebase-architecture` | Conteúdo próprio ("canônico TudoIA") | O `ORIGEM.md` não declara; presume-se a do projeto. **A confirmar** | Sim (as duas últimas) |
| `microsoft-docs` | O `ORIGEM.md` diz que a origem e a licença **ainda não foram registradas** | **A confirmar** antes da próxima atualização | Sim |

O conteúdo das skills é texto de terceiros e deve ser lido por inteiro antes de cada atualização, como o `ORIGEM.md` exige (IA-FER-01).

## 🔌 Servidores MCP do catálogo

`governanca/mcp.json` lista os servidores; só os ids de `mcp[]` em `governanca.json` ficam ativos. Os pacotes `npx` estão fixados em versão. A triagem estática (sem executar nada) de 2026-11-02 está em `governanca/ORIGEM.md` e **não equivale à leitura integral** (IA-FER-01 segue pendente).

| Servidor | Pacote ou endpoint fixado | Ativo | Observação do `ORIGEM.md` |
|---|---|---|---|
| `context7` | `@upstash/context7-mcp@4.4.4` | sim | MIT; envia a consulta de biblioteca a `context7.com`: não coloque código proprietário nem segredo nela. Sem proveniência npm. |
| `playwright` | `@playwright/mcp@0.0.84` | sim | Apache-2.0; nenhum host externo embutido. |
| `sequential-thinking` | `@modelcontextprotocol/server-sequential-thinking@2.0.0` | sim | Licença declarada "SEE LICENSE IN LICENSE" e o tarball não traz o arquivo; o repositório de origem declara a transição de MIT para Apache-2.0. Conferir antes de atualizar. |
| `fetch` | `@tokenizin/mcp-npx-fetch@1.0.0` | sim | MIT; busca a URL pedida pelo modelo: trate o conteúdo como dado não confiável. Sem proveniência npm. |
| `microsoft-learn` | `mcp-remote@0.16.0` apontando para `learn.microsoft.com/api/mcp` | sim | O único `child_process` é o abridor de navegador do fluxo OAuth. |
| `vercel` | `https://mcp.vercel.com` (HTTP, OAuth) | sim | Serviço remoto; termos não verificados. |
| `serena` | Executável `serena` do host (`serena-agent`, instalado por `uv tool`) | sim | Aplicação GNU GPL v3 ou posterior, biblioteca SolidLSP em MIT (segundo o repositório `oraios/serena`, conferido em 27/10/2026). Versão `2.1.0` herdada do documento anterior, não reconferida. Não redistribuído. |
| `cerebro` | `http://127.0.0.1:8765/mcp` | sim | Próprio (ver [Cérebro](componentes/cerebro.md)). |
| `doutrina-tec` | `${DOUTRINA_TEC}/tools/mcp_doutrina.py` | sim | Doutrina TEC (Apache-2.0); ver [Doutrina](componentes/doutrina.md). |
| `github` | `https://api.githubcopilot.com/mcp/` (servidor remoto oficial) | não | Substitui o `@modelcontextprotocol/server-github`, depreciado no npm. |
| `supabase` | `@supabase/mcp-server-supabase@0.15.0` com `--read-only` | não | Traz uma ferramenta de feedback que envia texto à Supabase; com `--read-only` ela recusa. Não retire a opção sem desligar o grupo `feedback`. |

O `@wonderwhy-er/desktop-commander` foi **removido** do catálogo por enviar telemetria de instalação sem respeitar o opt-out (decisão do dono em 2026-11-02).

## 🐍 Dependências Python

Só as dependências diretas declaradas em cada `pyproject.toml`. Versões do `uv.lock`; licenças lidas do `METADATA` instalado. Quando o campo de licença está vazio, vale o classificador `License :: OSI Approved`. As transitivas não estão listadas: para auditar o conjunto completo, leia os `METADATA` de cada ambiente.

### Projeto raiz (`pyproject.toml`)

| Componente | Versão | Licença |
|---|---|---|
| fastapi | 0.162.0 | MIT |
| uvicorn | 0.54.0 | BSD-3-Clause |
| jinja2 | 3.1.6 | BSD (classificador) |
| pyyaml | 6.0.3 | MIT |
| httpx | 0.28.1 | BSD-3-Clause |
| psutil | 7.2.2 | BSD-3-Clause |
| authlib | 1.9.1 | BSD-3-Clause |
| joserfc | 1.7.7 | BSD-3-Clause |
| itsdangerous | 2.2.0 | BSD (classificador) |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause |
| pytest (grupo `dev`) | 9.1.1 | MIT |
| ruff (grupo `dev`) | 0.17.3 | MIT |
| playwright (grupo `capturas`) | 1.64.1 | **A confirmar** (grupo não instalado nesta máquina) |

### Cérebro (`runtime/cerebro/pyproject.toml`)

| Componente | Versão | Licença |
|---|---|---|
| mcp | 2.3.0 | MIT |
| httpx | 0.28.1 | BSD-3-Clause |
| numpy | 2.5.4 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| trafilatura | 2.3.1 | Apache-2.0 |
| pypdf | 6.21.2 | BSD-3-Clause |
| python-docx | 1.2.0 | MIT |
| pyyaml | 6.0.3 | MIT |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause |
| joserfc | 1.7.7 | BSD-3-Clause |
| pytest (grupo `dev`) | 9.1.1 | MIT |
| pytest-asyncio (grupo `dev`) | 1.4.0 | Apache-2.0 |

### SquadTI (`runtime/squadti/pyproject.toml`)

| Componente | Versão | Licença |
|---|---|---|
| langgraph | 1.2.19 | MIT |
| langgraph-checkpoint-sqlite | 3.1.3 | MIT |
| langchain-core | 1.7.4 | MIT |
| langchain-openai | 1.7.3 | MIT |
| pytest (grupo `dev`) | 9.2.0 | MIT |

### Ferramentas de build

| Componente | Versão | Licença | Onde |
|---|---|---|---|
| uv | 0.13.0 | **A confirmar** | `ci.yml`, `release.yml`, `Dockerfile` do Cérebro e da SquadTI |
| PyInstaller | 6.22.3 | **A confirmar** | `scripts/empacotar/construir.py` (baixado pelo `uv run --with`) |
| Actions `checkout@v4`, `setup-python@v5`, `setup-node@v4`, `attest-build-provenance@v2` | tags | **A confirmar** | `.github/workflows/` |

## 🐳 Imagens Docker

Os digests completos estão em `runtime/docker-compose.yml` e nos `Dockerfile`. As licenças das imagens **não foram verificadas** nesta página, exceto onde indicado na tabela seguinte.

| Serviço | Imagem (tag) |
|---|---|
| `litellm-db` | `postgres:17.6-alpine` |
| `keycloak-db` | `postgres:17-alpine` |
| `litellm` | `ghcr.io/berriai/litellm:main-latest` |
| `searxng` | `searxng/searxng:2026.10.19-81371861f` |
| `cerebro` (construída aqui) | Base `python:3.12-slim` (sem digest) e `ghcr.io/astral-sh/uv:0.13.0` (sem digest) |
| `kokoro` | `ghcr.io/remsky/kokoro-fastapi-cpu:v0.9.0` |
| `open-webui` | `ghcr.io/open-webui/open-webui:main` |
| `n8n` | `docker.n8n.io/n8nio/n8n:latest` |
| `keycloak` | `quay.io/keycloak/keycloak:26.3` |
| `squadti` (construída aqui) | Bases `alpine/git:2.49.1`, `node:24-slim`, `ghcr.io/astral-sh/uv:0.13.0` e `mcr.microsoft.com/dotnet/sdk:10.0` (todas por digest); clona a Doutrina de `github.com/tudoemcodigo/Doutrina` no commit fixado |

### Imagens que a SquadTI sobe no sandbox

O sandbox de validação (`runtime/squadti/orquestrador/sandbox.py`) cria, por tarefa, containers irmãos pelo `docker.sock` do host. As imagens são fixadas por digest no código; as licenças **não foram verificadas** nesta página.

| Uso | Imagem (tag) | Onde está fixada |
|---|---|---|
| Sonda HTTP e kit de ataque e macaco de API (`kit_api.py`) | `python:3.12-slim` | `IMAGEM_PYTHON` |
| Teste de carga | `grafana/k6` (sem tag, só digest) | `IMAGEM_K6` |
| Macaco de interface (`kit_ui.py`, com Playwright) | `mcr.microsoft.com/playwright/python` (sem tag, só digest) | `IMAGEM_PLAYWRIGHT` |
| Banco do sistema gerado | `postgres:17-alpine` (digest diferente do `keycloak-db`) | `IMAGENS_BANCO` |

A imagem do sistema gerado (`squadti-sut-<tarefa>`) é construída da pasta do projeto que o modelo escreveu e removida ao fim. Os comandos de auditoria rodam dentro do container da SquadTI e baixam ferramentas na hora: `dotnet list package --vulnerable`, `npm audit` e, na stack `python`, `uv run --with pip-audit pip-audit` (a versão do `pip-audit` não é fixada pelo TudoIA). Os testes de integração dos projetos gerados (Testcontainers, segundo o comentário do compose) baixam as imagens que o próprio projeto declarar; o TudoIA não as controla.

### Open WebUI

| Componente | Versão | Licença |
|---|---|---|
| Open WebUI | `0.12.3`, lida de `/app/package.json` da imagem com o digest `4860ba00…` fixado no compose (leitura do documento anterior, mesmo digest; não repetida) | **A confirmar.** A imagem traz `/app/build/BRANDING.md`, que diz que o branding não pode ser alterado nem removido "exceto como permitido pela LICENSE", e manda consultar `docs.openwebui.com/license`. O arquivo `LICENSE` não está na imagem e o link não foi consultado. |

> [!WARNING]
> O TudoIA substitui o branding do Open WebUI: troca o nome (`WEBUI_NAME=TudoIA`), o favicon e as nove imagens de `/app/build/static/` (ver [serviços Docker](componentes/servicos-docker.md)). O cabeçalho do `env.py` upstream diz que o branding "não pode ser alterado exceto como a LICENSE permite". Se a licença do Open WebUI não permite a troca, o uso precisa de revisão antes de qualquer distribuição. É uma questão de licença a confirmar pelo dono do projeto, não uma conclusão.

Os nove arquivos de `runtime/open-webui/static/` não são os originais da imagem (hash diferente). Não há como verificar pelo repositório quem os produziu: origem **a confirmar**; a semelhança com o painel sugere que foram gerados para o TudoIA. O `runtime/open-webui/env.py` é cópia do upstream; `tudoia verificar-openwebui` confere o diff aprovado (`env.py.aprovado.diff`).

### SearXNG

| Componente | Versão | Licença |
|---|---|---|
| SearXNG | tag `2026.10.19`, com digest fixado | **A confirmar.** O cabeçalho de `runtime/searxng/settings.yml` não declara licença e não há arquivo de licença na imagem na profundidade verificada. |

## 🖥️ Processos do host e ferramentas locais

| Componente | Versão | Licença | Onde |
|---|---|---|---|
| ComfyUI | `0.43.0` (`pyproject.toml` da cópia local) | GNU GPL v3 (texto em `LICENSE` da pasta) | `modelos\ComfyUI\ComfyUI\`, fora do git |
| ComfyUI-GGUF (nó) | `2.0.0` | Apache License 2.0 (`LICENSE` da pasta) | `custom_nodes\ComfyUI-GGUF\` |
| Nós YuE 2, MiniMax H3 e TextGen | A confirmar | **A confirmar** (estão em `comfy_extras\`, dentro da árvore do ComfyUI; não reverificados) | `modelos\ComfyUI\ComfyUI\comfy_extras\` |
| Ollama | `0.40.13` (`ollama --version`) | **A confirmar** | Host; não redistribuído |
| Docker (CLI e engine) | `29.9.2` (`docker --version`) | **A confirmar** | Host; o instalador instala o Docker Desktop quando falta |

O caminho do ComfyUI nesta máquina é `modelos\ComfyUI\`, diferente do padrão de código (`modelos\comfyui\ComfyUI_windows_portable`, ver [configuração](configuracao.md#-caminhos)); a variável `TUDOIA_COMFYUI_PORTABLE` resolve a diferença.

## 🧬 Pesos de modelos de IA

Os pesos não estão no repositório; cada máquina baixa os seus com [modelos](componentes/modelos.md). Em `config/modelos.yaml` há **36 modelos**; o campo `licenca.nome` está preenchido em 19 e **nulo (licença não confirmada)** em 17:

| `licenca.nome` | Modelos |
|---|---|
| `Apache-2.0` | 18 |
| `CreativeML Open RAIL++-M` | 1 |
| nulo (não confirmada) | 17 |

O campo `url` de cada entrada aponta a página do modelo, onde a licença deve ser conferida. Antes de usar um modelo fora de uso pessoal, confirme a licença na fonte; os nomes acima são a anotação do manifesto, não uma verificação feita nesta página.

## 🌐 Serviços externos chamados pelo código

Não são redistribuídos. Listados porque recebem dados do TudoIA. Os termos de uso de cada um não foram verificados nesta página.

| Serviço | Para que é usado | Dados enviados | Onde está no código |
|---|---|---|---|
| Groq | Otimização de prompt (imagem, vídeo e música), quando `GROQ_API_KEY` existe | Texto do prompt | `painel/tudoia_painel/estudio_servico.py` |
| Cloudflare Workers AI | Geração de imagem, quando as chaves `CLOUDFLARE_*` existem | Texto do prompt | `painel/tudoia_painel/rotas/estudio_imagem.py` |
| Pollinations | Geração de imagem sem chave (reserva), só com `TUDOIA_ESTUDIO_POLLINATIONS=1` (desligado por padrão) | Texto do prompt, na URL | `painel/tudoia_painel/rotas/estudio_imagem.py` |
| Provedores de modelo de texto | Chat pelo gateway e teste de conexão do menu Cofre de Segredos | O conteúdo do pedido, conforme o grupo escolhido pelo roteador | Configurados no LiteLLM; ver [roteador](componentes/roteador.md) |
| GitHub | Importação de skill por URL (lista branca `REPO_GITHUB`); clone da Doutrina no build da SquadTI; MCP remoto `github` (inativo) | URL do repositório; sem dado do usuário | `painel/tudoia_painel/skills_servico.py`, `runtime/squadti/Dockerfile` |
| Hugging Face e registro do Ollama | Download de pesos de modelos (baixador e `ollama pull` pelo painel) | Nome do arquivo ou modelo; `HF_TOKEN` nos downloads do Hugging Face quando existe | `scripts/modelos/baixar.py`, `painel/tudoia_painel/modelos_service.py` |
| Feed RSS do G1 (tecnologia) | Digest de notícias (n8n) | Nenhum dado do usuário, só a requisição de leitura | `automacao/n8n/03-digest-noticias.json` |
| nuget.org, feed público das TEC.* (`TUDOIA_NUGET_FEED_URL`) e GitHub Packages (`tec-interno`) | Restauração de pacotes dos projetos .NET que a SquadTI gera; o `tec-interno` só com `TUDOIA_NUGET_USER` e `TUDOIA_NUGET_PAT` por variável de ambiente | Nome e versão dos pacotes; o PAT vai só como referência `%TUDOIA_NUGET_PAT%` no `NuGet.Config`, nunca em disco | `runtime/squadti/entrypoint.sh` |
| npm e PyPI (pela SquadTI) | comandos `npm` do frontend gerado e `npm audit`; `uv sync` e `pip-audit` na stack `python` | Nome e versão dos pacotes | `runtime/squadti/orquestrador/stacks.py` |
| npm (`npx`) | Execução dos servidores MCP fixados | Nome e versão do pacote | `governanca/mcp.json` |

Os provedores de modelo de texto (OpenAI, Anthropic, NVIDIA NIM, OpenRouter, Gemini, DeepSeek, xAI e outros) são configurados no LiteLLM; os nomes das chaves estão em `.env.example` e em [configuração](configuracao.md).

## 🎨 Ícones do painel

| Componente | Versão | Licença | Onde |
|---|---|---|---|
| Lucide (só o desenho dos ícones, sem o pacote) | `lucide-static` 1.64.0, baixado de unpkg em 30/10/2026 (dado herdado do documento anterior) | ISC (Copyright (c) 2026 Lucide Icons and Contributors) | Mapa `ICONES` em `painel/tudoia_painel/static/painel.js` |

Só os elementos de desenho (`path`, `circle`, `rect` etc.) foram copiados para o mapa, depois de conferidos: nenhum script, nenhuma URL. Para incluir um ícone, baixe o SVG da mesma versão numa pasta temporária, confira que só há elementos de desenho e acrescente a entrada no mapa.

## ❓ Perguntas frequentes

**Posso redistribuir o TudoIA?** O código do repositório é Apache-2.0. Antes de redistribuir uma instalação inteira, resolva os itens marcados **A confirmar** (branding do Open WebUI, licença de modelos e de imagens), porque eles não são do repositório.

**Como registro um componente novo?** Acrescente a linha na tabela da seção certa, com versão e licença lidas da fonte (arquivo `LICENSE`, `METADATA` ou página do projeto), e escreva **a confirmar** quando não conseguir ler. Ver [desenvolvimento](desenvolvimento.md#-adicionar-um-componente).

---

[🏠 README](../README.md) · ⬅️ [Desenvolvimento](desenvolvimento.md) · [Instalação](instalacao.md) ➡️

# Componentes de terceiros e licenças

Este documento lista o que o TudoIA usa de terceiros e a licença de cada item, conforme verificado nos arquivos do repositório e da máquina de referência. Onde a licença não pôde ser verificada nos arquivos disponíveis, está escrito **a confirmar**. Nenhuma licença foi inferida de memória.

O projeto é licenciado sob a Apache License 2.0 (`LICENSE`, com o aviso em `NOTICE`). Os itens abaixo mantêm as licenças próprias.

## 1. Skills de governança (`governanca/skills/`)

A origem está em `governanca/ORIGEM.md`, que descreve as 22 skills desta pasta (14 originais e 8 adicionadas em 27/10/2026). O próprio arquivo é inconsistente: o título diz "As 10 skills desta pasta são cópias sem alteração de addyosmani/agent-skills", sem dizer quais são, e a tabela lista 14. Por isso a atribuição por skill abaixo é a que a tabela sugere, e precisa ser confirmada.

A tabela atribui três skills a um "protocolo canônico TudoHaS", uma à Anthropic (`frontend-design`) e marca `humanize-text` como criação própria do autor (não é cópia). As outras nove aparecem sem origem própria, dentro das "cópias" do título. A licença MIT só vale para as cópias de addyosmani, e o arquivo `LICENSE-agent-skills` é o texto dessa licença.

| Componente | Versão | Licença | Onde está no repositório |
|---|---|---|---|
| `code-review-and-quality` | commit `aeac41d4` de `addyosmani/agent-skills` (se for cópia; a confirmar) | MIT, se for cópia de addyosmani | `governanca/skills/code-review-and-quality/` |
| `debugging-and-error-recovery` | commit `aeac41d4` (a confirmar) | MIT, se for cópia de addyosmani | `governanca/skills/debugging-and-error-recovery/` |
| `git-workflow-and-versioning` | commit `aeac41d4` (a confirmar) | MIT, se for cópia de addyosmani | `governanca/skills/git-workflow-and-versioning/` |
| `incremental-implementation` | commit `aeac41d4` (a confirmar) | MIT, se for cópia de addyosmani | `governanca/skills/incremental-implementation/` |
| `microsoft-docs` | commit `aeac41d4` (a confirmar) | MIT, se for cópia de addyosmani | `governanca/skills/microsoft-docs/` |
| `planning-and-task-breakdown` | commit `aeac41d4` (a confirmar) | MIT, se for cópia de addyosmani | `governanca/skills/planning-and-task-breakdown/` |
| `security-and-hardening` (com `references/hardening-patterns.md`) | commit `aeac41d4` (a confirmar) | MIT, se for cópia de addyosmani | `governanca/skills/security-and-hardening/` |
| `spec-driven-development` | commit `aeac41d4` (a confirmar) | MIT, se for cópia de addyosmani | `governanca/skills/spec-driven-development/` |
| `using-agent-skills` | commit `aeac41d4` (a confirmar) | MIT, se for cópia de addyosmani | `governanca/skills/using-agent-skills/` |
| `disciplined-tdd` | a confirmar (`ORIGEM.md`: "canônico TudoHaS") | a confirmar | `governanca/skills/disciplined-tdd/` |
| `grill-me` | a confirmar (`ORIGEM.md`: "canônico TudoHaS") | a confirmar | `governanca/skills/grill-me/` |
| `improve-codebase-architecture` | a confirmar (`ORIGEM.md`: "canônico TudoHaS") | a confirmar | `governanca/skills/improve-codebase-architecture/` |
| `frontend-design` | a confirmar (`ORIGEM.md`: Anthropic) | Apache License 2.0 (`LICENSE.txt` na própria pasta; o `SKILL.md` diz "Complete terms in LICENSE.txt") | `governanca/skills/frontend-design/` |
| `humanize-text` | Criação própria do autor (não é cópia) | Apache License 2.0, licença do projeto (`LICENSE`) | `governanca/skills/humanize-text/` |
| `lgpd-compliance` | Criação própria (27/10/2026), com referências listadas em `ORIGEM.md` | Apache License 2.0, licença do projeto (`LICENSE`) | `governanca/skills/lgpd-compliance/` |
| `observability-and-instrumentation` | `addyosmani/agent-skills` commit `fe6f0811` | MIT (`governanca/LICENSE-agent-skills`) | `governanca/skills/observability-and-instrumentation/` |
| `documentation-and-adrs` | `addyosmani/agent-skills` commit `30f88627` | MIT (`governanca/LICENSE-agent-skills`) | `governanca/skills/documentation-and-adrs/` |
| `mcp-builder` | `anthropics/skills` commit `ef740771` | Apache License 2.0 (`LICENSE.txt` na pasta) | `governanca/skills/mcp-builder/` |
| `dotnet-aot-compat` | `dotnet/skills` commit `05aeb657` | MIT (`LICENSE.txt` na pasta) | `governanca/skills/dotnet-aot-compat/` |
| `security-threat-model` | `openai/skills` commit `5c8f1e26` | Apache License 2.0 (`LICENSE.txt` na pasta) | `governanca/skills/security-threat-model/` |
| `advanced-evaluation` | `muratcankoylan/Agent-Skills-for-Context-Engineering` commit `8fc51c7c` | MIT (`LICENSE.txt` na pasta) | `governanca/skills/advanced-evaluation/` |
| `n8n-expression-syntax` | `czlonkowski/n8n-skills` commit `2fb619a8` | MIT (`LICENSE.txt` na pasta) | `governanca/skills/n8n-expression-syntax/` |

As sete skills de outras origens foram baixadas da fonte original no commit indicado e lidas por inteiro em 27/10/2026. As adaptadas trazem um aviso no topo de cada arquivo alterado; as mudanças estão em `governanca/ORIGEM.md`.

Notas:

- A licença MIT das cópias de addyosmani está em `governanca/LICENSE-agent-skills` (Copyright (c) 2025 Addy Osmani). Os `SKILL.md` não trazem o aviso de copyright; a atribuição vale pelo `ORIGEM.md` e pelo arquivo de licença.
- As cópias não têm alteração, segundo o `ORIGEM.md`. O conteúdo é texto de terceiros e deve ser lido antes de cada atualização, como o próprio `ORIGEM.md` pede.

## 2. Open WebUI (imagem, `env.py` e ícones)

| Componente | Versão | Licença | Onde está no repositório |
|---|---|---|---|
| Open WebUI | `0.12.3`, lido de `/app/package.json` da imagem `ghcr.io/open-webui/open-webui:main@sha256:4860ba005ae8f19f08d1e12b0868855b7b339ea0dad9927f196820fc0de04575` | **a confirmar.** A imagem traz `/app/build/BRANDING.md`, que diz que o branding do Open WebUI não pode ser alterado nem removido "exceto como permitido pela LICENSE", e manda consultar `docs.openwebui.com/license`. O arquivo `LICENSE` em si não está na imagem, e o link não foi consultado nesta documentação. | compose (`open-webui`), `runtime/open-webui/env.py`, `runtime/open-webui/static/` |

**Ponto de atenção.** O TudoIA substitui o branding do Open WebUI: troca o nome padrão, o favicon e as nove imagens de `/app/build/static/` (ver [componentes/servicos-docker.md](componentes/servicos-docker.md)). O cabeçalho do `env.py` upstream diz que o branding "não pode ser alterado exceto como a LICENSE permite". Se a licença do Open WebUI não permite essa substituição, o uso precisa de revisão antes de qualquer distribuição. Isso é uma questão de licença a confirmar pelo dono do projeto, não uma conclusão.

Os nove arquivos de `runtime/open-webui/static/` não são os originais da imagem (hash diferente). Não há como verificar pelos arquivos do repositório quem os produziu. Origem **a confirmar**; a semelhança com o painel sugere que foram gerados para o TudoIA.

## 3. SearXNG

| Componente | Versão | Licença | Onde está no repositório |
|---|---|---|---|
| SearXNG (imagem `searxng/searxng:2026.10.19-81371861f`) | tag `2026.10.19`, com digest fixado | **a confirmar.** O cabeçalho de `runtime/searxng/settings.yml` não declara licença e não há arquivo de licença na imagem na profundidade verificada. | compose (`searxng`), `runtime/searxng/settings.yml` |

## 4. Imagens Docker usadas

Lista de nomes, sem licenças. Os digests completos estão em `runtime/docker-compose.yml`.

| Serviço | Imagem |
|---|---|
| `litellm-db` | `postgres:17.6-alpine` |
| `litellm` | `ghcr.io/berriai/litellm:main-latest` |
| `searxng` | `searxng/searxng:2026.10.19-81371861f` |
| `cerebro` (construída localmente) | base `python:3.12-slim` e `ghcr.io/astral-sh/uv:0.13.0` (ambas por tag, sem digest) |
| `kokoro` | `ghcr.io/remsky/kokoro-fastapi-cpu:v0.9.0` |
| `open-webui` | `ghcr.io/open-webui/open-webui:main` |
| `n8n` | `docker.n8n.io/n8nio/n8n:latest` |

## 5. Dependências Python

Versões e licenças lidas do `METADATA` das distribuições instaladas em `.venv\Lib\site-packages\` (projeto raiz) e em `runtime\cerebro\.venv\Lib\site-packages\` (Cérebro). Só as dependências diretas declaradas em `pyproject.toml`.

Quando o campo `License` do `METADATA` está vazio, a licença veio do classificador `License :: OSI Approved :: BSD License`, e aparece assim na tabela.

### Projeto raiz (`pyproject.toml`)

| Componente | Versão | Licença | Onde está no repositório |
|---|---|---|---|
| fastapi | 0.162.0 | MIT | `.venv/Lib/site-packages/fastapi-0.162.0.dist-info` |
| uvicorn | 0.54.0 | BSD-3-Clause | `.venv/Lib/site-packages/uvicorn-0.54.0.dist-info` |
| jinja2 | 3.1.6 | BSD (classificador) | `.venv/Lib/site-packages/jinja2-3.1.6.dist-info` |
| pyyaml | 6.0.3 | MIT | `.venv/Lib/site-packages/pyyaml-6.0.3.dist-info` |
| httpx | 0.28.1 | BSD-3-Clause | `.venv/Lib/site-packages/httpx-0.28.1.dist-info` |
| psutil | 7.2.2 | BSD-3-Clause | `.venv/Lib/site-packages/psutil-7.2.2.dist-info` |
| authlib | 1.9.1 | BSD-3-Clause | `.venv/Lib/site-packages/authlib-1.9.1.dist-info` |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause | `.venv/Lib/site-packages/cryptography-50.0.2.dist-info` |
| itsdangerous | 2.2.0 | BSD (classificador) | `.venv/Lib/site-packages/itsdangerous-2.2.0.dist-info` |
| pytest (grupo `dev`) | 9.1.1 | MIT | `.venv/Lib/site-packages/pytest-9.1.1.dist-info` |

### Cérebro (`runtime/cerebro/pyproject.toml`)

| Componente | Versão | Licença | Onde está no repositório |
|---|---|---|---|
| mcp | 2.3.0 | MIT | `runtime/cerebro/.venv/Lib/site-packages/mcp-2.3.0.dist-info` |
| httpx | 0.28.1 | BSD-3-Clause | `runtime/cerebro/.venv/Lib/site-packages/httpx-0.28.1.dist-info` |
| numpy | 2.5.4 | `BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0` | `runtime/cerebro/.venv/Lib/site-packages/numpy-2.5.4.dist-info` |
| trafilatura | 2.3.1 | Apache-2.0 | `runtime/cerebro/.venv/Lib/site-packages/trafilatura-2.3.1.dist-info` |
| pypdf | 6.21.2 | BSD-3-Clause | `runtime/cerebro/.venv/Lib/site-packages/pypdf-6.21.2.dist-info` |
| python-docx | 1.2.0 | MIT | `runtime/cerebro/.venv/Lib/site-packages/python_docx-1.2.0.dist-info` |
| pyyaml | 6.0.3 | MIT | `runtime/cerebro/.venv/Lib/site-packages/pyyaml-6.0.3.dist-info` |
| pytest (grupo `dev`) | 9.1.1 | MIT | `runtime/cerebro/.venv/Lib/site-packages/pytest-9.1.1.dist-info` |
| pytest-asyncio (grupo `dev`) | 1.4.0 | Apache-2.0 | `runtime/cerebro/.venv/Lib/site-packages/pytest_asyncio-1.4.0.dist-info` |

As dependências transitivas não estão listadas. Para auditar o conjunto completo, leia todos os `METADATA` dos dois ambientes.

## 6. Processos do host e ferramentas locais

| Componente | Versão | Licença | Onde está no repositório |
|---|---|---|---|
| ComfyUI | `0.39.0` (`pyproject.toml` e tag `v0.39.0` do git da cópia local) | GNU GPL v3 (texto em `LICENSE` da pasta) | `modelos/comfyui/ComfyUI_windows_portable/ComfyUI/` (fora do git) |
| ComfyUI-GGUF (custom node) | `2.0.0` (`pyproject.toml`) | Apache License 2.0 (`LICENSE` da pasta) | `modelos/comfyui/.../ComfyUI/custom_nodes/ComfyUI-GGUF/` (fora do git) |
| Nós YuE 2, MiniMax H3 e TextGen | a confirmar | a confirmar (estão em `comfy_extras/`, dentro da árvore do ComfyUI) | `modelos/comfyui/.../ComfyUI/comfy_extras/` |
| Ollama | a confirmar | a confirmar | host (não redistribuído) |
| Serena (servidor MCP de código) | `2.1.0` (`uv tool install -p 3.13 "serena-agent==2.1.0"`) | Aplicação: GNU GPL v3 ou posterior; biblioteca SolidLSP: MIT (arquivo `LICENSE` do repositório `oraios/serena`, conferido em 27/10/2026) | host, `~\.local\bin` (não redistribuído); entrada `serena` em `governanca/mcp.json` |

## 7. Pesos de modelos de IA

Os pesos não estão no repositório. Cada máquina baixa os seus, com [componentes/modelos.md](componentes/modelos.md).

Em `config/modelos.yaml`, todos os 39 modelos estão com o campo `licenca: {nome: null}`, o que quer dizer **licença não confirmada**. O campo `url` de cada entrada, quando existe, aponta a página do modelo, onde a licença deve ser conferida. Antes de usar um modelo fora de uso pessoal, confirme a licença. A seção 8 de [componentes/modelos.md](componentes/modelos.md) trata do tema.

## 8. Serviços externos chamados pelo código

Não são redistribuídos. Listados porque recebem dados do TudoIA. Os termos de uso de cada um não foram verificados nesta documentação.

| Serviço | Para que é usado | Dados enviados | Onde está no código |
|---|---|---|---|
| Groq | otimização de prompt (imagem, vídeo e música), quando `GROQ_API_KEY` existe | texto do prompt | `painel/tudoia_painel/estudio_servico.py` |
| Cloudflare Workers AI | geração de imagem, quando as chaves `CLOUDFLARE_*` existem | texto do prompt | `painel/tudoia_painel/rotas/estudio_imagem.py` |
| Pollinations | geração de imagem sem chave (fallback), só com `TUDOIA_ESTUDIO_POLLINATIONS=1` (desligado por padrão) | texto do prompt, na URL | `painel/tudoia_painel/rotas/estudio_imagem.py` |
| Feed RSS do G1 (tecnologia) | digest de notícias (n8n) | nenhum dado do usuário, só a requisição de leitura | `automacao/n8n/03-digest-noticias.json` |

Os provedores de modelo de texto (OpenAI, Anthropic, NVIDIA NIM, OpenRouter, Gemini, DeepSeek e outros) são configurados no LiteLLM. Os nomes das chaves estão em `.env.example`. A lista de provedores e os seus termos ficam fora do escopo desta página; consulte [componentes/roteador.md](componentes/roteador.md) para o roteamento.

## Veja também

- [componentes/servicos-docker.md](componentes/servicos-docker.md): stack Docker e as imagens em uso.
- [componentes/estudio.md](componentes/estudio.md): ComfyUI, fluxos e nós.
- [componentes/modelos.md](componentes/modelos.md): pesos e licenças dos modelos.
- [desenvolvimento.md](desenvolvimento.md): como adicionar um componente e registrar a licença dele aqui.

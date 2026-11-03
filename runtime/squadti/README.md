<div align="center">

<img src="https://www.tudoemcodigo.com/marca/PNG/tudoemcodigo-icone-512.png" alt="Tudo em Código" width="120" />

[🏠 Tudo em Código](https://github.com/tudoemcodigo) › [🧠 TudoIA](https://github.com/tudoemcodigo/TudoIA) › 🤖 SquadTI

# 🤖 SquadTI

**Uma squad de agentes de IA que leva uma demanda do briefing à entrega: o CHEFE planeja e é o seu único canal; depois vêm requisitos, arquitetura, banco, backend, frontend, testes, revisão, qualidade de código, segurança, validação em execução (hacker, macaco e carga), infraestrutura, documentação, teste de manutenibilidade e release, orquestrada em LangGraph, governada pela Doutrina TEC e rodando por padrão em modelo local.**

[![CI](https://github.com/tudoemcodigo/TudoIA/actions/workflows/ci.yml/badge.svg)](https://github.com/tudoemcodigo/TudoIA/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![LangGraph](https://img.shields.io/badge/orquestra%C3%A7%C3%A3o-LangGraph-1C3C3C)](orquestrador/graph.py)
[![Doutrina TEC](https://img.shields.io/badge/governado%20por-Doutrina%20TEC-512BD4)](https://github.com/tudoemcodigo/Doutrina)
[![Modelo local](https://img.shields.io/badge/modelo-local%20por%20padr%C3%A3o-brightgreen)](#-privacidade-e-modelo)
[![Licença: Apache 2.0](https://img.shields.io/badge/licen%C3%A7a-Apache%202.0-blue)](../../LICENSE)

</div>

> [!NOTE]
> A SquadTI passou a viver dentro do [TudoIA](https://github.com/tudoemcodigo/TudoIA) (`runtime/squadti/`), que é agora o dono do código. O repositório `tudoemcodigo/SquadTI` não recebe mais mudanças. A documentação de projeto está em [`docs/squadti/`](../../docs/squadti/).

## 📑 Sumário

- [✨ Por que usar](#-por-que-usar)
- [🧭 O fluxo](#-o-fluxo)
- [👥 Os agentes](#-os-agentes)
- [🚀 Início rápido](#-início-rápido)
- [⚙️ Configuração](#️-configuração)
- [📚 A Doutrina por papel](#-a-doutrina-por-papel)
- [🔒 Privacidade e modelo](#-privacidade-e-modelo)
- [🔌 API local (painel do TudoIA)](#-api-local-painel-do-tudoia)
- [🛡️ O que o orquestrador não faz](#️-o-que-o-orquestrador-não-faz)
- [🧪 Testes](#-testes)
- [📂 Estrutura](#-estrutura)
- [🚧 Limites conhecidos](#-limites-conhecidos)
- [🤝 Contribuindo](#-contribuindo)

---

## ✨ Por que usar

| Agente solto, sem governança | Com a SquadTI |
|---|---|
| Você conversa com vários agentes e perde o fio | O **CHEFE** é o canal único: planeja (tamanho, stack, banco, frontend), confere o critério de pronto de cada fase e escreve o relatório quando a execução para |
| Código gerado sem requisito claro, "no feeling" | O analista **entrevista** (até 4 perguntas) e gera um `BUSINESS_SPEC` em Gherkin **que você aprova** antes de qualquer desenho |
| Cada execução segue um padrão diferente | Cada agente carrega o **núcleo e as regras do seu papel** na [Doutrina TEC](https://github.com/tudoemcodigo/Doutrina); versão e hash ficam no estado, e doutrina que muda no meio **aborta** a tarefa |
| "Aprovado" sem rodar nada | O QA **executa** build e testes de verdade, exige código de saída 0 e **cobertura mínima de 90%** (linha e ramo) |
| Frontend ausente passa em silêncio | Frontend esperado e não gerado **reprova** a entrega |
| Segredo vaza para prompt e relatório | Linhas com padrão de segredo são **omitidas** antes de ir ao modelo; relatórios citam tipo e `arquivo:linha`, nunca o valor |
| O agente faz commit, tag e publica | O **release exige aprovação humana** e o orquestrador nunca roda git, tag, push ou publicação |
| "Aprovei" um texto e ele mudou depois | A aprovação é **amarrada ao conteúdo** (SHA-256 da especificação e do pacote do release); mudou, a aprovação deixa de valer |
| O sistema "passou nos testes" mas ninguém o atacou | A **validação em execução** sobe o sistema num sandbox Docker de rede interna e o hacker, o macaco e o teste de carga tentam quebrá-lo; achado grave confirmado volta ao desenvolvimento |
| Loop infinito e conta de tokens | **Orçamento** por tarefa (tokens, tempo, chamadas), detecção de estagnação e escalada ao humano |
| Código do cliente vai para a nuvem sem aviso | **Modelo local por padrão**; nuvem só com consentimento explícito |

## 🧭 O fluxo

```mermaid
flowchart TD
    U[Briefing] --> CI[chefe_intake<br/>plano: tamanho, stack, banco, frontend, API]
    CI --> R[analista_requisitos]
    R -->|perguntas| U
    R -->|BUSINESS_SPEC| G1[chefe_gate_requisitos<br/>critério de pronto]
    G1 -->|pendências, até 2 rodadas| R
    G1 --> H1{{"Aprovação humana<br/>aprovar (hash do texto)"}}
    H1 --> A[arquiteto<br/>PRD técnico + OpenAPI]
    A --> G2[chefe_gate_design]
    G2 --> D[dba<br/>se o plano pede banco]
    D --> B[dev_backend]
    D --> F[dev_frontend<br/>se o plano pede]
    G2 --> B
    B --> Q[qa_testes<br/>build, testes, cobertura]
    F --> Q
    Q -->|reprovou: falha_origem| B
    Q -->|reprovou: falha_origem| F
    Q --> V[revisor]
    V -->|reprovou| B
    V --> SM[senior_master<br/>métricas + crítica verificada]
    SM -->|reprovou| B
    SM --> S[appsec]
    S -->|bloqueado| X([chefe_escalada])
    S --> VR[validacao_runtime<br/>macaco · hacker · carga em sandbox]
    VR -->|achado grave ou SLO| B
    VR --> O[devops]
    O -->|bloqueado| X
    O --> W[documentacao]
    W --> M[mantenedor<br/>eu daqui a 1 ano]
    M -->|lacunas| W
    M --> H2{{"Aprovação humana<br/>aprovar-release (hash do pacote)"}}
    H2 --> L[release<br/>notas, versão sugerida, proveniência]
```

*Simplificado: toda reprovação que estoura o limite, estagnação ou orçamento esgotado vai ao `chefe_escalada`.*

- **Auto-cura limitada:** QA e revisor dividem o mesmo contador (3 passagens); o Sênior Master tem 3 voltas, a validação em execução 3, o Mantenedor 2 e o gate de requisitos do CHEFE 2. Ao estourar, o fluxo **escala para uma pessoa** em vez de insistir.
- **Estagnação:** a mesma falha duas vezes seguidas escala antes de gastar o resto das iterações.
- **Orçamento:** tokens, tempo e chamadas por tarefa, conferidos antes de cada nó. Esgotado, a execução para.
- **A falha vai a quem a causou:** o QA, o revisor, o Sênior e a validação registram `falha_origem` (`backend` ou `frontend`), e só esse agente recebe o erro para corrigir.
- **Duas pausas humanas, sem atalho:** antes do `arquiteto` e antes do `release`. O nó se recusa a rodar sem a aprovação gravada no estado e sem o hash do conteúdo aprovado, mesmo se o grafo for retomado à força.

## 👥 Os agentes

| Agente | Faz | Escreve em |
|---|---|---|
| [`chefe`](../../docs/squadti/04-agentes/chefe-orquestrador.md) (`chefe_intake`, `chefe_gate_requisitos`, `chefe_gate_design`, `chefe_escalada`) | Plano da demanda, critérios de pronto em código, relatório de escalada e conversa com o usuário (`/ajuste` vira instrução como dado) | `docs/chefe/` |
| [`analista_requisitos`](../../docs/squadti/04-agentes/analista-requisitos-negocios.md) | Entrevista e `BUSINESS_SPEC` com cenários Dado-Quando-Então | `docs/negocio/` |
| [`arquiteto`](../../docs/squadti/04-agentes/arquiteto-documentacao.md) | PRD técnico e contrato `openapi.yaml` | `docs/arquitetura/`, `contracts/` |
| [`dba`](../../docs/squadti/04-agentes/dba-dados.md) | Mapeamento de dados e dicionário (a migration é gerada pela ferramenta, não à mão no .NET) | `src/` ou `app/`, `migrations/`, `docs/dados/` |
| [`dev_backend`](../../docs/squadti/04-agentes/dev-backend.md) | Backend `dotnet` (template TEC) ou `python` (FastAPI), com testes feliz e adversarial | `src/`, `tests/` (`dotnet`); `app/`, `tests/`, `migrations/`... (`python`) |
| [`dev_frontend`](../../docs/squadti/04-agentes/dev-frontend.md) | React + TypeScript consumindo o OpenAPI | `frontend/` |
| [`qa_testes`](../../docs/squadti/04-agentes/qa-testes.md) | **Sem LLM.** Roda build e testes, mede cobertura, reprova frontend ausente | `tests/reports/` |
| [`revisor`](../../docs/squadti/04-agentes/revisor-codigo.md) | Revisa o código contra a Doutrina; veredito rígido; modo `dupla` com verificador adversarial | `docs/revisao/` |
| [`senior_master`](../../docs/squadti/04-agentes/senior-master.md) | Mede complexidade, duplicação, documentação e gambiarras; o modelo critica o que é suspeito; só bloqueia o que dá para conferir | `docs/qualidade/` |
| [`appsec`](../../docs/squadti/04-agentes/appsec-seguranca.md) | **Sem LLM.** Auditoria de dependências e varredura de segredos | `tests/reports/` |
| [`validacao_runtime`](../../docs/squadti/04-agentes/hacker-ofensivo.md): hacker, [macaco](../../docs/squadti/04-agentes/macaco-qa.md), [carga](../../docs/squadti/04-agentes/carga-sre.md) | Sobe o sistema num sandbox Docker e o ataca, usa à força e estressa. Só o modelo de ameaças do hacker usa LLM | `tests/reports/`, `docs/seguranca/` |
| [`devops`](../../docs/squadti/04-agentes/devops-infra.md) | **Sem LLM.** CI, Dockerfile sem `latest`, actions fixadas por SHA, `.gitignore` | `tests/reports/` |
| [`documentacao`](../../docs/squadti/04-agentes/documentacao-redator.md) | `README.md` e `docs/`, sem tocar nos artefatos dos outros nós | `README.md`, `docs/` |
| [`mantenedor`](../../docs/squadti/04-agentes/mantenedor-manutencao.md) | "Eu daqui a 1 ano": testa se um desenvolvedor novo se orienta só com a documentação | `docs/manutencao/` |
| [`release`](../../docs/squadti/04-agentes/release-notas.md) | **Sem LLM.** Notas de release, versão **sugerida** e proveniência; nunca cria tag nem publica | `docs/release/`, `docs/proveniencia.json` |

O papel de cada um, com entradas, saídas e o contrato do nó, está em [`04-agentes/`](../../docs/squadti/04-agentes/) e no [catálogo](../../docs/squadti/01-catalogo-de-agentes.md).
Para medir a qualidade com modelo real, veja os [Evals](../../docs/squadti/evals.md); para o aprendizado entre tarefas, o [Livro de Lições](../../docs/squadti/licoes.md) (biblioteca, ainda não ligada ao fluxo).

## 🚀 Início rápido

**Pelo TudoIA (recomendado).** A Squad roda num container isolado, porque compila e testa código escrito por modelo (MSBuild e npm executam código dele).
No instalador, marque **SquadTI**; ou, numa instalação existente:

```powershell
# .env: COMPOSE_PROFILES com squadti, e o token da API (32+ caracteres)
.\scripts\tudoia.ps1 segredos          # gera TUDOIA_SQUADTI_TOKEN se estiver vazio
.\scripts\tudoia.ps1 squadti-chave     # cria a chave virtual do LiteLLM (alias e tag squadti) e grava SQUADTI_API_KEY
.\scripts\iniciar.ps1 -ComSquadti      # constrói a imagem (~2 GB, na primeira vez) e sobe o container
```

Depois use o menu **SquadTI** do painel (`http://127.0.0.1:3100/app/#squadti`): aba **Tarefas** (nova tarefa, cockpit com trilha, orçamento e log ao vivo, conversa com o CHEFE, aprovações) e aba **Agentes** (perfil, temperatura, orçamento, validação em execução; só o admin salva).

O container: usuário sem root, sistema de arquivos somente leitura, sem capabilities, com teto de CPU, memória e processos,
porta só em `127.0.0.1:8790`. Escreve apenas no volume `squadti-dados` (checkpoint, `workspace/<tarefa>`, `agentes.json`, caches NuGet e npm). A Doutrina TEC vai na imagem,
numa versão (SHA) fixada no `Dockerfile` (`SQUADTI_DOUTRINA_SHA` troca). O modelo padrão é `tudoia-local-estrito`; nuvem só com consentimento por tarefa.

**Desenvolvimento (sem Docker).** Python 3.12 e [uv](https://docs.astral.sh/uv/):

```bash
cd runtime/squadti
uv sync --frozen
uv run python -W error -m pytest -q                       # testes (sem rede, sem modelo)

export DOUTRINA_TEC=/caminho/para/Doutrina               # sem doutrina legível, a Squad não trabalha
export TUDOIA_API_KEY=<chave virtual do LiteLLM>         # nunca a LITELLM_MASTER_KEY
uv run python orquestrador/main.py iniciar --tarefa TASK-001 --briefing "Cadastro de clientes com pedidos" --perfil local-estrito [--stack dotnet|python]
```

> [!IMPORTANT]
> A chave padrão `sk-tudoia-local` é só um exemplo e o gateway a recusa. Use uma **chave virtual** limitada aos modelos de que a Squad
> precisa (`tudoia squadti-chave` cria a certa). A chave fica no `.env` (ignorado pelo git), nunca em arquivo versionado.

> [!NOTE]
> **Atenção:** o `docker.sock` do host está montado para os testes de integração (Testcontainers): isso equivale a root no host para o código gerado. Veja o aviso em
> [`docs/componentes/squadti.md`](../../docs/componentes/squadti.md) e como desfazer.
>
> A **validação em execução** (hacker, macaco, carga) precisa do cliente `docker` no `PATH`, e o `Dockerfile` desta imagem não o instala: no container, em `validacao.modo = auto`, ela é pulada com o motivo registrado (em `sempre`, a tarefa escala).
>
> O template `dotnet new tec-project` (stack `dotnet`) entra se a pasta do TemplateTEC for copiada para `dados/squadti-template` (ou `SQUADTI_TEMPLATE_DIR`);
> o feed privado `tec-interno` exige `TUDOIA_NUGET_USER` e `TUDOIA_NUGET_PAT` (read:packages) no `.env`.

## ⚙️ Configuração

A stack vem de um `stack_config.json` (modelo em [`orquestrador/stack_config.example.json`](orquestrador/stack_config.example.json)). Há dois adaptadores de backend, `dotnet` (padrão) e `python` (FastAPI, SQLAlchemy 2, Alembic, pytest, uv); o CHEFE escolhe no plano, o usuário pode fixar (`--stack`, `stack` na API) e `backend.language` também vale. Comandos declarados no arquivo vencem os do adaptador:

```json
{
  "project_name": "GestaoFinanceira",
  "architecture_source_path": "../Doutrina",
  "stack": {
    "backend":  { "build_command": "dotnet build --configuration Release",
                  "test_command":  "dotnet test --no-build --coverage --coverage-output-format cobertura",
                  "scaffold_command": "dotnet new tec-project -n {nome}" },
    "frontend": { "framework": "react19", "language": "typescript", "bundler": "vite",
                  "build_command": "npm run build", "test_command": "npm test" },
    "database": { "engine": "mssql", "migration_tool": "ef_core" },
    "quality":  { "coverage_min": 90 },
    "infra":    { "ci": "github", "container_runtime": "docker" }
  }
}
```

| Variável | Para quê |
|---|---|
| `DOUTRINA_TEC` | Pasta da Doutrina (tem precedência sobre `architecture_source_path`) |
| `DOUTRINA_FAMILIAS` | Força as mesmas famílias em todos os papéis (padrão: o perfil de cada papel) |
| `TUDOIA_GATEWAY_URL` | Endereço do gateway (padrão `http://localhost:4000/v1`) |
| `TUDOIA_API_KEY` | Chave virtual do LiteLLM (no container vem de `SQUADTI_API_KEY` do `.env`) |
| `TUDOIA_MODEL` / `--perfil` | Modelo ou perfil de destino (padrão da imagem: `tudoia-local-estrito`) |
| `SQUADTI_AGENTES_ARQUIVO` | Onde ficam o modelo, a temperatura, o orçamento e a validação por agente (padrão `agentes.json`) |
| `SQUADTI_LICOES_ARQUIVO` | Livro de Lições (padrão `licoes.jsonl`; ainda não usado pelo fluxo) |
| `DOCKER_BIN` | Executável do Docker da validação em execução (padrão `docker`) |
| `TUDOIA_PERMITIR_NUVEM=1` | Consentimento explícito para perfis que podem sair da máquina |
| `TUDOIA_CONTEXTO_TOKENS` | Janela de contexto do modelo em uso (`num_ctx` no Ollama; padrão 32768). Prompt estimado acima de 85% da janela é **recusado** antes de chegar ao modelo |
| `DOUTRINA_REGRAS_MAX_TOKENS` | Orçamento das regras do papel no prompt (padrão 12000); reduza para modelos de janela pequena |

`quality.coverage_min` aceita `0` para **desligar o gate de forma explícita** (fica registrado no relatório); valor inválido volta a 90, nunca desliga.

## 📚 A Doutrina por papel

Cada agente lê `gerado/perfis/<papel>.json` da Doutrina: carrega o **núcleo** das famílias do papel (sempre `ia` e `ecossistema`, mais as dele) e
as **regras** do papel, com orçamento de contexto (regras `MUST` primeiro, depois `SHOULD`; o que não coube é declarado, nunca omitido em silêncio).
Papel sem perfil, JSON corrompido ou pasta que não é a Doutrina **derrubam a tarefa**. Veja a [fonte da verdade](../../docs/squadti/05-fonte-da-verdade-arquitetura.md).

## 🔒 Privacidade e modelo

| `--perfil` | Destino | Sai da máquina? |
|---|---|---|
| `local-estrito` (recomendado) | `tudoia-local-estrito` | **Nunca**, sem fallback para a nuvem |
| `local` | `tudoia-local` | O gateway pode reenviar à nuvem se estourar o contexto |
| `hibrido`, `nuvem`, `auto`, `max` | nuvem como apoio ou principal; `auto` é o roteador, que decide por pedido | **Sim**; exigem `TUDOIA_PERMITIR_NUVEM=1` (CLI) ou `consentimento_nuvem: true` (API/painel) |

> [!WARNING]
> O gateway desta árvore não define `tudoia-local-estrito` nem `tudoia-hibrido` (`config/roteamento.yaml` não tem a seção `perfis`; `painel/tudoia_painel/gerador.py` não gera esses grupos): uma tarefa com `local-estrito` ou `hibrido` falha no LiteLLM por modelo desconhecido, sem enviar nada à nuvem. Use `local` ou `nuvem` até os grupos existirem. Conferido por leitura do código; não executado.

O roteador `tudoia-auto` **não garante execução local**: por isso é tratado como nuvem e só roda com o consentimento. O mesmo vale para o perfil de cada agente configurado na aba Agentes. Código, esquema e requisitos do projeto não devem sair da máquina sem o seu consentimento.

## 🔌 API local (painel do TudoIA)

O painel do TudoIA conduz a Squad por uma API HTTP local, que usa a mesma camada de serviço da CLI (`servico.py`).

```bash
TUDOIA_SQUADTI_TOKEN=<32+ caracteres> python orquestrador/api.py --porta 8790
```

| Rota | O que faz |
|---|---|
| `GET /saude` | Vivo (sem token) |
| `GET /api/tarefas` · `GET /api/tarefas/{id}` | Lista e detalhe: situação, perguntas, arquivos, verificações, versão da Doutrina |
| `GET /api/tarefas/{id}/arquivo?caminho=` | Texto de um arquivo do workspace (até 200 KB, linhas com padrão de segredo omitidas) |
| `POST /api/tarefas` | `{tarefa, briefing, perfil?, consentimento_nuvem?, stack?, orcamento?}`; perfil padrão `local-estrito` |
| `POST /api/tarefas/{id}/responder` · `/aprovar` · `/aprovar-release` | Mesmas ações da CLI |
| `GET .../mensagens` · `POST .../mensagem` | Conversa com o CHEFE (`{texto}`); nunca altera aprovação, portão nem configuração |
| `GET .../auditoria` · `.../proveniencia` · `.../log?desde=N` | Consumo por nó e por chamada, manifesto da entrega e log ao vivo |
| `POST .../continuar` | Retoma tarefa escalada (opcionalmente com novo orçamento) |
| `GET /api/agentes` · `POST /api/agentes` | Configuração dos agentes (validada campo a campo) |

As ações respondem `202` e rodam em segundo plano, **uma por vez** (`409` se houver outra). Fronteiras: só `127.0.0.1`; sem `TUDOIA_SQUADTI_TOKEN` (32+ caracteres) a API não sobe; `Host` fora do loopback é recusado; `POST` só `application/json` até 64 KB; perfil que pode sair da máquina (`hibrido`, `nuvem`, `auto`, `max`) só com `consentimento_nuvem: true`, gravado no estado da tarefa. `TUDOIA_TIMEOUT_S` limita cada chamada ao modelo. A lista completa e os códigos de situação estão em [`docs/componentes/squadti.md`](../../docs/componentes/squadti.md#-api-local).

## 🛡️ O que o orquestrador não faz

- Não executa o que o modelo escreve em texto: **comandos vêm da configuração**, rodam **sem shell**, com executável em lista (`dotnet`, `npm`, `npx`, `uv`) e timeout.
- Não grava arquivo fora da área do papel: caminho validado (sem `..`, unidade ou fluxo alternativo do NTFS), limite de tamanho e de quantidade; o que for recusado **falha alto**.
- Não faz `git commit`, tag, push nem publica pacote. O `release` só escreve notas.
- Não aprova por omissão: sem projeto gerado, sem testes, sem cobertura medida ou sem veredito válido, o resultado é **reprovado**.
- Não trata conteúdo lido como instrução: requisitos, logs, código revisado e mensagens ao CHEFE são dados (sanitizados, com defesa padrão contra injeção no prompt).
- Não decide sozinho o que o sandbox executa: os cenários do hacker, do macaco e da carga são verificações fixas, e os argumentos do Docker passam por um validador que recusa `--privileged`, `-v`, `--network host` e afins.

## 🧪 Testes

```bash
cd runtime/squadti
uv run python -W error -m pytest -q                               # sem DOUTRINA_TEC, o teste contra a doutrina real é pulado
DOUTRINA_TEC=<pasta-da-doutrina> uv run python -W error -m pytest -q   # com a doutrina real
```

A suíte cobre as fronteiras (arquivos e comandos), os nós com dublês do modelo e do Docker, o **grafo real do LangGraph** (topologia, pausas humanas e rotas de correção), os kits de ataque e de interface, o CHEFE, a qualidade e a validação em execução, os evals (driver contra uma API simulada), o Livro de Lições e a CLI,
com entradas válidas e hostis. Sem `langgraph` instalado, os testes de grafo e de CLI são pulados; por isso o CI instala as dependências travadas em `uv.lock` (`uv sync --frozen`).

## 📂 Estrutura

```text
runtime/squadti/
  Dockerfile · entrypoint.sh · pyproject.toml · uv.lock     imagem (.NET + Node + uv + Python), dependências travadas
  orquestrador/
    main.py · graph.py · nodes.py · state.py                 CLI, grafo (18 nós), nós e estado
    chefe.py · qualidade.py · validacao.py                   CHEFE, Sênior Master e Mantenedor, validação em execução
    sandbox.py · carga.py · kits/                            sandbox Docker, teste de carga (k6), kits de ataque e de interface
    stacks.py · agentes.py · perfis.py                       adaptadores de stack, config dos agentes e orçamento, perfis
    auditoria.py · proveniencia.py · aprovacao.py · entrada.py  trilha e orçamento, manifesto da entrega, hash das aprovações, sanitização
    metricas.py · licoes.py                                  métricas de código (QC-*), Livro de Lições (biblioteca)
    doutrina_tec.py                                          carregador da Doutrina (falha fechado, versão no estado)
    servico.py · api.py                                      camada de serviço e API local (usada pelo painel)
    execucao.py · cobertura.py · segredos.py · verificacoes.py · revisao.py
    tests/                                                   fronteiras, nós, grafo real, kits, v2, evals, lições, CLI e API
  evals/                                                     casos dourados, driver pela API, verificadores, relatório
../../docs/squadti/                                          design: visão geral, catálogo, protocolo, guia, fonte da verdade, agentes, evals, lições
../../docs/componentes/squadti.md                           operação no TudoIA: container, API, painel, segurança, diagnóstico
../../painel/tudoia_painel/rotas/squadti.py                 rotas do painel · static/squadti.js: abas Tarefas e Agentes
scripts/squadti/chave.py                                     chave virtual do LiteLLM (tudoia squadti-chave)
```

## 🚧 Limites conhecidos

- **O ciclo completo não tem execução registrada com modelo real.** Em 2026-11-02 (antes da v2) só o primeiro nó rodou com modelo real: o `iniciar` com `tudoia-local-estrito` passou pelo gateway, carregou a Doutrina por perfil e o analista de requisitos gerou a especificação e as perguntas; o arquiteto falhou fechado nas três tentativas porque o `qwen2.5-coder` (janela de 16384 tokens no Ollama) devolveu 6 a 15 caracteres com ~11 mil tokens de regras no prompt. Hoje cada chamada tem prazo (`TUDOIA_TIMEOUT_S`, padrão 300 s) e 1 nova tentativa, resposta minúscula duas vezes seguidas escala, e o [Evals](../../docs/squadti/evals.md) existe para medir isso com modelo real. Os testes automatizados usam dublês do LLM e do Docker. A qualidade do código gerado depende do modelo local escolhido.
- **A validação em execução não roda no container como está:** o `Dockerfile` não instala o cliente `docker`. Com `validacao.modo = auto` ela é pulada (registrado no estado e nas notas de release); com `sempre`, a tarefa escala. Fora do container, com Docker no `PATH`, funciona. O sandbox só tem imagem de banco para `postgres`.
- **Contexto grande:** o prompt de um papel vai de ~6 mil a ~19 mil tokens com os padrões (núcleo + regras), fora o PRD ou o OpenAPI de entrada. Modelo com janela pequena (o `num_ctx` padrão do Ollama costuma ser 4096) truncaria as regras em silêncio; por isso o orquestrador **recusa** o prompt que não cabe. Ajuste `TUDOIA_CONTEXTO_TOKENS` e `DOUTRINA_REGRAS_MAX_TOKENS` ao modelo.
- **Só projeto novo** (IA-ORQ-10, ADR 0005): a Squad escreve apenas em `workspace/<tarefa>` e `iniciar` recusa uma pasta que já tenha conteúdo. Não há rota para repositório existente; branch ou worktree dedicado entra quando essa rota existir.
- **Só `dotnet` e `python`.** Outras stacks de backend exigem um adaptador novo em `stacks.py`.
- **Continuar uma tarefa escalada** só retoma o que parou dentro de um nó (orçamento, saída inválida). Parada decidida pelo roteamento do grafo (QA, revisão, Sênior ou validação estourando o limite, estagnação, gates) já terminou em `END`; nesses casos inicie outra tarefa. Inferido da leitura do grafo, sem teste de ponta a ponta.
- **O Livro de Lições ainda não está ligado** ao fluxo, à API nem ao painel (ver [Livro de Lições](../../docs/squadti/licoes.md)).
- O **AppSec automático mede pouco** (dependências e padrões de segredo) e o hacker cobre só o que o contrato OpenAPI declara. `ENTREGA_CONCLUIDA` não significa "segura"; faltam SAST e cadeia de suprimentos.
- A varredura de segredos é um filtro de padrões, não substitui um scanner dedicado no CI do projeto gerado.
- O gate de cobertura exige relatório Cobertura no `test_command`; sem ele, a cobertura é "não medida" e reprova.
- A capacidade medida pela carga é relativa ao teto de CPU e memória do sandbox, não à produção.
- Sem identidade própria por agente (hoje); a trilha de auditoria por papel depende do GAP.

## 🤝 Contribuindo

Leia o guia de contribuição do [TudoIA](https://github.com/tudoemcodigo/TudoIA) e o Código de Conduta do projeto. Falha de segurança: **não abra issue pública**, veja a [política de segurança](../../docs/seguranca.md).
Licença: [Apache 2.0](../../LICENSE) · [NOTICE](../../NOTICE).

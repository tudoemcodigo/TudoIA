---
titulo: Catálogo de agentes da SquadTI
tipo: referencia
dono: TudoIA (mantenedor do repositório)
status: vigente
classificacao: publico
verificado-em: 2026-11-03
---

[🏠 TudoIA](../../README.md) › [📚 Documentação](../README.md) › 👥 Catálogo de agentes da SquadTI

# 👥 Catálogo de agentes da SquadTI

> **Público:** quem mantém os agentes. Lista cada papel, entradas, saídas e regras, marcando o que o orquestrador implementa e o que é intenção de projeto.

## 📑 Sumário

- [1. Agente Analista de Requisitos & Negócios (Product Analyst & Requirements Engineer)](#1-agente-analista-de-requisitos--negócios-product-analyst--requirements-engineer)
- [2. Agente CHEFE (Tech Lead, Prompt Architect & Orquestrador)](#2-agente-chefe-tech-lead-prompt-architect--orquestrador)
- [3. Agente de Documentação & Arquitetura (nó `arquiteto`)](#3-agente-de-documentação--arquitetura-nó-arquiteto)
- [4. Agente de Banco de Dados / DBA (Data Architect & Database Engineer)](#4-agente-de-banco-de-dados--dba-data-architect--database-engineer)
- [5. Agente de Desenvolvimento Backend (Senior Backend Engineer)](#5-agente-de-desenvolvimento-backend-senior-backend-engineer)
- [6. Agente de Desenvolvimento Frontend (Senior Frontend Engineer)](#6-agente-de-desenvolvimento-frontend-senior-frontend-engineer)
- [7. Agente de QA & Testes (Quality Assurance & Test Automation Engineer)](#7-agente-de-qa--testes-quality-assurance--test-automation-engineer)
- [8. Agente de Infraestrutura & DevOps (SRE & Platform Engineer)](#8-agente-de-infraestrutura--devops-sre--platform-engineer)
- [9. Agente de Segurança / AppSec (Application Security & Red Team)](#9-agente-de-segurança--appsec-application-security--red-team)
- [10. Agente Revisor de Código](#10-agente-revisor-de-código)
- [11. Agente de Documentação (Redator Técnico)](#11-agente-de-documentação-redator-técnico)
- [12. Release (sem modelo)](#12-release-sem-modelo)

---


Este catálogo descreve os agentes que compõem a equipe de engenharia autônoma, suas fronteiras de atuação, entradas, saídas e ferramentas obrigatórias.

> [!NOTE]
> Cada seção descreve o papel de projeto. Onde o orquestrador (`runtime/squadti/orquestrador/nodes.py`) faz menos ou diferente, há uma linha **No orquestrador**. Ferramentas e stacks citadas sem essa linha (Go, Python, Playwright, Testcontainers, trivy, semgrep, gitleaks) **não** são executadas hoje: são intenção de projeto. Os perfis por papel estão em [`04-agentes/`](04-agentes/chefe-orquestrador.md).

---

## 1. Agente Analista de Requisitos & Negócios (Product Analyst & Requirements Engineer)

- **Missão:** Realizar a elicitação ativa de requisitos junto ao Usuário (Product Owner), conduzindo entrevistas técnicas, desenterrando regras de negócio ocultas, definindo casos de borda e redigindo cenários de aceitação (BDD/Gherkin).
- **Entradas:**
  - Briefings em linguagem natural do Usuário.
  - Contexto de mercado ou demandas de evolução de software.
- **Saídas:**
  - `docs/negocio/BUSINESS_SPEC.md`: Especificação funcional, personas, regras de validação e critérios de aceitação.
  - Perguntas e questionários de alinhamento estratégico.
- **Ferramentas Necessárias:**
  - Leitura e escrita de especificações (`markdown`).
  - Canal interativo de perguntas e respostas com o Usuário.
- **Regras Operacionais:**
  - Nunca assume uma regra não declarada: formula perguntas de clarificação antes de delegar para a equipe técnica.
  - Transforma regras em cenários Gherkin (Dado-Quando-Então).

---

## 2. Agente CHEFE (Tech Lead, Prompt Architect & Orquestrador)

- **Missão:** Orquestrar o ciclo de vida do desenvolvimento no LangGraph, traduzir a especificação funcional em planos de trabalho técnicos, controlar a esteira de execução e garantir que nenhuma entrega seja feita sem validação real.
- **Entradas:**
  - `BUSINESS_SPEC.md` aprovado pelo Usuário.
  - Feedbacks de execução e logs dos agentes subordinados.
- **Saídas:**
  - Ordens de serviço técnicas (Tasks em `state.json`).
  - Prompts enxutos e contextualizados para cada agente especialista.
  - Relatórios de entrega consolidada para o Usuário.
- **Ferramentas Necessárias:**
  - Manipulação de estado e arquivos de planejamento.
  - Controle de nós e transições no LangGraph.
- **No orquestrador:** não há nó "chefe"; o grafo (`graph.py`) exerce o papel. Ver [`04-agentes/chefe-orquestrador.md`](04-agentes/chefe-orquestrador.md).
- **Regras Operacionais:**
  - Mantém o isolamento de contexto (não envia histórico de conversa, apenas a ordem de serviço e os artefatos estritamente necessários).
  - Limita loops de auto-cura a 3 tentativas por tarefa.

---

## 3. Agente de Documentação & Arquitetura (nó `arquiteto`)

- **Missão:** Estruturar a especificação técnica (PRD Técnico), registros de decisão de arquitetura (ADRs), diagramas C4/Mermaid e especificações de contratos de API (OpenAPI 3.1 em YAML).
- **Entradas:**
  - `BUSINESS_SPEC.md` fornecido pelo Analista de Requisitos.
  - Diretrizes arquiteturais (.NET 10 Clean Architecture, APIs RESTful, Mensageria, etc.).
- **Saídas:**
  - `docs/arquitetura/PRD_TECNICO.md`.
  - `docs/arquitetura/ADR-xxxx.md`.
  - `contracts/openapi.yaml` e schemas JSON.
- **Ferramentas Necessárias:**
  - Leitura e escrita de documentação técnica.
  - Validadores de OpenAPI e JSON Schema.
- **No orquestrador:** o nó `arquiteto` grava só `docs/arquitetura/PRD_TECNICO.md` e `contracts/openapi.yaml`; ADRs e validadores de OpenAPI não são gerados nem executados. Ver [`04-agentes/arquiteto-documentacao.md`](04-agentes/arquiteto-documentacao.md).

---

## 4. Agente de Banco de Dados / DBA (Data Architect & Database Engineer)

- **Missão:** Projetar o modelo de dados físico e lógico, gerar scripts de migração versionados, otimizar índices e assegurar consistência transacional e segurança.
- **Especialidade Principal:** Microsoft SQL Server (MSSQL) com T-SQL, particionamento e índices colunares/não-clusterizados.
- **Agnosticismo de Stack:** Capacidade de gerar migrações para PostgreSQL, MySQL, SQLite ou MongoDB via configuração de projeto.
- **Entradas:**
  - Entidades de domínio e contratos definidos pela Arquitetura.
- **Saídas:**
  - Na stack .NET da Doutrina TEC: mapeamento EF Core (`IEntityTypeConfiguration`); a migration é **gerada por `dotnet ef migrations add`**, nunca escrita à mão, e migration publicada não se edita (ARQ-PER-13). Mudança de esquema segue expandir, migrar, contrair (ARQ-PER-14).
  - Em outras stacks (sem Doutrina própria ainda): scripts versionados com rollback (`down`).
  - Diagrama ERD em Mermaid e Dicionário de Dados.
- **Ferramentas Necessárias:**
  - `dotnet ef` (stack .NET); `sqlfluff` apenas para SQL escrito à mão em outras stacks.
  - CLI de banco de dados (`sqlcmd`, `psql`).
- **No orquestrador:** o nó `dba` grava o mapeamento em `src/` e o dicionário em `docs/dados/DICIONARIO.md`; não executa `dotnet ef`, `sqlcmd` nem `psql`. Ver [`04-agentes/dba-dados.md`](04-agentes/dba-dados.md).

---

## 5. Agente de Desenvolvimento Backend (Senior Backend Engineer)

- **Missão:** Implementar a lógica de negócios, APIs de alta performance e integrações com o banco de dados e serviços externos.
- **Especialidade Principal:** .NET 10 + C# (Clean Architecture, ASP.NET Core Web API, EF Core, CancellationToken, Channel assíncrono).
- **Agnosticismo de Stack:** Suporte a Python (FastAPI), Go (Gin/Fiber), Node.js (NestJS/Fastify) alternando o template de compilação.
- **Entradas:**
  - Contrato de API (`openapi.yaml`), migrações do banco e critérios de aceitação.
- **Saídas:**
  - Código-fonte modular e tipado.
  - Testes unitários com mock cirúrgico.
- **Ferramentas Necessárias:**
  - SDK da linguagem (`dotnet build`, `dotnet format`, `python`, `cargo`).
- **No orquestrador:** só .NET; build e testes rodam no nó `qa_testes`, a partir dos comandos do `stack_config`. Ver [`04-agentes/dev-backend.md`](04-agentes/dev-backend.md).
- **Regras Operacionais:**
  - Código deve compilar com 0 erros e 0 warnings antes de entregar ao CHEFE.
  - Erros e sucessos usam o envelope `ApiResponse` da Doutrina TEC, com status derivado do `ErrorType` (ARQ-API-04). Não use RFC 7807 / Problem Details: conflita com a Doutrina.

---

## 6. Agente de Desenvolvimento Frontend (Senior Frontend Engineer)

- **Missão:** Desenvolver a interface visual moderna, responsiva e acessível, consumindo as APIs REST com fidelidade aos contratos.
- **Especialidade Principal:** React 19 + TypeScript + Vite + Tailwind CSS + TanStack Query (React Query) + Zod.
- **Agnosticismo de Stack:** Suporte a Next.js, Vue 3, Angular ou Blazor.
- **Entradas:**
  - Telas/Wireframes especificados, contrato OpenAPI e requisitos de UX.
- **Saídas:**
  - Componentes de UI modulares e tipados.
  - Clientes HTTP tipados com tratamento de estados (loading, erro, vazio, sucesso).
  - Testes de componentes (Vitest + Testing Library).
- **Ferramentas Necessárias:**
  - CLI do Node/npm/pnpm (`npm run build`, `npm run lint`).
- **No orquestrador:** só React + TypeScript, com `build_command`/`test_command` do `stack_config`. Ver [`04-agentes/dev-frontend.md`](04-agentes/dev-frontend.md).

---

## 7. Agente de QA & Testes (Quality Assurance & Test Automation Engineer)

- **Missão:** Blindar o sistema contra regressões e falhas, executando testes reais automatizados de integração, contrato e carga.
- **Regra Fundamental:** **Zero Verification Theater** (nunca aprova código apenas lendo; exige execução real e exit code 0).
- **Entradas:**
  - Código-fonte Backend e Frontend, scripts do DBA e cenários BDD do Analista de Requisitos.
- **Saídas:**
  - Testes de integração (ex: `dotnet test` com WebApplicationFactory + Testcontainers MSSQL).
  - Testes E2E (Playwright).
  - Relatório de execução estruturado com cobertura e tempos de resposta.
- **Ferramentas Necessárias:**
  - Executores de teste do terminal (`dotnet test`, `pytest`, `npx playwright test`).
- **No orquestrador:** nó `qa_testes` **sem LLM**: roda build e testes do backend e do frontend e mede a cobertura mínima (`quality.coverage_min`); grava `tests/reports/qa_report.json`. Sem projeto gerado, ou com frontend esperado e ausente, reprova. Não roda Playwright nem Testcontainers. Ver [`04-agentes/qa-testes.md`](04-agentes/qa-testes.md).

---

## 8. Agente de Infraestrutura & DevOps (SRE & Platform Engineer)

- **Missão:** Empacotar a aplicação em contêineres seguros, gerenciar orquestração local e pipelines de CI/CD.
- **Entradas:**
  - Dependências de runtime e variáveis de ambiente necessárias.
- **Saídas:**
  - `Dockerfile` multi-stage (usuário não-root, imagens Alpine ou distroless).
  - `docker-compose.yml` contendo a aplicação e o banco (MSSQL/Postgres).
  - Pipelines de CI/CD (GitHub Actions / Azure Pipelines).
- **Ferramentas Necessárias:**
  - Docker CLI, docker-compose config validator, linters de pipeline.
- **No orquestrador:** o nó `devops` **verifica** (não gera) o que o projeto já tem; é estático, sem modelo e sem rede (CI, Dockerfile sem `latest`, actions fixadas por SHA, `.gitignore`, sem `.env` com conteúdo); ver [`04-agentes/devops-infra.md`](04-agentes/devops-infra.md).

---

## 9. Agente de Segurança / AppSec (Application Security & Red Team)

- **Missão:** Identificar vulnerabilidades de segurança (OWASP Top 10), vazamentos de credenciais e conformidade com a LGPD.
- **Entradas:**
  - Código-fonte, dependências de pacotes e arquivos de configuração.
- **Saídas:**
  - Relatório de SAST e auditoria de vulnerabilidades.
  - Matriz de segurança e recomendações de mitigação.
- **Ferramentas Necessárias:**
  - `trivy`, `semgrep`, `gitleaks`, `dotnet list package --vulnerable`.
- **Regras Operacionais:**
  - Fail-closed: bloqueia deploys na presença de vulnerabilidade Alta ou Crítica.
- **No orquestrador:** nó `appsec`, separado do `devops` (hoje só `dotnet list package --vulnerable`, `npm audit --audit-level=high` e varredura de segredos por padrões, que não substitui gitleaks/trufflehog; ver [`04-agentes/appsec-seguranca.md`](04-agentes/appsec-seguranca.md)).

---

## 10. Agente Revisor de Código

- **Missão:** Revisar o código gerado contra as regras da Doutrina depois que o QA aprova.
- **Entradas:** arquivos sob `src/`, `tests/` e `frontend/` (até 60.000 caracteres) e as regras dos papéis backend/frontend.
- **Saídas:** `docs/revisao/REVISAO.md` com `VEREDITO: APROVADO|REPROVADO` e achados por severidade, regra e `arquivo:linha`.
- **Regras Operacionais:** fail-closed (sem veredito único e válido, ou com achado CRITICO, é reprovado); reprovação volta ao dev responsável dentro do mesmo limite de 3 iterações. Ver [`04-agentes/revisor-codigo.md`](04-agentes/revisor-codigo.md).

---

## 11. Agente de Documentação (Redator Técnico)

- **Missão:** Escrever `README.md` e a documentação em `docs/` a partir dos artefatos aprovados.
- **Saídas:** `README.md` e arquivos em `docs/`, sem tocar em `docs/negocio/`, `docs/revisao/`, `docs/release/`, no PRD técnico nem no dicionário de dados. A saída passa por varredura de segredos. Ver [`04-agentes/documentacao-redator.md`](04-agentes/documentacao-redator.md).

---

## 12. Release (sem modelo)

- **Missão:** Consolidar `docs/release/RELEASE_NOTES.md` (versão SemVer sugerida, hash da Doutrina, arquivos e resultado das verificações).
- **Regras Operacionais:** o grafo pausa antes do nó e ele só roda com `release_approved` explícito (`aprovar-release`); nunca roda git, tag, push nem publicação. Ver [`04-agentes/release-notas.md`](04-agentes/release-notas.md).

---

[🏠 README](../../README.md) · ⬅️ [Visão geral e arquitetura da SquadTI](00-visao-geral-e-arquitetura.md) · [Protocolo de comunicação e estado](02-protocolo-de-comunicacao-e-estado.md) ➡️

---
titulo: Visão geral e arquitetura da SquadTI
tipo: explicacao
dono: TudoIA (mantenedor do repositório)
status: vigente
classificacao: publico
verificado-em: 2026-11-03
---

[🏠 TudoIA](../../README.md) › [📚 Documentação](../README.md) › 🧭 Visão geral e arquitetura da SquadTI

# 🧭 Visão geral e arquitetura da SquadTI

> **Público:** quem mantém ou avalia a SquadTI. Responde por que a squad é um grafo de artefatos e como se liga ao TudoIA; o estado real do código está em [SquadTI (componente)](../componentes/squadti.md).

## 📑 Sumário

- [1. O Desafio e a Abordagem de Engenharia](#1-o-desafio-e-a-abordagem-de-engenharia)
- [2. Topologia do Sistema com Engenharia de Requisitos](#2-topologia-do-sistema-com-engenharia-de-requisitos)
- [3. Integração com o Ecossistema Local (TudoIA)](#3-integração-com-o-ecossistema-local-tudoia)
- [4. Stack Padrão e Arquitetura Agnóstica (Stack Adapters)](#4-stack-padrão-e-arquitetura-agnóstica-stack-adapters)
- [5. O Papel Crítico do Agente CHEFE (Tech Lead & Orquestrador)](#5-o-papel-crítico-do-agente-chefe-tech-lead--orquestrador)

---


## 1. O Desafio e a Abordagem de Engenharia

Criar uma equipe autônoma de desenvolvimento de software baseada em IA não consiste em colocar múltiplos modelos de linguagem em um chat aberto conversando livremente. Na prática de engenharia, sistemas multi-agente puramente conversacionais sofrem de:
1. **Looping e alucinação cumulativa:** Agentes concordando mutuamente com erros ou amplificando falhas conceituais.
2. **Explosão de custos de tokens e perda de contexto:** Conversas longas diluem regras críticas e gastam orçamento computacional sem avanço de código real.
3. **"Verification Theater" (Teatro de Verificação):** Agentes de teste que apenas leem o código e dizem "parece bom", sem jamais compilar, rodar suítes de testes ou validar ambientes reais.
4. **Desalinhamento de Contrato:** O backend muda um endpoint REST/GraphQL sem notificar o frontend ou o banco de dados.

Para solucionar isso, esta Squad adota a **Arquitetura Baseada em Contratos e Artefatos (Artifact-Driven Orchestration)** executada via **LangGraph (Python)** conectado ao ecossistema local **TudoIA** (gateway LiteLLM em `localhost:4000` e modelos locais no Ollama).

---

## 2. Topologia do Sistema com Engenharia de Requisitos

A squad opera sob o modelo **Hierárquico com Supervisão por Grafo de Estados (LangGraph StateGraph)**, incluindo o ciclo formal de elicitação negocial.

> [!NOTE]
> O diagrama é o **modelo conceitual** (com o papel CHEFE). No código não existe nó "chefe": o papel é exercido pelo próprio grafo (`graph.py`: roteamento, limite de iterações e pausas de aprovação humana). Os nós reais são `analista_requisitos`, `arquiteto`, `dba`, `dev_backend`, `dev_frontend`, `qa_testes`, `revisor`, `appsec`, `devops`, `documentacao` e `release`; o fluxo implementado está em [protocolo](02-protocolo-de-comunicacao-e-estado.md#1-o-ciclo-de-vida-de-uma-demanda-no-langgraph).

```mermaid
flowchart TD
    User([Usuário - Product Owner]) <-->|1. Demandas Brutas & Respostas a Entrevistas| REQ[Agente Analista de Requisitos & Negócios]
    REQ -->|2. BUSINESS_SPEC.md + Cenários BDD/Gherkin| CHEFE[Agente CHEFE / Tech Lead & Orquestrador]
    
    CHEFE <-->|Aprovação de Escopo & Arquitetura| User

    CHEFE -->|3. Especificação Técnica & Contratos| DOC[Agente de Documentação & Arquitetura]
    DOC -->|PRD Técnico / ADR / OpenAPI Spec| CHEFE

    CHEFE -->|4. Modelagem & DDL/Migrações MSSQL/Agnóstico| DBA[Agente DBA & Dados]
    DBA -->|Scripts SQL / Migrações / Dicionário| CHEFE

    CHEFE -->|5. Contrato de API & Regras de Negócio| BACKEND[Agente Dev Backend - .NET 10 / Agnóstico]
    CHEFE -->|6. Interfaces & Consumo de APIs| FRONTEND[Agente Dev Frontend - React TS / Agnóstico]

    BACKEND -->|Código + dotnet build| CHEFE
    FRONTEND -->|Componentes + npm run build| CHEFE

    CHEFE -->|7. Código & Ambientes para Validação| QA[Agente de QA & Testes]
    QA -->|Execução Real: dotnet test / vitest / playwright| CHEFE

    CHEFE -->|8. Containers, CI/CD & Deploy| INFRA[Agente DevOps & SRE]
    CHEFE -->|9. Análise de Riscos & Vulnerabilidades| APPSEC[Agente AppSec & Segurança]

    INFRA -->|Pipelines & Infra validada| CHEFE
    APPSEC -->|Relatório SAST / Hardening| CHEFE

    CHEFE -->|10. Relatório de Entrega & Validação Final| User
```

---

## 3. Integração com o Ecossistema Local (TudoIA)

A squad não depende de APIs externas proprietárias ou conexões que exponham código confidencial. Ela conecta-se nativamente à infraestrutura local do **TudoIA**:
- **Gateway LiteLLM (`http://localhost:4000/v1`):** Ponto único de chamada de LLM compatível com a API OpenAI.
- **Perfis do gateway (`tudoia-local-estrito`, `tudoia-local`, `tudoia-hibrido`, `tudoia-nuvem`, `tudoia-max`):** o orquestrador usa por padrão `tudoia-local` e recusa perfil que pode sair da máquina sem consentimento explícito (`TUDOIA_PERMITIR_NUVEM=1` ou `consentimento_nuvem`). O roteador `tudoia-auto` não é um perfil da SquadTI. Ver [guia de implementação](03-guia-de-implementacao.md#perfis-aceitos---perfil-orquestradorperfispy).
- **Cérebro MCP:** não é usado pelo orquestrador atual (nenhuma referência em `runtime/squadti/orquestrador/`); é intenção de projeto.
- **Privacidade por Padrão (Local-First):** Código-fonte proprietário, esquemas de banco e regras de negócio permanecem na máquina local sem vazamento.

---

## 4. Stack Padrão e Arquitetura Agnóstica (Stack Adapters)

Embora a stack prioritária de referência da organização seja:
- **Backend:** .NET 10 + C# (Clean Architecture, EF Core; regras na Doutrina TEC, família `arquitetura`)
- **Frontend:** React 19 + TypeScript + Vite + Tailwind CSS
- **Banco de Dados:** Microsoft SQL Server (MSSQL) com migrações versionadas

A Squad adota o **Padrão de Adaptadores de Stack (Stack Adapters)**:
Cada agente desenvolvedor, DBA e QA possui sub-regras modulares. Caso o projeto seja em Python/FastAPI, Go ou Node.js, o CHEFE injeta a receita correspondente do projeto sem alterar a mecânica orquestradora.

> **Estado real:** o código lê as famílias da Doutrina por perfil de papel (padrão `arquitetura`, `ia`, `ecossistema`), e as regras de stack são específicas de .NET. O código do orquestrador implementa só a stack .NET (+ frontend React). Outras stacks são intenção de projeto: exigem antes uma família própria na Doutrina, senão o agente trabalha sem regras.

---

## 5. O Papel Crítico do Agente CHEFE (Tech Lead & Orquestrador)

1. **Decomposição Estruturada de Demandas:** Traduz o documento funcional do Analista de Requisitos em tarefas técnicas e contratos estritos.
2. **Controle de Dependências e Ordem de Execução:** Garante que o banco e os contratos existam antes de qualquer desenvolvimento de código.
3. **Isolamento de Contexto (Context Firewalls):** Prompts cirúrgicos contendo apenas as especificações pertinentes àquele agente.
4. **Resolução de Conflitos e Retroalimentação:** Limita loops de correção a 3 passagens de verificação (QA e revisor dividem o contador, `LIMITE_ITERACOES` em `graph.py`) antes de acionar intervenção humana (Human-in-the-Loop).

---

[🏠 README](../../README.md) · ⬅️ [SquadTI (componente)](../componentes/squadti.md) · [Catálogo de agentes da SquadTI](01-catalogo-de-agentes.md) ➡️

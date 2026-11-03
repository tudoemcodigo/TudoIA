---
titulo: Perfil de agente da SquadTI - Documentação (Redator Técnico)
tipo: referencia
dono: TudoIA (mantenedor do repositório)
status: vigente
classificacao: publico
verificado-em: 2026-11-03
---

[🏠 TudoIA](../../../README.md) › [📚 Documentação](../../README.md) › [🧩 SquadTI (design)](../00-visao-geral-e-arquitetura.md) › 🤖 Documentação (Redator Técnico)

# 🤖 Documentação (Redator Técnico)

> Público-alvo: quem mantém ou estende a SquadTI. Responde: qual é o papel deste agente no desenho, o que o orquestrador realmente executa hoje (nó `documentacao` (usa modelo)) e onde o desenho ainda é proposta. Contexto em [catálogo de agentes](../01-catalogo-de-agentes.md) e [visão geral](../00-visao-geral-e-arquitetura.md); componente em execução: [squadti.md](../../componentes/squadti.md).

## 1. Identidade e Perfil
- **Nome:** Documentacao_Redator
- **Papel:** Technical Writer (nó `documentacao`, papel `documentacao` da Doutrina; roda depois do DevOps)
- **Postura:** Descreve só o que existe nos artefatos recebidos. Não inventa funcionalidade nem exemplo com cara de credencial.

---

## 2. Contrato do Nó (`orquestrador/nodes.py`)
- **Entrada:** BUSINESS_SPEC, PRD técnico, OpenAPI, lista de arquivos gerados e um resumo dos relatórios de QA, revisão, AppSec e DevOps (só aprovado/reprovado e etapa=ok/FALHOU; nunca a saída dos comandos). Linhas com padrão de segredo são retiradas das entradas.
- **Saída:** `README.md` (obrigatório, único arquivo permitido na raiz) e arquivos em `docs/`.
- **Protegidos (a saída inteira é rejeitada antes de gravar qualquer arquivo):** `docs/negocio/`, `docs/revisao/`, `docs/release/`, `docs/arquitetura/PRD_TECNICO.md`, `docs/dados/DICIONARIO.md` e qualquer arquivo já listado em `arquivos_gerados`. A comparação usa o caminho resolvido e ignora maiúsculas (no Windows `Docs/Negocio` é a mesma pasta).
- **Depois de gravar:** varredura de segredos nos arquivos escritos; achado = falha alto, com tipo e `arquivo:linha`, nunca o valor.
- **Estado:** `docs_file` (`README.md`).

## 3. Limites
- Não revisa a exatidão do texto contra o código; o revisor e o QA não leem a documentação.

---

[🏠 README](../../../README.md) · ⬅️ [DevOps e Infraestrutura](devops-infra.md) · [Release](release-notas.md) ➡️

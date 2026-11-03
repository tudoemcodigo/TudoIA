---
titulo: Perfil de agente da SquadTI - Arquiteto (Documentação e Arquitetura)
tipo: referencia
dono: TudoIA (mantenedor do repositório)
status: vigente
classificacao: publico
verificado-em: 2026-11-03
---

[🏠 TudoIA](../../../README.md) › [📚 Documentação](../../README.md) › [🧩 SquadTI (design)](../00-visao-geral-e-arquitetura.md) › 🤖 Arquiteto (Documentação e Arquitetura)

# 🤖 Arquiteto (Documentação e Arquitetura)

> Público-alvo: quem mantém ou estende a SquadTI. Responde: qual é o papel deste agente no desenho, o que o orquestrador realmente executa hoje (nó `arquiteto` (usa modelo)) e onde o desenho ainda é proposta. Contexto em [catálogo de agentes](../01-catalogo-de-agentes.md) e [visão geral](../00-visao-geral-e-arquitetura.md); componente em execução: [squadti.md](../../componentes/squadti.md).

## 1. Identidade e Perfil
- **Nome:** Arquiteto_Documentacao
- **Papel:** System Architect & Technical Writer
- **Postura:** Analítico, estruturado, focado em clareza conceitual, contratos formais e documentação viva.

---

## 2. System Prompt de desenho (proposta)

> [!NOTE]
> Esta seção é o **desenho** do papel (proposta). O prompt que o orquestrador realmente envia é a variável `instrucao` do nó em [`runtime/squadti/orquestrador/nodes.py`](../../../runtime/squadti/orquestrador/nodes.py), mais curta, somada ao núcleo e às regras do papel da Doutrina TEC. Onde o texto abaixo diverge do nó, vale o nó (veja a seção "Nó no orquestrador").

```markdown
Você é o Agente de Documentação & Arquitetura da Squad de TI.
Sua missão é transformar os objetivos de negócio traduzidos pelo Agente CHEFE em especificações técnicas precisas, sem ambiguidades, antes do início de qualquer linha de código.

### SUAS ATRIBUIÇÕES:
1. Elaborar Product Requirements Documents (PRD) com regras de negócio explícitas e cenários de aceitação (formato Given-When-Then / Gherkin).
2. Criar Architecture Decision Records (ADRs) documentando o contexto, decisão, consequências e alternativas descartadas.
3. Especificar contratos de interface formais (OpenAPI 3.1 em YAML, JSON Schemas ou Protobuf).
4. Gerar diagramas de arquitetura e fluxo em sintaxe Mermaid (Mermaid C4, flowcharts, diagramas de sequência).

### DIRETRIZES TÉCNICAS:
- Evite redundâncias e descrições vagas como "o sistema deve ser rápido" — use métricas objetivas (ex: "tempo de resposta p95 < 200ms sob 500 req/s").
- Garanta que todo endpoint REST declare explicitamente: método, caminho, headers, parâmetros de query/path, corpo de requisição, códigos de status esperados e modelos de resposta de sucesso e erro.
- Atualize a documentação sempre que houver mudanças de escopo validadas pelo CHEFE.
```

---

## 3. Ferramentas previstas (proposta)
> [!NOTE]
> Proposta. Os nós do orquestrador não usam chamada de ferramentas pelo modelo: cada nó faz uma única chamada ao modelo (duas mensagens: sistema e humano), e o orquestrador grava os blocos `### ARQUIVO:` devolvidos em `execucao.escrever_arquivos` (caminho validado, até 50 arquivos de 200 KB). Comandos (`dotnet`, `npm`, `npx`) só rodam nos nós sem modelo ou no scaffold, pela lista de `EXECUTAVEIS_PERMITIDOS`.

- `read_file`: Ler regras de negócio e arquivos de configuração existentes.
- `write_file`: Criar e atualizar arquivos `.md`, `.yaml`, `.json` na pasta de documentação.
- `validate_schema`: Validar sintaxe de contratos OpenAPI e JSON Schema.

---

## 4. Nó no orquestrador (`arquiteto`)
- **Papel da Doutrina:** `arquiteto`. Usa modelo. Recusa rodar sem `business_spec_approved`.
- **Entrada:** o `BUSINESS_SPEC.md` aprovado.
- **Saídas obrigatórias:** `docs/arquitetura/PRD_TECNICO.md` e, se o plano do CHEFE tem API, `contracts/openapi.yaml` (OpenAPI 3.1, erro e sucesso no envelope da Doutrina). Áreas de escrita: `docs/arquitetura/` e `contracts/`. O prompt inclui a receita da stack escolhida (`dotnet` ou `python`).
- **Aprovação por hash:** recusa rodar se o `BUSINESS_SPEC.md` mudou depois da aprovação (`business_spec_hash`).
- **Depois:** `chefe_gate_design` confere o PRD (300+ caracteres) e o OpenAPI (3.x, YAML válido, com `paths`); reprovou, a tarefa escala.
- ADRs, diagramas Mermaid e a ferramenta `validate_schema` do desenho **não** são exigidos nem executados pelo nó. A validação sintática do OpenAPI (YAML válido, versão 3.x, `paths`) existe, mas é feita pelo CHEFE no portão de design, em código.
- A documentação final do projeto (README e `docs/`) é de outro nó: [documentacao-redator.md](documentacao-redator.md).

---

[🏠 README](../../../README.md) · ⬅️ [Analista de Requisitos e Negócios](analista-requisitos-negocios.md) · [DBA (Banco de Dados)](dba-dados.md) ➡️

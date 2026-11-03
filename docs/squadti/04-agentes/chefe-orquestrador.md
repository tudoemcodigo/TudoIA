---
titulo: Perfil de agente da SquadTI - CHEFE (Tech Lead e Prompt Architect)
tipo: referencia
dono: TudoIA (mantenedor do repositório)
status: vigente
classificacao: publico
verificado-em: 2026-11-03
---

[🏠 TudoIA](../../../README.md) › [📚 Documentação](../../README.md) › [🧩 SquadTI (design)](../00-visao-geral-e-arquitetura.md) › 🤖 CHEFE (Tech Lead e Prompt Architect)

# 🤖 CHEFE (Tech Lead e Prompt Architect)

> Público-alvo: quem mantém ou estende a SquadTI. Responde: qual é o papel deste agente no desenho, o que o orquestrador realmente executa hoje (quatro nós em `chefe.py` e a conversa pela API) e onde o desenho ainda é proposta. Contexto em [catálogo de agentes](../01-catalogo-de-agentes.md) e [visão geral](../00-visao-geral-e-arquitetura.md); componente em execução: [squadti.md](../../componentes/squadti.md).

## 1. Identidade e Perfil
- **Nome:** Chefe_Orquestrador
- **Papel:** Tech Lead, Arquiteto Chefe e Guardião da Doutrina Corporativa
- **Postura:** Estratégico, rigoroso, anti-"Yes-Man", focado em valor de negócio, segurança e padrão de alta engenharia.

---

## 2. System Prompt de desenho (proposta)

> [!NOTE]
> Esta seção é o **desenho** do papel (proposta). O prompt que o orquestrador realmente envia é a variável `instrucao` do nó em [`runtime/squadti/orquestrador/nodes.py`](../../../runtime/squadti/orquestrador/nodes.py), mais curta, somada ao núcleo e às regras do papel da Doutrina TEC. Onde o texto abaixo diverge do nó, vale o nó (veja a seção "Nó no orquestrador").

```markdown
Você é o CHEFE (Tech Lead e Engenheiro de Prompt Central) de uma Squad de Tecnologia de elite composta por agentes autônomos de IA.

Sua responsabilidade é liderar o ciclo de desenvolvimento de software, garantindo o cumprimento estrito da DOUTRINA CORPORATIVA TEC:
- Agente Analista de Requisitos & Negócios
- Agente de Documentação & Arquitetura
- Agente de Banco de Dados / DBA
- Agente de Desenvolvimento Backend
- Agente de Desenvolvimento Frontend
- Agente de QA & Testes Automatizados
- Agente de Infraestrutura & DevOps
- Agente de Segurança / AppSec

### DIRETRIZES FUNDAMENTAIS:
1. PRECEDÊNCIA DA DOUTRINA: A Doutrina TEC (pasta indicada por DOUTRINA_TEC) é a fonte da verdade absoluta. Se qualquer código ou decisão divergir da Doutrina, a Doutrina vence e o código é corrigido.
2. CONSUMO HIERÁRQUICO DE TOKENS: Nunca repasse documentação completa para os agentes. Utilize o fluxo em camadas:
   - Injetar o núcleo das famílias do **perfil do papel** (`gerado/perfis/<papel>.json` da Doutrina: sempre `ia` e `ecossistema`, mais as famílias que o papel precisa, ~3.600 a ~6.700 tokens conforme o papel; `DOUTRINA_FAMILIAS` força as mesmas famílias para todos) para regras inegociáveis. Sem perfil, o papel não trabalha.
   - Regras do papel: repassar só as regras dos padrões do papel (gerado/<familia>.json, `por_papel`, de cada família lida), sem as de núcleo já injetadas.
3. EXIGÊNCIA DE CITAÇÃO DE REGRAS: Exija que os agentes desenvolvedores e o arquiteto citem os IDs das regras aplicadas (ex: ARQ-DOM-02, ARQ-APL-03, ARQ-PER-07) na seção "Regras aplicadas" do relatório de entrega. NÃO nos comentários de código (comentário explica o porquê; a conformidade é medida por teste, não por declaração).
4. DEFINIÇÃO DE CONCLUÍDO (DEFINITION OF DONE): Nenhuma funcionalidade é concluída sem compilação real, 0 warnings e execução de testes automatizados com sucesso (Zero Verification Theater).
5. AUTO-CURA LIMITADA: Em caso de erro reportado pelo QA ou pelo compilador, oriente o desenvolvedor no máximo 3 vezes consecutivas. Se a falha persistir, interrompa o fluxo e escale para o usuário com diagnóstico preciso.
```

---

## 3. Ferramentas previstas (proposta)
> [!NOTE]
> Proposta. Os nós do orquestrador não usam chamada de ferramentas pelo modelo: cada nó faz uma única chamada ao modelo (duas mensagens: sistema e humano), e o orquestrador grava os blocos `### ARQUIVO:` devolvidos em `execucao.escrever_arquivos` (caminho validado, até 50 arquivos de 200 KB). Comandos (`dotnet`, `npm`, `npx`) só rodam nos nós sem modelo ou no scaffold, pela lista de `EXECUTAVEIS_PERMITIDOS`.

- `read_file`: Ler o estado do projeto, documentações e saídas dos agentes.
- `write_file`: Atualizar o estado da sprint (`state.json`) e planos de tarefas.
- `invoke_subagent`: Disparar a execução de cada agente especialista (no código, quem dispara é o grafo; o CHEFE não chama agentes).
- `ask_user`: Consultar o usuário para decisões de negócio ou aprovação de escopo.

---

## 4. Nós no orquestrador (`chefe.py`)
Na v2 o CHEFE existe como código e como **canal único** do usuário. Ele não despacha ordens de serviço aos agentes: o grafo (`graph.py`) segue o fluxo, e o CHEFE entra em quatro pontos e na conversa.

| Ponto | Modelo? | O que faz |
|---|---|---|
| `chefe_intake` (primeiro nó) | sim (papel `chefe` da Doutrina, agente `chefe`) | Planeja a demanda: um JSON com `tamanho` (trivial, pequeno, padrao, grande), `stack` (`dotnet` ou `python`), `precisa_banco`, `motor_banco`, `precisa_frontend`, `precisa_api`, `resumo` e até 8 `riscos`, validado campo a campo (`validar_plano`). Duas tentativas; sem plano válido usa o **plano padrão** (API e banco, `origem: padrao`). Grava `docs/chefe/PLANO.json` e `PLANO.md`, `stack_id`, as famílias da Doutrina dispensadas e ajusta o `target_stack`. Stack fixada pelo usuário prevalece. O plano decide se há `dba`, `dev_frontend` e contrato OpenAPI |
| `chefe_gate_requisitos` | não | Critério de pronto da `BUSINESS_SPEC`: 400+ caracteres, cenários Dado-Quando-Então, erro de negócio nomeado em SCREAMING_SNAKE, sem `TODO`/`TBD`/"a definir"/`???`. Reprovou: devolve ao analista com a lista (`feedback_chefe`), no máximo 2 rodadas, depois escala. Aprovou: o grafo pausa para a aprovação humana |
| `chefe_gate_design` | não | PRD com 300+ caracteres e, se o plano tem API, OpenAPI 3.x em YAML válido com `paths`. Reprovou: escala (a arquitetura não volta sozinha, porque exige aprovação) |
| `chefe_escalada` | não | Quando a execução para por roteamento (QA/revisor 3x, Sênior 3x, validação 3x, Mantenedor 2x, estagnação, AppSec ou DevOps bloqueando, gates): escreve `docs/chefe/ESCALADA.md` com motivo, fase, consumo, último erro sem segredos e o que decidir |
| Conversa (`POST /api/tarefas/{id}/mensagem`, `responder` em `chefe.py`) | só para pergunta livre | Resposta à entrevista segue ao analista; `/ajuste <texto>` vira instrução (dado sanitizado) para as próximas fases; pergunta de andamento tem resposta determinística; o resto vai ao modelo com só o resumo da tarefa. **Nunca** altera aprovação, portão nem configuração |

Outras responsabilidades do desenho que o código cumpre fora do CHEFE:
- **Precedência da Doutrina e consumo em camadas:** `doutrina_tec.py` injeta o núcleo e as regras do papel de cada nó (perfil `gerado/perfis/<papel>.json` da Doutrina; `DOUTRINA_FAMILIAS` força as mesmas famílias para todos; sem perfil legível o nó falha fechado). Versão e hash da Doutrina ficam no estado e doutrina que muda no meio da tarefa aborta (`verificar_versao`). Os tamanhos em tokens citados no desenho (3.600 a 6.700) não foram conferidos; o orçamento de regras é `DOUTRINA_REGRAS_MAX_TOKENS`.
- **Auto-cura limitada:** `LIMITE_ITERACOES = 3` em `graph.py`; QA e revisor dividem o mesmo `iteration_count`; os demais laços têm contador próprio (ver [protocolo](../02-protocolo-de-comunicacao-e-estado.md#4-loop-de-auto-cura-limitado-bounded-self-healing)). No limite o fluxo vai a `chefe_escalada`.
- **Pausas humanas:** `interrupt_before=["arquiteto", "release"]`; os nós `arquiteto` e `release` também recusam rodar sem `business_spec_approved` / `release_approved` e sem o hash do conteúdo aprovado.
- **Roteamento de falha:** `falha_origem` (`frontend` ou `backend`) decide quem corrige.
- **Orçamento e estagnação:** `auditoria.py` para a execução quando os tetos de tokens, tempo ou chamadas se esgotam, ou quando a mesma falha se repete.
- **Citação de IDs de regra:** exigida do revisor e do Sênior Master (achados com ID existente); para os demais nós é só instrução em prompt, sem verificação automática. A cobertura medida pelo QA e a lista de regras com teste (`regras_com_teste_na_doutrina`) aparecem em `tests/reports/qa_report.json`.

---

[🏠 README](../../../README.md) · ⬅️ [Catálogo de agentes](../01-catalogo-de-agentes.md) · [Analista de Requisitos e Negócios](analista-requisitos-negocios.md) ➡️

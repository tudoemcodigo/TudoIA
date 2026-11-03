---
titulo: Perfil de agente da SquadTI - Sênior Master
tipo: referencia
dono: TudoIA (mantenedor do repositório)
status: vigente
classificacao: publico
verificado-em: 2026-11-03
---

[🏠 TudoIA](../../../README.md) › [📚 Documentação](../../README.md) › [🧩 SquadTI (design)](../00-visao-geral-e-arquitetura.md) › 🤖 Sênior Master

# 🤖 Sênior Master

> Público-alvo: quem mantém ou estende a SquadTI. Responde: o que o nó `senior_master` (usa modelo, depois de medir em código) faz, o que bloqueia e como devolve o código ao desenvolvimento. Contexto em [catálogo de agentes](../01-catalogo-de-agentes.md); componente em execução: [squadti.md](../../componentes/squadti.md).

## 1. Identidade e Perfil
- **Nome:** Senior_Master
- **Papel:** o desenvolvedor mais exigente do time: critica gambiarra, código repetido, função que faz coisa demais, nome ruim, abstração desnecessária, falta de tratamento de erro, acoplamento e documentação pobre.
- **Postura:** só bloqueia o que dá para **conferir**. Opinião de modelo sem regra, arquivo e linha existentes é descartada.

---

## 2. Contrato do Nó (`orquestrador/qualidade.py`, `metricas.py`)
- **Posição no grafo:** depois do `revisor`, antes do `appsec`. Agente configurável: `senior`. Contexto da Doutrina: papéis `backend` e, se houver `frontend/`, `frontend`.
- **Medição determinística (sem modelo):** `metricas.medir` analisa `src/`, `app/` e `frontend/src/` (sem testes, `node_modules`, migrations, saídas de build; até 400 arquivos de 400 KB). Python é lido pela AST; C# e TypeScript por varredura de chaves (aproximada). Acima do primeiro limite o achado é `MEDIO`; acima do segundo, `ALTO` (bloqueia).

| ID | O que mede | Aviso / bloqueia |
|---|---|---|
| `QC-CPX-01` | complexidade de função | 12 / 20 |
| `QC-LEN-01` | linhas por função | 60 / 120 |
| `QC-PAR-01` | parâmetros por função | 6 / 10 |
| `QC-DUP-01` | duplicação (janela de 6 linhas) | 5% / 15% |
| `QC-DOC-01` | API pública sem documentação | 20% / 50% |
| `QC-GAM-01` a `04` | pendência (`TODO`...), erro engolido (`ALTO`), supressão de verificação, sobra de depuração | por padrão: BAIXO, ALTO, MEDIO, BAIXO |

- **Crítica do modelo:** recebe a medição e o código (até 50.000 caracteres, os arquivos mais suspeitos primeiro, sem linhas com padrão de segredo) e devolve `docs/qualidade/SENIOR.md` com `VEREDITO: APROVADO|REPROVADO` e achados `- [SEVERIDADE] ID caminho:linha descrição`, com ID da Doutrina ou `QC-*`. O veredito é lido por `revisao.decidir` (mesmas regras do revisor: achado com regra, arquivo ou linha inexistente vai para `nao_verificados`).
- **Aprovação:** veredito válido **e** nenhuma violação medida de severidade `ALTO`. Sem código de produção para avaliar = reprovado.
- **Saída:** `docs/qualidade/RELATORIO_SENIOR.json` (métricas, até 200 violações, veredito do modelo). Os achados `ALTO`/`MEDIO` medidos (até 60) entram em `achados_agentes`, insumo do [Livro de Lições](../licoes.md).
- **Estado:** `senior_passed`, `senior_report_file`, `rodadas_senior`, `falha_origem`, `last_error_log` (resumo para o desenvolvimento, sem segredos).
- **Rota:** reprovado volta ao dev indicado por `falha_origem`; 3 reprovações ou a mesma falha duas vezes escalam. Aprovado segue ao `appsec`.

## 3. Limites
- As métricas de C# e TypeScript são aproximadas (sem parser completo); falso positivo de complexidade é possível.
- Os limites são constantes em `metricas.py`; não há configuração por tarefa.
- Não mede cobertura nem desempenho; isso é do QA e da carga.

---

[🏠 README](../../../README.md) · ⬅️ [Release](release-notas.md) · [Hacker (AppSec ofensivo)](hacker-ofensivo.md) ➡️

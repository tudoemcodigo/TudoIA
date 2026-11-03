---
titulo: Perfil de agente da SquadTI - Release
tipo: referencia
dono: TudoIA (mantenedor do repositório)
status: vigente
classificacao: publico
verificado-em: 2026-11-03
---

[🏠 TudoIA](../../../README.md) › [📚 Documentação](../../README.md) › [🧩 SquadTI (design)](../00-visao-geral-e-arquitetura.md) › 🤖 Release

# 🤖 Release

> Público-alvo: quem mantém ou estende a SquadTI. Responde: qual é o papel deste agente no desenho, o que o orquestrador realmente executa hoje (nó `release` (sem modelo)) e onde o desenho ainda é proposta. Contexto em [catálogo de agentes](../01-catalogo-de-agentes.md) e [visão geral](../00-visao-geral-e-arquitetura.md); componente em execução: [squadti.md](../../componentes/squadti.md).

## 1. Identidade e Perfil
- **Nome:** Release
- **Papel:** Consolidador de entrega (nó `release`, **sem modelo** e **sem ação irreversível**)
- **Postura:** Só resume e pede aprovação. Quem versiona, cria tag e publica é o humano.

---

## 2. Contrato do Nó (`orquestrador/nodes.py`)
- **Pausa humana:** o grafo para antes do nó (`interrupt_before`). O nó também recusa rodar se `release_approved` não for `True` no estado (um resume cego não contorna a pausa). A aprovação é explícita: `python main.py aprovar-release --tarefa TASK-001`, nunca padrão.
- **Pré-condições (falha fechado):** `tests_passed`, `review_passed`, `security_passed`, `devops_passed` verdadeiros e `docs_file` presente.
- **Saída:** `docs/release/RELEASE_NOTES.md` com versão SemVer **sugerida** (`0.0.1` se não há versão anterior conhecida; com `ultima_versao` no estado o nó não escolhe o próximo número), versão e hash da Doutrina, lista de arquivos e resultado de QA, revisão, AppSec e DevOps.
- **Nunca faz:** git, commit, tag, push, publicação, nem chamada a modelo. A única escrita é o arquivo de notas, que passa por varredura de segredos.
- **Estado:** `release_approved`, `release_notes_file`; fase final `ENTREGA_CONCLUIDA`.

---

[🏠 README](../../../README.md) · ⬅️ [Documentação (Redator Técnico)](documentacao-redator.md) · [Visão geral](../00-visao-geral-e-arquitetura.md) ➡️

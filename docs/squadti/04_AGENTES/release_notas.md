# Especificação de Agente: Release

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

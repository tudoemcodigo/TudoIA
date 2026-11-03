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
- **Pré-condições (falha fechado):** `tests_passed`, `review_passed`, `security_passed`, `devops_passed`, `senior_passed`, `manutencao_passed` verdadeiros e `docs_file` presente. Se a validação em execução rodou, também `hacker_passed` e `macaco_passed` e carga sem reprovação; se foi pulada, tem de haver o motivo (`validacao_motivo`) e as notas dizem que o sistema não foi validado em execução.
- **Aprovação por hash:** `aprovar-release` grava o hash do pacote (especificação, PRD, OpenAPI, relatórios, revisão e documentação); o nó recusa se algum desses arquivos mudou depois.
- **Saída:** `docs/release/RELEASE_NOTES.md` com versão SemVer **sugerida** (`0.0.1` se não há versão anterior conhecida; com `ultima_versao` no estado o nó não escolhe o próximo número), versão e hash da Doutrina, lista de arquivos e resultado de QA, revisão, AppSec, DevOps, Sênior Master, hacker, macaco, carga e manutenibilidade. Escreve também `docs/proveniencia.json` (Doutrina, modelos por agente, tokens, hashes das aprovações e SHA-256 de cada arquivo; sem prompt nem resposta de modelo).
- **Nunca faz:** git, commit, tag, push, publicação, nem chamada a modelo. A única escrita é o arquivo de notas, que passa por varredura de segredos.
- **Estado:** `release_approved`, `release_notes_file`; fase final `ENTREGA_CONCLUIDA`.

---

[🏠 README](../../../README.md) · ⬅️ [Documentação (Redator Técnico)](documentacao-redator.md) · [Sênior Master](senior-master.md) ➡️

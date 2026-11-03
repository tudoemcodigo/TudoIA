---
titulo: Perfil de agente da SquadTI - Revisor de Código
tipo: referencia
dono: TudoIA (mantenedor do repositório)
status: vigente
classificacao: publico
verificado-em: 2026-11-03
---

[🏠 TudoIA](../../../README.md) › [📚 Documentação](../../README.md) › [🧩 SquadTI (design)](../00-visao-geral-e-arquitetura.md) › 🤖 Revisor de Código

# 🤖 Revisor de Código

> Público-alvo: quem mantém ou estende a SquadTI. Responde: qual é o papel deste agente no desenho, o que o orquestrador realmente executa hoje (nó `revisor` (usa modelo)) e onde o desenho ainda é proposta. Contexto em [catálogo de agentes](../01-catalogo-de-agentes.md) e [visão geral](../00-visao-geral-e-arquitetura.md); componente em execução: [squadti.md](../../componentes/squadti.md).

## 1. Identidade e Perfil
- **Nome:** Revisor_Codigo
- **Papel:** Code Reviewer (nó `revisor`, roda depois que o QA aprova e antes do AppSec)
- **Postura:** Cético e objetivo. Cita a regra da Doutrina e o `arquivo:linha` de cada achado; não reescreve código.

---

## 2. Contrato do Nó (`orquestrador/nodes.py`, `revisao.py`)
- **Entrada:** arquivos de `arquivos_gerados` sob `src/`, `tests/` e `frontend/` (até 60.000 caracteres no total; arquivo grande é truncado e o corte é declarado no prompt). Contexto da Doutrina: papel `backend` se houver `src/` ou `tests/`, papel `frontend` se houver `frontend/`. Linhas com padrão de segredo são trocadas por marcador antes de ir ao modelo.
- **Saída:** `docs/revisao/REVISAO.md` (única área de escrita permitida), com uma linha exata `VEREDITO: APROVADO` ou `VEREDITO: REPROVADO` e achados no formato `- [CRITICO|ALTO|MEDIO|BAIXO] ID-DA-REGRA arquivo:linha descrição`.
- **Regra do veredito (falha fechado):** sem a linha, com mais de uma, ou sem o arquivo = REPROVADO. Qualquer achado `CRITICO` reprova mesmo com `APROVADO`. O veredito só vale no arquivo que o modelo devolveu nesta chamada: texto dentro do código revisado é dado, nunca instrução.
- **Estado:** `review_passed`, `review_file`, `falha_origem` (`frontend` só se todos os achados CRITICO/ALTO forem em `frontend/`; senão `backend`).
- **Rota:** reprovado volta ao dev indicado por `falha_origem`. O revisor incrementa o mesmo `iteration_count` do QA: no limite de 3, a tarefa termina com escalação humana e o AppSec não roda.

## 3. Limites
- Revisão por modelo não prova ausência de defeito; não substitui o QA nem o AppSec.
- Arquivo truncado ou fora do limite total não foi revisto; o prompt exige que a revisão diga isso.

---

[🏠 README](../../../README.md) · ⬅️ [QA e Testes Automatizados](qa-testes.md) · [Segurança (AppSec)](appsec-seguranca.md) ➡️

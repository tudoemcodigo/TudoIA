---
titulo: Perfil de agente da SquadTI - Hacker (AppSec ofensivo)
tipo: referencia
dono: TudoIA (mantenedor do repositório)
status: vigente
classificacao: publico
verificado-em: 2026-11-03
---

[🏠 TudoIA](../../../README.md) › [📚 Documentação](../../README.md) › [🧩 SquadTI (design)](../00-visao-geral-e-arquitetura.md) › 🤖 Hacker (AppSec ofensivo)

# 🤖 Hacker (AppSec ofensivo)

> Público-alvo: quem mantém ou estende a SquadTI. Responde: o que o hacker faz contra o sistema gerado, enquanto ele roda, e o que ele bloqueia. Não é um nó próprio: é uma etapa do nó `validacao_runtime`, junto do [macaco](macaco-qa.md) e da [carga](carga-sre.md). Contexto em [catálogo de agentes](../01-catalogo-de-agentes.md); componente em execução: [squadti.md](../../componentes/squadti.md).

## 1. Identidade e Perfil
- **Nome:** Hacker
- **Papel:** AppSec ofensivo. Complementa o nó `appsec` (que só audita dependências e segredos) atacando o sistema **rodando**.
- **Postura:** cenários fixos e reproduzíveis. O modelo nunca escolhe comando nem alvo.

---

## 2. Contrato (`orquestrador/validacao.py`, `kits/kit_api.py`, `sandbox.py`)
- **Pré-condição:** o `Dockerfile` do projeto constrói e o sistema responde em `/saude` dentro do sandbox (rede Docker `--internal`, sem rota para a internet). Sem o Docker, a etapa é **pulada** (`validacao.modo = auto`) ou a tarefa escala (`sempre`); ver [SquadTI](../../componentes/squadti.md#️-segurança).
- **Ataque (sem modelo):** o kit de API lê o contrato OpenAPI e roda até 400 requisições, com semente fixa, em categorias com ID próprio: autenticação (`AUTH-*`), injeção (`INJ-01` a `05`), vazamento de erro (`ERR-01`), cabeçalhos (`HDR-01` a `03`), CORS (`CORS-01`, `02`), método (`MET-01`), atribuição em massa (`MASS-01`), limites (`LIM-01`, `02`), limite de taxa (`RATE-01`) e acesso a objeto de outro usuário (`IDOR-01`). Cada achado traz `id`, `severidade`, `categoria`, `endpoint`, `metodo`, `evidencia` e `reproducao` (sem credenciais).
- **Modelo (único uso):** o agente `hacker` (papel `appsec` da Doutrina) escreve `docs/seguranca/MODELO_DE_AMEACAS.md` (ativos, fronteiras de confiança, STRIDE por endpoint, abusos de regra de negócio). Não bloqueia: falha ou recusa do modelo só pula o documento.
- **Sem contrato OpenAPI** utilizável: só o modelo de ameaças é produzido, e o relatório diz isso em `notas`.
- **Veredito:** achado `CRITICO` ou `ALTO` **confirmado** reprova (`hacker_passed = False`); `MEDIO` e `BAIXO` ficam no relatório. O texto devolvido ao desenvolvimento traz só os bloqueantes, com como reproduzir, e passa pelo filtro de segredos.
- **Saída:** `tests/reports/hacker_report.json` (`achados`, `executado`, `modelo_de_ameacas`, `notas`, `aprovado`).
- **Estado:** `hacker_passed`, `hacker_report_file`, `validacao_executada`, `rodadas_runtime`; achados estruturados (sem prosa) em `achados_agentes`.
- **Rota:** reprovado volta ao dev (3 voltas, depois escala; a mesma falha duas vezes escala antes). Aprovado ou pulado segue ao `devops`.

## 3. Limites
- Cobre o que o contrato OpenAPI declara; não faz fuzzing de protocolo, DAST completo nem análise de cadeia de suprimentos.
- Sem token válido o kit testa a autenticação, mas não os fluxos autenticados em profundidade (`--token` é opcional no kit, e o orquestrador não o fornece).
- O sandbox só tem imagem de banco para `postgres`; outros motores sobem sem banco, e o sistema pode não passar na saúde.
- `ENTREGA_CONCLUIDA` continua não significando "segura": revisão humana de segurança segue necessária.

---

[🏠 README](../../../README.md) · ⬅️ [Sênior Master](senior-master.md) · [Macaco (QA de uso à força)](macaco-qa.md) ➡️

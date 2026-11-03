---
titulo: Perfil de agente da SquadTI - Macaco (QA de uso à força)
tipo: referencia
dono: TudoIA (mantenedor do repositório)
status: vigente
classificacao: publico
verificado-em: 2026-11-03
---

[🏠 TudoIA](../../../README.md) › [📚 Documentação](../../README.md) › [🧩 SquadTI (design)](../00-visao-geral-e-arquitetura.md) › 🤖 Macaco (QA de uso à força)

# 🤖 Macaco (QA de uso à força)

> Público-alvo: quem mantém ou estende a SquadTI. Responde: como o macaco usa o sistema gerado "do pior jeito possível" e o que ele reprova. Etapa **sem modelo** do nó `validacao_runtime` (junto do [hacker](hacker-ofensivo.md) e da [carga](carga-sre.md)). Contexto em [catálogo de agentes](../01-catalogo-de-agentes.md); componente em execução: [squadti.md](../../componentes/squadti.md).

## 1. Identidade e Perfil
- **Nome:** Macaco
- **Papel:** QA exploratório automático. Complementa o `qa_testes` (que roda a suíte que o próprio desenvolvimento escreveu) com entrada que ninguém previu.
- **Postura:** determinístico. Semente fixa: a mesma sequência se repete, e cada achado traz como reproduzir.

---

## 2. Contrato (`orquestrador/validacao.py`, `kits/kit_api.py`, `kits/kit_ui.py`)
- **Pré-condição:** o sistema sobe no sandbox e responde em `/saude` (ver [hacker](hacker-ofensivo.md#2-contrato-orquestradorvalidacaopy-kitskit_apipy-sandboxpy)). Sem Docker, a etapa é pulada ou a tarefa escala conforme `validacao.modo`.
- **Macaco de API:** com o contrato OpenAPI, até 600 requisições com entrada errada de todo jeito: tipos trocados, texto hostil (SQL, XSS, travessia de caminho, `\u0000`, emoji em massa, números gigantes), campos faltando, JSON malformado. IDs `MAC-01` a `MAC-05` e `ERR-01` (vazamento de erro).
- **Macaco de interface:** só se o plano do CHEFE tem frontend **e** a raiz do sistema serve HTML. Roda em container Playwright na mesma rede: clica em tudo que é clicável, digita texto hostil em todo campo, aperta teclas aleatórias, volta e avança, redimensiona. Duração `validacao.ui_segundos` (padrão 60, de 10 a 600). IDs `UI-01` a `UI-06`. Se a imagem do Playwright não puder rodar, o fato é registrado em `notas` e a etapa segue.
- **Veredito:** achado `CRITICO` ou `ALTO` reprova (`macaco_passed = False`); `MEDIO` e `BAIXO` ficam no relatório. Se todos os bloqueantes são de interface, o erro volta ao `dev_frontend`; senão, ao `dev_backend`.
- **Saída:** `tests/reports/macaco_report.json` (`achados`, `executado`, `notas`, `aprovado`).
- **Estado:** `macaco_passed`, `macaco_report_file`, `validacao_executada`, `rodadas_runtime`.

## 3. Limites
- Sem contrato OpenAPI e sem frontend, o macaco não executa nada (`executado: false`).
- O macaco de interface depende da imagem `mcr.microsoft.com/playwright/python` (grande); em máquina sem espaço ou rede, fica só a parte de API.
- Acha defeito, não prova a ausência dele.

---

[🏠 README](../../../README.md) · ⬅️ [Hacker (AppSec ofensivo)](hacker-ofensivo.md) · [Carga (DevOps/SRE)](carga-sre.md) ➡️

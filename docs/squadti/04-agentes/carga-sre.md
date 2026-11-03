---
titulo: Perfil de agente da SquadTI - Carga (DevOps/SRE)
tipo: referencia
dono: TudoIA (mantenedor do repositório)
status: vigente
classificacao: publico
verificado-em: 2026-11-03
---

[🏠 TudoIA](../../../README.md) › [📚 Documentação](../../README.md) › [🧩 SquadTI (design)](../00-visao-geral-e-arquitetura.md) › 🤖 Carga (DevOps/SRE)

# 🤖 Carga (DevOps/SRE)

> Público-alvo: quem mantém ou estende a SquadTI. Responde: como a Squad mede até quantos usuários simultâneos o sistema gerado aguenta e o que isso reprova. Etapa **sem modelo** do nó `validacao_runtime`. Contexto em [catálogo de agentes](../01-catalogo-de-agentes.md); componente em execução: [squadti.md](../../componentes/squadti.md).

## 1. Identidade e Perfil
- **Nome:** Carga_SRE
- **Papel:** teste de carga e capacidade. Complementa o `devops` (higiene estática) medindo o comportamento sob uso.
- **Postura:** o número que sai é **capacidade relativa** ao teto de CPU e memória do sandbox. Serve para comparar versões e achar gargalo, não é a capacidade de produção.

---

## 2. Contrato (`orquestrador/carga.py`, `validacao.py`)
- **Gerador:** [k6](https://k6.io/) em container irmão, na rede interna do sandbox (imagem fixada por digest). Cada degrau é uma execução curta e independente (rampa de 10 s, sustento, descida de 10 s; 40 s no total); no primeiro degrau que viola o SLO a subida **para**.
- **Alvos:** a raiz e os `GET` do contrato sem parâmetro de caminho nem de consulta obrigatórios (até 20). Nada que escreva.
- **Perfis (`validacao.carga`):** `escalado` (padrão: 25, 50, 100, 200, 400 usuários), `completo` (500, 1000, 2500, 5000, 10000; só faz sentido com o gerador em outra máquina, porque aqui os dois disputam a mesma CPU), `nunca`.
- **Quando roda:** há contrato OpenAPI, `carga != nunca` e o plano não é `trivial` (ou `carga = completo`).
- **SLO (`validacao.slo`):** p95 ≤ 800 ms, p99 ≤ 2000 ms e taxa de erro (5xx e falha de conexão) ≤ 1%, por padrão. Métrica que o k6 não devolveu reprova o degrau (falha fechada).
- **Aprovação:** o sistema sustenta, dentro do SLO, o mínimo de usuários do tamanho do plano: `trivial` 25, `pequeno` 50, `padrao` 100, `grande` 200.
- **Diagnóstico do gargalo:** morte por falta de memória (OOM), CPU do alvo ≥ 85% do limite, memória ≥ 85%, muitas falhas com recursos folgados (conexões, pool do banco, timeout em cadeia) ou latência com recursos folgados (banco, bloqueio, E/S).
- **Saída:** `tests/reports/carga_report.json` (perfil, SLO, degraus com p95, p99, erro e vazão, `estavel_ate_vus`, `saturou_em_vus`, `gargalo`, `minimo_vus`, `aprovado`, `nota`).
- **Estado:** `carga_passed` (`None` se não rodou), `carga_report_file`. Reprovado devolve ao desenvolvimento backend o resumo com o gargalo provável.

## 3. Limites
- O container do alvo tem teto de 1 GB de memória, 1 CPU e 512 processos (padrão do sandbox); o resultado reflete esse teto.
- Sem banco de sandbox para motores diferentes de `postgres`, o gargalo de dados não é exercitado de forma realista.
- Não testa escrita nem fluxos autenticados (só `GET` sem parâmetros).

---

[🏠 README](../../../README.md) · ⬅️ [Macaco (QA de uso à força)](macaco-qa.md) · [Mantenedor](mantenedor-manutencao.md) ➡️

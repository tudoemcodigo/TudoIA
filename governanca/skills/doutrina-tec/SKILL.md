---
name: doutrina-tec
description: Doutrina TEC, fonte da verdade de como a TEC constrói software, em dez famílias. REQ (requisitos), DAD (dados), FRT (frontend React/TypeScript), QUA (testes e qualidade), SEC (segurança, ASVS 5.0 L3), DOC (documentação), ARQ (serviços .NET, Clean Architecture, CQRS, componentes TEC.*), CMP (construir, auditar e publicar os componentes TEC.*), IA (comportamento de agentes, segurança operacional, privacidade de dados, orquestração multiagente, skills e MCP) e ECO (mapa do ecossistema, precedência da verdade, glossário, adoção). Use ao criar, alterar ou revisar serviço, componente, domínio, command/query, API, persistência, segurança, mensageria, observabilidade, testes, CI, template (dotnet new tec-project) ou agente, ou quando o usuário citar "Doutrina TEC", "padrão TEC" ou IDs como ARQ-PER-13, CMP-AUD-01, IA-OPS-01 e ECO-PRE-01.
---

# Doutrina TEC

A doutrina é a fonte da verdade; esta skill só roteia. Defina `DOUTRINA_TEC` como a pasta do repositório `Doutrina`;
o caminho vem somente dessa variável (ECO-CON-09). Se o servidor MCP `doutrina-tec` estiver registrado, prefira-o aos arquivos.

Se `$DOUTRINA_TEC/gerado/manifesto.json` não estiver legível, não trabalhe: relate e peça o caminho (ECO-CON-01).
Registre `versao` e `hash` do manifesto no relato final (ECO-CON-02).

**Precedência (ECO-PRE-07):** a Doutrina vence qualquer outra skill em conflito. O agente executa só a parte compatível da skill
e relata o conflito com o ID da regra e o trecho da skill (arquivo e seção), sem obedecer nem corrigir em silêncio.
Em trabalho de serviço ou componente TEC, carregue esta skill antes das demais.

## Qual família

| Tarefa | Família (núcleo) |
|---|---|
| Serviço .NET (API, worker, domínio, persistência, CI do serviço) | `arquitetura` |
| Biblioteca `TEC.*`, `tec-workflows`, publicação de pacote | `componentes` |
| Como o agente age, segredos, privacidade, orquestração, skills/MCP | `ia` |
| Quem manda em quê, nomes, consumo da doutrina, versão adotada | `ecossistema` |
| Levantar, escrever ou aprovar requisito, critério de aceite, BUSINESS_SPEC | `requisitos` |
| Modelo de dados, migration, índice, multi-tenant, backup, privilégios (qualquer SGBD) | `dados` |
| Interface React + TypeScript, acessibilidade, segurança de SPA, testes de UI | `frontend` |
| Estratégia de testes, cobertura (90%), integração, contrato, e2e, carga, CI de testes | `qualidade` |
| Ameaças, SDL, cadeia de suprimentos, segredos, identidade, incidentes, segurança de LLM/agentes (ASVS 5.0 L3) | `seguranca` |
| README, ADR, arquitetura, runbook, documentação como código, docs para agentes | `documentacao` |

Atalho por papel: `$DOUTRINA_TEC/gerado/perfis/<papel>.md` lista, entre todas as famílias, os padrões do papel (requisitos, arquiteto, dba, backend, frontend, qa, appsec, devops, documentacao, chefe).

## Procedimento (poupe tokens)

1. Leia `$DOUTRINA_TEC/gerado/<familia>-nucleo.md` das famílias que se aplicam (regras inegociáveis). Se o `AGENTS.md` do projeto já
   traz o bloco `doutrina-tec`, ele é esse núcleo: não releia.
2. Leia `$DOUTRINA_TEC/INDEX.md` e escolha **só** os padrões cuja coluna *Leia quando* casa com a tarefa.
3. Dos padrões escolhidos, leia **apenas o bloco `## Regras`** (do cabeçalho até o próximo `## `). Abra a justificativa só se a regra for ambígua.
4. Para revisão ampla, use `$DOUTRINA_TEC/gerado/<familia>-regras.md` em vez de abrir os padrões.
5. Ao implementar ou revisar, cite o ID da regra (`ARQ-DOM-02`) em comentários de revisão e no relato final.
6. Regra com `evidencia` tem prova real (teste ou arquivo em outro repositório): rode ou confira em vez de confiar.

## Regras de conduta

- `MUST` não se contorna: se atrapalha, diga qual é e proponha ADR.
- Doutrina desatualizada em relação ao template ou componente: relate, não corrija em silêncio.
- Documentação de API dos componentes `TEC.*` está nos repositórios `lib-tec-*` (links em "Referências nos componentes" de cada padrão).
- Para **editar** a doutrina, siga `$DOUTRINA_TEC/AGENTS.md` e `GOVERNANCA.md`; nunca edite `INDEX.md`, `llms.txt`, `gerado/` nem o bloco `doutrina-tec` de um projeto.

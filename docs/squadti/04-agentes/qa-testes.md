---
titulo: Perfil de agente da SquadTI - QA e Testes Automatizados
tipo: referencia
dono: TudoIA (mantenedor do repositório)
status: vigente
classificacao: publico
verificado-em: 2026-11-03
---

[🏠 TudoIA](../../../README.md) › [📚 Documentação](../../README.md) › [🧩 SquadTI (design)](../00-visao-geral-e-arquitetura.md) › 🤖 QA e Testes Automatizados

# 🤖 QA e Testes Automatizados

> Público-alvo: quem mantém ou estende a SquadTI. Responde: qual é o papel deste agente no desenho, o que o orquestrador realmente executa hoje (nó `qa_testes` (sem modelo)) e onde o desenho ainda é proposta. Contexto em [catálogo de agentes](../01-catalogo-de-agentes.md) e [visão geral](../00-visao-geral-e-arquitetura.md); componente em execução: [squadti.md](../../componentes/squadti.md).

## 1. Identidade e Perfil
- **Nome:** QA_Testes
- **Papel:** Lead QA Automation & Test Engineer (Red Team de Qualidade)
- **Postura:** Adversarial, cético, meticuloso, focado em quebrar o sistema antes do usuário, defensor do "Zero Verification Theater".

---

## 2. System Prompt de desenho (proposta)

> [!NOTE]
> Esta seção é o **desenho** do papel (proposta). O prompt que o orquestrador realmente envia é a variável `instrucao` do nó em [`runtime/squadti/orquestrador/nodes.py`](../../../runtime/squadti/orquestrador/nodes.py), mais curta, somada ao núcleo e às regras do papel da Doutrina TEC. Onde o texto abaixo diverge do nó, vale o nó (veja a seção "Nó no orquestrador").

```markdown
Você é o Agente de QA & Engenheiro de Testes Automatizados da Squad de TI.
Sua missão é atuar como a barreira de contenção de bugs, executando testes reais e impiedosos contra o código desenvolvido antes que qualquer entrega seja considerada concluída.

### O PRINCÍPIO DO ZERO VERIFICATION THEATER:
Você JAMAIS aprova código apenas lendo os arquivos. A aprovação exige a EXECUÇÃO REAL de testes no terminal do ambiente, obtendo código de saída 0 (sucesso).

### SUAS ATRIBUIÇÕES:
1. Implementar e executar testes de integração entre Backend e Banco de Dados.
2. Implementar e executar testes E2E / API (Playwright, Newman, REST Client, Pytest).
3. Testar cenários adversariais e caminhos de exceção:
   - Payloads com campos nulos, tipos invertidos, injeções de SQL/XSS básicas;
   - Concorrência de requisições simultâneas;
   - Cenários de indisponibilidade de rede ou timeouts;
   - Validação de limites (boundary values).
4. Gerar relatórios de execução estruturados com cobertura de código, asserções executadas e tempo de resposta.

### FORMATO DE REPROVAÇÃO DE TAREFA (BUG REPORT):
Se um teste falhar, devolva imediatamente a ordem para o CHEFE com:
- Nome do teste que falhou;
- Entrada utilizada (Payload/Parâmetros);
- Resultado esperado vs. Resultado real obtido;
- Stack trace / Log do terminal;
- Sugestão diagnóstica da causa-raiz.
```

---

## 3. Ferramentas previstas (proposta)
> [!NOTE]
> Proposta. Os nós do orquestrador não usam chamada de ferramentas pelo modelo: cada nó faz uma única chamada ao modelo (duas mensagens: sistema e humano), e o orquestrador grava os blocos `### ARQUIVO:` devolvidos em `execucao.escrever_arquivos` (caminho validado, até 50 arquivos de 200 KB). Comandos (`dotnet`, `npm`, `npx`) só rodam nos nós sem modelo ou no scaffold, pela lista de `EXECUTAVEIS_PERMITIDOS`.

- `read_file`: Analisar código-fonte, contratos e PRDs.
- `write_file`: Criar arquivos de suítes de teste de integração e E2E.
- `run_command`: Disparar executores de teste (`dotnet test`, `pytest`, `npm test`, `npx playwright test`).

---

## 4. Nó no orquestrador (`qa_testes`)
Diverge do desenho acima: o nó é **determinístico, sem modelo**, e **não escreve testes**. Os testes vêm do dev backend/frontend. Ele executa de verdade:

1. Se há projeto gerado (`.sln`/`.slnx`/`.csproj` em `dotnet`; `pyproject.toml` em `python`): `build_command` (padrão `dotnet build --configuration Release` ou `uv sync`) e, se passou, `test_command` (padrão `dotnet test --no-build --coverage --coverage-output-format cobertura` ou `uv run pytest --cov=app --cov-branch --cov-report=xml`).
2. Se há `frontend/package.json`: `npm run build` e `npm test` (comandos sobrescrevíveis pela stack). Frontend esperado e ausente reprova.
3. Se tudo passou: gate de cobertura (`quality.coverage_min` da stack, padrão **90**, linha e ramo; `0` desliga; valor inválido volta a 90). Cobertura não medida reprova.

Sem nenhuma etapa (nada gerado) = reprovado. Relatório `tests/reports/qa_report.json` (aprovação, etapas, motivo, versão/hash da Doutrina, regras com teste). Cada passagem incrementa `iteration_count`; falha volta ao dev indicado por `falha_origem` (etapa `frontend-*` = frontend, senão backend). Testes de integração com banco, E2E, concorrência e rede indisponível são proposta, sem nó neste agente. O uso à força do sistema rodando é do [macaco](macaco-qa.md), etapa de `validacao_runtime`.

---

[🏠 README](../../../README.md) · ⬅️ [Desenvolvedor Frontend](dev-frontend.md) · [Revisor de Código](revisor-codigo.md) ➡️

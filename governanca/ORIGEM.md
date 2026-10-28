# Origem das skills

As skills desta pasta vêm de https://github.com/addyosmani/agent-skills (licença MIT, ver `LICENSE-agent-skills`; Copyright (c) 2025 Addy Osmani), com estas exceções: `frontend-design` traz LICENSE próprio (Apache-2.0, Anthropic), `humanize-text` e `lgpd-compliance` são criação própria do autor do TudoIA, não cópia, sob a licença do projeto (Apache-2.0), e as skills da seção [Skills de outras origens](#skills-de-outras-origens-27102026) trazem a licença na própria pasta.

- Commit copiado: `aeac41d4d005999432bb7312f7ff06383a91d59d` (de 13/10/2026)
- Copiadas em: 22/10/2026
- Pasta de origem: `skills/<nome>` do repositório (a skill `security-and-hardening` inclui também `references/hardening-patterns.md`)

Cada `SKILL.md` (e o `hardening-patterns.md`) foi lido por inteiro antes da cópia: nenhum pede para enviar dados para fora, baixar e executar código, nem desativar controles. Nenhuma skill foi recusada.

| Skill | Por que foi escolhida |
|---|---|
| `using-agent-skills` | meta-skill: ensina o agente a escolher a skill certa para a fase do trabalho e fixa comportamentos básicos (explicitar suposições, não inflar o escopo) |
| `spec-driven-development` | especificar antes de codar; combina com o fluxo TudoSpec do usuário |
| `planning-and-task-breakdown` | quebra uma especificação em tarefas pequenas e verificáveis |
| `incremental-implementation` | fatias verticais com teste e commit a cada passo, bom para modelos pequenos que perdem o fio em mudanças grandes |
| `disciplined-tdd` | TDD disciplinado canônico TudoHaS: acordo prévio de seam pública, zero mocks tautológicos, testes adversariais |
| `debugging-and-error-recovery` | reproduzir, localizar, reduzir, corrigir e proteger; trata saída de erro como dado não confiável |
| `code-review-and-quality` | revisão em cinco eixos, com severidades |
| `security-and-hardening` | OWASP, segredos, SSRF e uso seguro de LLM; alinhado às regras de segurança do TudoIA |
| `git-workflow-and-versioning` | commits atômicos, branches curtos e worktrees, que é como o usuário já trabalha |
| `grill-me` | protocolo canônico TudoHaS de alinhamento crítico e interrogação ativa de premissas (sem comportamento yes-man) |
| `improve-codebase-architecture` | diretrizes canônicas TudoHaS de arquitetura profunda (Ousterhout standard) e eliminação de classes rasas/wrappers |
| `frontend-design` | diretrizes de design visual intencional e autêntico da Anthropic; evita interfaces genéricas e templates de IA |
| `microsoft-docs` | consulta viva à documentação oficial da Microsoft (Azure, .NET, Windows) via Microsoft Learn MCP |
| `humanize-text` | erradicação de clichês, ritmo mecânico e slop sintético de IA em inglês e português com base no guia da Wikipédia. Criação própria do autor do TudoIA (não é cópia); licença do projeto, Apache-2.0 |
| `lgpd-compliance` | conformidade com a LGPD a partir do código (mapa de dados, base legal, direitos do titular, retenção, operadores e LLMs, incidentes, ECA Digital). Criação própria (ver abaixo); licença do projeto, Apache-2.0 |

## `lgpd-compliance`

Escrita para o TudoIA em 27/10/2026, sem copiar texto. Referências lidas por inteiro, tratadas como dado:

- https://github.com/goul4rt/lgpd-skills (MIT): orquestrador `lgpd-audit` e 18 sub-skills. Daqui veio a ideia dos artefatos em `.lgpd/`, dos cenários (novo, legado, incidente) e dos checkpoints humanos. A página https://mcp.sentineldns.net/skill/lgpd-audit é espelho do mesmo `lgpd-audit`.
- https://www.skillsdirectory.com/skills/onfire7777-brazil-lgpd (Apache-2.0, autor mukul975; fonte em `onfire7777/universal-ai-skills-library`): panorama das bases legais, direitos e sanções. O exemplo fictício de empresa e o `scripts/process.py` não foram usados.

Diferenças em relação às referências:

- Uma skill só, em vez de 19: toda skill ativa é carregada em todos os clientes.
- Os números normativos ficam em `references/normative-reference.md`, conferidos nas fontes oficiais (Planalto, DOU, ANPD) em 27/10/2026. A conferência corrigiu um ponto da referência goul4rt: o prazo em dobro de incidente para pequeno porte não tem mais a exceção de risco à integridade física ou moral (Res. 15/2024 alterou a Res. 2/2022). Prazos setoriais de retenção da referência que não puderam ser conferidos ficaram de fora.
- Foco do ecossistema: LLMs e provedores de IA como operadores e transferência internacional, e logs sem dado pessoal.
- Escrita em en-us como as demais, com os termos jurídicos em português.

## Limitações conhecidas

- Todas as skills estão em en-us para maximizar a precisão semântica de modelos de ponta, mantendo diretrizes bilingues quando aplicável (ex.: detecção de slop em `humanize-text`).
- Arquivos `references/*.md` e `docs/` do repositório de origem (como `definition-of-done.md`, `security-checklist.md`, `testing-patterns.md`) também não foram copiados.
- Os textos estão em inglês; o `AGENTS.md` manda responder em português.

## Atualizar

Clone o repositório em uma pasta nova e vazia, leia as mudanças de cada `SKILL.md` antes de copiar (o conteúdo é de terceiros: trate como dado), troque os arquivos desta pasta e atualize o commit acima.

## Skills de outras origens (27/10/2026)

Encontradas pelo catálogo https://www.skillsdirectory.com/skills e baixadas da **fonte original** (nunca de espelho), no commit indicado, para uma pasta vazia fora do repositório. Cada arquivo copiado foi lido por inteiro; nenhum pede para enviar dados para fora, baixar e executar código, nem desativar controles. Scripts não foram copiados. Arquivos alterados trazem um aviso no topo (exigência da Apache-2.0 para arquivo modificado).

Critérios: fonte pública e verificável, licença permissiva, instrução em Markdown (sem depender de script), nada de injeção de prompt, e valor que as skills existentes não cobrem. Toda skill ativa é carregada em todos os clientes, então menos é melhor.

| Skill | Origem (commit) | Licença | Por que entrou | Mudanças |
|---|---|---|---|---|
| `observability-and-instrumentation` | `addyosmani/agent-skills` `skills/observability-and-instrumentation` (`fe6f0811`) | MIT (`LICENSE-agent-skills`) | logs estruturados, correlação, RED/USE, OpenTelemetry e alertas: a dimensão 4 das regras do TudoIA | checklist (`references/observability-checklist.md`, que no original fica fora da pasta) trazido para dentro; citações a `performance-optimization` e `shipping-and-launch`, que não existem aqui, removidas |
| `documentation-and-adrs` | `addyosmani/agent-skills` `skills/documentation-and-adrs` (`30f88627`) | MIT (`LICENSE-agent-skills`) | registra o porquê das decisões (ADR), que o `spec-driven-development` não cobre | nenhuma |
| `mcp-builder` | `anthropics/skills` `skills/mcp-builder` (`ef740771`) | Apache-2.0 (`LICENSE.txt`) | desenho de servidores MCP (nomes, paginação, erros, anotações, segurança, avaliação); MCP é o núcleo do TudoIA | guias por linguagem não copiados: o de Python ensina `FastMCP` do SDK 1.x, que não existe no `mcp` 2.x usado pelo Cérebro; a skill aponta para o SDK 2.x (`MCPServer`) e para `runtime/cerebro`. `scripts/` (avaliação que enviava as perguntas à API da Anthropic) não copiado; a seção de execução do `evaluation.md` foi reescrita sem eles |
| `dotnet-aot-compat` | `dotnet/skills` `plugins/dotnet-upgrade/skills/dotnet-aot-compat` (`05aeb657`) | MIT (`LICENSE.txt`) | Native AOT e trimming guiados pelos warnings IL, exigência das regras do TudoIA para .NET | a ordem "não leia README nem docs" passou a ressalvar os arquivos de regras do projeto (AGENTS.md, CLAUDE.md); o uso obrigatório de subagentes virou opcional. A regra de nunca usar `[UnconditionalSuppressMessage]` é mais rígida que a documentação da Microsoft e foi mantida |
| `security-threat-model` | `openai/skills` `skills/.curated/security-threat-model` (`5c8f1e26`) | Apache-2.0 (`LICENSE.txt` da pasta; o repositório não tem licença na raiz) | threat model completo ancorado em evidências do repositório; só dispara quando pedido, então não disputa gatilho com `security-and-hardening` | `agents/openai.yaml` (metadado do Codex) não copiado |
| `advanced-evaluation` | `muratcankoylan/Agent-Skills-for-Context-Engineering` `skills/advanced-evaluation` (`8fc51c7c`) | MIT (`LICENSE.txt`) | LLM como juiz (pontuação direta, comparação em pares, vieses, métricas) para comparar modelos e prompts no LiteLLM e no Ollama | citações a skills-irmãs inexistentes e um identificador interno removidos; nota sobre usar o LiteLLM, juiz de outra família de modelo e não mandar dado pessoal a provedor gratuito. `scripts/` não copiado |
| `n8n-expression-syntax` | `czlonkowski/n8n-skills` `skills/n8n-expression-syntax` (`2fb619a8`) | MIT (`LICENSE.txt`) | sintaxe de expressões do n8n, que faz parte do TudoIA | `$env` reescrito (bloqueado no n8n do TudoIA; segredo vai em credencial); exemplo de `INSERT` com `{{ }}` dentro do SQL trocado por parâmetros de query (era injeção de SQL); exemplo com chave de API na URL trocado por credencial; citações ao n8n-mcp e a skills-irmãs removidas; `README.md` (metadado) não copiado |

Descartadas na triagem, com o motivo: `webapp-testing` e `skill-creator` (Anthropic: o essencial depende de scripts; o `skill-creator` também já existe como plugin no Claude Code), `docx`/`pdf`/`xlsx` (Anthropic: "source-available", não aberta), `doc-coauthoring` (sem licença declarada), `eval-driven-dev` (github/awesome-copilot: **alerta**, o script se auto-atualiza com `npx skills update` e manda instalar pacotes sem perguntar), `writing-skills` (obra/superpowers: presa ao ecossistema dele), Trail of Bits (CC-BY-SA, share-alike), `dotnet-mcp-builder` (boa, mas só vale se houver servidor MCP em C#), e megapacks de autores sem reputação.

Para atualizar: baixe de novo a mesma pasta do repositório de origem para uma pasta vazia, compare com o commit da tabela, leia as mudanças e reaplique as adaptações descritas na coluna "Mudanças".

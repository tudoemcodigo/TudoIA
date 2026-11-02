# Origem das skills

As skills desta pasta vêm de https://github.com/addyosmani/agent-skills (licença MIT, ver `LICENSE-agent-skills`; Copyright (c) 2025 Addy Osmani), com estas exceções: `frontend-design` traz LICENSE próprio (Apache-2.0, Anthropic), `humanize-text` e `lgpd-compliance` são criação própria do autor do TudoIA, não cópia, sob a licença do projeto (Apache-2.0), `disciplined-tdd`, `grill-me` e `improve-codebase-architecture` são canônico TudoIA (conteúdo próprio, não copiado do repositório do Osmani), `microsoft-docs` tem fonte própria (origem e licença ainda não registradas; verificar antes da próxima atualização), `doutrina-tec` é criação própria do ecossistema TEC (repositório Doutrina, Apache-2.0; ver [Modificações para o TudoIA](#modificações-para-o-tudoia-2026-11-01)), e as skills da seção [Skills de outras origens](#skills-de-outras-origens-27102026) trazem a licença na própria pasta.

- Commit copiado: `aeac41d4d005999432bb7312f7ff06383a91d59d` (de 13/10/2026)
- Copiadas em: 22/10/2026
- Pasta de origem: `skills/<nome>` do repositório (a skill `security-and-hardening` inclui também `references/hardening-patterns.md`)

Cada `SKILL.md` (e o `hardening-patterns.md`) foi lido por inteiro antes da cópia: nenhum pede para enviar dados para fora nem desativar controles. A afirmação anterior de que nenhum pede para baixar e executar código era falsa para `microsoft-docs` (fallback `npx @microsoft/learn-cli` / `npm install -g`) e `mcp-builder` (`npx @modelcontextprotocol/inspector`): em 01/11/2026 esses comandos passaram a exigir pedido do usuário e versão fixada e lida (IA-FER-02; ver a seção de modificações). Nenhuma skill foi recusada.

| Skill | Por que foi escolhida |
|---|---|
| `using-agent-skills` | meta-skill: ensina o agente a escolher a skill certa para a fase do trabalho e fixa comportamentos básicos (explicitar suposições, não inflar o escopo) |
| `spec-driven-development` | especificar antes de codar; combina com o fluxo TudoSpec do usuário |
| `planning-and-task-breakdown` | quebra uma especificação em tarefas pequenas e verificáveis |
| `incremental-implementation` | fatias verticais com teste e commit a cada passo, bom para modelos pequenos que perdem o fio em mudanças grandes |
| `disciplined-tdd` | TDD disciplinado canônico TudoIA: acordo prévio de seam pública, zero mocks tautológicos, testes adversariais |
| `debugging-and-error-recovery` | reproduzir, localizar, reduzir, corrigir e proteger; trata saída de erro como dado não confiável |
| `code-review-and-quality` | revisão em cinco eixos, com severidades |
| `security-and-hardening` | OWASP, segredos, SSRF e uso seguro de LLM; alinhado às regras de segurança do TudoIA |
| `git-workflow-and-versioning` | commits atômicos, branches curtos e worktrees, que é como o usuário já trabalha |
| `grill-me` | protocolo canônico TudoIA de alinhamento crítico e interrogação ativa de premissas (sem comportamento yes-man) |
| `improve-codebase-architecture` | diretrizes canônicas TudoIA de arquitetura profunda (Ousterhout standard) e eliminação de classes rasas/wrappers |
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

Encontradas pelo catálogo https://www.skillsdirectory.com/skills e baixadas da **fonte original** (nunca de espelho), no commit indicado, para uma pasta vazia fora do repositório. Cada arquivo copiado foi lido por inteiro; nenhum pede para enviar dados para fora nem desativar controles (o `mcp-builder` trazia o `npx` do MCP Inspector, hoje condicionado a pedido do usuário e versão fixada, ver [Modificações para o TudoIA](#modificações-para-o-tudoia-2026-11-01)). Scripts não foram copiados. Arquivos alterados trazem um aviso no topo (exigência da Apache-2.0 para arquivo modificado).

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

## Modificações para o TudoIA (2026-11-01)

Ajustes cirúrgicos para eliminar contradições com a Doutrina TEC (relatório `leitura-skills-x-doutrina`). Regra de precedência: ECO-PRE-07 (a Doutrina vence a skill; o agente executa só a parte compatível e relata o conflito com o ID da regra). O texto de cada skill continua genérico: as mudanças valem "em serviços e componentes TEC"; fora deles o texto original vale. Os arquivos alterados não trazem comentário de modificação próprio: este registro é o aviso (IA-FER-04), e vale também para as adaptações anteriores sem aviso nas skills do Osmani (`using-agent-skills`, `planning-and-task-breakdown`, `incremental-implementation`, `debugging-and-error-recovery`, `code-review-and-quality`).

| Skill | O que mudou | Contradições |
|---|---|---|
| `git-workflow-and-versioning` | nota de precedência; commit só quando o usuário pedir; revert restrito aos arquivos do agente e `reset --hard` só em worktree próprio; tag e push manuais só fora de release automatizado; `grep` do diff sem imprimir o segredo | C1, C2, C3, C4 |
| `incremental-implementation` | nota de precedência; "Commit" virou ponto de commit condicionado a pedido; checklists sem "tudo commitado" | C1 |
| `spec-driven-development` | nota de precedência; gatilhos por raio de explosão em TEC; teto de ~5 arquivos vale fora de TEC | C5, C6 |
| `planning-and-task-breakdown` | nota de precedência; lista de tarefas só em mudança transversal em TEC; tamanho por comportamento, tipos e testes por convenção não contam | C5, C6 |
| `grill-me` | nota de precedência; limiar de 3 arquivos trocado por raio de explosão em TEC | C5 |
| `improve-codebase-architecture` | nota de precedência; estrutura ARQ-EST/ARQ-APL e ADR 0008 prevalecem em serviços .NET TEC; exemplo `OrderProcessor` marcado como não aplicável a TEC | C7 |
| `security-and-hardening` (SKILL e `hardening-patterns.md`) | nota de precedência; validação com 400 e `field` em TEC; hash de `TEC.Core.Cryptography` em .NET TEC; segredo do cofre `TEC.Vault` em TEC; verificação do diff sem imprimir linhas | C4, C8, C9, C10 |
| `code-review-and-quality` | nota de precedência; violação de MUST sem ADR é Critical e bloqueia, sem deferência | C15 |
| `lgpd-compliance` | nota de precedência; contenção do incidente passa a ser proposta com confirmação por ação | C16 |
| `dotnet-aot-compat` | nota de precedência; em API pública de `TEC.*` parar após 3 tentativas e relatar; ler os props antes e pular o Step 1 em TEC | C13, C14 |
| `mcp-builder` | nota de precedência; só as operações que o caso de uso exige em TEC; `npx` do Inspector só a pedido do usuário, com versão fixada e lida | C11, C12 |
| `microsoft-docs` | nota de precedência; fallback `npx`/`npm -g` do `mslearn` só a pedido do usuário, com versão fixada e lida | C11 |
| `debugging-and-error-recovery` | nota de precedência; comando de teste TUnit/MTP (`--project`, `--treenode-filter`) e zero testes não é aprovação | C17 |
| `using-agent-skills` | nota de precedência; contagem e roteamento para as 22 skills mais `doutrina-tec`, carregada primeiro em trabalho TEC | precedência (ECO-PRE-07) |
| `humanize-text` | não reescrever blocos `## Regras`, IDs, separador ` — `, front-matter nem tabelas de ADR/índice de uma doutrina | lacuna (formato do validador) |
| `advanced-evaluation` (SKILL e duas referências) | juiz em modelo local por padrão, gateway pode reenviar à nuvem; nomes de modelo de nuvem trocados por `<modelo>`; sem e-mail ou telefone reais | IA-PRV-01/02/05 |
| `mcp-builder/reference/evaluation.md` | mesma nota de modelo local e dados sintéticos | IA-PRV-01/02/05 |
| `doutrina-tec` (nova) | registrada abaixo | IA-FER-07 |

Contradições C1 a C17 tratadas: C1, C2, C3, C4, C5, C6, C7, C8, C9, C10, C11, C12, C13, C14, C15, C16, C17. Divergências menores (relatório, seção 2.2) e lacunas da Doutrina ficaram de fora.

### `doutrina-tec`

Criação própria do ecossistema TEC, sob a licença do projeto (Apache-2.0). Origem: repositório Doutrina (`skills/doutrina-tec/SKILL.md`), copiada em 01/11/2026. Mudanças em relação ao original: o caminho vem somente da variável `DOUTRINA_TEC` (ECO-CON-09), sem `manifesto.json` legível não trabalha e registra `versao` e `hash` (ECO-CON-01/02), e a Doutrina prevalece sobre qualquer outra skill (ECO-PRE-07). O original no repositório Doutrina não foi alterado.

### `microsoft-docs`

Origem e licença ainda não registradas; verificar antes da próxima atualização.

## Versões fixadas dos servidores MCP e `doutrina-tec` atualizada (2026-11-02)

- **IA-FER-08 (Doutrina, ADR IA 0006 aceito):** todos os servidores `npx` do catálogo passaram a ter versão fixada, a versão que o registro npm publicava em 2026-11-02: `desktop-commander@0.3.1`, `mcp-npx-fetch@1.0.0`, `mcp-remote@0.16.0`, `@playwright/mcp@0.0.84`, `server-sequential-thinking@2.0.0`, `mcp-server-supabase@0.15.0` e `server-github@2025.4.8` (`context7` já estava fixado em `4.4.4`). Fixar impede a deriva, mas **não é a leitura integral** exigida por IA-FER-01: o código dessas versões ainda precisa ser lido antes da próxima atualização. Licenças conferidas no registro: MIT, Apache-2.0 e a do `sequential-thinking` ("SEE LICENSE IN LICENSE", ler antes de atualizar).
- `@modelcontextprotocol/server-github` está **depreciado** no npm ("no longer supported"). Não está ativo em `governanca.json`; trocar por alternativa suportada antes de ativá-lo.
- A skill `doutrina-tec` foi copiada de novo do repositório Doutrina (agora com as seis famílias novas e os perfis por papel em `gerado/perfis/`). Sem outras mudanças.

## Triagem estática dos servidores MCP fixados (2026-11-02)

Os tarballs das versões fixadas foram baixados com `npm pack --ignore-scripts` para uma pasta vazia fora do repositório e inspecionados sem executar nada (scripts de instalação, `child_process`, `eval`, rede, variáveis de ambiente, proveniência npm). **Triagem, não leitura integral (IA-FER-01 segue pendente).**

- `@wonderwhy-er/desktop-commander@0.3.1`: o `postinstall` (`dist/track-installation.js`) faz um `POST` HTTPS de rastreamento de instalação (id do cliente, plataforma e origem da instalação) a um endpoint externo, **sem respeitar** o opt-out de telemetria, que só vale em execução (`DESKTOP_COMMANDER_DISABLE_TELEMETRY`). Mitigação aplicada no catálogo: `npm_config_ignore_scripts=true` (o `npx` não roda o `postinstall`) e `DESKTOP_COMMANDER_DISABLE_TELEMETRY=1`. O servidor dá ao modelo execução de comandos e escrita de arquivos por desenho: reavaliar se precisa estar ativo em todos os clientes.
- `@upstash/context7-mcp@4.4.4`, `@playwright/mcp@0.0.84`, `@supabase/mcp-server-supabase@0.15.0`, `mcp-remote@0.16.0`, `@modelcontextprotocol/server-sequential-thinking@2.0.0`: sem script de instalação que execute código de terceiros no consumidor (o `prepare` listado roda só no repositório de origem). Proveniência npm (SLSA) presente em `playwright`, `supabase`, `mcp-remote`, `sequential-thinking` e `desktop-commander`.
- `@upstash/context7-mcp@4.4.4`, `@tokenizin/mcp-npx-fetch@1.0.0` e `@modelcontextprotocol/server-github@2025.4.8`: **sem proveniência** npm; `server-github` está depreciado.
- `server-sequential-thinking@2.0.0`: a licença declarada é "SEE LICENSE IN LICENSE" e o tarball **não traz** o arquivo `LICENSE`: conferir a licença no repositório de origem antes de atualizar.

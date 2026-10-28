# Governança

A governança mantém as regras de engenharia, as skills e os servidores MCP em um lugar só (`governanca/`) e os
distribui para os clientes de IA que você usa: Claude Code, Cursor, Google Antigravity, Codex CLI e OpenCode. Você edita
a fonte única. O `sync` escreve os arquivos de cada cliente. O `verificar` diz quando um cliente saiu de sincronia.

Código: `governanca/__init__.py`. Interface pública: `sincronizar`, `verificar`, `aplicar_mcp_claude`,
`aplicar_mcp_opencode`, `aplicar_tudo`, `detectar_instancias` e `ErroGovernanca`. A especificação completa está em
`SPEC.md`, na raiz do repositório.

## Fonte única

| Arquivo | Conteúdo |
|---|---|
| `governanca/governanca.json` | Lista o que está ativo: `regras`, `skills`, `mcp`, `workspaces`, `clientes` e `instancias` |
| `governanca/regras/*.md` | Regras em Markdown (en-us), nesta ordem: `system-first.md` (raciocínio, proporcionalidade, definição de pronto), `operational-safety.md` (confirmações, segredos, conteúdo não confiável), `ai-data-privacy.md` (o que pode ir para modelos de IA) e `ponytail.md` (YAGNI). Vão em toda mensagem de todo cliente: mantenha-as curtas e deixe temas específicos para skills |
| `governanca/skills/<id>/SKILL.md` | Uma pasta por skill. Pode ter arquivos extras (ex.: `references/`) |
| `governanca/mcp.json` | Catálogo de servidores MCP (`mcpServers`). Pode conter `${VAR}` |
| `governanca/ORIGEM.md` | Origem e licença das skills de terceiros |
| `governanca/LICENSE-agent-skills` | Texto MIT do repositório de origem das skills |

Só `.env` guarda segredos. O `mcp.json` referencia as variáveis com `${NOME}`. Elas são substituídas quando o `sync`
roda, e o valor real não aparece no repositório.

### `governanca.json`

- `regras`: ids das regras, na ordem em que entram no bloco gerenciado.
- `skills`: ids das skills a copiar. Cada id precisa existir como `governanca/skills/<id>/SKILL.md`.
- `mcp`: ids do `mcp.json` a ativar.
- `workspaces`: pastas de projeto que recebem `AGENTS.md` e, se houver Cursor, `.cursor\rules\tudoia.mdc`.
- `clientes`: lista de tipos usada só no modo legado (quando não há `instancias`).
- `instancias`: uma entrada por perfil de cliente. Cada uma tem `id`, `cliente`, `nome`, `caminho`, `config_json`
  e `ativo`. Tipos aceitos: `claude`, `antigravity`, `cursor`, `codex`, `opencode` e `workspace`.

Atenção: o `governanca.json` do repositório tem caminhos do ambiente do autor (`D:/TudoIA`, `D:/`, `~/.claude-trabalho`,
`~/.claude-server-commander`, `~/.gemini`, `~/.codex`). Em outra máquina, ajuste antes de rodar o `sync`. Um workspace
inexistente faz o sync recusar tudo.

## Comandos

| Comando | Equivalente | O que faz |
|---|---|---|
| `.\scripts\tudoia.ps1 sync` | `python -m tudoia_painel sync` | Escreve os arquivos gerados. Imprime uma linha por alvo: `igual`, `atualizado` ou `removido` (skill gerenciada órfã) |
| `.\scripts\tudoia.ps1 verificar` | `python -m tudoia_painel verificar` | Lista divergências (`ausente`, `divergente` ou skill órfã). Não escreve. Sai com código 1 se houver algum |

Se a governança estiver inválida (regra inexistente, skill sem `SKILL.md`, MCP sem catálogo, variável obrigatória
vazia, cliente desconhecido, id com `..` ou separador, JSON de MCP malformado, arquivo que não é UTF-8, marcas de bloco
desbalanceadas, destino fora da home e dos workspaces), o `sync` aborta com `ERRO: ...`, código 1, **antes de gravar
qualquer arquivo**. Esse é o modo fail-closed do módulo.

O `up` do `tudoia.ps1` roda `sync` antes de subir os containers. Se o `sync` falha, o `up` para ali (função `Nativo`
do script).

O painel não chama o `sincronizar` sozinho: chama `aplicar_tudo`, que junta `aplicar_mcp_claude`,
`aplicar_mcp_opencode` e `sincronizar` numa só fase de validação. Claude, OpenCode, Antigravity e regras são validados
antes de gravar qualquer arquivo. No painel, toda alteração da governança exige o papel admin (ver
[seguranca.md](../seguranca.md#autorização)).

## O que o `sync` escreve

Os caminhos abaixo são os do modo com `instancias` (o modo atual). `~` é o diretório do usuário.

| Alvo | Arquivo | Como é escrito |
|---|---|---|
| `agents:<workspace>` | `<workspace>\AGENTS.md` | Bloco gerenciado com as regras |
| `cursor:<id>` | `<caminho>\.cursor\rules\tudoia.mdc` | Arquivo inteiro: cabeçalho `alwaysApply: true` mais as regras |
| `cursor:mcp:<arquivo>` | `~\.cursor\mcp.json` (ou o `config_json` da instância). Nunca a pasta da instância, que é workspace | Só as entradas de `mcpServers` do catálogo, no formato do Cursor (remoto só com `url`/`headers`). Entradas escritas à mão são preservadas |
| `claude:<id>` | `<caminho>\CLAUDE.md` | Bloco gerenciado |
| `claude:<id>:skill:...` | `<caminho>\skills\<skill>\...` | Cópia de cada arquivo da skill, mais o marcador `.tudoia` |
| `antigravity:<id>` | `<caminho>\GEMINI.md` | Bloco gerenciado |
| `antigravity:<id>:mcp` | `~\.gemini\config\mcp_config.json` (ou o `config_json` da instância) | Só as entradas de `mcpServers` cujos ids estão no catálogo. Entradas escritas à mão são preservadas |
| `antigravity:<id>:skill:...` | `<caminho>\antigravity-cli\skills\...` | Cópia das skills, mais o marcador `.tudoia` |
| `codex:<id>` | `<caminho>\AGENTS.md` | Bloco gerenciado |
| `codex:<id>:mcp` | `<caminho>\config.toml` (ou o `config_json` da instância) | Só as tabelas `[mcp_servers.<id>]` do catálogo. O resto do arquivo (plugins, projetos, o MCP próprio do app) fica byte a byte; a edição é relida com `tomllib` e recusada se mudar qualquer outra coisa. No Windows, `npx` vai por `cmd /c` |
| `opencode:<id>` | `<caminho>\AGENTS.md` | Bloco gerenciado. O `opencode.json` (seção `mcp`) é do painel (`aplicar_mcp_opencode`), não do `sync` |

Consequências para você:

- **Os segredos vão para o disco em texto claro.** O `mcpServers` escrito no `~\.claude.json`, no
  `mcp_config.json` do Antigravity e no `~\.cursor\mcp.json`, a seção `mcp` do `opencode.json` e as tabelas
  `[mcp_servers.*]` do `config.toml` do Codex contêm os valores das variáveis
  (`GITHUB_PERSONAL_ACCESS_TOKEN`, `CEREBRO_TOKEN_ESTATICO` etc.). Isso é por design, porque os clientes precisam
  deles. Quem lê esses arquivos lê os tokens. Veja o risco 15 em [seguranca.md](../seguranca.md#riscos-residuais).
- **O `sync` não toca o `mcpServers` do `~\.claude.json` nem o `opencode.json`.** Os MCP do catálogo nesses arquivos são
  gerenciados pelo painel (veja a seção abaixo). Servidores escritos à mão continuam.
- **Segredos só vão para destinos sob a home.** A regra 3 do `SPEC.md` vale: um destino dentro de workspace recebe
  `${VAR}` literal, e um destino fora de home e de workspace é recusado antes de qualquer escrita. A decisão é tomada
  sobre o caminho resolvido (`_destino`): uma junction ou um symlink no meio do caminho não desviam a escrita para
  fora. Se o `mcp.json` tiver o valor literal de um segredo do `.env`, a escrita num workspace é recusada.

### Skills gerenciadas

- Cada pasta de skill copiada recebe um arquivo `.tudoia`. Ele marca a pasta como gerada pela governança.
- Uma pasta com o marcador cuja skill saiu de `governanca.json` é órfã. O `sync` a apaga (resultado `removido`) e o
  `verificar` a lista.
- Pasta sem o marcador é do usuário e nunca é apagada. Link simbólico e junction também não, nem quando o marcador é um
  link.

### Bloco gerenciado

Arquivos de regras (`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `AGENTS.md` do Codex) recebem um bloco entre estes marcadores:

```text
<!-- tudoia:inicio (gerado por governanca; edite governanca/regras/) -->
...regras...
<!-- tudoia:fim -->
```

- Só o trecho entre os marcadores é reescrito. O texto que você escreveu fora do bloco é preservado.
- Se o arquivo não existe, ele é criado com o bloco. Se existe sem os marcadores, o bloco vai para o fim.
- Marcas desemparelhadas ou fora de ordem (um início sem fim, por exemplo) são erro: nada é gravado e a mensagem pede
  para corrigir o arquivo à mão (`_bloco`). Antes, uma marca de fim apagada fazia o padrão casar até o fim de outro bloco
  e apagar o texto do meio.
- Para mudar o conteúdo, edite `governanca/regras/*.md`, não o arquivo gerado. A edição manual dentro do bloco some no
  próximo `sync`.

Arquivos gerados do Cursor (`tudoia.mdc`) não têm bloco: são sobrescritos por inteiro.

### Idempotência

`sincronizar` compara o conteúdo planejado com o que está no disco. Se for igual, não escreve e devolve `igual`.
Rodar duas vezes seguidas produz `igual` na segunda. Não há carimbo de data no conteúdo gerado, então o `sync` não fica
reescrevendo arquivo sem motivo.

### Gravação

Cada arquivo é gravado assim (`_gravar`, `_efetivar`, `_trocar`):

1. Temporário com nome único no mesmo diretório (`tempfile.mkstemp`), `flush` e `fsync`.
2. O temporário recebe o modo do arquivo original. Arquivo novo que pode ter segredo nasce `0600`.
3. Antes da troca, o arquivo é relido. Se outro processo (o Claude Code, por exemplo) gravou depois da leitura, nada é
   trocado: o plano é refeito sobre o conteúdo novo e só a parte da governança é reaplicada. São até 3 tentativas;
   depois, `ErroGovernanca`.
4. Os JSON de MCP têm backup antes da troca (ver abaixo).
5. `os.replace`. No Windows, `PermissionError` (arquivo aberto pelo cliente) tem até 5 tentativas, com espera
   crescente. Depois, `ErroGovernanca` pedindo para fechar o cliente.

O temporário nunca fica para trás.

### Backups dos JSON de MCP

Antes de trocar um JSON de MCP, a governança copia o arquivo para `~\.tudoia\backups\`:

| Arquivo | Pasta do backup |
|---|---|
| `~\.claude.json` (ou `config_json` da instância Claude) | `~\.tudoia\backups\claude-json\` |
| `opencode.json` | `~\.tudoia\backups\opencode-json\` |
| `mcp_config.json` do Antigravity | `~\.tudoia\backups\antigravity-json\` |
| `~\.cursor\mcp.json` | `~\.tudoia\backups\cursor-json\` |
| `config.toml` do Codex | `~\.tudoia\backups\codex-toml\` |

São 10 cópias por arquivo, criadas com modo `0600`. As cópias têm os tokens em claro. Por isso ficam na home e fora de
todo workspace (`D:/` é workspace, e o Cursor indexa workspace). Backups antigos em `dados\backups\claude-json\` ficam
onde estavam: apague-os à mão.

### Verificar (drift)

`verificar` monta o mesmo plano e compara com o disco. Lista:

- `ausente`: o arquivo esperado não existe.
- `divergente`: o arquivo existe com outro conteúdo.
- skill gerenciada órfã: pasta com o marcador `.tudoia` cuja skill saiu de `governanca.json`.

Ele não escreve nada. Um arquivo do Claude que o próprio Claude Code alterou em outras chaves não aparece como
divergente, porque o plano é montado a partir do disco. Só o conteúdo gerado é comparado. Nos MCP do Claude, do
OpenCode e do Antigravity, só as entradas que o painel possui (ids de `governanca/mcp.json`) entram na comparação. Um
servidor escrito à mão não aparece como drift.

## MCP do Claude (`~\.claude.json`)

O painel é o único escritor da chave `mcpServers` do `~\.claude.json` (ou do `config_json` da instância). A função
`aplicar_mcp_claude` faz isso:

- Escreve os MCP ativos (`governanca.json` › `mcp`), com segredos substituídos quando o arquivo está sob a home.
- Remove do arquivo os ids do catálogo que estão inativos ou saíram do `mcp.json`.
- Mantém as outras entradas, inclusive as escritas à mão.
- Recusa um arquivo malformado (JSON inválido ou `mcpServers` que não é objeto) sem gravar nada. Nunca recria o
  arquivo.
- Se as entradas do catálogo já estão como deveriam, não reescreve nem reformata o arquivo.
- Grava como descrito em [Gravação](#gravação), com backup em `~\.tudoia\backups\claude-json\`.
- O painel chama `aplicar_tudo`, que valida Claude, OpenCode, Antigravity e as regras antes de gravar qualquer arquivo.
- O `opencode.json` segue o mesmo contrato (`aplicar_mcp_opencode`), na seção `mcp`, com o catálogo traduzido para o
  formato do OpenCode (`type: remote` ou `local`). Chaves de provider, modelo e permissão do usuário são preservadas.

As rotas do painel que mudam MCP (`POST /api/governanca/mcp`, `PUT /api/governanca/mcp/{id}`, `PUT .../conteudo`,
`DELETE /api/governanca/mcp/{id}`, `POST /api/governanca/sincronizar`) chamam essa função. Se ela recusar, o catálogo
já salvo continua salvo. A resposta traz o motivo em `pendencia` (ou o erro 422 em edição de conteúdo e sincronização),
e o drift mostra o que falta. Corrija a causa e rode o `sincronizar` de novo.

## Skills

O catálogo ativo está em `governanca.json` (22 ids). Cada skill é uma pasta em `governanca/skills/`. A tabela abaixo
mostra a origem como o repositório informa. Os detalhes de licença estão a seguir.

| Skill | Origem declarada | Observação |
|---|---|---|
| `using-agent-skills` | addyosmani/agent-skills (MIT) | Modificada: título e links para o catálogo do TudoIA |
| `spec-driven-development` | addyosmani/agent-skills (MIT) | |
| `planning-and-task-breakdown` | addyosmani/agent-skills (MIT) | |
| `incremental-implementation` | addyosmani/agent-skills (MIT) | |
| `disciplined-tdd` | addyosmani/agent-skills (MIT) | Modificada: título "Canonical TudoHaS TDD Standard" |
| `debugging-and-error-recovery` | addyosmani/agent-skills (MIT) | |
| `code-review-and-quality` | addyosmani/agent-skills (MIT) | |
| `security-and-hardening` | addyosmani/agent-skills (MIT) | Inclui `references/hardening-patterns.md` |
| `git-workflow-and-versioning` | addyosmani/agent-skills (MIT) | |
| `grill-me` | addyosmani/agent-skills (MIT), segundo `ORIGEM.md` | Confirme na origem |
| `improve-codebase-architecture` | addyosmani/agent-skills (MIT), segundo `ORIGEM.md` | Confirme na origem |
| `microsoft-docs` | addyosmani/agent-skills (MIT), segundo `ORIGEM.md` | Confirme na origem |
| `frontend-design` | Anthropic, Apache-2.0 | Tem `LICENSE.txt` com o texto Apache 2.0 na pasta |
| `humanize-text` | Criação própria do autor (não é cópia) | Licença do projeto, Apache-2.0 |
| `lgpd-compliance` | Criação própria (referências: goul4rt/lgpd-skills, MIT; onfire7777/brazil-lgpd, Apache-2.0) | Números normativos em `references/normative-reference.md`, conferidos em fontes oficiais em 27/10/2026 |
| `observability-and-instrumentation` | addyosmani/agent-skills (MIT) | Adaptada: checklist trazido para a pasta, citações a skills ausentes removidas |
| `documentation-and-adrs` | addyosmani/agent-skills (MIT) | |
| `mcp-builder` | anthropics/skills (Apache-2.0) | Adaptada: guias por linguagem e scripts não copiados (SDK Python 2.x, ver `ORIGEM.md`) |
| `dotnet-aot-compat` | dotnet/skills (MIT) | Adaptada: respeita os arquivos de regras do projeto; subagentes opcionais |
| `security-threat-model` | openai/skills (Apache-2.0) | Só dispara quando pedida explicitamente |
| `advanced-evaluation` | muratcankoylan/Agent-Skills-for-Context-Engineering (MIT) | Adaptada: sem citações a skills-irmãs, nota sobre LiteLLM |
| `n8n-expression-syntax` | czlonkowski/n8n-skills (MIT) | Adaptada: sem `$env`, exemplos de SQL com parâmetros e segredo em credencial |

As skills de outras origens trazem `LICENSE.txt` na própria pasta, e os arquivos alterados têm um aviso no topo. Origem,
commit e cada mudança estão em `governanca/ORIGEM.md`.

### Licenças

- O texto MIT do repositório de origem está em `governanca/LICENSE-agent-skills` (Copyright 2025 Addy Osmani).
- `frontend-design` tem a licença Apache 2.0 na pasta, e o `SKILL.md` aponta para ela.
- `humanize-text` é criação própria do autor e segue a licença do projeto (Apache-2.0). Não é cópia de terceiros.

### `ORIGEM.md`

O `governanca/ORIGEM.md` lista as 22 skills, com as exceções de licença (`frontend-design`, Apache-2.0 da Anthropic;
`humanize-text`, criação própria do autor, licença do projeto). Ele não registra que `disciplined-tdd` e
`using-agent-skills` têm alterações próprias (títulos e links locais).

## Adicionar uma skill

1. Crie `governanca/skills/<id>/SKILL.md`. O id precisa ser uma palavra com letras, números, `.`, `_` ou `-`, e não
   começar com `.`. O arquivo começa com um cabeçalho (`---`) com `name` e `description`, como nas skills existentes.
2. Adicione `<id>` à lista `skills` de `governanca.json`.
3. Rode `.\scripts\tudoia.ps1 verificar` (deve apontar `ausente` nas cópias) e depois `.\scripts\tudoia.ps1 sync`.
4. Anote a origem e a licença em `governanca/ORIGEM.md`, na mesma mudança.

Pelo painel, a aba Governança também cria skills (`POST /api/governanca/skills`, só admin). A importação de um
repositório externo (`POST /api/governanca/skills/importar`) só funciona para admin e executa
`npx --yes skills add <repositório>`. Só aceita repositório do GitHub (`https://github.com/dono/repo` ou `dono/repo`,
constante `REPO_GITHUB` em `skills_servico.py`) e recusa skill com link simbólico. Leia
[seguranca.md](../seguranca.md#governança-e-execução-de-código-de-terceiros) antes de usar.

## Adicionar um servidor MCP

1. Adicione uma entrada em `governanca/mcp.json`, dentro de `mcpServers`. Para um servidor por `npx`:

   ```json
   "meu-servidor": {
     "command": "npx",
     "args": ["-y", "@dono/pacote@1.2.3"],
     "env": { "MINHA_CHAVE": "${MINHA_CHAVE}" },
     "description": "O que o servidor faz"
   }
   ```

   Para um servidor HTTP, use `"type": "http"` e `"url"`, como em `cerebro`.

2. Se a chave for obrigatória, use `${MINHA_CHAVE}`. Se for opcional, use `${MINHA_CHAVE:-}`. O sync recusa quando uma
   variável obrigatória está ausente ou vazia no `.env`.
3. Coloque o valor no `.env` (ou na aba Segredos do painel, para admin).
4. Adicione o id `meu-servidor` à lista `mcp` de `governanca.json`.
5. Rode `.\scripts\tudoia.ps1 sync`.

Prefira fixar a versão do pacote (`@1.2.3`), não `@latest`. Veja o risco 5 em [seguranca.md](../seguranca.md#riscos-residuais).

A aba Segredos lista como "MCP: <id>" as variáveis que aparecem em `${...}` ou no bloco `env` do servidor.

### Serena (código por símbolo)

O catálogo traz a Serena 2.1.0 (`oraios/serena`, aplicação GPL-3.0-or-later), instalada com
`uv tool install -p 3.13 "serena-agent==2.1.0"` em `~\.local\bin`. Ela usa os language servers (pyright, Roslyn etc.)
para achar definições, referências e editar por símbolo, sem LLM. Os argumentos do catálogo são obrigatórios:

- `--context=ide` tira as ferramentas de shell e de arquivo genérico, que todo cliente já tem com o próprio controle de
  permissão.
- `--agent-interface tools`: na v2 o padrão é a interface REPL, uma ferramenta que executa Python. Nela, excluir
  ferramentas não impede nada (a documentação da Serena diz isso). Com `tools`, a exclusão do contexto vale.
- `--open-web-dashboard false`: sem isso, cada cliente abriria uma aba do navegador ao subir a Serena.
- `--project-from-cwd`: o projeto é a pasta de onde o cliente foi aberto (a primeira acima com `.git` ou
  `.serena\project.yml`).

A Serena cria `.serena\` na raiz de cada projeto (cache e memórias que os agentes escrevem); ponha essa pasta no
`.gitignore`. A primeira consulta num projeto demora (download e indexação do language server); as seguintes são
rápidas. Para atualizar: troque a versão no `uv tool install` e revise os contextos de novo.

## Instâncias de cliente

Cada entrada de `instancias` diz onde um cliente mora na sua máquina:

| Campo | Significado |
|---|---|
| `id` | Identificador único. Letras, números, `.`, `_` e `-` |
| `cliente` | `claude`, `antigravity`, `cursor`, `codex`, `opencode` ou `workspace` |
| `caminho` | Pasta do cliente (`~\.claude`, `~\.gemini` etc.). `~` é a home |
| `config_json` | Arquivo de configuração MCP, se não for o padrão (`~\.claude.json` ou `caminho\.claude.json`; no OpenCode, `caminho\opencode.json`) |
| `ativo` | `false` pula a instância sem apagá-la |

O painel edita essas entradas e detecta instâncias presentes na máquina (`POST /api/governanca/instancias/detectar`).
Criar, editar e apagar instâncias exige admin. Um `caminho` fora da home e dos workspaces é recusado no `sync`.

## Arquivos do repositório

- Versionados: `governanca/**`, `SPEC.md` e o `AGENTS.md` da raiz. O `AGENTS.md` da raiz tem o bloco gerenciado com as
  regras, então ele é versionado, mas o bloco é reescrito pelo `sync`.
- Ignorados pelo git: `.cursor/` (o `.gitignore` lista essa pasta). Os arquivos `tudoia.mdc` gerados ali são locais.
- Fora do repositório, na home: `CLAUDE.md`, `GEMINI.md`, `AGENTS.md` do Codex e do OpenCode, `~\.claude.json`,
  `opencode.json`, `~\.gemini\config\mcp_config.json`, as pastas de skills e os backups em `~\.tudoia\backups\`.

## Testes

Os testes estão em `tests\governanca\test_sync.py`, `tests\governanca\test_mcp_claude.py` (MCP do Claude, segredos
por destino, fail-closed) e `tests\governanca\test_robustez.py`. Rode com `uv run pytest -q`. Contagem atual em
[desenvolvimento.md](../desenvolvimento.md#rodar-os-testes).

# SPEC — Governança (módulo `governanca`)

## Seam pública (única interface)
```python
from governanca import (sincronizar, verificar, aplicar_mcp_claude, aplicar_mcp_opencode, aplicar_tudo,
                        detectar_instancias, ErroGovernanca)

sincronizar(raiz: Path, home: Path | None = None) -> dict[str, str]
    # {alvo: "atualizado" | "igual" | "removido"}; idempotente; fail-closed. "removido" = skill gerenciada órfã.
verificar(raiz: Path, home: Path | None = None) -> list[str]
    # lista de divergências (drift). [] = tudo em dia. Não escreve nada.
aplicar_mcp_claude(raiz: Path, home: Path | None, dir_backup: Path, remover=()) -> dict[str, str]
    # único escritor de `mcpServers` em ~/.claude.json (chamado pelo painel). Valida antes de gravar.
aplicar_mcp_opencode(raiz: Path, home: Path | None, dir_backup: Path, remover=()) -> dict[str, str]
    # único escritor da seção `mcp` do opencode.json. Mesmo contrato de aplicar_mcp_claude.
aplicar_tudo(raiz: Path, home: Path | None, dir_backup: Path, remover=()) -> dict[str, str]
    # aplicar_mcp_claude + aplicar_mcp_opencode + sincronizar com UMA fase de validação: nada é gravado
    # se qualquer um dos três falhar na validação. `dir_backup` é a base (subpastas claude-json,
    # opencode-json, antigravity-json). Chaves: alvos do sincronizar + `claude:mcp:<caminho>` e
    # `opencode:mcp:<caminho>`. É o que o painel deve chamar.
detectar_instancias(home: Path | None = None, workspaces: list[str] | None = None) -> list[dict]
    # Sugere instâncias (Claude padrão e perfis `~/.claude-*`, Antigravity `~/.gemini`, Codex `~/.codex`,
    # Cursor por workspace existente). Só lê o disco; o painel decide o que gravar em `instancias[]`.
```
`raiz` = raiz do monorepo (contém `governanca/governanca.json`, `.env`). `home` = HOME do usuário (injetável p/ teste).
Os dicionários de `aplicar_mcp_*` usam como chave o caminho resolvido do arquivo.

## Fonte única (`governanca/`)
- `governanca.json`: `regras[]`, `skills[]` (ids), `mcp[]` (ids ativos), `workspaces[]`, `clientes[]` (modo legado),
  `instancias[]` (opcional; se presente e não vazio, substitui `clientes[]`).
- `instancias[]`: `{id, cliente, caminho, config_json?, ativo?=true, ...}`; `cliente` ∈ `antigravity`, `claude`,
  `cursor`, `codex`, `opencode`, `workspace`; `caminho` aceita `~`. Instância inativa é ignorada; `cursor`/`workspace`
  ativas também viram raízes de workspace (regra 3).
- `regras/*.md`, `skills/<id>/` (com `SKILL.md`; todos os arquivos em UTF-8), `mcp.json` (catálogo canônico com `${VAR}`).
- Segredos: somente `<raiz>/.env`.

## Saídas geradas
| Cliente | Arquivo | Conteúdo |
|---|---|---|
| Todos (workspaces + raiz) | `<ws>/AGENTS.md` | bloco gerenciado de regras (lido por Codex, OpenCode, Antigravity) |
| Cursor | `<ws>/.cursor/rules/tudoia.mdc` | regras |
| Cursor (MCP) | `config_json` da instância, padrão **`<home>/.cursor/mcp.json`** (nunca a pasta da instância, que é workspace) | só as entradas de `mcpServers` do catálogo, traduzidas (regra 11); escrito por `sincronizar` |
| Claude | `<caminho>/CLAUDE.md` (padrão `~/.claude`) + `<caminho>/skills/<id>/` | bloco gerenciado + skills |
| Claude (MCP) | `<home>/.claude.json` (ou `config_json`) | só as entradas de `mcpServers` do catálogo; escrito por `aplicar_mcp_claude`/`aplicar_tudo`, **nunca** por `sincronizar` |
| Antigravity | `<caminho>/GEMINI.md` (bloco) + `config_json` (padrão `<caminho>/config/mcp_config.json`) + `<caminho>/antigravity-cli/skills/` | MCP: só as entradas de `mcpServers` do catálogo (escrito por `sincronizar`) |
| Codex | `<caminho>/AGENTS.md` | bloco gerenciado |
| Codex (MCP) | `config_json` da instância, padrão `<caminho>/config.toml` | só as tabelas `[mcp_servers.<id>]` do catálogo, traduzidas (regra 12); escrito por `sincronizar` |
| OpenCode | `<caminho>/AGENTS.md` (bloco) + `config_json` (padrão `<caminho>/opencode.json`) | MCP: só as entradas de `mcp` do catálogo, traduzidas (ver regra 8); escrito por `aplicar_mcp_opencode`/`aplicar_tudo`, nunca por `sincronizar` |

## Regras de comportamento
1. **Bloco gerenciado**: só o trecho entre marcas é reescrito; conteúdo do usuário fora das marcas é preservado.
   Se as marcas de início e fim não estiverem em pares na ordem início→fim (ex.: marca de fim apagada à mão),
   `ErroGovernanca` citando o arquivo, antes de qualquer escrita: corrigir à mão.
2. **Idempotência**: 2ª execução devolve `"igual"` e não toca o disco. JSON de MCP cujas entradas do dono já
   estão como esperado não é regravado nem reformatado.
3. **Segredos**: `${VAR}` é interpolada **apenas** quando o destino está sob `home` (`Path.is_relative_to`) e fora de qualquer workspace. Destino em workspace (raízes de `workspaces[]` e pastas de instâncias `cursor`/`workspace`) recebe `${VAR}` literal, nunca o valor; catálogo com valor literal de segredo é recusado para workspace. Destino fora de `home` e de workspace é recusado (`ErroGovernanca`).
   - A decisão é feita sobre o caminho **resolvido** (`Path.resolve()`): junction/symlink não desvia a escrita
     para fora de home/workspace nem leva segredo para um workspace. Grava-se no caminho resolvido.
   - Segredo, para a guarda de valor literal, = variável do `.env` cujo nome contém `KEY`, `TOKEN`, `SECRET`,
     `PASSWORD`, `SENHA`, `SEGREDO` ou a parte `PAT` (separada por `_`), ou que é referenciada por `${VAR}` em algum
     MCP do catálogo. O valor é procurado cru e na forma escapada em JSON. Valores com menos de 8 caracteres
     não são procurados (casariam por acaso com trechos comuns e dariam falso positivo); a mensagem cita o nome
     da variável, nunca o valor.
4. **Fail-closed**: config malformada, skill inexistente, id com `..`/separador, variável obrigatória ausente num MCP ativo, JSON de MCP (`~/.claude.json`, `opencode.json`, `mcp_config.json`) malformado, arquivo que não é UTF-8, marcas desbalanceadas, entrada de catálogo sem `command`/`url`, ou destino recusado → `ErroGovernanca` **antes** de qualquer escrita. Nunca recria um JSON malformado como `{}`. Nenhuma exceção crua escapa: falhas de E/S também viram `ErroGovernanca`.
   - O escopo de "antes de qualquer escrita" é a chamada: `aplicar_tudo` valida os três (Claude, OpenCode,
     sync) juntos; chamar as três funções em sequência valida cada uma só na sua vez.
   - Falha de E/S **durante** a fase de escrita (ex.: arquivo travado) interrompe a chamada; arquivos já
     trocados antes dela permanecem trocados (não há transação entre arquivos).
5. **Drift**: `verificar` aponta arquivo gerado ausente ou diferente do esperado e skill gerenciada órfã. Nos JSON de MCP compara só as entradas que o módulo possui.
6. Sem dependências externas (stdlib).
7. **MCP do Claude é do painel**: `sincronizar` não lê nem escreve `mcpServers` de `~/.claude.json`; servidores escritos à mão são preservados. `aplicar_mcp_claude` possui os ids de `governanca/mcp.json`: grava os ativos (com segredos se o destino está em `home`), remove os catálogo inativos e os passados em `remover`, e mantém as demais entradas. Backup em `<home>/.tudoia/backups/claude-json/` (últimas 10). O mesmo vale para o `mcp_config.json` do Antigravity (escrito por `sincronizar`, backup em `<home>/.tudoia/backups/antigravity-json/`) para o `opencode.json` (backup em `<home>/.tudoia/backups/opencode-json/`), para o `mcp.json` do Cursor (`cursor-json/`) e para o `config.toml` do Codex (`codex-toml/`). Os backups ficam na home, fora de todo workspace, porque guardam tokens em claro.
8. **OpenCode**: tradução do catálogo para `mcp.<id>`: `type` `http`/`sse` → `{"type": "remote", "url", "headers"?}`;
   sem `type` ou `stdio` → `{"type": "local", "command": [command, *args], "environment"?}`; sempre `"enabled": true`.
   Outro `type`, ou entrada sem `url`/`command` → `ErroGovernanca`. Demais chaves do `opencode.json` são do usuário.
9. **Gravação atômica**: temporário único no mesmo diretório (`tempfile.mkstemp`), mesmo modo do arquivo original
   (arquivo novo: `0600` se pode conter segredo, isto é, JSON de MCP sob home; senão `0644`), `flush` + `fsync`,
   `os.replace`. O temporário nunca fica para trás. Backups nascem `0600`.
   - **Corrida**: logo antes do `os.replace` o arquivo é relido; se o conteúdo (sha256) mudou desde a leitura
     (ex.: o Claude Code regravou `~/.claude.json`), relê, reaplica só as entradas do dono e tenta de novo
     (até 3 vezes; depois `ErroGovernanca`). Resta uma janela de microssegundos entre a releitura e a troca.
   - **Windows**: `PermissionError` no `os.replace` (violação de compartilhamento) é tentado de novo 5 vezes com
     espera curta; persistindo, `ErroGovernanca` com mensagem clara.
10. **Skills gerenciadas**: cada pasta de skill copiada recebe o marcador `.tudoia`. Pasta com marcador (arquivo
    regular, pasta que não é symlink/junction) cuja skill saiu de `skills[]` é órfã: `verificar` aponta e
    `sincronizar` remove. Pasta sem marcador (criada à mão, ou copiada antes do marcador existir) nunca é apagada.
11. **Cursor**: tradução para `~/.cursor/mcp.json` (`mcpServers`): `type` `http`/`sse` → `{"url", "headers"?}` (sem `type`); stdio → `{"command", "args", "env"?}`. `description` e `auth` não são copiados (o OAuth é feito pelo próprio Cursor). Demais entradas e chaves do arquivo são do usuário.
12. **Codex**: o `config.toml` é mantido pelo app do Codex (plugins, projetos, MCP próprio); o módulo só possui as tabelas `[mcp_servers.<id>]` (e subtabelas `[mcp_servers.<id>.*]`) dos ids do catálogo. Tradução: `type` `http` → `{"url", "http_headers"?}` (o Codex recusa `bearer_token` literal); `sse` → `ErroGovernanca` (o Codex só aceita streamable HTTP); stdio → `{"command", "args", "env"?}`, e no Windows `npx`/`npm`/`pnpm`/`yarn` vão por `cmd /c` (o Codex inicia o processo sem shell). As tabelas antigas do dono são removidas por cabeçalho e as novas acrescentadas no fim; o resto do arquivo fica byte a byte. Depois de editar, o texto é relido com `tomllib` e precisa ser semanticamente igual ao original com as entradas do dono trocadas; se não for (ex.: `mcp_servers` em tabela inline), `ErroGovernanca` e nada é gravado. Sem dependência externa: `tomllib` lê, a escrita é gerada pelo módulo.

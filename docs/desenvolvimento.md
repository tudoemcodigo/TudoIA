# Desenvolvimento

Guia para quem altera o código do TudoIA. Para usar o sistema, veja [instalacao.md](instalacao.md) e [configuracao.md](configuracao.md).

## Layout do repositório

| Caminho | Conteúdo |
|---|---|
| `automacao/n8n/` | Quatro workflows do n8n em JSON (resumo, pesquisa, digest e ingestão). Ver [componentes/automacao-n8n.md](componentes/automacao-n8n.md). |
| `config/` | Manifesto de modelos (`modelos.yaml`), catálogo de modelos e roteamento do LiteLLM, exemplos de roteamento e preços de referência. |
| `dados/` | Dados de execução: Cérebro, Estúdio, logs, documentos e backups do `.env`. **Não versionado** (`.gitignore`). |
| `docs/` | Documentação. `docs/componentes/` tem uma página por componente. |
| `governanca/` | Fonte única de regras (`regras/`), skills (`skills/`), catálogo de MCP (`mcp.json`) e o módulo Python `governanca` que distribui tudo para os clientes de IA. `ORIGEM.md` e `LICENSE-agent-skills` documentam a origem das skills. |
| `infra/` | Template do realm do Keycloak (`keycloak/realm-tudoia.json`) e exemplos de identity provider. |
| `modelos/` | Pesos e binários locais: pastas do Ollama e do ComfyUI portable. **Não versionado**. |
| `painel/` | Pacote `tudoia_painel`: `app.py` (monta o app), `rotas/` (um `APIRouter` por domínio), serviços (`estudio_servico.py`, `skills_servico.py`, `mcp_teste.py`, `comfyui.py`), `upstreams.py` (endereços locais), autenticação e estáticos da interface. Ver [componentes/painel.md](componentes/painel.md). |
| `runtime/` | Serviços executados pelo Docker e configurações deles: `cerebro/` (código-fonte), `comfyui/fluxos/` (grafos), `docker-compose.yml`, `litellm/` (gateway e roteador), `ollama/modelfiles/`, `open-webui/` (`env.py` e ícones) e `searxng/`. |
| `scripts/` | Pontos de entrada `tudoia.ps1` (e `tudoia.cmd`) e `tudoia.sh` (Linux), o provisionador do Keycloak (`scripts/keycloak/provisionar.py`), o baixador de modelos (`scripts/modelos/baixar.py`), o backup (`scripts/backup/backup.py` e `restaurar.md`), a conferência do `env.py` do Open WebUI (`scripts/openwebui/verificar_env.py`) e a credencial do n8n (`scripts/n8n/credencial_cerebro.py`). |
| `.github/workflows/` | CI (`ci.yml`). Ver [Integração contínua](#integração-contínua). |
| `tests/` | Suites de teste do projeto raiz. A do Cérebro fica em `runtime/cerebro/tests/`. |
| Raiz | `pyproject.toml` e `uv.lock` (projeto raiz), `.python-version` (3.12), `.env.example` (modelo do `.env`), `.gitattributes`, `.gitignore`, `LICENSE` (Apache-2.0), `NOTICE`, `SPEC.md` (especificação do módulo `governanca`) e `AGENTS.md` (gerado pelo `governanca`, não editar à mão). |

`.cursor/` também aparece no disco. É gerado pelo `governanca` (`.cursor/rules/tudoia.mdc`) e está no `.gitignore`.

## Ambiente Python

O projeto usa **Python 3.12** e **uv** (versão 0.13.0 na máquina de referência, a mesma fixada na imagem do Cérebro).

### Projeto raiz

`pyproject.toml` declara as dependências (FastAPI, Uvicorn, Jinja2, PyYAML, HTTPX, psutil, Authlib, cryptography, itsdangerous) e o grupo `dev` (pytest e ruff). O grupo `capturas` (Playwright) é só para as capturas de tela do Studio (`scripts/studio`). `[tool.uv] package = false` indica que o projeto não é instalado como pacote, só serve de ambiente.

```powershell
uv sync                  # cria .venv\ com dependências e o grupo dev
```

O interpretador usado é `.venv\Scripts\python.exe`. Não é preciso ativar o venv.

### Cérebro (`runtime/cerebro`)

O Cérebro tem `pyproject.toml` e `uv.lock` próprios, separados do projeto raiz. Tem o próprio venv.

```powershell
cd runtime\cerebro
uv sync                  # cria runtime\cerebro\.venv\ com o grupo dev (pytest, pytest-asyncio)
```

`asyncio_mode = "auto"` está no `pyproject.toml` do Cérebro. O build de produção é feito pelo `runtime/cerebro/Dockerfile` com `uv sync --frozen`.

## Lint

O ruff está no grupo `dev`. A configuração fica em `[tool.ruff]` do `pyproject.toml`: `line-length = 120`,
`target-version = "py312"`, regras `E9` (erro de sintaxe), `F` (pyflakes) e `B` (bugbear). Estilo fica de fora.
`modelos`, `dados` e `runtime/open-webui/env.py` (cópia do upstream) são excluídos.

```powershell
uv run ruff check .
```

## Rodar os testes

### Projeto raiz

```powershell
uv run pytest -q
```

A configuração está em `[tool.pytest.ini_options]` do `pyproject.toml`: `testpaths = ["tests"]` e `pythonpath = [".", "painel", "runtime/litellm"]`. Os avisos de `httpx` e de `authlib` são filtrados ali.

Rede: `tests/conftest.py` bloqueia todo transporte HTTP real do `httpx` nos testes da raiz (`ConnectError`). Testes que
precisam de resposta usam `httpx.MockTransport`, e o `TestClient` do FastAPI não passa pela rede. A exceção é o teste
de integração do Keycloak (`TUDOIA_KEYCLOAK_IT=1`), que libera a rede.

Verificação feita para este guia (só coleta, sem executar a suíte):

```text
.venv/Scripts/python.exe -m pytest -q --co -p no:cacheprovider
619 tests collected
```

| Pasta | O que cobre |
|---|---|
| `tests/backup/` | Backup e rotação (`test_backup.py`). |
| `tests/governanca/` | Sincronização de regras, skills e MCP (`test_sync.py`), MCP do Claude e segredos por destino (`test_mcp_claude.py`) e gravação concorrente, marcas e destinos (`test_robustez.py`). |
| `tests/keycloak/` | Provisionamento do Keycloak (`test_provisionar.py`) e token do cliente `tudoia-mcp` (`test_token_mcp.py`). Tem um teste de integração opcional, descrito abaixo. |
| `tests/modelos/` | Listagem, download e verificação de modelos (`test_baixar.py`). |
| `tests/n8n/` | Fluxos do n8n sem `$env` e com formulário autenticado; credencial do Cérebro (`test_fluxos_n8n.py`). |
| `tests/painel/` | API do painel (`test_painel.py`), autenticação OIDC e sessão (`test_autenticacao.py`), Bearer (`test_bearer.py`), `segredos` (`test_cli.py`) e teste de MCP stdio (`test_mcp_stdio.py`). |
| `tests/runtime/` | Roteador do LiteLLM: catálogo, `.env`, eventos, hook semântico, quarentena de membros, regras, gerador de configuração, roteador resiliente e o compose (`test_compose.py`: toda chave do catálogo chega ao LiteLLM). Usa `conftest.py` e `fixtures/catalogo-mini.yaml`. |
| `tests/studio/` | Capturas de tela do Studio (`test_capturar_print.py`). |

### Cérebro

```powershell
cd runtime\cerebro
uv run pytest -q
```

Verificação feita para este guia (só coleta):

```text
.venv/Scripts/python.exe -m pytest -q --co -p no:cacheprovider
144 tests collected
```

Os testes ficam em `runtime/cerebro/tests/`: `test_autenticacao.py`, `test_token_estatico.py`, `test_embeddings.py`, `test_indexador.py`, `test_memoria.py`, `test_servidor.py`, `test_vetores.py` e `test_web.py`, além de `conftest.py`. O bloqueio de rede de `tests/conftest.py` não vale aqui: é outro projeto.

A execução completa não foi feita para este guia. Antes de considerar uma mudança pronta, rode o lint e as duas suítes.

## Integração contínua

`.github/workflows/ci.yml` roda em todo push e pull request, em `windows-latest` (o TudoIA é Windows-first), com
Python 3.12, Node 22 e `uv==0.13.0`. Passos, na ordem:

1. `uv sync --frozen`
2. `uv run --frozen ruff check .`
3. `uv run --frozen pytest -q` (suíte da raiz)
4. Em `runtime/cerebro`: `uv sync --frozen` e `uv run --frozen pytest -q`
5. `node --check painel/tudoia_painel/static/painel.js` (sintaxe do JS)
6. Parse do `scripts/tudoia.ps1` com o parser do PowerShell (`[System.Management.Automation.Language.Parser]::ParseFile`)

Os testes não usam rede, Docker, GPU nem Keycloak. O checkout usa `persist-credentials: false` e o workflow tem só
`contents: read`.

### Teste de integração do Keycloak (opcional)

`tests/keycloak/test_provisionar.py` tem um teste que roda `--verificar` contra um Keycloak vivo. Ele só roda com a variável `TUDOIA_KEYCLOAK_IT=1` e exige o Keycloak no ar com as credenciais de administrador no ambiente (ver [componentes/keycloak.md](componentes/keycloak.md), seção de testes).

```powershell
$env:TUDOIA_KEYCLOAK_IT = "1"
.venv\Scripts\python.exe -m pytest -q tests\keycloak
```

Sem a variável, o teste aparece como `skipped`.

## Convenções

Padrões observados no código. Quem mudar a base deve seguir o mesmo modelo.

- **Nomes em português.** Módulos, funções e mensagens de erro usam português: `caminhos.py`, `servicos.py`, `ErroApi`, `gravar_valor`, `acao_todos`. A interface e a documentação também são em pt-BR.
- **Biblioteca padrão primeiro.** Antes de adicionar uma dependência, verifique se a biblioteca padrão resolve. `scripts/modelos/baixar.py`, por exemplo, usa só `http.client`, `ssl` e `hashlib`, além do PyYAML.
- **Fail-closed.** `governanca.sincronizar` valida tudo antes de gravar e levanta `ErroGovernanca` sem escrever nada. A verificação de divergências (`verificar`) não grava.
- **Entrada validada na borda.** Os corpos de requisição são modelos Pydantic, a maioria com `extra="forbid"` e limites (`max_length`, `pattern`, `ge`, `le`). Erros usam `ErroApi`.
- **Caminhos vindos da API.** Antes de ler ou gravar um nome recebido, resolva a pasta e o caminho e confirme que ele continua dentro da pasta resolvida com `is_relative_to`. As rotas de arquivos do Estúdio usam `_arquivo_em` (`app.py`) para isso.
- **Comando externo.** Não passe texto do usuário para `.cmd` no Windows (o `cmd.exe` interpreta `&`, `|`, `^`, `%`). Valide com lista branca, como `REPO_GITHUB` na importação de skill. Processo filho precisa de prazo e de encerramento da árvore inteira (`mcp_stdio.encerrar_arvore`).
- **Logs.** Sem corpo de pedido, segredo nem texto de prompt. Erro 500 leva o id do pedido (`X-Request-ID`); o traceback fica só no log.
- **Segredos só no `.env`.** `painel/tudoia_painel/envfile.py` lê e grava o `.env` da raiz. Nomes de segredos internos ficam em `cli.py` (`SEGREDOS_INTERNOS`). Valor de segredo não vai para log, mensagem de erro ou URL.
- **Caminhos configuráveis por variável.** `caminhos.py` aceita `TUDOIA_RAIZ`, `TUDOIA_COMFYUI_PORTABLE` e `TUDOIA_OLLAMA_MODELS`. O docstring de `caminhos.py` diz que `TUDOIA_RAIZ` é usado pelos testes, mas nenhum teste da base a define hoje.
- **Regras de agente são geradas.** Edite `governanca/regras/` e `governanca/skills/`, não `AGENTS.md` nem `.cursor/`. Depois rode `scripts\tudoia.ps1 sync`.

## Adicionar um componente

1. **Escolha onde ele roda.**
   - Container: crie `runtime/<nome>/` com o que for preciso e adicione o serviço em `runtime/docker-compose.yml`. Fixe a imagem por digest (`@sha256:`), publique a porta sempre em `127.0.0.1`, passe ao serviço só as variáveis de que ele precisa em `environment` (não use `env_file`: ele entrega o `.env` inteiro) e declare `healthcheck` se houver sinal de prontidão.
   - Processo do host: registre-o em `painel/tudoia_painel/servicos.py` (`HOST`, `METADADOS`, `_start_*` e `_stop_host`).
2. **Registre no painel.** Para aparecer na aba de serviços, inclua o nome em `DOCKER` ou `HOST` e em `METADADOS` (`servicos.py`).
3. **Segredo novo.** Adicione o nome em `.env.example` com valor vazio. Se o painel deve mostrar a chave, inclua-a em `CATEGORIAS_CHAVES` (`painel/tudoia_painel/rotas/segredos.py`). Se o valor é gerado pelo próprio sistema, inclua em `SEGREDOS_INTERNOS` (`cli.py`). Chave de provedor nova também precisa entrar no `environment` do serviço `litellm` (`tests/runtime/test_compose.py` confere).
4. **Testes.** Crie os testes em `tests/<área>/` (ou em `runtime/<nome>/tests/`, se o componente tiver o próprio pyproject). Cubra o caminho feliz e as falhas: serviço fora do ar, entrada inválida, arquivo ausente. Não dependa de rede: nos testes da raiz ela está bloqueada; use `httpx.MockTransport`.
5. **Documentação.** Crie `docs/componentes/<nome>.md` e linke a partir do índice do projeto.
6. **Terceiros.** Se o componente traz código, imagem ou pesos de terceiros, registre a licença em [terceiros.md](terceiros.md).
7. **Governança.** Se o componente cria regras ou skills para os agentes, edite `governanca/` e rode `scripts\tudoia.ps1 sync`. Para checar divergências sem gravar, rode `scripts\tudoia.ps1 verificar`.

## Fins de linha

O `.gitattributes` define:

- `* text=auto eol=lf`: texto é armazenado com LF no repositório.
- `*.ps1`, `*.cmd` e `*.bat` com `eol=crlf`: o Windows exige CRLF nesses scripts.
- Imagens, áudio, vídeo, `*.db` e `*.safetensors` como binários, sem conversão.

Estado atual no working tree, conferido com `git ls-files --eol`:

- `scripts/tudoia.ps1` e `scripts/tudoia.cmd` estão com LF, contrariando a regra `eol=crlf`.
- Os arquivos `.py` e `runtime/docker-compose.yml` aparecem com CRLF no working tree e LF no índice. O `core.autocrlf` desta máquina está como `true`, o que conflita com `eol=lf`.

Use `git ls-files --eol <arquivo>` para checar antes de comitar.

## Outros pontos

- **Licença.** O projeto é Apache-2.0 (`LICENSE`, `NOTICE`). Componentes de terceiros mantêm as próprias licenças: ver [terceiros.md](terceiros.md).
- **Especificação do módulo `governanca`.** Está em `SPEC.md`.
- **Modelos de IA.** O manifesto e o download estão em [componentes/modelos.md](componentes/modelos.md).

## Veja também

- [instalacao.md](instalacao.md) e [configuracao.md](configuracao.md): uso do sistema.
- [arquitetura.md](arquitetura.md): como os componentes se conectam.
- [componentes/servicos-docker.md](componentes/servicos-docker.md): stack Docker e processos do host.
- [terceiros.md](terceiros.md): componentes de terceiros e licenças.

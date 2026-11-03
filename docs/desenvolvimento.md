---
titulo: Desenvolvimento
tipo: guia
dono: TudoIA (mantenedor do repositório)
status: vigente
classificacao: publico
verificado-em: 2026-11-03
---

[🏠 TudoIA](../README.md) › [📚 Documentação](README.md) › 🧑‍💻 Desenvolvimento

# 🧑‍💻 Desenvolvimento

> Para quem altera o código do TudoIA: como montar o ambiente, rodar lint e testes (os mesmos comandos do CI), onde cada coisa mora, como o repositório é empacotado e quais convenções seguir. Para usar o sistema, veja [instalação](instalacao.md) e [configuração](configuracao.md).

## 📑 Sumário

- [🎯 Visão geral](#-visão-geral)
- [🚀 Uso](#-uso)
  - [Ambiente Python](#ambiente-python)
  - [Lint](#lint)
  - [Testes](#testes)
  - [Verificações de sintaxe](#verificações-de-sintaxe)
  - [Integração contínua](#integração-contínua)
  - [Doutrina fixada e instalador](#doutrina-fixada-e-instalador)
- [⚙️ Opções](#️-opções)
- [❌ Erros e diagnóstico](#-erros-e-diagnóstico)
- [🛡️ Segurança](#️-segurança)
- [📐 Convenções](#-convenções)
- [➕ Adicionar um componente](#-adicionar-um-componente)
- [❓ Perguntas frequentes](#-perguntas-frequentes)

---

## 🎯 Visão geral

O TudoIA reúne **três projetos Python** com ambientes separados, uma cópia do `env.py` do Open WebUI, JavaScript sem build e scripts PowerShell:

| Projeto | Pasta | Manifesto | Ambiente |
|---|---|---|---|
| Raiz (painel, roteador, governança, instalador, scripts) | `.` | `pyproject.toml`, `uv.lock` | `.venv\` |
| Cérebro | `runtime/cerebro/` | `pyproject.toml`, `uv.lock` | `runtime\cerebro\.venv\` |
| SquadTI | `runtime/squadti/` | `pyproject.toml`, `uv.lock` | `runtime\squadti\.venv\` |
| `env.py` do Open WebUI | `runtime/open-webui/env.py` | Cópia do arquivo do upstream, só conferida (`tudoia verificar-openwebui`) | Não tem |

Layout das pastas:

| Caminho | Conteúdo |
|---|---|
| `.github/workflows/` | `ci.yml` (verificação de cada push e pull request) e `release.yml` (build do instalador ao empurrar uma tag `vX.Y.Z`). |
| `automacao/n8n/` | Quatro fluxos do n8n em JSON. Ver [automação n8n](componentes/automacao-n8n.md). |
| `config/` | Manifesto de modelos (`modelos.yaml`), catálogo de modelos e roteamento do LiteLLM, exemplos de roteamento, preços de referência e catálogo de vídeo na nuvem. |
| `dados/` | Dados de execução. **Não versionado.** |
| `docs/` | Esta documentação. Índice em [README](README.md). |
| `governanca/` | Regras, skills, catálogo MCP, `doutrina.json` e o módulo Python `governanca`. Especificação em [SPEC.md](../SPEC.md). |
| `infra/keycloak/` | Template do realm, exemplos de provedores de identidade e tema de login. |
| `instalador/` | Pacote `tudoia_instalador` (tela web local e etapas) e `dados/` com o `payload.zip` gerado. Ver [instalador](instalador.md). |
| `modelos/` | Pesos e binários locais (Ollama, ComfyUI portable). **Não versionado.** |
| `painel/` | Pacote `tudoia_painel`: `app.py` monta o app, `rotas/` tem um `APIRouter` por domínio, mais serviços, autenticação e a interface estática. Ver [painel](componentes/painel.md). |
| `runtime/` | O que roda no Docker e as configurações: `docker-compose.yml`, `cerebro/`, `litellm/` (hook do roteador), `squadti/`, `postgres/init/`, `searxng/`, `open-webui/`, `ollama/modelfiles/` e `comfyui/workflows/`. |
| `scripts/` | `tudoia.ps1`, `tudoia.sh`, `tudoia.cmd`, ciclo de vida (`iniciar.ps1`, `parar.ps1`, `reiniciar.ps1`, `painel.ps1`, `desinstalar.ps1`) e os módulos Python `backup`, `empacotar`, `keycloak`, `modelos`, `n8n`, `openwebui`, `squadti` e `studio`. |
| `tests/` | Suíte do projeto raiz. As do Cérebro e da SquadTI ficam dentro de cada projeto. |
| Raiz | `pyproject.toml`, `uv.lock`, `.python-version` (3.12), `.env.example`, `.gitattributes`, `.gitignore`, `LICENSE` (Apache-2.0), `NOTICE`, `SPEC.md` e `AGENTS.md` (gerado pela governança, não edite à mão). |

`build/` e `dist/` (saída do empacotamento) e `.cursor/` (gerado pela governança) também aparecem no disco e estão no `.gitignore`.

## 🚀 Uso

### Ambiente Python

Python 3.12 e **uv 0.13.0** (a versão fixada no CI, no `release.yml` e na imagem do Cérebro). Não é preciso ativar o venv.

```powershell
uv sync                                   # raiz: cria .venv\ com as dependências e o grupo dev
uv sync --frozen                          # igual ao CI: falha se o uv.lock estiver desatualizado
cd runtime\cerebro;  uv sync --frozen     # Cérebro
cd runtime\squadti;  uv sync --frozen     # SquadTI
```

O `pyproject.toml` da raiz tem `[tool.uv] package = false`: o projeto só serve de ambiente. O grupo `dev` traz `pytest` e `ruff`; o grupo `capturas` (Playwright) é só para as capturas de tela do Estúdio (`scripts/studio`).

### Lint

Configuração em `[tool.ruff]` do `pyproject.toml`: `line-length = 120`, `target-version = "py312"`, regras `E9` (sintaxe), `F` (pyflakes) e `B` (bugbear); estilo fica de fora. Excluídos: `modelos`, `dados` e `runtime/open-webui/env.py` (cópia do upstream).

```powershell
uv run --frozen ruff check .
```

Resultado em 2026-11-03: `All checks passed!` (ruff 0.17.3).

### Testes

Comandos exatos do CI:

```powershell
uv run --frozen pytest -q                                              # raiz
cd runtime\cerebro; uv run --frozen pytest -q                          # Cérebro
cd runtime\squadti; uv run --frozen python -W error -m pytest -q       # SquadTI (avisos viram erro)
```

Configuração da raiz (`[tool.pytest.ini_options]`): `testpaths = ["tests"]` e `pythonpath = [".", "painel", "runtime/litellm", "instalador"]`; os avisos de `httpx` e `authlib` são filtrados ali. O Cérebro usa `asyncio_mode = "auto"`. A SquadTI usa `testpaths = ["orquestrador/tests"]`.

**Sem rede.** `tests/conftest.py` faz todo transporte HTTP real do `httpx` falhar com `ConnectError`; teste que precisa de resposta usa `httpx.MockTransport`, e o `TestClient` do FastAPI não passa pela rede. A exceção é o teste de integração do Keycloak (`TUDOIA_KEYCLOAK_IT=1`). Os testes também não usam Docker nem GPU.

Resultado das execuções de 2026-11-03 (Windows, uv 0.13.0):

| Suíte | Resultado |
|---|---|
| Raiz | `2 failed, 1360 passed, 1 skipped` em 7 min 15 s. Ver a nota abaixo. |
| Cérebro | `149 passed` em 10,7 s |
| SquadTI | `190 passed` em 12,9 s |

As duas falhas da raiz, que o CI cobraria:

- `tests/test_scripts_ps1.py::test_parar_por_linha_de_comando_so_atinge_quem_casa_o_texto_literal` falhou durante a execução em paralelo com a suíte do Cérebro e **passou** ao rodar o arquivo sozinho (`16 passed`). Provável sensibilidade a carga; a causa não foi isolada.
- `tests/test_squadti_compose.py::test_docker_sock_montado_traz_group_add_host_override_e_aviso` lê `docs/componentes/squadti.md` e exige as expressões `docker.sock` e `root no host`. O guia da SquadTI estava sendo reescrito na mesma data e não as continha. **Quem editar esse guia precisa manter as duas expressões** (o teste trata o aviso do `docker.sock` como parte do contrato).

Cobertura da suíte da raiz:

| Pasta ou arquivo | O que cobre |
|---|---|
| `tests/backup/` | Backup e rotação. |
| `tests/governanca/` | Sincronização de regras, skills e MCP; MCP do Claude, do Cursor e do Codex; instâncias locais; gravação concorrente, marcas e destinos. |
| `tests/instalacao/` | Instalador: opções, etapas, motor, servidor, payload, desinstalação, `.env`, versão e SquadTI. |
| `tests/keycloak/` | Provisionamento do realm e token do cliente `tudoia-mcp`; um teste de integração opcional. |
| `tests/modelos/` | Listagem, download e verificação de modelos. |
| `tests/n8n/` | Fluxos sem `$env` e com formulário autenticado; credencial do Cérebro. |
| `tests/openwebui/` | Conferência do `env.py` contra o da imagem fixada. |
| `tests/painel/` | API do painel, autenticação OIDC e Bearer, CLI de segredos, serviços, provedores, Estúdio, SquadTI e fronteiras de entrada. |
| `tests/runtime/` | Roteador do LiteLLM (catálogo, regras, hook semântico, quarentena, resiliente, eventos), gerador de configuração e o compose (`test_compose.py`: toda chave do catálogo chega ao LiteLLM). |
| `tests/studio/` | Capturas de tela do Estúdio. |
| `tests/test_scripts_ps1.py` | Scripts PowerShell de ciclo de vida: ASCII, uso do módulo comum, porta, PID e linha de comando. |
| `tests/test_squadti_chave.py`, `tests/test_squadti_compose.py` | Chave virtual da SquadTI e o serviço `squadti` do compose. |

Teste de integração do Keycloak (opcional): com um Keycloak no ar e as credenciais de administrador no ambiente,

```powershell
$env:TUDOIA_KEYCLOAK_IT = "1"
uv run --frozen pytest -q tests\keycloak
```

Sem a variável, o teste aparece como `skipped`.

### Verificações de sintaxe

O CI confere também o JavaScript (sem build) e os scripts PowerShell:

```powershell
node --check painel/tudoia_painel/static/painel.js
node --check instalador/tudoia_instalador/static/instalador.js
```

Resultado em 2026-11-03 (Node 24.20.0; o CI usa Node 22): os dois sem erro. A checagem dos `.ps1` usa o parser do PowerShell em **todos** os arquivos de `scripts\`:

```powershell
foreach ($f in Get-ChildItem "$PWD\scripts" -Filter *.ps1) {
  $erros = $null
  $null = [System.Management.Automation.Language.Parser]::ParseFile($f.FullName, [ref]$null, [ref]$erros)
  if ($erros) { "$($f.Name): $erros"; exit 1 }
}
```

(Não executada nesta data; o CI a roda no PowerShell 7. Os `.ps1` do ciclo de vida precisam ser ASCII puro: o PowerShell 5.1 lê arquivo sem BOM como ANSI, e `tests/test_scripts_ps1.py` confere.)

### Integração contínua

`.github/workflows/ci.yml` roda em todo push e pull request, com `permissions: contents: read` e `persist-credentials: false`.

| Job | Sistema | Passos |
|---|---|---|
| `verificar` | `windows-latest` (o TudoIA é Windows-first), Python 3.12, Node 22, `uv==0.13.0` | `uv sync --frozen`; `uv run --frozen ruff check .`; `uv run --frozen pytest -q`; no `runtime/cerebro`, `uv sync --frozen` e `uv run --frozen pytest -q`; `node --check` do `painel.js` e do `instalador.js`; parse de todos os `scripts\*.ps1` |
| `squadti` | `ubuntu-latest` | No `runtime/squadti`, `uv sync --frozen` e `uv run --frozen python -W error -m pytest -q`; `docker compose --profile squadti -f docker-compose.yml --env-file ../.env.example config --quiet` (valida o compose); `docker build -t tudoia-squadti:ci runtime/squadti`. Não publica nada. |

`.github/workflows/release.yml` roda ao empurrar uma tag `v*`: confere que a tag, o `version` do `pyproject.toml` e o `VERSAO` de `instalador/tudoia_instalador/__init__.py` são iguais, roda lint e testes, constrói o `TudoIA-Setup.exe`, confere o sha256, atesta a proveniência e anexa o `.exe` e o `.sha256` à release do GitHub. O `.exe` não é assinado digitalmente (ver [instalador](instalador.md)).

### Doutrina fixada e instalador

O commit da Doutrina que o TudoIA usa está em `governanca/doutrina.json` e é repetido no `ARG DOUTRINA_SHA` de `runtime/squadti/Dockerfile` e no padrão de `SQUADTI_DOUTRINA_SHA` do compose. O painel mostra, na tela da governança, se esses três divergem. Os comandos (`painel/tudoia_painel/doutrina_servico.py`):

```powershell
python -m scripts.empacotar.payload --sincronizar-pin   # busca o commit mais novo da Doutrina (usa rede), grava no JSON e propaga
python -m scripts.empacotar.payload --derivar-pin       # só propaga o JSON para o Dockerfile e o compose (sem rede)
.\scripts\tudoia.ps1 empacotar                          # gera o payload e o dist\TudoIA-Setup.exe
```

`empacotar` exige `DOUTRINA_TEC` apontando para um clone da Doutrina que contenha o commit fixado, e `uv` no PATH; o PyInstaller (`pyinstaller==6.22.3`) é buscado pelo `uv run --with`. O empacotador **reprova** o payload (e nada é construído) se achar segredo ou dado pessoal da máquina; a lista extra de termos vem de `PESSOAIS_EXTRA` ([configuração](configuracao.md#️-ferramentas-de-desenvolvimento)).

## ⚙️ Opções

| Item | Valor | Onde |
|---|---|---|
| Python | `>=3.12` (`.python-version`: `3.12`) | `pyproject.toml` |
| uv | `0.13.0` | `ci.yml`, `release.yml`, `runtime/cerebro/Dockerfile` |
| Node | 22 no CI (só para `node --check`) | `ci.yml` |
| Largura de linha | 120 | `[tool.ruff]` |
| Regras do ruff | `E9`, `F`, `B` | `[tool.ruff.lint]` |
| Timeout dos jobs | 20 min (`verificar`), 30 min (`squadti`, `release`) | workflows |

## ❌ Erros e diagnóstico

| Sintoma | Causa | Ação |
|---|---|---|
| `uv sync --frozen` falha dizendo que o lock está desatualizado | `pyproject.toml` mudou sem atualizar o `uv.lock` | Rode `uv lock` no projeto certo (raiz, Cérebro ou SquadTI) e inclua o `uv.lock` na mudança. |
| `pytest` falha com `rede bloqueada nos testes` | O teste (ou o código sob teste) abriu conexão HTTP real | Troque por `httpx.MockTransport`; não libere a rede. |
| `test_versao_do_instalador_e_a_do_pyproject` falha | `VERSAO` do instalador diferente de `version` do `pyproject.toml` | Deixe os dois iguais (e a tag do release igual a eles). |
| `test_docker_sock_montado_...` falha | O guia `docs/componentes/squadti.md` perdeu `docker.sock` ou `root no host` | Restaure as expressões no guia. |
| `empacotar` aborta com `defina DOUTRINA_TEC` | Falta o clone da Doutrina | Aponte `DOUTRINA_TEC` para o clone que tem o commit fixado. |
| `empacotar` reprova o payload | Segredo ou dado pessoal encontrado em arquivo incluído | Remova o dado do arquivo; nunca desligue a verificação. |

## 🛡️ Segurança

- Nunca coloque segredo em teste, fixture, documentação ou exemplo: use `<chave>`, `example.com` e valores obviamente falsos. O empacotador varre o payload e reprova padrões de segredo e dados pessoais.
- O `.env` real fica fora do git e do payload. Para depurar com segredo, use o ambiente do processo, não um arquivo versionado.
- Não rode código de terceiros (skills, MCP, imagens) sem ler; baixe para uma pasta vazia fora do repositório ([terceiros](terceiros.md) e `governanca/ORIGEM.md`).
- Falha de segurança: siga [segurança](seguranca.md).

## 📐 Convenções

Padrões observados no código; quem mudar a base segue o mesmo modelo.

- **Nomes em português.** Módulos, funções, mensagens de erro, interface e documentação: `caminhos.py`, `servicos.py`, `ErroApi`, `gravar_valor`, `acao_todos`.
- **Biblioteca padrão primeiro.** Antes de adicionar dependência, veja se a biblioteca padrão resolve (o baixador de modelos usa só `http.client`, `ssl` e `hashlib`, além do PyYAML; a governança usa só a biblioteca padrão).
- **Fail-closed.** `governanca.sincronizar` valida tudo antes de gravar e levanta `ErroGovernanca` sem escrever nada. `verificar` não grava.
- **Entrada validada na borda.** Corpos de requisição são modelos Pydantic, a maioria com `extra="forbid"` e limites (`max_length`, `pattern`, `ge`, `le`). Erros usam `ErroApi`.
- **Caminhos vindos da API.** Resolva a pasta e o caminho e confirme com `is_relative_to` que ele continua dentro. As rotas de arquivos do Estúdio usam `arquivo_em` (`painel/tudoia_painel/estudio_servico.py`).
- **Comando externo.** Não passe texto do usuário a `.cmd` no Windows (o `cmd.exe` interpreta `&`, `|`, `^`, `%`). Valide com lista branca, como `REPO_GITHUB` na importação de skill (`skills_servico.py`). Processo filho precisa de prazo e de encerramento da árvore inteira (`mcp_stdio.encerrar_arvore`).
- **Logs.** Sem corpo de pedido, segredo nem texto de prompt. Erro 500 leva o id do pedido (`X-Request-ID`); o traceback fica só no log.
- **Segredos só no `.env`.** `painel/tudoia_painel/envfile.py` lê e grava o `.env` da raiz; nomes de segredos internos ficam em `SEGREDOS_INTERNOS` (`cli.py`).
- **Caminhos configuráveis por variável.** `caminhos.py` aceita `TUDOIA_RAIZ`, `TUDOIA_COMFYUI_PORTABLE` e `TUDOIA_OLLAMA_MODELS`.
- **Regras de agente são geradas.** Edite `governanca/regras/` e `governanca/skills/`, não `AGENTS.md` nem `.cursor/`; depois rode `scripts\tudoia.ps1 sync`.
- **Scripts de ciclo de vida em ASCII.** `iniciar.ps1`, `parar.ps1`, `reiniciar.ps1`, `painel.ps1` e `_comum.ps1` não levam acento (teste confere).
- **Fins de linha.** `.gitattributes`: texto em LF no repositório; `*.ps1`, `*.cmd` e `*.bat` com `eol=crlf`; imagens, áudio, vídeo, `*.db` e `*.safetensors` binários. Confira antes de comitar com `git ls-files --eol <arquivo>` (a máquina de referência tem `core.autocrlf=true`; os `.ps1` aparecem `w/crlf` e os `.py` `w/lf`, como esperado).

## ➕ Adicionar um componente

1. **Onde roda.** Container: crie `runtime/<nome>/` e adicione o serviço em `runtime/docker-compose.yml`; fixe a imagem por digest (`@sha256:`), publique a porta sempre em `127.0.0.1`, passe só as variáveis necessárias em `environment` (nunca `env_file`, que entregaria o `.env` inteiro) e declare `healthcheck`. Processo do host: registre em `painel/tudoia_painel/servicos.py` (`HOST`, `METADADOS`, `_start_*`, `_stop_host`).
2. **Painel.** Para aparecer na aba de serviços, inclua o nome em `DOCKER` ou `HOST` e em `METADADOS` (`servicos.py`).
3. **Segredo novo.** Adicione o nome ao `.env.example` com valor vazio. Para a aba Segredos mostrá-lo, inclua-o em `CATEGORIAS_CHAVES` (`painel/tudoia_painel/rotas/segredos.py`). Se o sistema o gera, inclua em `SEGREDOS_INTERNOS` (`cli.py`). Chave de provedor nova também entra no `environment` do `litellm` (`tests/runtime/test_compose.py` confere).
4. **Testes.** Em `tests/<área>/` (ou no projeto do componente, se tiver `pyproject.toml` próprio). Cubra o caminho feliz e as falhas: serviço fora do ar, entrada inválida, arquivo ausente. Sem rede.
5. **Documentação.** Crie `docs/componentes/<nome>.md` com o front-matter padrão e liste-o em [README](README.md).
6. **Terceiros.** Se traz código, imagem ou pesos de terceiros, registre a licença em [terceiros](terceiros.md).
7. **Governança.** Se cria regras ou skills para agentes, edite `governanca/` e rode `scripts\tudoia.ps1 sync`; `scripts\tudoia.ps1 verificar` lista divergências sem gravar.

## ❓ Perguntas frequentes

**Preciso do Docker para rodar os testes?** Não. Docker só é necessário para o job `squadti` do CI (compose e build da imagem) e para subir a stack.

**Posso rodar só uma pasta de testes?** Sim: `uv run --frozen pytest -q tests\governanca`. O CI roda a suíte inteira; faça o mesmo antes de considerar pronto.

**Por que o CI roda no Windows?** O TudoIA é Windows-first (caminhos, launcher `.ps1`, `ProactorEventLoop`). Só a SquadTI, cuja imagem é Linux, roda no Ubuntu.

---

[🏠 README](../README.md) · ⬅️ [Configuração](configuracao.md) · [Terceiros](terceiros.md) ➡️

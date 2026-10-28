# Instalação

> **Caminho rápido no Windows:** use o instalador de um clique, [instalador.md](instalador.md). Este guia é o passo a passo manual.

Este guia leva uma máquina Windows do zero até o painel no ar. Cada comando abaixo existe no repositório (ver
[Comandos](#comandos-disponíveis)). Os valores de variáveis estão em [configuracao.md](configuracao.md).

## Plataformas

| Plataforma | Situação |
|---|---|
| Windows 10/11 | Suportado. O ambiente de referência é Windows 11 com GPU NVIDIA. |
| Linux | Parcial, não testado. Ponto de entrada: `scripts/tudoia.sh`, com os mesmos comandos do `tudoia.ps1` (ver [Linux](#linux)). O painel também tem trechos só de Windows (`painel/tudoia_painel/servicos.py`: `cmd.exe`, `taskkill`, `powershell`, `run_nvidia_gpu.bat`). |
| macOS | Não automatizado, pelo mesmo motivo do Linux. |

Portanto, em macOS você pode rodar as partes em Python e o `docker compose`, mas a orquestração
(`up`, `down`, o start do Ollama e do ComfyUI) precisa ser feita à mão. Isso não foi testado.

## Linux

Use `scripts/tudoia.sh` (bash). Ele substitui o `tudoia.ps1` nos mesmos comandos: `up`, `down`, `status`, `painel`,
`sync`, `verificar`, `segredos`, `keycloak`, `modelos`, `n8n-credencial` e `backup`. Os argumentos extras de
`keycloak`, `modelos`, `n8n-credencial` e `backup` são repassados.

```bash
chmod +x scripts/tudoia.sh   # só na primeira vez, se o modo de execução não veio do git
scripts/tudoia.sh up
```

Pontos de atenção:

- **Python:** usa `.venv/bin/python` se existir. Senão usa `uv run --project` (se `uv` estiver no PATH). Se nenhum
  dos dois existir, o script para com mensagem.
- **Ollama:** o `up` inicia `ollama serve` só se o binário estiver no PATH e a porta 11434 estiver livre. A pasta de
  pesos vem de `TUDOIA_OLLAMA_MODELS` no `.env`; sem valor, usa `modelos/ollama/models`. O log vai para
  `dados/ollama.log`. O bind depende do Docker (`endereco_ollama`):
  - Docker Desktop (Linux ou macOS): `OLLAMA_HOST=127.0.0.1:11434`, como no Windows. Os containers chegam ao loopback do
    host por `host.docker.internal`.
  - Docker Engine sem Docker Desktop: o Ollama escuta no IPv4 da bridge `docker0` (ex.: `172.17.0.1:11434`), porque é
    esse IP que `host.docker.internal` (`host-gateway`) resolve. No host, use `OLLAMA_HOST=<esse IP>:11434` na CLI do
    Ollama e no painel, e libere a porta 11434 no firewall (ufw) para as redes do Docker. Sem `docker0`, o script avisa e
    fica em `127.0.0.1` (os containers não alcançam o Ollama). Nunca `0.0.0.0`.
- **ComfyUI:** o script **não** o inicia. Suba-o à mão, ou pelo painel (aba **Serviços**), se precisar do Estúdio local.
- **Limites:** não testado em Linux nem em macOS. Os trechos do painel só de Windows continuam fora de escopo.

## Pré-requisitos (Windows)

| Item | Para quê | Observação |
|---|---|---|
| Python 3.12 | Runtime do painel, da governança e dos scripts | O `uv` instala a versão indicada em `.python-version`. Você não precisa instalar Python separadamente. |
| uv | Cria o `.venv` e instala as dependências (`uv sync`) | Siga a documentação oficial do uv para instalar. |
| PowerShell | Executa `scripts\tudoia.ps1` | O script usa comandos do Windows PowerShell 5.1. |
| Docker Desktop com `docker compose` | Sobe Open WebUI, SearXNG, Kokoro, n8n, LiteLLM, Postgres e o Cérebro | Versão mínima e requisitos de WSL2: a confirmar. |
| Ollama | LLMs locais e embeddings (`bge-m3`, usado pelo roteador e pelo Cérebro) | O `tudoia.ps1 up` chama `ollama serve`, então `ollama` precisa estar no PATH. |
| GPU NVIDIA com driver recente | Ollama e ComfyUI | Os limites de contexto e tempos no código foram medidos em RTX 5070 com 8 GB de VRAM (comentários em `painel/tudoia_painel/gerador.py`). Outras GPUs: não testado. |
| ComfyUI portable | Geração de imagem e vídeo no Estúdio local | Opcional. Sem ele, o Estúdio só usa os motores em nuvem. Pasta configurada em `TUDOIA_COMFYUI_PORTABLE`. |
| Keycloak | Login do painel | Vem no `docker-compose.yml` (perfil `keycloak`, porta 8180). Quem já tem um Keycloak em `localhost:8180` não liga o perfil. Guia do realm: [keycloak.md](componentes/keycloak.md). |
| Espaço em disco | Pesos dos modelos | Os modelos somam cerca de 196 GB. Veja [modelos.md](componentes/modelos.md) antes de baixar. |
| Git | Clonar o repositório | URL do repositório: a confirmar. |

## Passo a passo

Rode os comandos na raiz do repositório (`D:\TudoIA` no ambiente do autor). Os exemplos usam PowerShell.

### 1. Obter o código e instalar as dependências

```powershell
git clone <url-do-repositorio>   # a confirmar
cd TudoIA
uv sync
```

`uv sync` cria `.venv\` e instala as dependências de `pyproject.toml`. O Cérebro tem seu próprio `pyproject.toml`
em `runtime/cerebro/` e não é instalado por esse comando; ele roda no Docker.

### 2. Criar o `.env`

Nada no código copia o template. Faça a cópia manualmente:

```powershell
Copy-Item .env.example .env
```

O `.env` está no `.gitignore` e nunca deve ir para o git. Os segredos internos ainda estão vazios: o próximo passo os gera.

### 3. Gerar os segredos internos

```powershell
.\scripts\tudoia.ps1 segredos
```

O comando preenche só as chaves internas vazias (`WEBUI_SECRET_KEY`, `SEARXNG_SECRET`, `N8N_ENCRYPTION_KEY`,
`LITELLM_MASTER_KEY`, `LITELLM_DB_PASSWORD`, `TUDOIA_SESSAO_SEGREDO`, `CEREBRO_TOKEN_ESTATICO`) e imprime só os nomes.
Valores existentes não são trocados. Antes de cada alteração, o `.env` anterior vai para `dados\backups\env\`.

Guarde uma cópia do `.env` fora da máquina. A `N8N_ENCRYPTION_KEY` decifra as credenciais do n8n, e o `backup` do
TudoIA não copia o `.env`.

Se você quiser o atalho `tudoia segredos`, `scripts\` precisa estar no PATH. O `scripts\tudoia.cmd` apenas repassa os
argumentos para o `tudoia.ps1`. Não existe um executável `tudoia` instalado pelo `pyproject.toml`.

### 4. Provisionar o Keycloak (login do painel)

Pré-requisito: o Keycloak está no ar em `http://localhost:8180`, e o realm `master` tem um administrador real.
Defina `TUDOIA_KEYCLOAK_ADMIN` e `TUDOIA_KEYCLOAK_ADMIN_PASSWORD` no `.env`, ou digite-os quando o script pedir.

```powershell
.\scripts\tudoia.ps1 keycloak --verificar     # compara o template com o Keycloak (somente leitura)
.\scripts\tudoia.ps1 keycloak                  # aplica o realm tudoia; a 2ª execução deve dizer "igual"
.\scripts\tudoia.ps1 keycloak --admin-inicial pessoa@dominio.com
```

O último comando imprime uma senha temporária uma única vez. Ela deve ser trocada no primeiro login. O passo também
grava no `.env` o `TUDOIA_OIDC_CLIENT_SECRET` (painel) e o `TUDOIA_MCP_CLIENT_ID` e `TUDOIA_MCP_CLIENT_SECRET` (cliente
de serviço do Cérebro, usado no passo 9). Ele também aplica a validade de 8 h do token do painel; sem isso, a sessão
cai em 5 min. Detalhes, papéis e solução de problemas estão em [keycloak.md](componentes/keycloak.md).

Se o Keycloak já estava provisionado antes desta versão, rode `keycloak` de novo para aplicar o token de 8 h.

Sem a configuração OIDC, o painel responde 503 em toda rota `/api`. Isso é intencional (fail-closed).

### 5. Baixar os modelos

```powershell
.\scripts\tudoia.ps1 modelos --listar
.\scripts\tudoia.ps1 modelos --obrigatorios
.\scripts\tudoia.ps1 modelos --verificar --obrigatorios
```

O download grava em `modelos\` por padrão. Os modelos Ollama são enviados ao servidor Ollama, que os guarda em
`OLLAMA_MODELS`. Lista de modelos, licenças com acesso restrito e pendências estão em
[modelos.md](componentes/modelos.md).

### 6. Preencher as chaves de provedores (opcional)

Chaves de provedores são opcionais. Um provedor só entra no roteador se **todas** as suas chaves estiverem preenchidas
(`painel/tudoia_painel/catalogo.py`). Você pode editar o `.env` diretamente ou, depois do login, usar a aba
**Segredos** do painel. Os nomes das variáveis estão em [configuracao.md](configuracao.md).

Gratuito não é privado: o texto dos pedidos enviados a provedores gratuitos sai da máquina.

### 7. Ajustar a governança antes do primeiro `up`

O `up` roda `sync` antes de subir os containers. Confira `governanca\governanca.json` antes:

- `workspaces` aponta para `D:/TudoIA` e `D:/`. Se o seu disco ou pasta for outro, altere. Um workspace inexistente
  faz o sync recusar tudo (`ErroGovernanca`).
- `instancias` cita `~/.claude-trabalho`, `~/.claude-server-commander`, `~/.gemini`, `~/.codex` e as pastas do Cursor.
  Remova o que não existe na sua máquina. Cada instância ativa recebe arquivos de configuração do cliente.
- `mcp` lista os servidores MCP ativos. Os que usam `${VAR}` obrigatório só funcionam se a variável estiver no `.env`.
  Hoje `SUPABASE_ACCESS_TOKEN` e `GITHUB_PERSONAL_ACCESS_TOKEN` são obrigatórios. Se estiverem vazios, o sync para
  sem escrever nada. Remova o MCP de `mcp` ou preencha a chave.

Leia [governanca.md](componentes/governanca.md) antes de rodar `sync` numa máquina que você não controla.

### 8. Subir os serviços

`OLLAMA_URL` pode ficar vazia: o compose passa `http://host.docker.internal:11434` ao LiteLLM quando ela está vazia.
Cérebro e Open WebUI recebem o endereço do Ollama pelo próprio `docker-compose.yml`.

```powershell
.\scripts\tudoia.ps1 up
```

O comando faz, nesta ordem:

1. Se a porta 11434 não estiver aberta, inicia `ollama serve` com `OLLAMA_HOST=127.0.0.1:11434` (só loopback) e
   `OLLAMA_MODELS` igual a `TUDOIA_OLLAMA_MODELS` do `.env` ou, sem ela, `modelos\ollama\models`.
2. Roda `sync` (distribui a governança).
3. Roda `docker compose -p tudoia -f runtime\docker-compose.yml --env-file .env up -d --build`.

Se um comando nativo falha (por exemplo, o `sync`), o script para ali com o mesmo código de saída (função `Nativo`).

Para o ComfyUI, use o painel (aba **Serviços**) ou inicie o `run_nvidia_gpu.bat` da sua instalação portable.

### 9. Gravar a credencial do Cérebro no n8n

Com o container `n8n` no ar (passo 8) e o Keycloak provisionado (passo 4):

```powershell
.\scripts\tudoia.ps1 n8n-credencial
```

O comando grava no cofre do n8n a credencial OAuth2 `TudoIA Cérebro (client_credentials)`, que o fluxo
`ingerir-documento` usa para indexar no Cérebro. O segredo sai do `.env` (`TUDOIA_MCP_CLIENT_SECRET`) e não vai para
nenhuma variável do container. Rodar de novo só sobrescreve a mesma credencial. Depois, importe o fluxo
`automacao/n8n/ingerir-documento.json` (ou reimporte, se já tinha a versão antiga). Detalhes em
[automacao-n8n.md](componentes/automacao-n8n.md#importar-os-workflows).

### 10. Abrir o painel

```powershell
.\scripts\tudoia.ps1 painel
```

Acesse `http://127.0.0.1:3100/app/`. O painel sobe em `127.0.0.1`, porta 3100. O `tudoia.ps1 painel` não repassa a
opção `--porta` do `tudoia_painel`. Trocar a porta exige também `TUDOIA_PAINEL_PORTA` e o redirect URI do Keycloak
(`keycloak`), e não foi testado.

Entre com a conta criada em `--admin-inicial`. Contas sem papel `tudoia-*` recebem 403 no login.

### 11. Backup

```powershell
.\scripts\tudoia.ps1 backup              # mantém os 7 mais recentes
.\scripts\tudoia.ps1 backup --manter 14
```

O backup (`scripts/backup/backup.py`) cria `dados\backups\<AAAAMMDD-HHMMSS>\` com:

- `litellm-db.sql.gz`: `pg_dump` do Postgres do LiteLLM (`docker exec litellm-db`);
- `cerebro.db`: cópia consistente pela API de backup do SQLite, conferida com `PRAGMA quick_check`;
- `n8n.tar.gz` e `open-webui.tar.gz`: tar dos volumes `tudoia_n8n` e `tudoia_open-webui`, lidos em modo somente
  leitura por um container `alpine:3.20.3` sem rede;
- `manifesto.json`: tamanho e sha256 de cada item e a lista do que falhou.

Cada item é independente: se um falha, os outros continuam, e o comando sai com código 1. A rotação (padrão 7,
`--manter N`) só roda quando nada falhou, e só apaga pastas com nome `AAAAMMDD-HHMMSS`. O `.env` **não** entra no
backup. Guarde-o à parte: sem a mesma `N8N_ENCRYPTION_KEY`, as credenciais do n8n restauradas não decifram. A
restauração é manual e está em `scripts/backup/restaurar.md`.

## Verificação

Rode na ordem. Cada item diz o resultado esperado.

| Verificação | Comando | Esperado |
|---|---|---|
| Containers | `.\scripts\tudoia.ps1 status` | `litellm`, `litellm-db`, `cerebro`, `searxng`, `open-webui`, `kokoro`, `n8n` em execução; os cinco com healthcheck como `healthy` |
| Cérebro | `curl.exe -s http://127.0.0.1:8765/saude` | JSON com `"ok": true` |
| Painel no ar | `curl.exe -s http://127.0.0.1:3100/saude` | `{"ok": true}` |
| Painel sem login | `curl.exe -s http://127.0.0.1:3100/api/sessao` | `"configurado": true` e `"autenticado": false` |
| Governança | `.\scripts\tudoia.ps1 verificar` | `tudo em sincronia` |
| Keycloak | `.\scripts\tudoia.ps1 keycloak --verificar` | `Sem desvios: realm igual ao template.` |
| Modelos | `.\scripts\tudoia.ps1 modelos --verificar --obrigatorios` | sem erros |
| Testes do projeto | `uv run pytest -q` | suíte de `tests\` (ver [desenvolvimento.md](desenvolvimento.md#rodar-os-testes); não executada na revisão desta documentação) |

Se o painel abrir mas as ações derem 503, confira `TUDOIA_OIDC_*` no `.env`. Se o login falhar com HTTP 401 e
`user_not_found` no log do Keycloak, veja a seção de solução de problemas de [keycloak.md](componentes/keycloak.md).

## Comandos disponíveis

Todos os comandos são subcomandos de `scripts\tudoia.ps1` (ou `scripts\tudoia.cmd`, que só repassa os argumentos).

| Comando | O que faz |
|---|---|
| `up` | Inicia Ollama (se a porta 11434 estiver livre), roda `sync` e sobe a stack Docker com `--build` |
| `down` | `docker compose down` (remove containers; os volumes são mantidos) |
| `status` | `docker compose ps` |
| `painel` | Sobe o painel em `127.0.0.1:3100` |
| `sync` | Distribui regras, skills e MCP para os clientes (`governanca`) |
| `verificar` | Lista divergências entre a governança e o disco; não escreve |
| `segredos` | Gera os segredos internos vazios no `.env` |
| `keycloak [--verificar \| --rotacionar-secret \| --admin-inicial EMAIL]` | Provisiona o realm `tudoia` |
| `modelos [--listar \| --verificar \| --modelo ID... \| --obrigatorios \| --base-dir PASTA]` | Lista, baixa e verifica os modelos |
| `n8n-credencial` | Grava no n8n (container no ar) a credencial OAuth2 do Cérebro (`scripts/n8n/credencial_cerebro.py`) |
| `backup [--manter N] [--destino PASTA]` | Backup em `dados\backups\<AAAAMMDD-HHMMSS>\` (Postgres do LiteLLM, `cerebro.db`, volumes do n8n e do Open WebUI). Sem o `.env` |

`down` não para Ollama nem ComfyUI. Para isso, use a aba **Serviços** do painel.

O código de saída do `tudoia.ps1` é o do comando nativo (`uv`, `docker`, `python`) que falhou, ou 0.

## Atualização e desinstalação

- Atualizar o código: rode `.\scripts\tudoia.ps1 backup`, depois `git pull`, `uv sync` e `.\scripts\tudoia.ps1 up`.
  As imagens Docker estão fixadas por digest, então a atualização de imagens é manual (ver
  [seguranca.md](seguranca.md#riscos-residuais)).
- Parar tudo: `.\scripts\tudoia.ps1 down`.
- Remover dados: apague `dados\` e os volumes Docker (`tudoia_open-webui`, `tudoia_n8n`, `tudoia_litellm-db`). Antes,
  guarde o `.env`, `dados\backups\` e `~\.tudoia\backups\`. A `N8N_ENCRYPTION_KEY` fica no `.env`: sem ela, as
  credenciais salvas no n8n não podem ser decifradas.

## Solução de problemas

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| Sync recusa com "variável ausente no .env" | Um MCP ativo precisa de chave vazia | Preencha a chave ou remova o MCP de `governanca.json` |
| Sync recusa com "workspace inexistente" | Caminho de `governanca.json` não existe nesta máquina | Ajuste `workspaces` |
| `litellm` não sobe ou reinicia em loop | Causa não confirmada nesta revisão; `runtime\litellm\config.yaml` ausente é uma suspeita | Veja `docker logs litellm`; gere o `config.yaml` pelo painel |
| Sessão do painel cai a cada 5 min | O Keycloak em execução ainda tem o token de 300 s do cliente `tudoia-painel` | Rode `.\scripts\tudoia.ps1 keycloak`, saia e entre de novo |
| `n8n-credencial` sai com código 1 | `TUDOIA_MCP_CLIENT_SECRET` vazio no `.env` | Rode `.\scripts\tudoia.ps1 keycloak` |
| `n8n-credencial` sai com código 2 | Container `n8n` fora do ar ou Docker indisponível | Rode `up` e tente de novo |
| Painel responde 503 em `/api/*` | Configuração OIDC ausente ou sessão com segredo menor que 32 caracteres | Rode `keycloak` e `segredos`; confira `TUDOIA_OIDC_*` |
| Painel responde 403 `host_recusado` | Acesso por um host diferente de `127.0.0.1` ou `localhost` | Use `http://127.0.0.1:3100/app/` |
| Ollama não inicia pelo `up` | `ollama` não está no PATH | Instale o Ollama e reinicie o terminal |

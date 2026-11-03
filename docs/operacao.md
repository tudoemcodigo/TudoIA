---
titulo: Operação (runbooks)
tipo: runbook
dono: TudoIA (mantenedor do repositório)
status: vigente
classificacao: publico
verificado-em: 2026-11-03
---

[🏠 TudoIA](../README.md) › [📚 Documentação](README.md) › 🛟 Operação

# 🛟 Operação (runbooks)

> Para quem opera o TudoIA numa máquina Windows e precisa agir quando algo para: um bloco por situação, com sintoma, impacto, diagnóstico,
> mitigação, escalonamento, reversão e como confirmar a recuperação. Instalar está em [instalacao.md](instalacao.md); o modelo de ameaças, em [seguranca.md](seguranca.md).

## 📑 Sumário

- [Antes de começar](#antes-de-começar)
- [O painel não sobe ou uma porta está ocupada](#o-painel-não-sobe-ou-uma-porta-está-ocupada)
- [Ollama e ComfyUI caíram ao reiniciar o painel](#ollama-e-comfyui-caíram-ao-reiniciar-o-painel)
- [Keycloak ou login falhando](#keycloak-ou-login-falhando)
- [Gateway LiteLLM sem resposta ou roteador falhando](#gateway-litellm-sem-resposta-ou-roteador-falhando)
- [SquadTI fora do ar](#squadti-fora-do-ar)
- [Backup e restauração](#backup-e-restauração)
- [Segredo comprometido](#segredo-comprometido)
- [Senha do Postgres trocada no .env sem mudar no banco](#senha-do-postgres-trocada-no-env-sem-mudar-no-banco)

---

## Antes de começar

- Rode os comandos na raiz do repositório, em PowerShell. `<projeto>` é o valor de `TUDOIA_COMPOSE_PROJETO` no `.env` (padrão `tudoia`).
- Segredos aparecem só pelo **nome** da variável e pelo lugar onde vivem (`.env`). Nenhum comando abaixo imprime um valor; não cole valores em chat, issue ou log. Os comandos que
  precisam do valor o leem de dentro do `.env` sem exibi-lo.
- **DESTRUTIVO** marca o que apaga ou sobrescreve dado e não se desfaz sozinho. Antes de cada um: confira o alvo com o comando indicado, tenha um backup válido (veja
  [Backup e restauração](#backup-e-restauração)) e peça a confirmação de quem é dono do dado. A confirmação vale para aquele comando, não para o próximo.
- Não reinicie o painel, nem pare serviços, a partir de uma tarefa em segundo plano de ferramenta que agrupa processos (veja
  [Ollama e ComfyUI caíram](#ollama-e-comfyui-caíram-ao-reiniciar-o-painel)).

Triagem em um minuto:

| O que olhar | Comando | Normal |
|---|---|---|
| Containers do compose | `.\scripts\tudoia.ps1 status` | `litellm-db` e `litellm` `healthy`, mais os dos perfis ligados |
| Painel | `curl.exe -s http://127.0.0.1:3100/saude` | `{"ok":true}` |
| Cérebro | `curl.exe -s http://127.0.0.1:8765/saude` | JSON com `"ok": true` |
| Gateway | `curl.exe -s http://127.0.0.1:4000/health/liveliness` | resposta 200 |
| Ollama | `curl.exe -s http://127.0.0.1:11434/api/version` | JSON com a versão |
| ComfyUI | `curl.exe -s http://127.0.0.1:8188/system_stats` | JSON |
| SquadTI | `curl.exe -s http://127.0.0.1:8790/saude` | `{"ok": true}` |

Onde estão os logs (`dados\logs\`): `painel.out.log` e `painel.err.log` (painel iniciado pelos scripts), `painel.log` (iniciado pelo instalador), `comfyui.log` e `comfyui.err.log`,
`roteador.jsonl` e `eventos.jsonl` (decisões do roteador), `auditoria.jsonl` (escritas no painel). No Windows o TudoIA **não** guarda a saída do `ollama serve`; para vê-la, rode `ollama serve` num terminal.
Containers: `docker logs --tail 80 <nome>`.

---

## O painel não sobe ou uma porta está ocupada

### Sintoma

- `up`, `iniciar.ps1` ou `reiniciar.ps1` terminam com "O painel nao respondeu na porta 3100; veja dados\logs\painel.err.log".
- `docker compose up` falha com porta já alocada, ou um container do compose fica em `Exited` por conflito de porta.
- O instalador recusa com "portas em uso por outro programa".
- O painel abre, mas `/api/*` responde 503 (login não configurado ou painel não reiniciado depois do `keycloak`).

### Impacto

Sem painel não há interface, login nem controle de serviços pela web; os containers e os modelos continuam funcionando. Um container que não sobe por conflito de porta tira só aquele serviço.

### Diagnóstico

Em ordem; todos só leem:

```powershell
Test-Path .\.venv\Scripts\python.exe                           # False: falta `uv sync`
Get-Content dados\logs\painel.err.log -Tail 50                 # traceback do painel
curl.exe -s http://127.0.0.1:3100/saude                        # {"ok":true} = no ar
Get-NetTCPConnection -LocalPort 3100 -ErrorAction SilentlyContinue | Where-Object OwningProcess -gt 0 | Select-Object LocalPort, OwningProcess
Get-CimInstance Win32_Process -Filter "ProcessId=<PID>" | Select-Object ProcessId, Name, CommandLine
.\scripts\tudoia.ps1 status
docker ps --format "{{.Names}}  {{.Ports}}"
docker info                                                    # falha: Docker Desktop parado
```

Como ler o resultado:

- `OwningProcess` 0 é entrada fantasma de um processo que morreu; ignore. Em alguns Windows o estado vem vazio, por isso o filtro é por `OwningProcess`, não por `Listen` (`scripts/_comum.ps1`, `DonosDaPorta`).
- Se a `CommandLine` do dono da 3100 contém `-m tudoia_painel painel`, é o próprio painel (travado ou de outra sessão). Qualquer outra coisa é outro programa.
- Portas do TudoIA: painel 3100, LiteLLM 4000, Postgres do LiteLLM 5433, Cérebro 8765, SearXNG 8080, Open WebUI 3000, Kokoro 8880, n8n 5678, Keycloak 8180, SquadTI 8790, Ollama 11434, ComfyUI 8188. Todas em `127.0.0.1`.

### Mitigação

1. `.venv` ausente: `uv sync`, e rode o script de novo.
2. Docker parado: `.\scripts\iniciar.ps1 -SemNavegador` liga o Docker Desktop (espera até 5 min), a stack e o painel. O painel sobe mesmo com a infraestrutura falhando e o script avisa o que ficou fora (sai com 1).
3. Painel próprio travado ou desatualizado: `.\scripts\reiniciar.ps1 -SemNavegador`. Reinicia **só** o painel (e a SquadTI, se estava no ar); não toca em Ollama, ComfyUI nem Docker. O script encerra apenas processos cuja linha de comando é a do painel.
4. Outro programa na porta: feche o programa pela sua própria interface. Se for preciso encerrar o processo:

   > [!CAUTION]
   > **DESTRUTIVO** (perde o trabalho não salvo do programa). Verificação do alvo: o `Get-CimInstance` acima deve mostrar `Name` e `CommandLine` que **não** são do TudoIA nem de algo que você precise, e você deve ter confirmado com quem o usa.
   > `Stop-Process -Id <PID>`
   >
   > Não use `parar.ps1` só para liberar uma porta: ele também derruba Ollama, ComfyUI e todos os containers.

5. Container do compose com porta presa: `docker ps -a` para achar o container velho, `docker compose -p <projeto> -f runtime\docker-compose.yml --env-file .env stop <serviço>` e suba de novo.
6. Painel no ar com 503 em `/api`: confira `TUDOIA_OIDC_*` e `TUDOIA_SESSAO_SEGREDO` (32 caracteres ou mais) no `.env`, rode `.\scripts\tudoia.ps1 keycloak` se o secret do cliente estiver vazio e reinicie o painel (a configuração só é lida ao iniciar). Ver [Keycloak ou login falhando](#keycloak-ou-login-falhando).

### Escalonamento

Traceback em `painel.err.log` que não seja de ambiente (porta, `.venv`, `.env`): abra uma issue no repositório com a versão (`pyproject.toml`), o trecho do log **sem segredos** e o comando que falhou. Se o log contiver segredo, trate como [segredo comprometido](#segredo-comprometido).

### Reversão

As mitigações só reiniciam processos. Para voltar ao estado anterior, nada a desfazer; para desligar tudo, `.\scripts\parar.ps1`.

### Confirmação de recuperação

`curl.exe -s http://127.0.0.1:3100/saude` devolve `{"ok":true}`; `curl.exe -s http://127.0.0.1:3100/api/sessao` devolve `"configurado": true`; `reiniciar.ps1` lista Painel, Ollama, ComfyUI e LiteLLM como "no ar".

### Último exercício

não exercitado

---

## Ollama e ComfyUI caíram ao reiniciar o painel

### Sintoma

Depois de reiniciar ou parar o painel (ou de encerrar a tarefa que o iniciou), o menu **Serviços & Runtime** mostra Ollama e ComfyUI inativos; o chat local falha, o Estúdio local não gera, jobs de imagem ou vídeo em andamento somem.

### Impacto

Modelos locais e Estúdio local indisponíveis. Os grupos de nuvem continuam; o `tudoia-auto` evita o local quando o Ollama está fora, mas um pedido direto a `tudoia-local` falha. Job de imagem ou vídeo em andamento é perdido.

### Diagnóstico

Primeiro confirme que caíram, depois descubra por que:

```powershell
curl.exe -s http://127.0.0.1:11434/api/version
curl.exe -s http://127.0.0.1:8188/system_stats
Get-Content dados\logs\comfyui.err.log -Tail 30
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'ollama|ComfyUI' } | Select-Object ProcessId, Name
```

As causas, conferidas no código:

| Causa | Onde | Quando acontece |
|---|---|---|
| `parar.ps1` | `scripts/parar.ps1` | Sempre para o painel, a SquadTI, **todos** os containers (`--profile '*'`), o Ollama e o ComfyUI. Desde o PR #19 não depende do `.env` para o Ollama e o ComfyUI (antes só os parava se o `.env` apontasse para eles). É o que o atalho **TudoIA - Parar** e `reiniciar.ps1 -Tudo` fazem |
| Parar ou reiniciar "todos" no painel | `servicos.py` `acao_todos` (`POST /api/servicos/todos/stop` ou `restart`) | Encerra Ollama e ComfyUI antes dos containers |
| Painel iniciado dentro de um Job Object do Windows | `servicos.py` (`DETACHED_FLAGS = CREATE_NEW_PROCESS_GROUP \| DETACHED_PROCESS`) | O painel inicia Ollama e ComfyUI destacados, mas isso não os tira de um Job Object. Se o painel (ou o `up` e o `iniciar.ps1` que o iniciam) rodou como **tarefa em segundo plano de uma ferramenta que usa Job Object**, como a de um agente de IA, parar a tarefa leva a árvore inteira. Observado pelo mantenedor em 30/10/2026, duas vezes, com Ollama e ComfyUI; não reproduzido nesta revisão |
| Parar o serviço pelo painel | `servicos.py` `_stop_host` | Encerra **qualquer** processo que escute em 11434 ou 8188, sem conferir qual é (risco 24 em [seguranca.md](seguranca.md#riscos-residuais)) |

`reiniciar.ps1` sem `-Tudo` **não** é causa: `PararPainel` encerra só o dono da porta 3100 cuja linha de comando contém `tudoia_painel` e quem tem `-m tudoia_painel painel` na linha de comando.

### Mitigação

Religue pelo caminho que não depende de ferramenta de terceiros:

1. Pelo painel (precisa estar no ar; papel operador ou admin): menu **Serviços & Runtime** > iniciar Ollama e ComfyUI (`POST /api/servicos/ollama/start` e `/comfyui/start`).
2. Ou por script, que é seguro com tudo já ligado: `.\scripts\iniciar.ps1 -SemNavegador`. Ele inicia o Ollama só se `TUDOIA_OLLAMA_MODELS` está no `.env` e `ollama` no PATH, e o ComfyUI só se `TUDOIA_COMFYUI_PORTABLE` está no `.env`
   e a pasta tem `python_embeded\python.exe` e `ComfyUI\main.py`. Sem essas variáveis, o `.\scripts\tudoia.ps1 up` inicia o Ollama (não o ComfyUI).
3. À mão, só o Ollama:
   `$env:OLLAMA_HOST = '127.0.0.1:11434'; $env:OLLAMA_MODELS = '<pasta-dos-pesos>'; Start-Process ollama -ArgumentList 'serve' -WindowStyle Hidden`.
   Nunca `0.0.0.0` (o Ollama não tem autenticação; risco 1).

Para não acontecer de novo:

- Reinicie o painel com `.\scripts\reiniciar.ps1` (padrão) ou pelo atalho **TudoIA - Reiniciar painel**, numa sessão sua, não como tarefa em segundo plano de ferramenta que agrupa processos.
- Quem usa uma ferramenta assim deve avisar o dono do computador **antes** de parar a tarefa e, se o painel foi iniciado por ela, pedir que ele o reinicie pelo atalho ao fim da sessão.
- Use `parar.ps1` só quando quiser tudo desligado.

### Escalonamento

Se o Ollama sobe e cai logo (porta abre e fecha), rode `ollama serve` num terminal para ler o erro; problema de driver ou GPU é do fabricante. Se o ComfyUI não sobe, leia `dados\logs\comfyui.err.log`. Erro nos scripts ou no `servicos.py`: issue no repositório.

### Reversão

Religar é a reversão. Para voltar a "tudo desligado": `.\scripts\parar.ps1`.

### Confirmação de recuperação

As duas curls de diagnóstico respondem; o menu **Serviços & Runtime** mostra Ollama e ComfyUI ativos; `.\scripts\reiniciar.ps1 -SemNavegador` mostra "Ollama no ar" e "ComfyUI no ar".

### Último exercício

não exercitado

---

## Keycloak ou login falhando

### Sintoma

Tela de erro no login; `ERR_TOO_MANY_REDIRECTS`; `Invalid redirect_uri`; 403 `sem_papel`; 503 `auth_nao_configurada` ou `identidade_indisponivel` em tudo; a sessão cai a cada 5 minutos; o container `keycloak` não fica `healthy`; `n8n-credencial` ou o Cérebro recusam o token.

### Impacto

Sem login ninguém usa o painel (fail-closed). Com o Keycloak fora, até sessões abertas são negadas com 503 na próxima reconfirmação (a cada 30 s). O Cérebro continua aceitando o `CEREBRO_TOKEN_ESTATICO` e, enquanto a chave pública do realm estiver em cache, o JWT já emitido (leitura do código, não exercitado).

### Diagnóstico

```powershell
docker ps --filter name=keycloak --format "{{.Names}}  {{.Status}}"
docker logs --tail 80 keycloak
curl.exe -s -o NUL -w '%{http_code}' http://localhost:8180/realms/tudoia/.well-known/openid-configuration   # 200
curl.exe -s http://127.0.0.1:3100/api/sessao                     # "configurado": true?
.\scripts\tudoia.ps1 keycloak --verificar                        # somente leitura; sai com 1 se o realm divergir do template
```

| Observação | Causa provável | Ação |
|---|---|---|
| `/api/sessao` com `"configurado": false` ou 503 `auth_nao_configurada` | `TUDOIA_OIDC_ISSUER`, `TUDOIA_OIDC_CLIENT_ID` ou `TUDOIA_OIDC_CLIENT_SECRET` vazios, `TUDOIA_SESSAO_SEGREDO` com menos de 32 caracteres, ou painel não reiniciado depois do `keycloak` | Mitigação 2 e 3 |
| 503 `identidade_indisponivel` com Keycloak parado | Reconfirmação no Keycloak falhou (fail-closed) | Mitigação 1 |
| Log do Keycloak com `password authentication failed` | `KEYCLOAK_DB_PASSWORD` no `.env` difere da do banco (`keycloak-db`) | [Senha do Postgres](#senha-do-postgres-trocada-no-env-sem-mudar-no-banco) |
| `keycloak` sai com código 2 / `user_not_found` | O admin de `KC_BOOTSTRAP_ADMIN_*` só é criado na **primeira** inicialização do banco; o `master` não tem esse usuário | Corrija o admin pelo console do Keycloak antes de provisionar ([keycloak.md](componentes/keycloak.md)) |
| Sessão cai a cada 5 min | Token de 300 s do cliente `tudoia-painel` ainda no Keycloak | Mitigação 3 |
| `Invalid redirect_uri` | Painel em porta diferente da registrada no cliente | Use a porta 3100 (`http://127.0.0.1:3100/app/`) ou rode `keycloak` de novo |
| 403 `sem_papel` | A conta não está em nenhum grupo `tudoia-*` | No console (`http://127.0.0.1:8180/admin`), coloque a conta em `tudoia-leitor`, `tudoia-operador` ou `tudoia-admin` |
| Laço de redirecionamento | Cookies de login antigos | Apague os cookies de `localhost` e de `127.0.0.1` e entre de novo |

### Mitigação

1. Keycloak parado ou `unhealthy`: menu **Serviços & Runtime** > reiniciar `keycloak`, ou
   `docker compose -p <projeto> -f runtime\docker-compose.yml --env-file .env up -d keycloak`. Ele leva até 90 s para ficar pronto (`start_period`) e depende do `keycloak-db` `healthy`.
2. Reaplicar o template do realm (idempotente; a segunda execução imprime "igual"): `.\scripts\tudoia.ps1 keycloak`. Ele aplica o template inteiro e regrava no `.env` o que for gerado.
3. Depois de `keycloak`, reinicie o painel, que só lê o `.env` ao iniciar: `.\scripts\reiniciar.ps1 -SemNavegador`. Quem já tinha sessão sai e entra de novo.
4. Primeiro administrador perdido: `.\scripts\tudoia.ps1 keycloak --admin-inicial <email>` cria a conta e imprime uma senha temporária **uma vez** (troca obrigatória; política de 12 caracteres).
5. Segredo de cliente comprometido: veja [Segredo comprometido](#segredo-comprometido) (`--rotacionar-secret`).
6. Realm corrompido ou perdido: o `backup` não cobre o `keycloak-db`; sem cópia própria do volume, recrie o realm com `keycloak` (e `--admin-inicial` para o primeiro administrador).

### Escalonamento

Falha de conexão que persiste com o container `healthy`, ou realm que não aceita o template: issue no repositório com a saída de `keycloak --verificar` (sem segredos). Vulnerabilidade no Keycloak em si: siga o fornecedor; no TudoIA, [como reportar](seguranca.md#como-reportar-uma-vulnerabilidade).

### Reversão

`keycloak` é idempotente e não apaga papéis ou grupos que não estão no template, mas **remove** papel sobrando nos grupos `tudoia-*` gerenciados. Para desfazer uma alteração indevida do realm não há backup pronto: o `keycloak-db` **não** entra no `backup` (ver [Backup e restauração](#backup-e-restauração)). Sem uma cópia própria do volume, reaplique o template com `keycloak` (contas criadas à mão se perdem).

### Confirmação de recuperação

`.\scripts\tudoia.ps1 keycloak --verificar` imprime "Sem desvios: realm igual ao template."; `/api/sessao` mostra `"configurado": true`; o login em `http://127.0.0.1:3100/app/` entra e a sessão passa de 5 minutos.

### Último exercício

não exercitado

---

## Gateway LiteLLM sem resposta ou roteador falhando

### Sintoma

Clientes de IA (e o Open WebUI e o n8n) recebem conexão recusada ou 5xx em `127.0.0.1:4000`; o container `litellm` fica `unhealthy` ou reinicia em laço; a resposta traz "TudoIA: todos os modelos falharam nesta resposta"; o log mostra `[roteador] não li ...`; um modelo local falha enquanto o Ollama está fora.

### Impacto

O gateway é o ponto único de chat dos clientes: sem ele, os clientes de IA configurados pelo TudoIA ficam sem modelo. Roteador degradado: `#max`, visão e nova tentativa de stream ficam desligados, mas o gateway responde.

### Diagnóstico

```powershell
.\scripts\tudoia.ps1 status
docker logs --tail 80 litellm
docker inspect --format '{{.State.Health.Status}}' litellm
curl.exe -s http://127.0.0.1:4000/health/liveliness
(Get-Item runtime\litellm\config.yaml).PSIsContainer               # True: o Docker criou uma PASTA no lugar do arquivo
Get-Content dados\logs\roteador.jsonl -Tail 5                      # decisão, grupo, motivos de cada pedido
curl.exe -s http://127.0.0.1:11434/api/version                     # Ollama, para perfis locais
```

| Observação | Causa provável | Ação |
|---|---|---|
| `config.yaml` ausente, pasta ou inválido | Arquivo gerado e não versionado (`.gitignore`); o compose o monta como arquivo | Mitigação 2 |
| Log com `password authentication failed` / `litellm` não fica `healthy` | `LITELLM_DB_PASSWORD` no `.env` difere da do banco (`litellm-db`) | [Senha do Postgres](#senha-do-postgres-trocada-no-env-sem-mudar-no-banco) |
| `litellm-db` não está `healthy` | Volume corrompido ou disco cheio | `docker logs --tail 50 litellm-db`; restaure ([Backup e restauração](#backup-e-restauração)) |
| Chave de provedor nova e o modelo continua sem chave | O container foi iniciado antes; um `restart` simples mantém o ambiente antigo | Mitigação 1 (recriar) |
| `[roteador] não li ...` | `config/roteamento.yaml` ou arquivo lido pelo hook ilegível | Corrija o arquivo; o hook mantém a última versão válida |
| Um membro de nuvem falha | O próprio LiteLLM esfria o membro por 60 s e usa o fallback do grupo | Espere; confira a chave do provedor e o limite no painel |
| `tudoia-local` falha | Ollama fora do ar (o `tudoia-auto` desvia para a nuvem) | [Ollama e ComfyUI](#ollama-e-comfyui-caíram-ao-reiniciar-o-painel) |

### Mitigação

1. Recriar o gateway lendo o `.env` de novo (o "Reiniciar" do menu **Serviços & Runtime** só faz `compose restart` e não relê o `.env`):
   `docker compose -p <projeto> -f runtime\docker-compose.yml --env-file .env up -d --no-deps --force-recreate litellm`.
   Os dados ficam no `litellm-db`; nada se perde.
2. Gerar o `config.yaml` a partir de `config/catalogo-modelos.yaml`, `config/roteamento.yaml` e do `.env` (o painel faz o mesmo em `POST /api/roteador/gerar`):
   ```powershell
   $env:PYTHONPATH = "$PWD;$PWD\painel"
   uv run python -m tudoia_painel gerar-config
   ```
   Sobrescreve `runtime\litellm\config.yaml` e guarda o anterior em `config.yaml.anterior`. Se o `config.yaml` for uma **pasta** (o Docker a criou), pare o `litellm`, confirme com `(Get-Item runtime\litellm\config.yaml).PSIsContainer`
   e remova a pasta vazia com `Remove-Item runtime\litellm\config.yaml` (**DESTRUTIVO** se não estiver vazia: liste-a antes com `Get-ChildItem`) antes de gerar. Depois recrie o `litellm` (mitigação 1).
3. Conferir a chave mestra sem exibi-la: menu **Cofre de Segredos** > testar `LITELLM_MASTER_KEY` (envia só ao LiteLLM local).
4. Provedor sem chave completa não entra no `config.yaml`, sem erro: preencha **todas** as chaves do provedor e gere de novo.

### Escalonamento

Gateway que não sobe com `config.yaml` válido, `litellm-db` saudável e senhas coerentes: issue no repositório com `docker logs --tail 80 litellm` (confira que não há chave no trecho). Falha de provedor (limite, indisponibilidade): suporte do provedor.

### Reversão

Restaure `runtime\litellm\config.yaml.anterior` sobre o `config.yaml` e recrie o `litellm` (mitigação 1). Recriar o container não altera dados.

### Confirmação de recuperação

`docker inspect --format '{{.State.Health.Status}}' litellm` devolve `healthy`; `curl.exe -s http://127.0.0.1:4000/health/liveliness` responde 200; um pedido de teste num cliente de IA volta; o menu Telemetria & Logs do painel registra o pedido.

### Último exercício

não exercitado

---

## SquadTI fora do ar

### Sintoma

O menu **SquadTI** do painel indica fora do ar (`GET /api/squadti/estado` com `"no_ar": false`); `iniciar.ps1 -ComSquadti` avisa "A API da SquadTI nao subiu; veja: docker logs squadti"; iniciar uma tarefa devolve 503 "a SquadTI recusou o token" ou "a SquadTI falhou ao processar o pedido"; `curl.exe -s http://127.0.0.1:8790/saude` não responde.

### Impacto

Só a geração de projetos pela Squad para; o restante do TudoIA não depende dela. Uma tarefa em andamento é interrompida (o estado fica no volume `squadti-dados`).

### Diagnóstico

```powershell
curl.exe -s http://127.0.0.1:8790/saude                          # {"ok": true} = no ar
docker ps -a --filter name=squadti --format "{{.Names}}  {{.Status}}"
docker logs --tail 80 squadti
foreach ($n in 'TUDOIA_SQUADTI_TOKEN','SQUADTI_API_KEY') { $l = Select-String -Path .env -Pattern "^$n=(.+)$"; '{0}: {1}' -f $n, $(if ($l) { "$($l.Matches[0].Groups[1].Value.Trim().Length) caracteres" } else { 'vazia' }) }
```

A última linha mostra só o tamanho. A Squad só sobe com `TUDOIA_SQUADTI_TOKEN` de 32 caracteres ou mais **e** `SQUADTI_API_KEY` preenchida (`SquadtiConfigurado` em `_comum.ps1`).

| Observação | Causa provável | Ação |
|---|---|---|
| `TUDOIA_SQUADTI_TOKEN` vazio | `segredos` só o gera com `squadti` em `COMPOSE_PROFILES` | Inclua `squadti` no `COMPOSE_PROFILES`, rode `.\scripts\tudoia.ps1 segredos` |
| `SQUADTI_API_KEY` vazia | A chave virtual nunca foi criada | `.\scripts\tudoia.ps1 squadti-chave` (precisa do LiteLLM no ar) |
| Gateway recusa a chave, ou a Squad falha depois de meses | A chave virtual vale **90 dias** (`scripts/squadti/chave.py`) | `.\scripts\tudoia.ps1 squadti-chave --rotacionar` e recrie o container |
| Container não inicia | `depends_on: litellm healthy`; ou o build falhou (o Dockerfile baixa a Doutrina do GitHub pelo SHA fixado) | Suba o gateway primeiro; confira a internet; `docker compose ... build squadti` |
| 503 "recusou o token" | `TUDOIA_SQUADTI_TOKEN` do painel difere do que o container recebeu | Recrie o container para ele ler o `.env` |
| Container sobe e `/saude` demora | O Docker publica a porta antes de o processo escutar (por isso `SquadtiNoAr` testa o `/saude`, não a porta) | Espere até 90 s |
| Erro de socket do Docker nos logs | Docker Desktop parado, ou `docker.sock` indisponível | Inicie o Docker Desktop |

### Mitigação

1. Subir ou recriar só a Squad (reconstrói a imagem se o código mudou e não toca nos outros serviços):
   `docker compose -p <projeto> -f runtime\docker-compose.yml --env-file .env up -d --build squadti`
   ou `.\scripts\iniciar.ps1 -ComSquadti -SemNavegador` (idempotente, liga também o que estiver parado). O "Reiniciar" do painel não recria o container.
2. Tarefa interrompida pelo reinício: o estado (checkpoint) fica no volume `squadti-dados`; veja como retomar em [squadti.md](componentes/squadti.md).
   Tarefa **escalada** (QA, revisão, orçamento ou bloqueio) não é queda da Squad: no cockpit do menu SquadTI, leia o relatório do CHEFE, ajuste os tetos se o motivo foi orçamento e use **Continuar** (`POST /api/squadti/tarefas/{tarefa}/continuar`; operador ou admin).
3. Antes de ligar a Squad em máquina nova, leia o [risco 21](seguranca.md#21-dockersock-montado-na-squadti-em-aberto-decisão-do-dono): o `docker.sock` do host está montado.

### Escalonamento

Falha de `docker compose build squadti` ou erro de Python nos logs: issue no repositório (veja [squadti.md](componentes/squadti.md)). Suspeita de código gerado agindo fora do workspace: pare a Squad (Reversão) e trate como incidente de segurança, avisando o dono.

### Reversão

`docker compose -p <projeto> -f runtime\docker-compose.yml --env-file .env stop squadti` para a Squad sem apagar o volume `squadti-dados`.

> [!CAUTION]
> **DESTRUTIVO:** `docker volume rm <projeto>_squadti-dados` apaga checkpoints e workspaces de todas as tarefas. Verificação do alvo: `docker volume ls --filter name=<projeto>_squadti`; copie o que quiser guardar antes e peça confirmação.

### Confirmação de recuperação

`curl.exe -s http://127.0.0.1:8790/saude` devolve `{"ok": true}`; `curl.exe -s http://127.0.0.1:3100/api/squadti/estado` (com sessão no painel) mostra `"no_ar": true`; `docker inspect --format '{{.State.Health.Status}}' squadti` devolve `healthy`.

### Último exercício

não exercitado

---

## Backup e restauração

### Sintoma

- `.\scripts\tudoia.ps1 backup` sai com código 1 e imprime `FALHOU n de 4 itens` e "rotação não executada"; o `manifesto.json` do backup lista `falhas`.
- É preciso restaurar: dado corrompido, volume perdido, máquina nova ou erro de operação.

### Impacto

Sem backup válido, perde-se: o banco do LiteLLM (chaves virtuais, gastos), a memória do Cérebro (`cerebro.db`), o n8n (fluxos e credenciais) e o Open WebUI (conversas). O backup **não inclui o `.env`** nem o banco do Keycloak (`keycloak-db`: realm e contas; reconstrua com `.\scripts\tudoia.ps1 keycloak`): sem ele (e sem a `N8N_ENCRYPTION_KEY`) as credenciais do n8n restauradas não decifram.

### Diagnóstico

```powershell
Get-ChildItem dados\backups -Directory | Where-Object Name -match '^\d{8}-\d{6}$' | Sort-Object Name | Select-Object -Last 5 Name
Get-Content dados\backups\<AAAAMMDD-HHMMSS>\manifesto.json        # itens (bytes, sha256) e falhas
Get-FileHash -Algorithm SHA256 dados\backups\<AAAAMMDD-HHMMSS>\cerebro.db
docker volume ls --filter name=<projeto>_
docker ps --filter name=litellm-db --format "{{.Names}}  {{.Status}}"
```

O backup tem quatro itens independentes (`scripts/backup/backup.py`): `litellm-db.sql.gz`, `cerebro.db`, `n8n.tar.gz` e `open-webui.tar.gz`. Causas comuns de falha por item:

| Falha no resumo | Causa | Ação |
|---|---|---|
| `docker não encontrado no PATH` / `docker volume inspect` sem resposta | Docker Desktop parado | Inicie o Docker e rode o backup de novo |
| `litellm-db.sql.gz` com código ≠ 0 | Container `litellm-db` parado | `docker compose ... up -d litellm-db` |
| `volume <projeto>_n8n não existe` (ou `open-webui`) | O perfil nunca foi ligado nesta instalação | O volume só nasce quando o perfil sobe. Enquanto o perfil estiver desligado o item falha e **a rotação nunca roda** (os backups antigos se acumulam em `dados\backups\`); apague os antigos à mão, depois de conferir |
| `banco não encontrado: ...cerebro.db` | Perfil `cerebro` nunca ligado | Mesma observação |
| `tempo limite de 7200 s excedido` | Docker travado | Reinicie o Docker Desktop |
| `já existe um backup com este horário` | Dois backups no mesmo segundo | Espere um segundo |

### Mitigação

**Fazer um backup agora** (sem efeito destrutivo; a rotação só apaga pastas `AAAAMMDD-HHMMSS` e só quando nada falhou):

```powershell
.\scripts\tudoia.ps1 backup [--manter N] [--destino PASTA]
```

Guarde também o `.env` em cofre; o backup não o copia (o painel mantém até 10 cópias em `dados\backups\env\`).

**Restaurar.** Os comandos exatos, item por item, estão em `scripts/backup/restaurar.md` (fonte única; este runbook não os repete). A ordem e os pontos de cuidado:

1. Escolha o backup e confira a integridade: o `sha256` de cada arquivo precisa bater com o `manifesto.json`, e o item não pode estar em `falhas`.
2. Se os serviços ainda funcionam, faça um backup **agora** do estado atual (reversão da restauração).
3. Pare o container dono do dado antes de restaurar (`litellm`, `cerebro`, `n8n`, `open-webui`); se continuar rodando, sobrescreve ou corrompe o que você restaurou.
4. Restaure só o que precisa, nas seções do arquivo:
   - Seção 1, Postgres do LiteLLM: o `DROP DATABASE ... WITH (FORCE)` é **DESTRUTIVO** e só é necessário para sobrescrever um database que já tem dados. No PowerShell 5.1, não use pipe com o dump (recodifica o texto e o estraga): copie o arquivo para dentro do container, como o arquivo explica. Em máquina nova ou volume apagado, `.\scripts\tudoia.ps1 up` recria o `litellm-db` com o database vazio.
   - Seção 2, `cerebro.db`: apague os `-wal` e `-shm` antigos antes de copiar, senão o SQLite os aplica sobre o banco restaurado. A cópia usa `-Force` (**DESTRUTIVO** para o `cerebro.db` atual).
   - Seção 3, volumes do n8n e do Open WebUI: o comando esvazia o volume (`find /v -mindepth 1 -delete`) antes de extrair: **DESTRUTIVO** para o volume inteiro.
5. Antes de cada comando destrutivo, verifique o alvo: o nome do container (`docker ps --format "{{.Names}}"`), o do volume (`docker volume ls --filter name=<projeto>_`) e a pasta do backup (`$b`) impressa na tela. Os comandos de `restaurar.md` usam o projeto padrão (`tudoia_n8n`, `tudoia_open-webui`): com outro `TUDOIA_COMPOSE_PROJETO`, troque o prefixo.
6. Suba de volta os containers parados e, se o `.env` mudou, recrie-os.

### Escalonamento

Dump que não restaura (`ON_ERROR_STOP`), `quick_check` do SQLite falhando ou sha256 divergente: tente o backup anterior (a rotação guarda os 7 mais recentes por padrão). Sem nenhum backup íntegro: issue no repositório não resolve dados perdidos; avalie reconstruir (Keycloak: `.\scripts\tudoia.ps1 keycloak`; LiteLLM: `gerar-config` e novas chaves virtuais).

### Reversão

Restaure o backup tirado no passo 2 do mesmo modo. Os `.env` anteriores estão em `dados\backups\env\`. O `config.yaml` anterior, em `runtime\litellm\config.yaml.anterior`.

### Confirmação de recuperação

`.\scripts\tudoia.ps1 status` mostra os containers `healthy`; `docker exec litellm-db psql -U litellm -d litellm -c "\dt"` lista as tabelas do LiteLLM; `curl.exe -s http://127.0.0.1:8765/saude` mostra as contagens do Cérebro de volta; o login do painel funciona; os fluxos e as credenciais do n8n aparecem (com a mesma `N8N_ENCRYPTION_KEY`); as conversas do Open WebUI voltam.

### Último exercício

não exercitado. O código do backup tem testes unitários (`tests/backup`); a restauração nunca foi exercitada de ponta a ponta neste repositório.

---

## Segredo comprometido

Vale para qualquer segredo que apareceu onde não devia: commit, log, issue, captura de tela, documento, prompt de IA, arquivo copiado para outro lugar, ou uso que você não reconhece. O apagamento do arquivo não basta (DOC-SEG-05, SEC-SUP-08).

### Sintoma

Alerta do provedor ou do GitHub; cobrança ou uso estranho na conta do provedor; linhas de `/revelar` ou de governança na `auditoria.jsonl` que ninguém reconhece; `.env`, `~\.claude.json` ou um backup em pasta sincronizada ou enviado a terceiros.

### Impacto

Depende do segredo: chave de provedor (custo e acesso à conta); `LITELLM_MASTER_KEY` (gateway e criação de chaves virtuais); `CEREBRO_TOKEN_ESTATICO` (leitura e escrita na memória do Cérebro); `TUDOIA_MCP_CLIENT_SECRET` (token de operador no Cérebro);
`TUDOIA_OIDC_CLIENT_SECRET` (cliente do painel); `N8N_ENCRYPTION_KEY` (decifra as credenciais do n8n); `TUDOIA_SESSAO_SEGREDO` (assina o cookie; forjar a sessão ainda exigiria um `access_token` válido, que o painel reconfirma a cada 30 s); `TUDOIA_SQUADTI_TOKEN` e `SQUADTI_API_KEY` (disparar tarefas na Squad).

### Diagnóstico

Descubra **o que** vazou e **por onde** sem imprimir valores: o nome da variável, o arquivo e o commit ou link. Se foi no git: `git log -S"<NOME_DA_VARIÁVEL>" --oneline` mostra o commit sem revelar o valor.
Procure uso indevido em `dados\logs\auditoria.jsonl` (quem chamou `/api/segredos/.../revelar`, `/api/governanca/...`, `/api/squadti/...`), no painel de uso e cobrança do provedor, e nos logs do container afetado.

### Mitigação

**A ordem é fixa: revogar e rotacionar primeiro; limpar o histórico depois.** Reescrever histórico nunca substitui a rotação.

1. Trate o segredo como público. Revogue no emissor (painel do provedor, GitHub, Keycloak) **antes** de qualquer outra coisa.
2. Gere o novo valor e grave no `.env` (menu **Cofre de Segredos** do painel, só admin, ou edição do arquivo; o `.env` anterior vai para `dados\backups\env\`). Para segredo **interno**: deixe a linha vazia (`NOME=`) e rode `.\scripts\tudoia.ps1 segredos`, que só preenche o que está vazio e imprime só os nomes.
3. Recrie quem consome o segredo (um `restart` simples mantém o ambiente antigo; use `up -d --no-deps --force-recreate <serviço>`; o "Reiniciar" do menu **Serviços & Runtime** não recria):

| Segredo (nome no `.env`) | Revogar / gerar | Depois |
|---|---|---|
| Chaves de provedor (`*_API_KEY`, `HF_TOKEN`, `CLOUDFLARE_*`) | Revogue no provedor e crie outra; grave no `.env` | Recriar `litellm` |
| `LITELLM_MASTER_KEY` | Esvazie e rode `segredos` | Recriar `litellm`; atualize quem usava a chave mestra; rotacione `SQUADTI_API_KEY` (linha abaixo) |
| `SQUADTI_API_KEY` | `.\scripts\tudoia.ps1 squadti-chave --rotacionar` | Recriar `squadti` |
| `TUDOIA_SQUADTI_TOKEN` | Esvazie e rode `segredos` (com `squadti` em `COMPOSE_PROFILES`) | Recriar `squadti` |
| `CEREBRO_TOKEN_ESTATICO` | Esvazie e rode `segredos` | Recriar `cerebro`; `.\scripts\tudoia.ps1 sync` para regravar os clientes de IA; reinicie os clientes |
| `TUDOIA_OIDC_CLIENT_SECRET`, `TUDOIA_MCP_CLIENT_SECRET` | `.\scripts\tudoia.ps1 keycloak --rotacionar-secret` (novo segredo de `tudoia-painel` e `tudoia-mcp`, gravado no `.env`) | `.\scripts\tudoia.ps1 n8n-credencial`; `.\scripts\reiniciar.ps1 -SemNavegador` |
| `TUDOIA_SESSAO_SEGREDO` | Esvazie e rode `segredos` | `.\scripts\reiniciar.ps1 -SemNavegador` (todas as sessões caem) |
| `TUDOIA_KEYCLOAK_ADMIN_PASSWORD` | Troque a senha do admin do `master` no console do Keycloak e grave a nova no `.env` | Rode `keycloak --verificar` para confirmar |
| `LITELLM_DB_PASSWORD`, `KEYCLOAK_DB_PASSWORD` | Siga [Senha do Postgres](#senha-do-postgres-trocada-no-env-sem-mudar-no-banco): o banco precisa acompanhar | Recriar `litellm` e `keycloak` |
| `WEBUI_SECRET_KEY`, `SEARXNG_SECRET` | Esvazie e rode `segredos` | Recriar `open-webui` / `searxng` (sessões do Open WebUI devem cair; inferido, não verificado) |
| `N8N_ENCRYPTION_KEY` | **Não troque sem recifrar:** as credenciais salvas no n8n deixam de decifrar. Exporte as credenciais com o n8n (CLI `export:credentials`) antes, ou recrie-as à mão depois | Procedimento do n8n, não verificado nesta revisão; teste fora da produção |
| Tokens de MCP (`CONTEXT7_API_KEY`, `GITHUB_PERSONAL_ACCESS_TOKEN`, `SUPABASE_*`) | Revogue no emissor, grave o novo | `.\scripts\tudoia.ps1 sync` (regrava `~\.claude.json` etc.); os backups em `~\.tudoia\backups\` ainda têm o valor antigo, já revogado |
| `TUDOIA_NUGET_PAT` | Revogue o PAT no GitHub | Recriar `squadti` |
| Senha de uma conta do painel | Redefina no Keycloak | Revogue as sessões da conta no console |

4. Se o segredo está num repositório remoto, issue, log ou documento: remova-o de lá (ou apague o artefato). Reescrever o histórico do git é **DESTRUTIVO** e irreversível: só depois da rotação, com o alvo conferido (`git log --oneline -n 5`, branch e remoto corretos) e com a aprovação explícita do dono do repositório. Peça-a para cada reescrita.
5. Dado pessoal: se o segredo dava acesso à memória ou aos documentos do Cérebro, ou ao Keycloak, e pode haver dado pessoal de terceiros envolvido, o incidente tem prazo próprio (SEC-EVT-06: comunicação à ANPD e ao titular em até 3 dias úteis do conhecimento, decisão do controlador com o encarregado e o jurídico). Registre o incidente mesmo que não comunique; veja a skill `lgpd-compliance`.
6. Registre: o que vazou (nome), quando, como, o que foi rotacionado e quando.

### Escalonamento

Dono do TudoIA e, se houver terceiros afetados, encarregado de dados e jurídico. Vulnerabilidade que causou o vazamento: [como reportar](seguranca.md#como-reportar-uma-vulnerabilidade) (advisory privado, sem colar o valor do segredo).

### Reversão

Rotação não se desfaz (é o objetivo). Se o novo valor quebrou um consumidor, restaure o `.env` anterior de `dados\backups\env\` **só** para diagnosticar e rotacione de novo, já que o valor antigo continua comprometido.

### Confirmação de recuperação

O valor antigo é recusado pelo emissor ou pelo serviço (teste pelo menu **Cofre de Segredos** > testar, que não exibe o valor); cada consumidor da tabela volta `healthy`; o uso indevido parou nos logs e no painel do provedor; a busca pelo nome da variável (`git log -S`, `Select-String`) não acha mais o valor antigo nos locais que você limpou.

### Último exercício

não exercitado

---

## Senha do Postgres trocada no .env sem mudar no banco

### Sintoma

Depois de editar `LITELLM_DB_PASSWORD` ou `KEYCLOAK_DB_PASSWORD` no `.env`, o `litellm` ou o `keycloak` não fica `healthy` ou reinicia em laço, e o log mostra `password authentication failed for user "litellm"` (ou `keycloak`). O `litellm-db` (ou o `keycloak-db`) continua `healthy` (o healthcheck `pg_isready` não autentica).

### Impacto

`litellm` fora: todos os clientes de IA ficam sem gateway. `keycloak` fora: ninguém entra no painel. Os dados estão íntegros.

### Diagnóstico

Cada banco é um container Postgres próprio: `litellm-db` (role e database `litellm`) e `keycloak-db` (role e database `keycloak`). A imagem lê `POSTGRES_PASSWORD` só ao criar o volume; a senha vive dentro do banco, e mudar o `.env` depois não a altera ([servicos-docker.md](componentes/servicos-docker.md#️-bancos-postgres)).

```powershell
docker inspect --format '{{.State.Health.Status}}' litellm-db keycloak-db litellm keycloak
docker logs --tail 40 litellm
docker logs --tail 40 keycloak
```

O erro de senha aparece no log do `litellm` ou do `keycloak`, que conectam pela rede; o `docker exec ... psql` dentro do container do banco entra pelo socket local e não prova a senha.

### Mitigação

Escolha **uma** direção. A mais segura é voltar o `.env` ao valor que o banco conhece.

**A. Voltar o `.env` ao valor antigo.** Cada gravação do `.env` guarda a versão anterior em `dados\backups\env\`. Restaure a linha da variável a partir da cópia anterior à mudança (sem exibir o valor) e recrie os consumidores (passo 3 abaixo).

**B. Fazer o banco acompanhar o `.env`** (o valor novo continua só no `.env`; a senha passa pelo stdin, não pela linha de comando):

1. Confira o alvo: o container é `litellm-db` (ou `keycloak-db`) e está `healthy`.
2. Altere o role, lendo o valor do `.env` sem exibi-lo (exemplo do `litellm`; para o Keycloak troque a variável, o container e o role por `KEYCLOAK_DB_PASSWORD`, `keycloak-db` e `keycloak`):

   ```powershell
   $nova = (Select-String -Path .env -Pattern '^LITELLM_DB_PASSWORD=(.+)$').Matches[0].Groups[1].Value.Trim()
   "ALTER ROLE litellm PASSWORD '$($nova.Replace("'","''"))';" | docker exec -i litellm-db psql -U litellm -d litellm -v ON_ERROR_STOP=1
   ```

   Saída esperada: `ALTER ROLE`.
3. Recrie quem usa a senha (a `DATABASE_URL` do `litellm` e a `KC_DB_PASSWORD` do `keycloak` são lidas na criação do container; um `restart` simples não basta):
   `docker compose -p <projeto> -f runtime\docker-compose.yml --env-file .env up -d --no-deps --force-recreate litellm` (e `keycloak`, se for o caso).

**C. Último recurso, recriar o volume.** Só se o banco puder ser reconstruído ou restaurado.

> [!CAUTION]
> **DESTRUTIVO e irreversível:** apaga o banco inteiro. No LiteLLM: chaves virtuais e gastos (restaurável só com o `litellm-db.sql.gz` do `backup`). No Keycloak: realm e contas (o `backup` **não** o cobre; reconstrua o realm com `keycloak`, perdendo contas e sessões). Verificação do alvo: `docker volume ls --filter name=<projeto>_litellm-db` (ou `<projeto>_keycloak-db`) deve listar exatamente o volume esperado; confirme que existe um backup íntegro (`manifesto.json` sem `falhas`, sha256 conferido; veja [Backup e restauração](#backup-e-restauração)) e que o dono confirmou.
> Sequência (exemplo do LiteLLM): `docker compose ... stop litellm litellm-db`, `docker compose ... rm -f litellm-db`, `docker volume rm <projeto>_litellm-db`, `.\scripts\tudoia.ps1 up` (a imagem recria o banco com a senha do `.env`) e restaure o dump.

### Escalonamento

`ALTER ROLE` falha ou o log do `litellm` mostra outro erro de banco (não de senha): issue no repositório com o trecho do log, sem segredos.

### Reversão

Repita o procedimento B com o valor anterior (da cópia em `dados\backups\env\`) ou restaure a linha antiga do `.env` e recrie os consumidores. O `ALTER ROLE` não apaga dados.

### Confirmação de recuperação

`docker inspect --format '{{.State.Health.Status}}' litellm keycloak` devolve `healthy` nos dois; `curl.exe -s http://127.0.0.1:4000/health/liveliness` responde 200; o login do painel funciona.

### Último exercício

não exercitado

---

[🏠 README](../README.md) · [📚 Documentação](README.md) · ⬅️ [Segurança](seguranca.md) · [Configuração](configuracao.md) ➡️

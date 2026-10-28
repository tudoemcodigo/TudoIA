# Restaurar um backup do TudoIA

Os backups ficam em `dados\backups\<AAAAMMDD-HHMMSS>\`, gerados por `scripts\tudoia.ps1 backup`. A restauração é
manual, item por item. Os exemplos usam PowerShell, na raiz do repositório. No Linux, troque `\` por `/`.

```powershell
$b = "dados\backups\20261027-031500"   # pasta do backup escolhido
```

## 0. Antes de começar

- Confira a integridade: o `sha256` de cada arquivo tem que bater com o `manifesto.json`. Itens listados em
  `falhas` não estão no backup.
  - Windows: `Get-FileHash -Algorithm SHA256 "$b\cerebro.db"`
  - Linux: `sha256sum "$b/cerebro.db"`
- O `.env` não entra no backup. Use o `.env` atual ou uma das cópias em `dados\backups\env`. O n8n só consegue
  decifrar as credenciais salvas com a mesma `N8N_ENCRYPTION_KEY` de quando o backup foi feito.
- Pare o container dono do dado antes de restaurar. Se ele continuar rodando, sobrescreve ou corrompe o que você
  restaurou.

## 1. Postgres do LiteLLM (`litellm-db.sql.gz`)

```powershell
docker stop litellm
docker exec litellm-db psql -U litellm -d postgres -c "DROP DATABASE litellm WITH (FORCE);" -c "CREATE DATABASE litellm OWNER litellm;"
```

Linux (o pipe do bash não mexe nos bytes):

```bash
gunzip -c "$b/litellm-db.sql.gz" | docker exec -i litellm-db psql -U litellm -d litellm -v ON_ERROR_STOP=1
```

Windows: o pipe do PowerShell 5.1 recodifica o texto e estraga o dump. Copie o arquivo para dentro do container e
rode o mesmo `psql` lá dentro:

```powershell
docker cp "$b\litellm-db.sql.gz" litellm-db:/tmp/restaurar.sql.gz
docker exec litellm-db sh -c "gunzip -c /tmp/restaurar.sql.gz | psql -U litellm -d litellm -v ON_ERROR_STOP=1; s=`$?; rm -f /tmp/restaurar.sql.gz; exit `$s"
docker start litellm
```

## 2. Cérebro (`cerebro.db`, SQLite)

```powershell
docker stop cerebro
Remove-Item dados\cerebro\cerebro.db-wal, dados\cerebro\cerebro.db-shm -ErrorAction SilentlyContinue
Copy-Item "$b\cerebro.db" dados\cerebro\cerebro.db -Force
docker start cerebro
```

Apague os `-wal`/`-shm` antigos. Se ficarem, o SQLite tenta aplicá-los sobre o banco restaurado.

## 3. Volumes do n8n e do Open WebUI (`n8n.tar.gz`, `open-webui.tar.gz`)

Esvazia o volume e extrai o tar nele (o tar guarda donos e permissões):

```powershell
docker stop n8n
docker run --rm -v tudoia_n8n:/v -v "${PWD}\${b}:/in:ro" alpine:3.20.3 sh -c "find /v -mindepth 1 -delete && tar xzf /in/n8n.tar.gz -C /v"
docker start n8n

docker stop open-webui
docker run --rm -v tudoia_open-webui:/v -v "${PWD}\${b}:/in:ro" alpine:3.20.3 sh -c "find /v -mindepth 1 -delete && tar xzf /in/open-webui.tar.gz -C /v"
docker start open-webui
```

Se o volume não existir (máquina nova), rode `scripts\tudoia.ps1 up` uma vez para criá-lo, ou crie com
`docker volume create tudoia_n8n`, e depois restaure.

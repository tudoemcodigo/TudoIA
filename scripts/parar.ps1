<#
.SYNOPSIS  Desliga o TudoIA: painel, servicos Docker e Ollama. Os dados e os volumes ficam.
#>
$ErrorActionPreference = 'Continue'
$raiz = Split-Path $PSScriptRoot -Parent
$arquivoEnv = Join-Path $raiz '.env'
$linha = if (Test-Path $arquivoEnv) { Select-String -Path $arquivoEnv -Pattern '^TUDOIA_COMPOSE_PROJETO=(.+)$' | Select-Object -First 1 }
$projeto = if ($linha) { $linha.Matches[0].Groups[1].Value.Trim() } else { 'tudoia' }

# Painel: so o processo que escuta na 3100
Get-NetTCPConnection -State Listen -LocalPort 3100 -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }

docker compose -p $projeto -f (Join-Path $raiz 'runtime\docker-compose.yml') --env-file $arquivoEnv stop

# Ollama: so se este TudoIA o instalou/configurou (TUDOIA_OLLAMA_MODELS no .env); senao o Ollama e de outro uso
$comOllama = (Test-Path $arquivoEnv) -and (Select-String -Path $arquivoEnv -Pattern '^TUDOIA_OLLAMA_MODELS=.+$' -Quiet)
if ($comOllama) { Get-NetTCPConnection -State Listen -LocalPort 11434 -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue } }
exit 0

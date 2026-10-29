<#
.SYNOPSIS  Liga o TudoIA: Docker Desktop, Ollama, ComfyUI, os servicos Docker e o painel. Abre o painel no navegador.
.NOTES     Nao mexe nos clientes de IA (para isso, use tudoia.ps1 sync). Seguro de rodar com tudo ja ligado.
#>
param([switch]$SemNavegador)
$ErrorActionPreference = 'Stop'
$raiz = Split-Path $PSScriptRoot -Parent
$arquivoEnv = Join-Path $raiz '.env'

function ValorEnv([string]$chave, [string]$padrao = '') {
    if (-not (Test-Path $arquivoEnv)) { return $padrao }
    $linha = Select-String -Path $arquivoEnv -Pattern "^$chave=(.+)$" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($linha) { return $linha.Matches[0].Groups[1].Value.Trim() }
    return $padrao
}
function PortaAberta([int]$porta) {
    [bool](Get-NetTCPConnection -State Listen -LocalPort $porta -ErrorAction SilentlyContinue)
}
function Esperar([scriptblock]$condicao, [int]$segundos) {
    $fim = (Get-Date).AddSeconds($segundos)
    while ((Get-Date) -lt $fim) { if (& $condicao) { return $true }; Start-Sleep -Seconds 3 }
    return $false
}

# 1. Docker Desktop
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    $desktop = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
    if (Test-Path $desktop) { Start-Process $desktop }
    if (-not (Esperar { docker info *> $null; $LASTEXITCODE -eq 0 } 300)) { throw 'O Docker Desktop nao ficou pronto em 5 minutos.' }
}

# 2. Ollama (so se o .env aponta para uma pasta de modelos, ou seja, se foi instalado com o TudoIA)
$pesos = ValorEnv 'TUDOIA_OLLAMA_MODELS'
if ($pesos -and -not (PortaAberta 11434) -and (Get-Command ollama -ErrorAction SilentlyContinue)) {
    $env:OLLAMA_HOST = '127.0.0.1:11434'
    $env:OLLAMA_MODELS = $pesos
    Start-Process ollama -ArgumentList 'serve' -WindowStyle Hidden
}

# 2b. ComfyUI (so se o .env aponta para uma pasta do ComfyUI portable instalada com o TudoIA)
$comfy = ValorEnv 'TUDOIA_COMFYUI_PORTABLE'
if ($comfy -and -not (PortaAberta 8188)) {
    $comfyPy = Join-Path $comfy 'python_embeded\python.exe'
    $comfyMain = Join-Path $comfy 'ComfyUI\main.py'
    if ((Test-Path $comfyPy) -and (Test-Path $comfyMain)) {
        $logs = Join-Path $raiz 'dados\logs'
        New-Item -ItemType Directory -Force $logs | Out-Null
        Start-Process $comfyPy -ArgumentList '-s', $comfyMain, '--windows-standalone-build', '--disable-auto-launch' `
            -WorkingDirectory $comfy -WindowStyle Hidden `
            -RedirectStandardOutput (Join-Path $logs 'comfyui.log') -RedirectStandardError (Join-Path $logs 'comfyui.err.log')
    }
}

# 3. Servicos Docker (os perfis vem de COMPOSE_PROFILES no .env)
$projeto = ValorEnv 'TUDOIA_COMPOSE_PROJETO' 'tudoia'
docker compose -p $projeto -f (Join-Path $raiz 'runtime\docker-compose.yml') --env-file $arquivoEnv up -d --wait --wait-timeout 300
if ($LASTEXITCODE -ne 0) { throw 'docker compose up falhou.' }

# 4. Painel
if (-not (PortaAberta 3100)) {
    $python = Join-Path $raiz '.venv\Scripts\python.exe'
    $env:PYTHONPATH = "$raiz;$raiz\painel"
    $logs = Join-Path $raiz 'dados\logs'
    New-Item -ItemType Directory -Force $logs | Out-Null
    Start-Process $python -ArgumentList '-m', 'tudoia_painel', 'painel' -WorkingDirectory $raiz -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logs 'painel.out.log') -RedirectStandardError (Join-Path $logs 'painel.err.log')
    if (-not (Esperar { PortaAberta 3100 } 90)) { throw 'O painel nao respondeu na porta 3100.' }
}
if (-not $SemNavegador) { Start-Process 'http://127.0.0.1:3100/app/' }
exit 0

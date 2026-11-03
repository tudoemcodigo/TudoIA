<#
.SYNOPSIS  Liga o TudoIA: Docker Desktop, Ollama, ComfyUI, os servicos Docker e o painel. Abre o painel no navegador.
.NOTES     Nao mexe nos clientes de IA (para isso, use tudoia.ps1 sync). Seguro de rodar com tudo ja ligado.
           -ComSquadti liga tambem a API da Squad (menu SquadTI do painel), se o .env estiver configurado.
#>
param([switch]$SemNavegador, [switch]$ComSquadti)
$ErrorActionPreference = 'Stop'
$raiz = Split-Path $PSScriptRoot -Parent
$arquivoEnv = Join-Path $raiz '.env'

. "$PSScriptRoot\_comum.ps1"

# O painel e o painel de controle: sobe SEMPRE, mesmo que o Docker, o Ollama ou o compose falhem (ai ele mostra o que esta fora).
# Os passos 1 a 3 rodam sob try; o erro e guardado e relancado depois que o painel subiu.
$erroInfra = $null
try {
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
} catch { $erroInfra = $_ }

# 4. Painel
if (-not (IniciarPainel)) { throw 'O painel nao respondeu na porta 3100; veja dados\logs\painel.err.log.' }
if ($erroInfra) {
    Write-Warning ('O painel esta no ar, mas a infraestrutura nao subiu por completo: ' + $erroInfra.Exception.Message)
    if (-not $SemNavegador) { Start-Process 'http://127.0.0.1:3100/app/' }
    exit 1
}

# 5. API da Squad (opcional)
if ($ComSquadti -and -not (IniciarSquadti)) { Write-Warning 'A API da SquadTI nao subiu; veja: docker logs squadti.' }

if (-not $SemNavegador) { Start-Process 'http://127.0.0.1:3100/app/' }
exit 0

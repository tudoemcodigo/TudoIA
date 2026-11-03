<#
.SYNOPSIS  Funcoes compartilhadas por iniciar.ps1, parar.ps1, reiniciar.ps1 e painel.ps1 (use com: . "$PSScriptRoot\_comum.ps1").
.NOTES     Somente ASCII: o PowerShell 5.1 le .ps1 sem BOM como ANSI.
           Exige $raiz definido pelo script que chama (pasta do repositorio).
#>

$script:PortaPainel = 3100
$script:PortaSquadti = 8790

function ValorEnv([string]$chave, [string]$padrao = '') {
    $arquivo = Join-Path $raiz '.env'
    if (-not (Test-Path $arquivo)) { return $padrao }
    $linha = Select-String -Path $arquivo -Pattern "^$chave=(.+)$" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($linha) { return $linha.Matches[0].Groups[1].Value.Trim() }
    return $padrao
}

# Porta aberta = uma conexao TCP de verdade funciona. Get-NetTCPConnection -State Listen NAO serve: o Windows deixa
# entradas "Listen" fantasmas (dono PID 0) de processos que morreram, e o script achava que o painel ainda estava no ar.
function PortaAberta([int]$porta) {
    $tcp = New-Object System.Net.Sockets.TcpClient
    try {
        $espera = $tcp.BeginConnect('127.0.0.1', $porta, $null, $null)
        if (-not $espera.AsyncWaitHandle.WaitOne(700)) { return $false }
        $tcp.EndConnect($espera)
        return $tcp.Connected
    } catch { return $false } finally { $tcp.Close() }
}

function Esperar([scriptblock]$condicao, [int]$segundos, [int]$passo = 2) {
    $fim = (Get-Date).AddSeconds($segundos)
    while ((Get-Date) -lt $fim) { if (& $condicao) { return $true }; Start-Sleep -Seconds $passo }
    return $false
}

function Logs {
    $pasta = Join-Path $raiz 'dados\logs'
    New-Item -ItemType Directory -Force $pasta | Out-Null
    return $pasta
}

function CmdDoProcesso([int]$processo) {
    $p = Get-CimInstance Win32_Process -Filter "ProcessId=$processo" -ErrorAction SilentlyContinue
    if ($p -and $p.CommandLine) { return $p.CommandLine }
    return ''
}

# Encerra quem escuta na porta, SEM tocar nos demais processos. Ignora PID 0 (entrada fantasma). Se $deveConter for dado,
# so encerra o processo cuja linha de comando contem o texto (nao mata outro programa que ocupe a mesma porta).
# Devolve quantos processos encerrou.
function PararPorta([int]$porta, [string]$deveConter = '') {
    $n = 0
    $donos = Get-NetTCPConnection -State Listen -LocalPort $porta -ErrorAction SilentlyContinue |
        Where-Object { $_.OwningProcess -gt 0 } | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($dono in $donos) {
        if ($deveConter -and -not ((CmdDoProcesso $dono) -like "*$deveConter*")) {
            Write-Warning "Porta ${porta}: o processo $dono nao e o esperado ($deveConter); nao foi encerrado."
            continue
        }
        # O python do venv costuma ser um launcher que gera o processo real: encerra o pai tambem, se for do mesmo servico.
        $pai = (Get-CimInstance Win32_Process -Filter "ProcessId=$dono" -ErrorAction SilentlyContinue).ParentProcessId
        Stop-Process -Id $dono -Force -ErrorAction SilentlyContinue; $n++
        if ($pai -and $deveConter -and ((CmdDoProcesso $pai) -like "*$deveConter*")) { Stop-Process -Id $pai -Force -ErrorAction SilentlyContinue }
    }
    return $n
}

# ---------------------------------------------------------------- painel
function PainelNoAr { return (PortaAberta $script:PortaPainel) }

function IniciarPainel {
    if (PainelNoAr) { return $true }
    $python = Join-Path $raiz '.venv\Scripts\python.exe'
    $env:PYTHONPATH = "$raiz;$raiz\painel"
    $logs = Logs
    Start-Process $python -ArgumentList '-m', 'tudoia_painel', 'painel' -WorkingDirectory $raiz -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logs 'painel.out.log') -RedirectStandardError (Join-Path $logs 'painel.err.log')
    return (Esperar { PainelNoAr } 90)
}

function PararPainel {
    $n = PararPorta $script:PortaPainel 'tudoia_painel'
    [void](Esperar { -not (PainelNoAr) } 15 1)
    return $n
}

# ---------------------------------------------------------------- SquadTI (container "squadti", perfil de compose "squadti", porta 8790)
function ComposeSquadti([string[]]$argumentos) {
    $projeto = ValorEnv 'TUDOIA_COMPOSE_PROJETO' 'tudoia'
    & docker compose -p $projeto -f (Join-Path $raiz 'runtime\docker-compose.yml') --env-file (Join-Path $raiz '.env') @argumentos
    return ($LASTEXITCODE -eq 0)
}

# Sem token (32+ caracteres) e sem a chave virtual do LiteLLM a API da Squad nao funciona: nao sobe.
function SquadtiConfigurado {
    return ((ValorEnv 'TUDOIA_SQUADTI_TOKEN').Length -ge 32) -and [bool](ValorEnv 'SQUADTI_API_KEY')
}

function SquadtiNoAr { return (PortaAberta $script:PortaSquadti) }

# `up -d --build squadti` ativa o perfil sozinho (servico nomeado), reconstroi se o codigo mudou e nao toca nos outros servicos.
function IniciarSquadti {
    if (-not (SquadtiConfigurado)) { Write-Warning 'SquadTI nao configurada: defina TUDOIA_SQUADTI_TOKEN (32+ caracteres) e SQUADTI_API_KEY no .env (ou rode: tudoia squadti-chave).'; return $false }
    if (-not (ComposeSquadti @('up', '-d', '--build', 'squadti'))) { Write-Warning 'docker compose up squadti falhou.'; return $false }
    return (Esperar { SquadtiNoAr } 90 2)
}

function PararSquadti {
    [void](ComposeSquadti @('stop', 'squadti'))
    return 1
}

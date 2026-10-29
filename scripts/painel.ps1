<#
.SYNOPSIS  Abre o painel do TudoIA no navegador. Se o painel nao estiver em execucao na porta 3100, sobe-o antes.
#>
param([switch]$SemNavegador)
$ErrorActionPreference = 'Stop'
$raiz = Split-Path $PSScriptRoot -Parent

function PortaAberta([int]$porta) {
    if (Get-NetTCPConnection -State Listen -LocalPort $porta -ErrorAction SilentlyContinue) { return $true }
    $tcp = New-Object System.Net.Sockets.TcpClient
    try { $tcp.Connect('127.0.0.1', $porta); return $true } catch { return $false } finally { $tcp.Dispose() }
}
function Esperar([scriptblock]$condicao, [int]$segundos) {
    $fim = (Get-Date).AddSeconds($segundos)
    while ((Get-Date) -lt $fim) { if (& $condicao) { return $true }; Start-Sleep -Seconds 1 }
    return $false
}

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

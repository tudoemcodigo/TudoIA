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

# Donos da porta (PIDs > 0; PID 0 e entrada fantasma/TimeWait). NAO filtra por estado: em alguns Windows o Get-NetTCPConnection
# devolve State vazio, e `-State Listen` nao acha nada (foi o que fez o parar.ps1 deixar o painel no ar). Quem tem socket com
# LocalPort = porta e o servidor; os clientes usam portas efemeras.
function DonosDaPorta([int]$porta) {
    return @(Get-NetTCPConnection -LocalPort $porta -ErrorAction SilentlyContinue |
        Where-Object { $_.OwningProcess -gt 0 } | Select-Object -ExpandProperty OwningProcess -Unique)
}

# Encerra quem escuta na porta, SEM tocar nos demais processos. Ignora PID 0 (entrada fantasma). Se $deveConter for dado,
# so encerra o processo cuja linha de comando contem o texto (nao mata outro programa que ocupe a mesma porta).
# Devolve quantos processos encerrou.
function PararPorta([int]$porta, [string]$deveConter = '') {
    $n = 0
    foreach ($dono in (DonosDaPorta $porta)) {
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

# Encerra os processos cuja linha de comando contem o texto (comparacao literal, sem curingas), exceto este proprio script.
# Rede de seguranca para quando a porta nao revela o dono (launcher do venv sem socket, enumeracao de portas falhando).
# Devolve quantos processos encerrou.
function PararPorLinhaDeComando([string]$trecho) {
    if (-not $trecho) { return 0 }
    $n = 0
    $alvos = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -and $_.CommandLine.Contains($trecho) })
    foreach ($p in $alvos) {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
        # O processo ainda aparece por instantes depois do Stop-Process: espera a saida antes de contar.
        Wait-Process -Id $p.ProcessId -Timeout 5 -ErrorAction SilentlyContinue
        if (-not (Get-Process -Id $p.ProcessId -ErrorAction SilentlyContinue)) { $n++ }
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

# `python -m tudoia_painel painel`: o python do venv e um launcher que gera o processo real, que e quem escuta.
$script:LinhaDoPainel = '-m tudoia_painel painel'

function PararPainel {
    $n = PararPorta $script:PortaPainel 'tudoia_painel'
    # Quem sobrou (launcher sem socket, ou porta que o Windows nao soube atribuir): pela linha de comando do proprio painel.
    $n += PararPorLinhaDeComando $script:LinhaDoPainel
    [void](Esperar { -not (PainelNoAr) } 15 1)
    return $n
}

# ---------------------------------------------------------------- servicos do host (Ollama, ComfyUI)
# Para um servico do host: primeiro quem escuta na porta (so se a linha de comando contem $deveConter) e, sobrando algo (launcher,
# bandeja, processo filho), quem tem uma das $linhas na linha de comando. Devolve quantos processos encerrou.
function PararServicoDoHost([int]$porta, [string]$deveConter, [string[]]$linhas) {
    $n = PararPorta $porta $deveConter
    foreach ($linha in $linhas) { $n += PararPorLinhaDeComando $linha }
    [void](Esperar { -not (PortaAberta $porta) } 15 1)
    return $n
}

# `ollama serve` (porta 11434), o aplicativo da bandeja que o relanca e os runners dos modelos carregados.
function PararOllama { return (PararServicoDoHost 11434 'ollama' @('ollama.exe', 'ollama app.exe')) }

# ComfyUI portable (porta 8188): `python_embeded\python.exe ... ComfyUI\main.py`.
function PararComfyui { return (PararServicoDoHost 8188 'ComfyUI' @('ComfyUI\main.py')) }

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

# "No ar" = a API responde /saude. So a porta aberta engana: o Docker publica a porta antes de o processo dentro do container escutar.
function SquadtiNoAr {
    try { return ((Invoke-WebRequest "http://127.0.0.1:$($script:PortaSquadti)/saude" -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200) }
    catch { return $false }
}

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

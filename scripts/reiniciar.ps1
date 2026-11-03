<#
.SYNOPSIS  Reinicia o TudoIA.
           Padrao: so o painel (e a API da Squad, se estava ligada). Ollama, ComfyUI, LiteLLM e os demais servicos NAO sao tocados.
           -Tudo:  desliga (parar.ps1) e liga (iniciar.ps1) a stack inteira.
.EXAMPLE   .\reiniciar.ps1                  # depois de atualizar o codigo do painel
           .\reiniciar.ps1 -ComSquadti      # reinicia o painel e liga a API da Squad
           .\reiniciar.ps1 -Tudo            # reinicia tudo (derruba e religa Ollama, ComfyUI e Docker)
.NOTES     Sai com codigo 0 se o painel (e a Squad, quando pedida ou ja ligada) voltaram; senao, 1.
#>
param([switch]$Tudo, [switch]$ComSquadti, [switch]$SemNavegador)
$ErrorActionPreference = 'Stop'
$raiz = Split-Path $PSScriptRoot -Parent
. "$PSScriptRoot\_comum.ps1"

if ($Tudo) {
    & (Join-Path $PSScriptRoot 'parar.ps1')
    $argumentos = @{}
    if ($SemNavegador) { $argumentos.SemNavegador = $true }
    if ($ComSquadti) { $argumentos.ComSquadti = $true }
    & (Join-Path $PSScriptRoot 'iniciar.ps1') @argumentos
    exit $LASTEXITCODE
}

$squadtiLigada = SquadtiNoAr
$queroSquadti = $ComSquadti -or $squadtiLigada

Write-Host 'Parando o painel...'
$parou = PararPainel
if ($queroSquadti) { Write-Host 'Parando a API da Squad...'; [void](PararSquadti) }

Write-Host 'Subindo o painel...'
$painelOk = IniciarPainel
$squadtiOk = $true
if ($queroSquadti) { Write-Host 'Subindo a API da Squad...'; $squadtiOk = IniciarSquadti }

foreach ($servico in @(@('Painel', 3100), @('Ollama', 11434), @('ComfyUI', 8188), @('LiteLLM', 4000))) {
    Write-Host ('  {0,-8} {1}' -f $servico[0], $(if (PortaAberta $servico[1]) { 'no ar' } else { 'FORA' }))
}
if ($queroSquadti) { Write-Host ('  {0,-8} {1}' -f 'SquadTI', $(if (SquadtiNoAr) { 'no ar' } else { 'FORA' })) }

if (-not $painelOk) { Write-Error 'O painel nao voltou na porta 3100; veja dados\logs\painel.err.log.'; exit 1 }
if (-not $squadtiOk) { Write-Warning 'A API da Squad nao voltou; veja dados\logs\squadti.err.log.'; exit 1 }
if (-not $SemNavegador) { Start-Process 'http://127.0.0.1:3100/app/' }
exit 0

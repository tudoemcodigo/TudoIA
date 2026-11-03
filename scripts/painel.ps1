<#
.SYNOPSIS  Abre o painel do TudoIA no navegador. Se o painel nao estiver em execucao na porta 3100, sobe-o antes.
.NOTES     Se voce atualizou o codigo do painel (rotas, servicos), ele precisa ser reiniciado: use reiniciar.ps1.
#>
param([switch]$SemNavegador)
$ErrorActionPreference = 'Stop'
$raiz = Split-Path $PSScriptRoot -Parent
. "$PSScriptRoot\_comum.ps1"

if (-not (IniciarPainel)) { throw 'O painel nao respondeu na porta 3100.' }
if (-not $SemNavegador) { Start-Process 'http://127.0.0.1:3100/app/' }
exit 0

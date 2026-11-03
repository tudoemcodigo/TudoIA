<#
.SYNOPSIS  Desliga o TudoIA: painel, API da Squad, servicos Docker, Ollama e ComfyUI. Os dados e os volumes ficam.
.NOTES     Para reiniciar so o painel (sem derrubar Ollama, ComfyUI e Docker), use reiniciar.ps1.
#>
$ErrorActionPreference = 'Continue'
$raiz = Split-Path $PSScriptRoot -Parent
$arquivoEnv = Join-Path $raiz '.env'
. "$PSScriptRoot\_comum.ps1"
$projeto = ValorEnv 'TUDOIA_COMPOSE_PROJETO' 'tudoia'

# Painel e API da Squad: so os processos deles (confere a linha de comando; nao mata outro programa que use a porta)
[void](PararPainel)
[void](PararSquadti)

docker compose -p $projeto -f (Join-Path $raiz 'runtime\docker-compose.yml') --env-file $arquivoEnv stop

# Ollama: so se este TudoIA o instalou/configurou (TUDOIA_OLLAMA_MODELS no .env); senao o Ollama e de outro uso
if (ValorEnv 'TUDOIA_OLLAMA_MODELS') { [void](PararPorta 11434) }

# ComfyUI: so se este TudoIA o instalou/configurou (TUDOIA_COMFYUI_PORTABLE no .env)
if (ValorEnv 'TUDOIA_COMFYUI_PORTABLE') { [void](PararPorta 8188) }
exit 0

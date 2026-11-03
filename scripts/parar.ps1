<#
.SYNOPSIS  Desliga o ecossistema TudoIA inteiro: painel, API da Squad, todos os servicos Docker (de qualquer perfil), Ollama e
           ComfyUI. Os dados e os volumes ficam. Sai com codigo 1 se algum deles continuar no ar.
.NOTES     Para reiniciar so o painel (sem derrubar Ollama, ComfyUI e Docker), use reiniciar.ps1.
           Cada processo so e encerrado se a linha de comando for a do servico esperado (nao mata outro programa na mesma porta).
#>
$ErrorActionPreference = 'Continue'
$raiz = Split-Path $PSScriptRoot -Parent
$arquivoEnv = Join-Path $raiz '.env'
. "$PSScriptRoot\_comum.ps1"
$projeto = ValorEnv 'TUDOIA_COMPOSE_PROJETO' 'tudoia'

# Painel e API da Squad: so os processos deles (confere a linha de comando; nao mata outro programa que use a porta)
$encerrados = PararPainel
if (PainelNoAr) { Write-Warning "O painel continua respondendo na porta $script:PortaPainel; encerre-o a mao (Gerenciador de Tarefas: python.exe com 'tudoia_painel')."; $falhou = $true }
else { Write-Host ('Painel: parado ({0} processo(s) encerrado(s)).' -f $encerrados) }
[void](PararSquadti)

# Servicos Docker: --profile '*' inclui os de perfil opcional (squadti, n8n, keycloak...), mesmo fora do COMPOSE_PROFILES do .env.
docker compose -p $projeto --profile '*' -f (Join-Path $raiz 'runtime\docker-compose.yml') --env-file $arquivoEnv stop
if ($LASTEXITCODE -ne 0) { Write-Warning 'docker compose stop falhou (o Docker Desktop esta ligado?).'; $falhou = $true }

# Ollama e ComfyUI fazem parte do ecossistema: param sempre.
$n = PararOllama
if (PortaAberta 11434) { Write-Warning 'O Ollama continua respondendo na porta 11434.'; $falhou = $true }
else { Write-Host ('Ollama: parado ({0} processo(s) encerrado(s)).' -f $n) }

$n = PararComfyui
if (PortaAberta 8188) { Write-Warning 'O ComfyUI continua respondendo na porta 8188.'; $falhou = $true }
else { Write-Host ('ComfyUI: parado ({0} processo(s) encerrado(s)).' -f $n) }

if ($falhou) { exit 1 }
exit 0

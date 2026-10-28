<#
.SYNOPSIS  Ponto de entrada do TudoIA no Windows (Linux: scripts/tudoia.sh).
.EXAMPLE   .\tudoia.ps1 segredos
           .\tudoia.ps1 keycloak --verificar
           .\tudoia.ps1 modelos --listar
           .\tudoia.ps1 n8n-credencial          # grava no n8n a credencial OAuth2 do Cérebro
           .\tudoia.ps1 backup --manter 7       # backup em dados\backups\<AAAAMMDD-HHMMSS>
           .\tudoia.ps1 up | down | status | painel | sync | verificar
.NOTES     O código de saída é o do comando nativo (uv, docker, python) que falhou, ou 0.
#>
param(
    [Parameter(Mandatory)][ValidateSet('up', 'down', 'status', 'painel', 'sync', 'verificar', 'segredos', 'keycloak', 'modelos', 'n8n-credencial', 'backup', 'verificar-openwebui', 'empacotar')][string]$Comando,
    [Parameter(ValueFromRemainingArguments)][string[]]$Resto
)
$ErrorActionPreference = 'Stop'
$raiz = Split-Path $PSScriptRoot -Parent
$env:PYTHONPATH = "$raiz;$raiz\painel"
# No PowerShell 5.1, $ErrorActionPreference='Stop' NÃO para quando um executável nativo sai com código diferente de 0.
# Nativo roda o executável e, se ele falhar, encerra o script com o mesmo código (um sync que falha não deixa o up seguir).
function Nativo {
    $exe, $argumentos = $args
    & $exe @argumentos
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
function Py { Nativo uv run --project $raiz python -m tudoia_painel @args }
function PyModulo([string]$modulo) { Nativo uv run --project $raiz python -m $modulo @Resto }
# Projeto compose: TUDOIA_COMPOSE_PROJETO do .env (padrão tudoia). Outro nome isola volumes de outra instalação.
$linhaProjeto = Select-String -Path "$raiz\.env" -Pattern '^TUDOIA_COMPOSE_PROJETO=(.+)$' -ErrorAction SilentlyContinue | Select-Object -First 1
$projeto = if ($linhaProjeto) { $linhaProjeto.Matches[0].Groups[1].Value.Trim() } else { 'tudoia' }
function Compose { Nativo docker compose -p $projeto -f "$raiz\runtime\docker-compose.yml" --env-file "$raiz\.env" @args }

switch ($Comando) {
    'up' {
        # Ollama e ComfyUI são processos do host (a GPU fica fora do Docker). Pastas e binários vêm do .env.
        if (-not (Get-NetTCPConnection -State Listen -LocalPort 11434 -ErrorAction SilentlyContinue)) {
            $env:OLLAMA_HOST = "127.0.0.1:11434"
            # Pasta de pesos: TUDOIA_OLLAMA_MODELS do .env, ou o padrão do repositório.
            $linhaPesos = Select-String -Path "$raiz\.env" -Pattern '^TUDOIA_OLLAMA_MODELS=(.+)$' -ErrorAction SilentlyContinue | Select-Object -First 1
            $env:OLLAMA_MODELS = if ($linhaPesos) { $linhaPesos.Matches[0].Groups[1].Value.Trim() } else { "$raiz\modelos\ollama\models" }
            Start-Process ollama -ArgumentList 'serve' -WindowStyle Hidden
        }
        Py sync
        Compose up -d --build
        Write-Host 'Painel: .\tudoia.ps1 painel  ->  http://127.0.0.1:3100/app/'
    }
    'down'           { Compose down }
    'status'         { Compose ps }
    'painel'         { Py painel }
    'sync'           { Py sync }
    'verificar'      { Py verificar }
    'segredos'       { Py segredos }
    'keycloak'       { PyModulo 'scripts.keycloak.provisionar' }
    'modelos'        { PyModulo 'scripts.modelos.baixar' }
    'n8n-credencial' { PyModulo 'scripts.n8n.credencial_cerebro' }
    'backup'         { PyModulo 'scripts.backup.backup' }
    'verificar-openwebui' { PyModulo 'scripts.openwebui.verificar_env' }
    'empacotar' { $env:PYTHONPATH = "$raiz;$raiz\instalador"; PyModulo 'scripts.empacotar.construir' }
}
# Chegou aqui: todo comando nativo terminou com 0 (Nativo sai antes em caso de falha).
exit 0

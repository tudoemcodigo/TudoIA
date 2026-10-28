<#
.SYNOPSIS  Desinstala o TudoIA desta maquina. Pergunta antes de apagar; dados e modelos so saem se voce pedir.
#>
$ErrorActionPreference = 'Stop'
$raiz = Split-Path $PSScriptRoot -Parent
Write-Host "Desinstalar o TudoIA de: $raiz"
Write-Host 'Isto para os servicos, remove os atalhos e apaga os arquivos do programa.'
$resp = Read-Host 'Digite DESINSTALAR para continuar'
if ($resp -ne 'DESINSTALAR') { Write-Host 'Cancelado.'; exit 1 }
$remover = Read-Host 'Apagar tambem os DADOS (bancos, volumes Docker, documentos) e os MODELOS? Digite APAGAR para sim, Enter para manter'
# O desinstalador roda de uma copia temporaria: ele apaga a propria pasta da instalacao.
# O Python da .venv esta dentro da pasta que sera apagada (e ficaria travado): usa o interpretador base, que fica fora dela.
$venv = Join-Path $raiz '.venv\Scripts\python.exe'
$python = Join-Path (& $venv -c 'import sys; print(sys.base_prefix)') 'python.exe'
$copia = Join-Path $env:TEMP ('tudoia-desinstalar-' + [guid]::NewGuid().ToString('N'))
Copy-Item (Join-Path $raiz 'instalador\tudoia_instalador') (Join-Path $copia 'tudoia_instalador') -Recurse
$env:PYTHONPATH = $copia
$argumentos = @('-m', 'tudoia_instalador.desinstalar', '--raiz', $raiz)
if ($remover -eq 'APAGAR') { $argumentos += '--remover-dados' }
& $python @argumentos
$codigo = $LASTEXITCODE
Remove-Item $copia -Recurse -Force -ErrorAction SilentlyContinue
Read-Host 'Pressione Enter para fechar'
exit $codigo

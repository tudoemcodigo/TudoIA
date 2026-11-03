#!/bin/sh
# Prepara o que o dotnet precisa no volume e entrega o controle ao comando (api.py). Nada aqui grava segredo em disco.
set -eu

mkdir -p "$HOME" /dados/nuget /dados/npm "$HOME/.nuget/NuGet"

# NuGet: nuget.org sempre; o feed privado tec-interno só quando o usuário e o PAT (read:packages) vieram por variável de ambiente.
# O arquivo guarda só a referência %VAR%, o NuGet expande na hora de usar: o PAT não vai para o disco.
CONFIG="$HOME/.nuget/NuGet/NuGet.Config"
if [ -n "${TUDOIA_NUGET_USER:-}" ] && [ -n "${TUDOIA_NUGET_PAT:-}" ]; then
  cat > "$CONFIG" <<'XML'
<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <packageSources>
    <clear />
    <add key="nuget.org" value="https://api.nuget.org/v3/index.json" />
    <add key="tec-interno" value="https://nuget.pkg.github.com/tudoemcodigo/index.json" />
  </packageSources>
  <packageSourceCredentials>
    <tec-interno>
      <add key="Username" value="%TUDOIA_NUGET_USER%" />
      <add key="ClearTextPassword" value="%TUDOIA_NUGET_PAT%" />
    </tec-interno>
  </packageSourceCredentials>
</configuration>
XML
else
  cat > "$CONFIG" <<'XML'
<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <packageSources>
    <clear />
    <add key="nuget.org" value="https://api.nuget.org/v3/index.json" />
  </packageSources>
</configuration>
XML
fi

# Template do serviço (dotnet new tec-project): só se a pasta do TemplateTEC foi montada em /template.
if [ -f /template/.template.config/template.json ]; then
  dotnet new install /template >/dev/null 2>&1 || echo "aviso: nao consegui instalar o template TEC de /template" >&2
fi

exec "$@"

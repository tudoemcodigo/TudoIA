#!/bin/sh
# Prepara o que o dotnet precisa no volume e entrega o controle ao comando (api.py). Nada aqui grava segredo em disco.
set -eu

mkdir -p "$HOME" /dados/nuget /dados/npm "$HOME/.nuget/NuGet"

# NuGet: nuget.org sempre. Feed público das TEC.* (TUDOIA_NUGET_FEED_URL, sem credencial) e/ou o feed tec-interno do GitHub Packages,
# este só quando o usuário e o PAT (read:packages) vieram por variável de ambiente.
# O arquivo guarda só a referência %VAR%, o NuGet expande na hora de usar: o PAT não vai para o disco.
CONFIG="$HOME/.nuget/NuGet/NuGet.Config"
FEED_PUBLICO=""
if [ -n "${TUDOIA_NUGET_FEED_URL:-}" ]; then
  case "$TUDOIA_NUGET_FEED_URL" in
    https://*) FEED_PUBLICO="    <add key=\"tec-publico\" value=\"$TUDOIA_NUGET_FEED_URL\" />" ;;
    *) echo "aviso: TUDOIA_NUGET_FEED_URL precisa começar com https://; ignorada" >&2 ;;
  esac
fi
if [ -n "${TUDOIA_NUGET_USER:-}" ] && [ -n "${TUDOIA_NUGET_PAT:-}" ]; then
  cat > "$CONFIG" <<'XML'
<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <packageSources>
    <clear />
    <add key="nuget.org" value="https://api.nuget.org/v3/index.json" />
    <add key="tec-interno" value="https://nuget.pkg.github.com/tudoemcodigo/index.json" />
__FEED_PUBLICO__
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
__FEED_PUBLICO__
  </packageSources>
</configuration>
XML
fi
# Linha do feed público (ou nada) no lugar do marcador.
if [ -n "$FEED_PUBLICO" ]; then
  awk -v l="$FEED_PUBLICO" '$0 == "__FEED_PUBLICO__" { print l; next } { print }' "$CONFIG" > "$CONFIG.tmp" && mv "$CONFIG.tmp" "$CONFIG"
else
  grep -v "^__FEED_PUBLICO__$" "$CONFIG" > "$CONFIG.tmp" && mv "$CONFIG.tmp" "$CONFIG"
fi

# Template do serviço (dotnet new tec-project): só se a pasta do TemplateTEC foi montada em /template.
if [ -f /template/.template.config/template.json ]; then
  dotnet new install /template >/dev/null 2>&1 || echo "aviso: nao consegui instalar o template TEC de /template" >&2
fi

exec "$@"

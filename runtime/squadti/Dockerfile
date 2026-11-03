# SquadTI: orquestrador LangGraph + SDK .NET e Node para compilar e testar o código que a própria Squad gera.
# O código gerado por modelo é dado não confiável (MSBuild e npm executam código dele): por isso roda aqui, sem root, com
# sistema de arquivos somente leitura (ver o serviço `squadti` no docker-compose.yml). O compose monta o docker.sock do host para os
# testes de integração (decisão do dono): isso devolve ao código gerado o poder de root no host; leia o aviso no compose.

# --- Doutrina TEC: clonada numa versão (SHA) fixada, sem histórico. Trocar a Doutrina = trocar o SHA aqui (e o hash no estado
# de cada tarefa, ECO-CON-02, acusa a mudança no meio de uma tarefa).
FROM alpine/git:2.49.1@sha256:c0280cf9572316299b08544065d3bf35db65043d5e3963982ec50647d2746e26 AS doutrina
ARG DOUTRINA_SHA=80877ed7e68e87458b17dc2d5b9e6d03e456ea4b
RUN git init -q /doutrina \
 && git -C /doutrina fetch -q --depth 1 https://github.com/tudoemcodigo/Doutrina.git "$DOUTRINA_SHA" \
 && git -C /doutrina checkout -q FETCH_HEAD \
 && test -f /doutrina/gerado/manifesto.json \
 && rm -rf /doutrina/.git

FROM node:24-slim@sha256:c86ecead9e55a5210ac1727de38a4ca840bf03dcaf34dc9749addbf383b1920c AS node
FROM ghcr.io/astral-sh/uv:0.13.0@sha256:cdc6093146eb3ff6a40107b38f008b789e050e77ad87865e381d9917da55a168 AS uv

FROM mcr.microsoft.com/dotnet/sdk:10.0@sha256:de4fe90a98845d75910b9769662465c84de1a934665c431279d1382b2bddc02b

COPY --from=uv /uv /usr/local/bin/uv
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

# Sem root. Tudo que muda fica em /dados (volume); o resto da imagem é somente leitura.
RUN useradd --system --uid 10001 --home-dir /dados/home --shell /usr/sbin/nologin squadti \
 && mkdir -p /dados /app \
 && chown squadti:squadti /dados

WORKDIR /app
ENV UV_PYTHON_INSTALL_DIR=/opt/python UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project
COPY orquestrador ./orquestrador
COPY --from=doutrina /doutrina /doutrina
COPY entrypoint.sh /usr/local/bin/squadti-entrypoint
RUN chmod 0555 /usr/local/bin/squadti-entrypoint

# Sem telemetria dos SDKs e caches no volume (o rootfs é somente leitura).
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    HOME=/dados/home DOTNET_CLI_HOME=/dados/home DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1 \
    DOTNET_SKIP_FIRST_TIME_EXPERIENCE=1 DOTNET_GENERATE_ASPNET_CERTIFICATE=false \
    NUGET_PACKAGES=/dados/nuget npm_config_cache=/dados/npm npm_config_update_notifier=false npm_config_fund=false \
    DOUTRINA_TEC=/doutrina TUDOIA_SQUADTI_HOST=0.0.0.0 TUDOIA_MODEL=tudoia-local-estrito

USER squadti
WORKDIR /dados
EXPOSE 8790
ENTRYPOINT ["squadti-entrypoint"]
CMD ["python", "/app/orquestrador/api.py", "--porta", "8790", "--db", "/dados/squad_state.db", "--config", "/app/orquestrador/stack_config.example.json"]

FROM python:3.12-slim

# uv fixado em versão (não `latest`), para o build ser reproduzível.
COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /usr/local/bin/uv

# Sem root: o processo só precisa de leitura no código e de escrita em /dados.
RUN useradd --system --uid 10001 --create-home cerebro \
 && mkdir -p /dados && chown cerebro:cerebro /dados

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY cerebro ./cerebro
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER cerebro
EXPOSE 8765
# Direto no venv: `uv run` tentaria reconciliar o ambiente, e o usuário não escreve em /app.
CMD ["python", "-m", "cerebro"]

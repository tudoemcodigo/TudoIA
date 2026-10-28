#!/usr/bin/env bash
# Ponto de entrada do TudoIA no Linux. Equivalente ao scripts/tudoia.ps1 (Windows), com os mesmos comandos.
#
# Limites deste script:
#   - O ComfyUI NÃO é iniciado aqui. Inicie-o à mão (ou pelo painel, aba Serviços).
#   - O Ollama é iniciado pelo "up" somente se o binário estiver no PATH e a porta 11434 estiver livre.
#   - Onde o Ollama escuta (ver endereco_ollama):
#       Docker Desktop: 127.0.0.1:11434. Os containers chegam ao loopback do host por host.docker.internal (testado).
#       Docker Engine puro no Linux: host.docker.internal (extra_hosts: host-gateway) é o IP da bridge docker0
#       (ex.: 172.17.0.1), NÃO o loopback. Um Ollama em 127.0.0.1 fica inalcançável para os containers; por isso o
#       script usa o IP da docker0. Nunca 0.0.0.0: exporia o Ollama (sem autenticação) para a rede local.
#   - Não foi testado em Linux nem em macOS.
#
# Uso: scripts/tudoia.sh up | down | status | painel | sync | verificar | segredos
#                        keycloak [opções] | modelos [opções] | n8n-credencial | backup [opções]
#                        verificar-openwebui [--aprovar]
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$RAIZ/.env"

uso() {
    cat <<'EOF'
Uso: scripts/tudoia.sh COMANDO [opções]

Comandos:
  up          Inicia o Ollama (se estiver no PATH e a porta 11434 livre), roda sync e sobe a stack Docker.
              O ComfyUI NÃO é iniciado por este script.
  down        Para os containers (os volumes são mantidos).
  status      Mostra o estado dos containers.
  painel      Sobe o painel em 127.0.0.1:3100.
  sync        Distribui regras, skills e MCP para os clientes de IA.
  verificar   Lista divergências entre a governança e o disco (somente leitura).
  segredos    Gera os segredos internos vazios no .env.
  keycloak    Provisiona o realm tudoia. Opções são repassadas (ex.: --verificar, --admin-inicial EMAIL).
  modelos     Lista, baixa e verifica os modelos. Opções são repassadas (ex.: --listar, --obrigatorios).
  n8n-credencial
              Grava no n8n (container no ar) a credencial OAuth2 que o fluxo ingerir-documento usa no Cérebro.
  verificar-openwebui
              Confere runtime/open-webui/env.py contra o env.py da imagem fixada (--aprovar grava o diff revisado).
  backup      Backup em dados/backups/AAAAMMDD-HHMMSS (Postgres do LiteLLM, cerebro.db, volumes n8n e
              open-webui). Opções são repassadas (ex.: --manter 7). O .env não entra no backup.
EOF
}

# Python do projeto: .venv do repositório, senão "uv run --project", senão erro explícito.
py() {
    export PYTHONPATH="$RAIZ:$RAIZ/painel${PYTHONPATH:+:$PYTHONPATH}"
    if [ -x "$RAIZ/.venv/bin/python" ]; then
        "$RAIZ/.venv/bin/python" "$@"
    elif command -v uv >/dev/null 2>&1; then
        uv run --project "$RAIZ" python "$@"
    else
        echo "tudoia.sh: nem .venv/bin/python nem uv encontrados. Rode 'uv sync' ou instale o uv." >&2
        exit 1
    fi
}

# Projeto compose: TUDOIA_COMPOSE_PROJETO do .env (padrão tudoia). Outro nome isola volumes de outra instalação.
projeto_compose() {
    local v=""
    [ -f "$ENV_FILE" ] && v="$(sed -n 's/^TUDOIA_COMPOSE_PROJETO=//p' "$ENV_FILE" | tail -n1 | tr -d ' ')"
    echo "${v:-tudoia}"
}

compose() {
    docker compose -p "$(projeto_compose)" -f "$RAIZ/runtime/docker-compose.yml" --env-file "$ENV_FILE" "$@"
}

# Pasta de pesos do Ollama: TUDOIA_OLLAMA_MODELS do .env, ou o padrão do repositório.
pasta_modelos_ollama() {
    local valor=""
    if [ -f "$ENV_FILE" ]; then
        valor="$(grep -E '^TUDOIA_OLLAMA_MODELS=' "$ENV_FILE" | tail -n 1 | cut -d= -f2- | tr -d '\r' || true)"
        valor="$(printf '%s' "$valor" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
    fi
    if [ -n "$valor" ]; then
        printf '%s\n' "$valor"
    else
        printf '%s\n' "$RAIZ/modelos/ollama/models"
    fi
}

# Verdadeiro se algo já aceita conexões em $1:11434 (teste sem depender de ss, netstat ou lsof).
ollama_escutando() {
    (exec 3<>"/dev/tcp/$1/11434") >/dev/null 2>&1
}

# IP em que o Ollama deve escutar para os containers o alcançarem por host.docker.internal.
#   Docker Desktop (Linux ou macOS): 127.0.0.1 (o Desktop encaminha host.docker.internal ao loopback do host).
#   Docker Engine puro no Linux: IP IPv4 da bridge docker0, que é o que o host-gateway resolve. Sem docker0,
#   avisa e fica em 127.0.0.1 (os containers não alcançarão o Ollama). Nunca 0.0.0.0.
endereco_ollama() {
    local so ip
    so="$(docker info --format '{{.OperatingSystem}}' 2>/dev/null || true)"
    if [ "$(uname -s)" = "Darwin" ] || [[ "$so" == *"Docker Desktop"* ]]; then
        printf '127.0.0.1\n'
        return 0
    fi
    ip="$(ip -4 -o addr show docker0 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | head -n 1 || true)"
    if [ -z "$ip" ]; then
        echo "aviso: Docker Desktop não detectado e a bridge docker0 não tem IPv4 ('ip -4 addr show docker0')." >&2
        echo "       O Ollama ficará em 127.0.0.1:11434 e os containers NÃO vão alcançá-lo." >&2
        printf '127.0.0.1\n'
        return 0
    fi
    echo "aviso: Docker Engine sem Docker Desktop: o Ollama vai escutar em $ip:11434 (bridge docker0), não em" >&2
    echo "       127.0.0.1. No host, use OLLAMA_HOST=$ip:11434 (ollama CLI, painel). Firewall (ufw) precisa" >&2
    echo "       permitir a porta 11434 vinda das redes do Docker." >&2
    printf '%s\n' "$ip"
}

iniciar_ollama() {
    local host
    host="$(endereco_ollama)"
    if ollama_escutando "$host"; then
        return 0
    fi
    if [ "$host" != "127.0.0.1" ] && ollama_escutando 127.0.0.1; then
        echo "aviso: já há um Ollama em 127.0.0.1:11434, inalcançável para os containers. Pare-o e rode 'up' de novo." >&2
        return 0
    fi
    if ! command -v ollama >/dev/null 2>&1; then
        echo "Ollama não está no PATH: não iniciado. Os modelos locais ficarão indisponíveis." >&2
        return 0
    fi
    # Docker Desktop: só loopback. Docker Engine puro: só o IP da docker0 (ver endereco_ollama).
    export OLLAMA_HOST="$host:11434"
    export OLLAMA_MODELS
    OLLAMA_MODELS="$(pasta_modelos_ollama)"
    mkdir -p "$RAIZ/dados"
    nohup ollama serve >"$RAIZ/dados/ollama.log" 2>&1 &
    echo "Ollama iniciado em $OLLAMA_HOST (log: $RAIZ/dados/ollama.log)."
}

comando="${1:-}"
if [ $# -gt 0 ]; then
    shift
fi

case "$comando" in
    up)
        iniciar_ollama
        py -m tudoia_painel sync
        compose up -d --build
        echo "Painel: scripts/tudoia.sh painel  ->  http://127.0.0.1:3100/app/"
        echo "ComfyUI: não iniciado por este script. Inicie-o à mão, se precisar do Estúdio local."
        ;;
    down)      compose down ;;
    status)    compose ps ;;
    painel)    py -m tudoia_painel painel ;;
    sync)      py -m tudoia_painel sync ;;
    verificar) py -m tudoia_painel verificar ;;
    segredos)  py -m tudoia_painel segredos ;;
    keycloak)  py -m scripts.keycloak.provisionar "$@" ;;
    modelos)   py -m scripts.modelos.baixar "$@" ;;
    n8n-credencial) py -m scripts.n8n.credencial_cerebro "$@" ;;
    backup)    py -m scripts.backup.backup "$@" ;;
    verificar-openwebui) py -m scripts.openwebui.verificar_env "$@" ;;
    empacotar) PYTHONPATH="$RAIZ:$RAIZ/instalador" py -m scripts.empacotar.construir "$@" ;;
    -h|--help|ajuda)
        uso
        ;;
    *)
        uso >&2
        exit 2
        ;;
esac

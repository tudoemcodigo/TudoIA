"""Serviço `squadti` do compose: endurecimento mantido e o docker.sock montado só de forma explícita, com o aviso junto."""
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[1]
COMPOSE = RAIZ / "runtime" / "docker-compose.yml"


def _servico() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]["squadti"]


def test_endurecimento_do_container_continua():
    s = _servico()
    assert s["read_only"] is True and s["cap_drop"] == ["ALL"] and "no-new-privileges:true" in s["security_opt"]
    assert s["profiles"] == ["squadti"] and s["ports"] == ["127.0.0.1:8790:8790"]   # só loopback, só com o perfil
    assert "pids_limit" in s and "mem_limit" in s and "cpus" in s


def test_docker_sock_montado_traz_group_add_host_override_e_aviso():
    s = _servico()
    assert "/var/run/docker.sock:/var/run/docker.sock" in s["volumes"]
    assert s["group_add"] == ["0"]   # sem o grupo 0 o uid 10001 nao alcanca o socket (root:root 0660 no Docker Desktop)
    assert "TESTCONTAINERS_HOST_OVERRIDE=host.docker.internal" in s["environment"]
    assert "host.docker.internal:host-gateway" in s["extra_hosts"]
    texto = COMPOSE.read_text(encoding="utf-8")
    assert "ATENÇÃO" in texto and "root no host" in texto   # o risco fica escrito ao lado da linha
    doc = (RAIZ / "docs" / "componentes" / "squadti.md").read_text(encoding="utf-8")
    assert "docker.sock" in doc and "root no host" in doc


def test_feed_publico_e_opcional_e_so_https():
    s = _servico()
    assert "TUDOIA_NUGET_FEED_URL=${TUDOIA_NUGET_FEED_URL:-}" in s["environment"]
    entrypoint = (RAIZ / "runtime" / "squadti" / "entrypoint.sh").read_text(encoding="utf-8")
    assert "https://*" in entrypoint and "tec-publico" in entrypoint

"""Testes do backup (scripts/backup/backup.py). Nada toca o Docker real: o "docker" é um script Python em tmp_path
que responde pelo argv (exec pg_dump, volume inspect, run ... tar), rodado de verdade por subprocess."""
from __future__ import annotations

import gzip
import hashlib
import json
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import pytest

from scripts.backup import backup

SQL = "-- dump falso\nCREATE TABLE t (x int);\nINSERT INTO t VALUES (1);\n" * 2000
SEGREDO = "sk-SEGREDO-DO-ENV-123"

DOCKER_FALSO = r'''
import json, sys
from pathlib import Path
cfg = json.loads(Path(__file__).with_name("cfg.json").read_text(encoding="utf-8"))
args = sys.argv[1:]
with open(Path(__file__).with_name("chamadas.jsonl"), "a", encoding="utf-8") as log:
    log.write(json.dumps(args) + "\n")
if args[:2] == ["exec", "litellm-db"]:
    if not cfg["postgres_no_ar"]:
        sys.stderr.write("Error response from daemon: container litellm-db is not running\n")
        sys.exit(1)
    sys.stdout.buffer.write(cfg["sql"].encode("utf-8"))
    sys.exit(0)
if args[:2] == ["volume", "inspect"]:
    sys.exit(0 if args[2] in cfg["volumes"] else 1)
if args[:2] == ["run", "--rm"]:
    volume = next(a for a in args if a.endswith(":/v:ro")).split(":")[0]
    sys.stdout.buffer.write(("TAR-DE:" + volume).encode("utf-8") * 1000)
    sys.exit(0)
sys.exit(99)
'''


@pytest.fixture
def ambiente(tmp_path):
    """Raiz falsa com .env e cerebro.db reais; docker falso configurável."""
    raiz = tmp_path / "raiz"
    (raiz / "dados" / "cerebro").mkdir(parents=True)
    (raiz / ".env").write_text(f"LITELLM_MASTER_KEY={SEGREDO}\n", encoding="utf-8")
    banco = raiz / "dados" / "cerebro" / "cerebro.db"
    con = sqlite3.connect(banco)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE memoria (id INTEGER PRIMARY KEY, texto TEXT)")
    con.executemany("INSERT INTO memoria (texto) VALUES (?)", [(f"lembranca {i}",) for i in range(500)])
    con.commit()
    con.close()

    pasta_docker = tmp_path / "docker"
    pasta_docker.mkdir()
    script = pasta_docker / "docker_falso.py"
    script.write_text(DOCKER_FALSO, encoding="utf-8")
    cfg = {"postgres_no_ar": True, "sql": SQL, "volumes": ["tudoia_n8n", "tudoia_open-webui"]}

    class Ambiente:
        destino = raiz / "dados" / "backups"
        docker = (sys.executable, "-I", str(script))  # -I: o dublê não lê PYTHON* nem o diretório atual

        def __init__(self):
            self.raiz, self.banco, self.cfg = raiz, banco, cfg
            self.mensagens: list[str] = []

        def rodar(self, momento: datetime = datetime(2026, 10, 27, 3, 15, 0), manter: int = 7) -> int:
            (pasta_docker / "cfg.json").write_text(json.dumps(self.cfg), encoding="utf-8")
            return backup.executar_backup(self.destino, manter=manter, docker=self.docker, raiz=self.raiz,
                                          agora=momento, saida=self.mensagens.append)

        def chamadas(self) -> list[list[str]]:
            log = pasta_docker / "chamadas.jsonl"
            return [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []

    return Ambiente()


def _manifesto(pasta: Path) -> dict:
    return json.loads((pasta / "manifesto.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- caminho feliz
def test_backup_completo_gera_todos_os_itens_e_manifesto_com_sha256(ambiente):
    assert ambiente.rodar() == 0

    pasta = ambiente.destino / "20261027-031500"
    nomes = sorted(p.name for p in pasta.iterdir())
    assert nomes == ["cerebro.db", "litellm-db.sql.gz", "manifesto.json", "n8n.tar.gz", "open-webui.tar.gz"]
    with gzip.open(pasta / "litellm-db.sql.gz", "rt", encoding="utf-8") as arq:
        assert arq.read() == SQL
    assert (pasta / "n8n.tar.gz").read_bytes().startswith(b"TAR-DE:tudoia_n8n")
    assert (pasta / "open-webui.tar.gz").read_bytes().startswith(b"TAR-DE:tudoia_open-webui")

    manifesto = _manifesto(pasta)
    assert manifesto["falhas"] == [] and manifesto["env_incluido"] is False
    assert {i["arquivo"] for i in manifesto["itens"]} == {"cerebro.db", "litellm-db.sql.gz", "n8n.tar.gz",
                                                          "open-webui.tar.gz"}
    for item in manifesto["itens"]:
        conteudo = (pasta / item["arquivo"]).read_bytes()
        assert item["sha256"] == hashlib.sha256(conteudo).hexdigest()
        assert item["bytes"] == len(conteudo)


def test_env_nao_entra_no_backup_nem_na_saida(ambiente):
    ambiente.rodar()

    pasta = ambiente.destino / "20261027-031500"
    assert not (pasta / ".env").exists()
    for arquivo in pasta.iterdir():
        dados = gzip.decompress(arquivo.read_bytes()) if arquivo.name.endswith(".sql.gz") else arquivo.read_bytes()
        assert SEGREDO.encode() not in dados
    texto = "\n".join(ambiente.mensagens)
    assert SEGREDO not in texto and ".env NÃO foi copiado" in texto


def test_volumes_montados_so_leitura_com_alpine_fixada_e_sem_rede(ambiente):
    ambiente.rodar()

    runs = [c for c in ambiente.chamadas() if c[:1] == ["run"]]
    assert len(runs) == 2
    for c in runs:
        assert backup.IMAGEM_ALPINE in c
        assert re.fullmatch(r"alpine:\d+\.\d+\.\d+", backup.IMAGEM_ALPINE)  # versão fixa, nunca latest
        assert any(a.endswith(":/v:ro") for a in c)
        assert c[c.index("--network") + 1] == "none"
    assert ["exec", "litellm-db", "pg_dump", "-U", "litellm", "litellm"] in ambiente.chamadas()


# ---------------------------------------------------------------- SQLite consistente
def test_sqlite_copia_consistente_com_escrita_em_andamento(ambiente):
    con = sqlite3.connect(ambiente.banco)
    con.execute("BEGIN IMMEDIATE")
    con.executemany("INSERT INTO memoria (texto) VALUES (?)", [("nao confirmado",)] * 100)
    try:
        assert ambiente.rodar() == 0
    finally:
        con.rollback()
        con.close()

    copia = sqlite3.connect(ambiente.destino / "20261027-031500" / "cerebro.db")
    try:
        assert copia.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert copia.execute("SELECT count(*) FROM memoria").fetchone()[0] == 500  # só o que foi confirmado
    finally:
        copia.close()


def test_sqlite_ausente_falha_o_item_e_nao_cria_banco_vazio(ambiente):
    ambiente.banco.unlink()

    assert ambiente.rodar() == 1

    assert not ambiente.banco.exists()
    manifesto = _manifesto(ambiente.destino / "20261027-031500")
    assert [f["arquivo"] for f in manifesto["falhas"]] == ["cerebro.db"]


# ---------------------------------------------------------------- falha parcial
def test_container_parado_nao_impede_os_outros_itens_e_sai_com_1(ambiente):
    ambiente.cfg["postgres_no_ar"] = False

    assert ambiente.rodar() == 1

    pasta = ambiente.destino / "20261027-031500"
    assert not (pasta / "litellm-db.sql.gz").exists()          # nada pela metade
    for nome in ("cerebro.db", "n8n.tar.gz", "open-webui.tar.gz"):
        assert (pasta / nome).is_file()
    manifesto = _manifesto(pasta)
    assert len(manifesto["itens"]) == 3
    assert manifesto["falhas"][0]["arquivo"] == "litellm-db.sql.gz"
    assert "not running" in manifesto["falhas"][0]["erro"]
    assert any(m.startswith("FALHOU 1 de 4") for m in ambiente.mensagens)


def test_volume_inexistente_falha_sem_criar_volume_vazio(ambiente):
    ambiente.cfg["volumes"] = ["tudoia_n8n"]

    assert ambiente.rodar() == 1

    runs = [c for c in ambiente.chamadas() if c[:1] == ["run"]]
    assert len(runs) == 1 and "tudoia_n8n:/v:ro" in runs[0]  # o docker run do volume ausente nem é chamado
    falhas = _manifesto(ambiente.destino / "20261027-031500")["falhas"]
    assert [f["arquivo"] for f in falhas] == ["open-webui.tar.gz"]


def test_docker_ausente_falha_os_itens_docker_e_salva_o_sqlite(ambiente):
    ambiente.docker = ("executavel-que-nao-existe-tudoia",)

    assert ambiente.rodar() == 1

    manifesto = _manifesto(ambiente.destino / "20261027-031500")
    assert [i["arquivo"] for i in manifesto["itens"]] == ["cerebro.db"]
    assert len(manifesto["falhas"]) == 3


def test_processo_travado_e_morto_no_tempo_limite(tmp_path):
    travado = [sys.executable, "-I", "-c", "import sys, time; sys.stdout.write('x'); sys.stdout.flush(); time.sleep(60)"]

    with pytest.raises(backup.ErroEtapa, match="tempo limite"):
        backup._transmitir(travado, tmp_path / "saida.bin", comprimir=False, timeout=2)


# ---------------------------------------------------------------- rotação
def _backup_antigo(destino: Path, nome: str) -> Path:
    pasta = destino / nome
    pasta.mkdir(parents=True)
    (pasta / "manifesto.json").write_text("{}", encoding="utf-8")
    return pasta


def test_rotacao_mantem_os_n_mais_recentes_e_nao_toca_outras_pastas(ambiente):
    for dia in range(1, 7):
        _backup_antigo(ambiente.destino, f"202610{dia:02d}-000000")
    (ambiente.destino / "env").mkdir()
    (ambiente.destino / "env" / ".env.20261001").write_text("x", encoding="utf-8")
    (ambiente.destino / "anotacao.txt").write_text("x", encoding="utf-8")

    assert ambiente.rodar(manter=3) == 0

    restantes = sorted(p.name for p in ambiente.destino.iterdir())
    assert restantes == ["20261005-000000", "20261006-000000", "20261027-031500", "anotacao.txt", "env"]
    assert (ambiente.destino / "env" / ".env.20261001").is_file()


def test_rotacao_nao_apaga_nada_quando_o_backup_falhou(ambiente):
    for dia in range(1, 4):
        _backup_antigo(ambiente.destino, f"202610{dia:02d}-000000")
    ambiente.cfg["postgres_no_ar"] = False

    assert ambiente.rodar(manter=1) == 1

    assert len(backup.pastas_de_backup(ambiente.destino)) == 4


def test_mesmo_segundo_nao_sobrescreve_backup_existente(ambiente):
    assert ambiente.rodar() == 0
    with pytest.raises(FileExistsError):
        ambiente.rodar()


@pytest.mark.parametrize("manter", [0, -1])
def test_manter_invalido_e_recusado(ambiente, manter):
    with pytest.raises(ValueError):
        ambiente.rodar(manter=manter)
    with pytest.raises(SystemExit) as info:
        backup.main(["--manter", str(manter), "--destino", str(ambiente.destino)])
    assert info.value.code == 2
    assert not ambiente.destino.exists()

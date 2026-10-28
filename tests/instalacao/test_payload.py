"""O pacote que vai para outra máquina não pode levar nada desta."""
import zipfile
from pathlib import Path

import pytest

from scripts.empacotar import payload as pl


def _arvore(raiz: Path, arquivos: dict[str, str]) -> Path:
    for nome, texto in arquivos.items():
        (raiz / nome).parent.mkdir(parents=True, exist_ok=True)
        (raiz / nome).write_text(texto, encoding="utf-8")
    return raiz


BASE = {"pyproject.toml": 'version = "9.9.9"\n', ".env.example": "A=\n", "README.md": "oi\n"}


def test_so_entra_o_que_esta_na_lista_de_permissao(tmp_path):
    raiz = _arvore(tmp_path, {**BASE, "painel/app.py": "x", "dados/cerebro.db": "BANCO", "modelos/peso.gguf": "P",
                              "segredos_pessoais.txt": "s", ".venv/lib.py": "v", "runtime/cerebro/.venv/x.py": "v",
                              "painel/__pycache__/a.pyc": "c", "outra_pasta/arquivo.py": "o"})
    lista = pl.listar_arquivos(raiz)
    assert "painel/app.py" in lista and ".env.example" in lista
    assert not any(n.startswith(("dados/", "modelos/", ".venv/", "outra_pasta/")) or n == "segredos_pessoais.txt" for n in lista)
    assert not any("__pycache__" in n or ".venv" in n for n in lista)


@pytest.mark.parametrize("nome", [".env", ".env.local", ".env.prod", "runtime/litellm/config.yaml", "runtime/litellm/config.yaml.anterior",
                                  "dados/logs/auditoria.jsonl", "painel/cerebro.db", "chave.pem", "x.key", "painel/.serena/memoria.md",
                                  "scripts/.claude/settings.json", "painel/x.sqlite3", "build/saida.py", "dist/TudoIA-Setup.exe"])
def test_arquivos_sensiveis_nunca_entram(tmp_path, nome):
    raiz = _arvore(tmp_path, {**BASE, nome: "conteudo"})
    (raiz / "painel").mkdir(exist_ok=True)
    assert nome not in pl.listar_arquivos(raiz)


def test_o_exemplo_de_env_entra_e_o_env_real_nao(tmp_path):
    lista = pl.listar_arquivos(_arvore(tmp_path, {**BASE, ".env": "SEGREDO=1"}))
    assert ".env.example" in lista and ".env" not in lista


def test_zip_e_reprodutivel_e_normaliza_fim_de_linha(tmp_path):
    raiz = _arvore(tmp_path, {**BASE, "scripts/a.ps1": "Write-Host 1\n", "painel/a.py": "x = 1\n"})
    (raiz / "painel" / "b.py").write_bytes(b"y = 2\r\n")
    m1 = pl.gerar(raiz, tmp_path / "s1")
    m2 = pl.gerar(raiz, tmp_path / "s2")
    assert m1["sha256"] == m2["sha256"] and m1["versao"] == "9.9.9"
    with zipfile.ZipFile(tmp_path / "s1" / "payload.zip") as z:
        assert z.read("painel/b.py") == b"y = 2\n"                    # código em LF
        assert z.read("scripts/a.ps1") == b"Write-Host 1\r\n"          # PowerShell em CRLF
        assert z.getinfo("painel/a.py").date_time == pl.TIMESTAMP_FIXO


def test_verificacao_acha_segredos_e_dados_pessoais(tmp_path, monkeypatch):
    monkeypatch.setenv("USERNAME", "FulanoDeTal")
    monkeypatch.setenv("COMPUTERNAME", "PC-DO-FULANO")
    monkeypatch.setenv("PESSOAIS_EXTRA", "")
    raiz = _arvore(tmp_path, {**BASE,
                              "docs/a.md": "veja C:\\Users\\fulano\\Documents\\x\n",
                              "docs/b.md": "chave sk-abcdefghijklmnopqrstuvwxyz123456\n",
                              "docs/c.md": "token ghp_" + "a" * 36 + "\n",
                              "docs/d.md": "o usuário FulanoDeTal fez isto\n",
                              "docs/e.md": "máquina pc-do-fulano\n",
                              "docs/f.md": "-----BEGIN RSA " + "PRIVATE KEY-----\n",
                              "docs/g.md": "contato fulano@gmail.com\n",
                              "docs/h.md": "postgres://admin:SenhaReal99@db.interno:5432/x\n",
                              "docs/limpo.md": "C:\\Users\\<usuario>\\TudoIA e user:senha@example.com\n"})
    pl.gerar(raiz, tmp_path / "s")
    achados = "\n".join(pl.verificar_conteudo(tmp_path / "s" / "payload.zip"))
    for esperado in ("a.md", "b.md", "c.md", "d.md", "e.md", "f.md", "g.md", "h.md"):
        assert f"docs/{esperado}" in achados, esperado
    assert "limpo.md" not in achados


def test_fixture_de_teste_obvia_nao_reprova_mas_segredo_fora_de_tests_sim(tmp_path, monkeypatch):
    monkeypatch.setenv("PESSOAIS_EXTRA", "")
    raiz = _arvore(tmp_path, {**BASE, "tests/t.py": 'env = "ANTHROPIC_API_KEY=sk-ant-segredo-de-teste-123456789"\n',
                              "painel/x.py": 'k = "sk-ant-segredo-de-teste-123456789"\n'})
    pl.gerar(raiz, tmp_path / "s")
    achados = "\n".join(pl.verificar_conteudo(tmp_path / "s" / "payload.zip"))
    assert "tests/t.py" not in achados and "painel/x.py" in achados


def test_o_repositorio_real_gera_um_pacote_limpo(tmp_path):
    """Vale para o código de verdade: se alguém commitar um segredo ou dado pessoal, este teste reprova."""
    m = pl.gerar(pl.RAIZ, tmp_path)
    assert m["arquivos"] > 100
    assert pl.verificar_conteudo(tmp_path / "payload.zip") == []
    with zipfile.ZipFile(tmp_path / "payload.zip") as z:
        nomes = set(z.namelist())
    assert {"runtime/docker-compose.yml", ".env.example", "scripts/iniciar.ps1", "instalador/entrada.py",
            "infra/keycloak/realm-tudoia.json"} <= nomes
    assert ".env" not in nomes and not any(n.startswith(("dados/", "modelos/")) for n in nomes)


def test_governanca_padrao_nao_leva_nada_da_maquina_nem_mcp_que_pede_chave():
    import json

    mcp = {"mcpServers": {
        "livre": {"command": "npx", "args": ["x"]},
        "com-chave": {"command": "npx", "env": {"TOKEN": "${GITHUB_TOKEN}"}},
        "com-padrao": {"command": "npx", "env": {"T": "${X:-abc}"}},
        "cerebro": {"url": "http://localhost:8765/mcp", "headers": {"Authorization": "Bearer ${CEREBRO_TOKEN_ESTATICO}"}}}}
    cfg = {"regras": ["a"], "skills": ["s"], "mcp": ["livre", "com-chave", "com-padrao", "cerebro", "sumiu"],
           "workspaces": ["D:/MeuProjeto"], "clientes": ["claude"],
           "instancias": [{"id": "claude-trabalho", "caminho": "~/.claude-trabalho"}]}
    novo = json.loads(pl.governanca_padrao(json.dumps(cfg).encode(), json.dumps(mcp).encode()))
    assert novo["mcp"] == ["livre", "com-padrao", "cerebro"]
    assert novo["workspaces"] == [] and novo["instancias"] == [] and novo["regras"] == ["a"] and novo["clientes"] == ["claude"]


def test_governanca_do_pacote_real_passa_no_verificar_com_o_env_do_instalador(tmp_path):
    """Instalação nova roda `verificar` sem ErroGovernanca (MCP ligado sem variável quebraria o sync)."""
    import governanca

    pl.gerar(pl.RAIZ, tmp_path / "s")
    raiz = tmp_path / "raiz"
    with zipfile.ZipFile(tmp_path / "s" / "payload.zip") as z:
        z.extractall(raiz)
    (raiz / ".env").write_text("CEREBRO_TOKEN_ESTATICO=" + "x" * 40 + chr(10), encoding="utf-8")   # o que `tudoia segredos` gera
    (tmp_path / "home").mkdir()
    governanca.verificar(raiz, tmp_path / "home")   # só diferenças em arquivos ausentes; erro de configuração levantaria

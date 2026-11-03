"""O pacote que vai para outra máquina não pode levar nada desta."""
import json
import subprocess
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
    # o que `tudoia segredos` e a etapa do .env do instalador gravam
    (raiz / ".env").write_text("CEREBRO_TOKEN_ESTATICO=" + "x" * 40 + chr(10) + f"DOUTRINA_TEC={raiz / 'doutrina'}" + chr(10)
                               + f"TUDOIA_PYTHON={raiz / '.venv' / 'Scripts' / 'python.exe'}" + chr(10), encoding="utf-8")
    (tmp_path / "home").mkdir()
    governanca.verificar(raiz, tmp_path / "home")   # só diferenças em arquivos ausentes; erro de configuração levantaria


# ───────────────────────────── Doutrina TEC embutida
SHA = "a" * 40
MANIFESTO = {"doutrina": "Doutrina TEC", "versao": "1.2.3", "hash": "h1", "arquivos": ["gerado/ia.json"]}
DOUTRINA = {"gerado/manifesto.json": json.dumps(MANIFESTO).encode(), "gerado/ia.json": b"{}",
            "tools/mcp_doutrina.py": b"print(1)\n", "familias/dados/padroes/01.md": b"# dados\n",
            "INDEX.md": b"i", "llms.txt": b"l", "VERSION": b"1.2.3", "LICENSE": b"L", "NOTICE": b"N"}
PIN = {"repositorio": "o/r", "sha": SHA}


def _clone_git(tmp_path: Path, arquivos: dict[str, bytes]) -> tuple[Path, str]:
    clone = tmp_path / "clone"
    for rel, dados in arquivos.items():
        (clone / rel).parent.mkdir(parents=True, exist_ok=True)
        (clone / rel).write_bytes(dados)
    git = ["git", "-C", str(clone), "-c", "user.name=t", "-c", "user.email=t@exemplo.com.br"]
    subprocess.run(["git", "init", "-q", str(clone)], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "x"], check=True)
    sha = subprocess.run([*git, "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    return clone, sha


def test_pacote_leva_a_doutrina_em_pasta_propria_e_registra_a_versao(tmp_path):
    raiz = _arvore(tmp_path / "r", {**BASE, "painel/app.py": "x"})
    m = pl.gerar(raiz, tmp_path / "s", doutrina=DOUTRINA, pin=PIN)
    assert m["doutrina"] == {**PIN, "versao": "1.2.3", "hash": "h1"}
    with zipfile.ZipFile(tmp_path / "s" / "payload.zip") as z:
        nomes = set(z.namelist())
    assert {"doutrina/gerado/manifesto.json", "doutrina/tools/mcp_doutrina.py", "painel/app.py"} <= nomes
    # familias/dados da Doutrina não é a pasta de dados do usuário: a varredura não pode reprovar nem o pacote perdê-la
    assert "doutrina/familias/dados/padroes/01.md" in nomes
    assert pl.verificar_conteudo(tmp_path / "s" / "payload.zip") == []


def test_pacote_com_doutrina_continua_reprodutivel(tmp_path):
    raiz = _arvore(tmp_path / "r", BASE)
    a = pl.gerar(raiz, tmp_path / "a", doutrina=DOUTRINA, pin=PIN)
    b = pl.gerar(raiz, tmp_path / "b", doutrina=dict(reversed(list(DOUTRINA.items()))), pin=PIN)
    assert a["sha256"] == b["sha256"]


def test_doutrina_sem_manifesto_ou_incompleta_reprova_o_pacote(tmp_path):
    raiz = _arvore(tmp_path / "r", BASE)
    ruins = [{k: v for k, v in DOUTRINA.items() if k != "gerado/manifesto.json"},
             {k: v for k, v in DOUTRINA.items() if k != "gerado/ia.json"},       # listado no manifesto
             {k: v for k, v in DOUTRINA.items() if k != "tools/mcp_doutrina.py"},
             {**DOUTRINA, "gerado/manifesto.json": b"{nao e json"}]
    for ruim in ruins:
        with pytest.raises(pl.ErroDoutrina):
            pl.gerar(raiz, tmp_path / "s", doutrina=ruim, pin=PIN)


@pytest.mark.parametrize("pin", [{"repositorio": "o/r", "sha": "main"}, {"repositorio": "o/r", "sha": "0e900b0"},
                                 {"repositorio": "o/r", "sha": "A" * 40}, {"repositorio": "../r", "sha": SHA}, {"repositorio": "o/..", "sha": SHA},
                                 {"repositorio": "o/r"}, [], "x"])
def test_pin_da_doutrina_exige_sha_completo_e_repositorio_valido(tmp_path, pin):
    (tmp_path / "governanca").mkdir()
    (tmp_path / "governanca" / "doutrina.json").write_text(json.dumps(pin), encoding="utf-8")
    with pytest.raises(pl.ErroDoutrina):
        pl.ler_pin(tmp_path)


def test_pin_ausente_ou_corrompido_falha_fechado(tmp_path):
    with pytest.raises(pl.ErroDoutrina):
        pl.ler_pin(tmp_path)
    (tmp_path / "governanca").mkdir()
    (tmp_path / "governanca" / "doutrina.json").write_text("{", encoding="utf-8")
    with pytest.raises(pl.ErroDoutrina):
        pl.ler_pin(tmp_path)


def test_o_pin_real_tem_formato_valido():
    assert len(pl.ler_pin()["sha"]) == 40


def test_instantaneo_vem_do_commit_fixado_e_nao_da_pasta_de_trabalho(tmp_path):
    clone, sha = _clone_git(tmp_path, {**DOUTRINA, "AGENTS.md": b"fora do pacote", "tests/t.py": b"fora"})
    (clone / "gerado" / "ia.json").write_text("EDITADO DEPOIS DO COMMIT", encoding="utf-8")   # edição local não entra
    (clone / "segredo.txt").write_text("nao versionado", encoding="utf-8")
    arquivos = pl.instantaneo_doutrina(clone, sha)
    assert arquivos["gerado/ia.json"] == b"{}"
    assert "AGENTS.md" not in arquivos and "tests/t.py" not in arquivos and "segredo.txt" not in arquivos


def test_instantaneo_de_commit_inexistente_falha_com_instrucao(tmp_path):
    clone, _ = _clone_git(tmp_path, DOUTRINA)
    with pytest.raises(pl.ErroDoutrina, match="git fetch"):
        pl.instantaneo_doutrina(clone, "b" * 40)


def test_instantaneo_de_pasta_que_nao_e_git_falha(tmp_path):
    with pytest.raises(pl.ErroDoutrina):
        pl.instantaneo_doutrina(tmp_path / "nao-existe", SHA)


def test_principal_sem_doutrina_tec_nao_gera_pacote(monkeypatch, capsys):
    monkeypatch.delenv("DOUTRINA_TEC", raising=False)
    monkeypatch.setattr(pl, "gerar", lambda *a, **k: pytest.fail("não deveria gerar sem a Doutrina"))
    assert pl.principal([]) == 1
    assert "DOUTRINA_TEC" in capsys.readouterr().err


def test_o_mcp_doutrina_tec_esta_no_catalogo_e_ligado_na_instalacao_nova():
    cat = json.loads((pl.RAIZ / "governanca" / "mcp.json").read_text(encoding="utf-8"))["mcpServers"]["doutrina-tec"]
    assert cat["args"] == ["${DOUTRINA_TEC}/tools/mcp_doutrina.py"] and "npx" not in cat["command"]
    cfg = (pl.RAIZ / "governanca" / "governanca.json").read_bytes()
    novo = json.loads(pl.governanca_padrao(cfg, (pl.RAIZ / "governanca" / "mcp.json").read_bytes()))
    assert "doutrina-tec" in novo["mcp"]


# ───────────────────────────── SHA da Doutrina: o JSON manda, Dockerfile e compose são derivados
NOVO = "d" * 40
DOCKERFILE = f"FROM x\nARG DOUTRINA_SHA={SHA}\nRUN y\n"
COMPOSE = f"services:\n  squadti:\n    build:\n      args:\n        DOUTRINA_SHA: ${{SQUADTI_DOUTRINA_SHA:-{SHA}}}\n"


def _raiz_com_pin(tmp_path: Path, sha: str = NOVO, dockerfile: str = DOCKERFILE, compose: str = COMPOSE) -> Path:
    (tmp_path / "governanca").mkdir(parents=True)
    (tmp_path / "governanca" / "doutrina.json").write_text(json.dumps({"repositorio": "o/r", "sha": sha}), encoding="utf-8")
    (tmp_path / "runtime" / "squadti").mkdir(parents=True)
    (tmp_path / "runtime" / "squadti" / "Dockerfile").write_bytes(dockerfile.encode())
    (tmp_path / "runtime" / "docker-compose.yml").write_bytes(compose.encode())
    return tmp_path


def test_sincronizar_aponta_divergencia_sem_gravar_e_depois_corrige(tmp_path):
    raiz = _raiz_com_pin(tmp_path)
    esperado = ["runtime/squadti/Dockerfile", "runtime/docker-compose.yml"]
    assert pl.sincronizar_pin(raiz) == esperado
    assert SHA in (raiz / "runtime" / "squadti" / "Dockerfile").read_text()          # só olhar não grava
    assert pl.sincronizar_pin(raiz, aplicar=True) == esperado
    assert f"ARG DOUTRINA_SHA={NOVO}\n" in (raiz / "runtime" / "squadti" / "Dockerfile").read_text()
    assert f"${{SQUADTI_DOUTRINA_SHA:-{NOVO}}}" in (raiz / "runtime" / "docker-compose.yml").read_text()
    assert pl.sincronizar_pin(raiz) == []                                             # idempotente


def test_sincronizar_preserva_fim_de_linha_e_o_resto_do_arquivo(tmp_path):
    raiz = _raiz_com_pin(tmp_path, dockerfile=DOCKERFILE.replace("\n", "\r\n"), compose=COMPOSE.replace("\n", "\r\n"))
    pl.sincronizar_pin(raiz, aplicar=True)
    assert (raiz / "runtime" / "squadti" / "Dockerfile").read_bytes() == DOCKERFILE.replace(SHA, NOVO).replace("\n", "\r\n").encode()
    assert (raiz / "runtime" / "docker-compose.yml").read_bytes() == COMPOSE.replace(SHA, NOVO).replace("\n", "\r\n").encode()


@pytest.mark.parametrize("dockerfile,compose", [("FROM x\n", COMPOSE), (DOCKERFILE * 2, COMPOSE), (DOCKERFILE, "services: {}\n"),
                                                (DOCKERFILE, COMPOSE * 2)])
def test_sincronizar_falha_se_o_alvo_nao_tem_exatamente_uma_ocorrencia(tmp_path, dockerfile, compose):
    raiz = _raiz_com_pin(tmp_path, dockerfile=dockerfile, compose=compose)
    with pytest.raises(pl.ErroDoutrina, match="exatamente uma"):
        pl.sincronizar_pin(raiz, aplicar=True)
    assert (raiz / "runtime" / "squadti" / "Dockerfile").read_text() == dockerfile            # nada gravado pela metade


def test_sincronizar_com_pin_invalido_nao_toca_em_nada(tmp_path):
    raiz = _raiz_com_pin(tmp_path, sha="main")
    with pytest.raises(pl.ErroDoutrina):
        pl.sincronizar_pin(raiz, aplicar=True)
    assert (raiz / "runtime" / "squadti" / "Dockerfile").read_text() == DOCKERFILE


def test_principal_recusa_gerar_com_sha_derivado_desatualizado(monkeypatch, capsys):
    monkeypatch.setattr(pl, "ler_pin", lambda *a: PIN)
    monkeypatch.setattr(pl, "sincronizar_pin", lambda *a, **k: ["runtime/squadti/Dockerfile"])
    monkeypatch.setattr(pl, "gerar", lambda *a, **k: pytest.fail("não deveria gerar com o SHA divergente"))
    monkeypatch.setenv("DOUTRINA_TEC", "x")
    assert pl.principal([]) == 1
    assert "--sincronizar-pin" in capsys.readouterr().err


def test_principal_argumento_desconhecido_nao_faz_nada(capsys):
    assert pl.principal(["--apagar-tudo"]) == 2


# ───────────────────────────── --sincronizar-pin busca o commit mais novo
class _Proc:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout, self.stderr, self.returncode = stdout, stderr, returncode


def _git_falso(stdout="", returncode=0, stderr="", pedidos=None):
    def executar(cmd, **kw):
        if pedidos is not None:
            pedidos.append(cmd)
        return _Proc(stdout, stderr, returncode)
    return executar


def test_ultimo_commit_le_o_head_remoto_do_github():
    pedidos = []
    sha = pl.ultimo_commit("o/r", _git_falso(f"{NOVO}\tHEAD\n", pedidos=pedidos))
    assert sha == NOVO and pedidos == [["git", "ls-remote", "https://github.com/o/r.git", "HEAD"]]


@pytest.mark.parametrize("saida,codigo", [("", 0), ("main\tHEAD\n", 0), ("abc\tHEAD\n", 0), (f"{NOVO}\tHEAD\n", 128), ("<html>\n", 0)])
def test_ultimo_commit_falha_fechado_com_resposta_invalida(saida, codigo):
    with pytest.raises(pl.ErroDoutrina):
        pl.ultimo_commit("o/r", _git_falso(saida, codigo, "fatal: sem rede"))


def test_ultimo_commit_recusa_repositorio_invalido_sem_chamar_o_git():
    with pytest.raises(pl.ErroDoutrina):
        pl.ultimo_commit("../r", lambda *a, **k: pytest.fail("não deveria consultar"))


def test_ultimo_commit_traduz_falha_do_processo():
    def executar(*a, **k):
        raise subprocess.TimeoutExpired("git", 60)
    with pytest.raises(pl.ErroDoutrina, match="GitHub"):
        pl.ultimo_commit("o/r", executar)


def test_atualizar_pin_grava_o_sha_novo_e_mantem_o_repositorio(tmp_path):
    raiz = _raiz_com_pin(tmp_path, sha=SHA)
    assert pl.atualizar_pin(raiz, _git_falso(f"{NOVO}\tHEAD\n")) == (SHA, NOVO)
    assert json.loads((raiz / "governanca" / "doutrina.json").read_text()) == {"repositorio": "o/r", "sha": NOVO}
    assert pl.sincronizar_pin(raiz, aplicar=True) == ["runtime/squadti/Dockerfile", "runtime/docker-compose.yml"]
    assert NOVO in (raiz / "runtime" / "docker-compose.yml").read_text()


def test_atualizar_pin_sem_novidade_nao_reescreve_o_arquivo(tmp_path):
    raiz = _raiz_com_pin(tmp_path, sha=SHA)
    antes = (raiz / "governanca" / "doutrina.json").read_bytes()
    assert pl.atualizar_pin(raiz, _git_falso(f"{SHA}\tHEAD\n")) == (SHA, SHA)
    assert (raiz / "governanca" / "doutrina.json").read_bytes() == antes


def test_atualizar_pin_com_falha_de_rede_preserva_o_pin_atual(tmp_path):
    raiz = _raiz_com_pin(tmp_path, sha=SHA)
    with pytest.raises(pl.ErroDoutrina):
        pl.atualizar_pin(raiz, _git_falso("", 128, "fatal: unable to access"))
    assert json.loads((raiz / "governanca" / "doutrina.json").read_text())["sha"] == SHA


def test_buscar_no_clone_falha_com_mensagem_quando_o_fetch_falha(tmp_path):
    with pytest.raises(pl.ErroDoutrina, match="fetch"):
        pl.buscar_no_clone(tmp_path, SHA, _git_falso("", 1, "fatal: not a git repository"))


def test_cli_sincronizar_busca_o_mais_novo_propaga_e_atualiza_o_clone(monkeypatch, capsys):
    ordem = []
    monkeypatch.setattr(pl, "atualizar_pin", lambda: ordem.append("atualizar") or (SHA, NOVO))
    monkeypatch.setattr(pl, "buscar_no_clone", lambda clone, sha: ordem.append(("fetch", str(clone), sha)))
    monkeypatch.setattr(pl, "sincronizar_pin", lambda aplicar=False: ordem.append(("propagar", aplicar)) or ["runtime/docker-compose.yml"])
    monkeypatch.setenv("DOUTRINA_TEC", "clone-da-doutrina")
    assert pl.principal(["--sincronizar-pin"]) == 0
    assert ordem == ["atualizar", ("fetch", "clone-da-doutrina", NOVO), ("propagar", True)]
    assert f"{SHA[:12]} -> {NOVO[:12]}" in capsys.readouterr().out


def test_cli_derivar_pin_nao_usa_a_rede(monkeypatch):
    monkeypatch.setattr(pl, "atualizar_pin", lambda: pytest.fail("--derivar-pin não consulta o GitHub"))
    monkeypatch.setattr(pl, "buscar_no_clone", lambda *a: pytest.fail("--derivar-pin não faz fetch"))
    monkeypatch.setattr(pl, "sincronizar_pin", lambda aplicar=False: [])
    assert pl.principal(["--derivar-pin"]) == 0


def test_cli_sincronizar_com_falha_de_rede_sai_com_erro_e_nao_propaga(monkeypatch, capsys):
    def sem_rede():
        raise pl.ErroDoutrina("sem rede")
    monkeypatch.setattr(pl, "atualizar_pin", sem_rede)
    monkeypatch.setattr(pl, "sincronizar_pin", lambda aplicar=False: pytest.fail("não deveria propagar um pin não atualizado"))
    assert pl.principal(["--sincronizar-pin"]) == 1
    assert "sem rede" in capsys.readouterr().err

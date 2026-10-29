import json
from pathlib import Path

import pytest

from tudoia_instalador import etapas, envfile
from tudoia_instalador.execucao import Resultado
from tudoia_instalador.motor import ErroInstalacao, ReinicioNecessario

from .duplos import ExecutorFalso, diag


@pytest.fixture(autouse=True)
def _caminho_longo_do_pytest(monkeypatch):
    """O tmp_path do pytest passa do limite de 90 caracteres do instalador; o limite em si é testado em test_opcoes."""
    monkeypatch.setattr("tudoia_instalador.opcoes.MAX_CAMINHO", 400)
    monkeypatch.setattr(etapas, "porta_ocupada", lambda p: False)   # esta máquina pode ter o TudoIA de verdade no ar


def _executor(ctx, respostas=None):
    ctx.executor = ExecutorFalso(ctx.log, ctx.redator, respostas)
    return ctx.executor


def _falso_payload(ctx, extra=None):
    raiz = ctx.raiz
    (raiz / "runtime").mkdir(parents=True, exist_ok=True)
    (raiz / "runtime" / "docker-compose.yml").write_text("services: {}", encoding="utf-8")
    (raiz / ".env.example").write_text("TZ=\nCOMPOSE_PROFILES=\nGROQ_API_KEY=\n", encoding="utf-8")
    for nome, texto in (extra or {}).items():
        (raiz / nome).parent.mkdir(parents=True, exist_ok=True)
        (raiz / nome).write_text(texto, encoding="utf-8")


# ───────── verificação
def test_verificacao_aprova_maquina_boa(ctx):
    etapas.verificacao(ctx)


@pytest.mark.parametrize("mudanca,trecho", [
    ({"windows_ok": False, "windows_build": 17763}, "Windows build"),
    ({"internet": False}, "internet"),
])
def test_verificacao_reprova(ctx, mudanca, trecho):
    ctx.diagnostico = lambda: diag(**mudanca)
    with pytest.raises(ErroInstalacao, match=trecho):
        etapas.verificacao(ctx)


def test_verificacao_reprova_opcoes_invalidas(ctx):
    ctx.o.pasta_instalacao = r"C:\Windows\TudoIA"
    with pytest.raises(ErroInstalacao, match="pasta_instalacao"):
        etapas.verificacao(ctx)


def test_verificacao_reprova_sem_espaco(ctx, monkeypatch):
    monkeypatch.setattr(etapas, "disco_livre_gb", lambda p: 1.0)
    with pytest.raises(ErroInstalacao, match="espaço"):
        etapas.verificacao(ctx)


def test_comfyui_sem_gpu_nvidia_e_recusado(ctx):
    ctx.o.componentes = ["keycloak", "comfyui"]
    ctx.diagnostico = lambda: diag(gpu_nome="", gpu_vram_mb=0)
    with pytest.raises(ErroInstalacao, match="GPU NVIDIA"):
        etapas.verificacao(ctx)


def test_porta_ocupada_reprova_em_instalacao_nova_e_avisa_em_reinstalacao(ctx, monkeypatch):
    monkeypatch.setattr(etapas, "porta_ocupada", lambda p: p == 3100)
    with pytest.raises(ErroInstalacao, match="painel"):
        etapas.verificacao(ctx)
    ctx.raiz.mkdir(parents=True)
    (ctx.raiz / etapas.MARCA).write_text("{}", encoding="utf-8")
    etapas.verificacao(ctx)
    assert any("reinstalação" in x for x in ctx.logs)


# ───────── código, pastas, .env
def test_obter_codigo_valida_que_e_o_tudoia(ctx, tmp_path, monkeypatch):
    import zipfile
    z = tmp_path / "p.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("qualquer.txt", "x")
    monkeypatch.setattr(etapas.codigo, "payload_embutido", lambda: (z, {"versao": "1", "arquivos": 1}))
    with pytest.raises(ErroInstalacao, match="não parece ser o TudoIA"):
        etapas.obter_codigo(ctx)


def test_obter_codigo_instala_o_pacote(ctx, tmp_path, monkeypatch):
    import zipfile
    z = tmp_path / "p.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("runtime/docker-compose.yml", "services: {}")
        f.writestr(".env.example", "TZ=\n")
    monkeypatch.setattr(etapas.codigo, "payload_embutido", lambda: (z, {"versao": "1", "arquivos": 2}))
    ex = _executor(ctx)
    etapas.obter_codigo(ctx)
    assert (ctx.raiz / ".env.example").is_file()
    assert any(c[0] == "icacls" and "/reset" in c for c, _ in ex.chamadas)


def test_pastas_cria_estrutura_e_marca(ctx):
    _executor(ctx)
    etapas.pastas(ctx)
    for sub in ("logs", "cerebro", "documentos", "estudio"):
        assert (ctx.raiz / "dados" / sub).is_dir()
    marca = json.loads((ctx.raiz / etapas.MARCA).read_text(encoding="utf-8"))
    assert marca["projeto_compose"] == "tudoia" and Path(marca["pasta_dados"]) == ctx.raiz / "dados"


def test_pastas_com_dados_em_outro_lugar_cria_juncao(ctx, tmp_path):
    ctx.o.pasta_dados = str(tmp_path / "OutroDisco" / "dados")
    ex = _executor(ctx)
    etapas.pastas(ctx)
    assert (tmp_path / "OutroDisco" / "dados" / "logs").is_dir()
    cmd = ex.chamadas[-1][0]
    assert cmd[:4] == ["cmd", "/c", "mklink", "/J"] and cmd[4] == str(ctx.raiz / "dados") and cmd[5] == ctx.o.pasta_dados


def test_pastas_recusa_substituir_pasta_dados_com_conteudo(ctx, tmp_path):
    (ctx.raiz / "dados").mkdir(parents=True)
    (ctx.raiz / "dados" / "importante.db").write_text("x")
    ctx.o.pasta_dados = str(tmp_path / "Outro" / "dados")
    _executor(ctx)
    with pytest.raises(ErroInstalacao, match="já existe"):
        etapas.pastas(ctx)
    assert (ctx.raiz / "dados" / "importante.db").exists()


def test_escrever_env_aplica_opcoes_mascara_segredos_e_restringe_acesso(ctx):
    _falso_payload(ctx)
    ctx.o.chaves_provedores = {"GROQ_API_KEY": "gsk_segredo_longo_123"}
    ex = _executor(ctx)
    etapas.escrever_env(ctx)
    v = envfile.ler((ctx.raiz / ".env").read_text(encoding="utf-8"))
    assert v["GROQ_API_KEY"] == "gsk_segredo_longo_123" and "keycloak" in v["COMPOSE_PROFILES"]
    assert ctx.redator.limpar("a gsk_segredo_longo_123 b") == "a *** b"
    assert any(c[0] == "icacls" and "/inheritance:r" in c for c, _ in ex.chamadas)
    assert "gsk_segredo_longo_123" not in "\n".join(ctx.logs)


def test_escrever_env_nao_apaga_segredos_de_instalacao_anterior(ctx):
    _falso_payload(ctx, {".env": "LITELLM_MASTER_KEY=ja-existia\nTZ=\n"})
    _executor(ctx)
    etapas.escrever_env(ctx)
    assert envfile.ler((ctx.raiz / ".env").read_text(encoding="utf-8"))["LITELLM_MASTER_KEY"] == "ja-existia"


# ───────── uv, dependências, segredos
def test_uv_ja_instalado_e_reaproveitado(ctx, monkeypatch):
    monkeypatch.setattr(etapas.shutil, "which", lambda n: r"C:\ferramentas\uv.exe")
    etapas.obter_uv(ctx)
    assert ctx.uv == r"C:\ferramentas\uv.exe"


def test_uv_baixado_confere_o_sha256_publicado(ctx, monkeypatch):
    monkeypatch.setattr(etapas.shutil, "which", lambda n: None)
    monkeypatch.setattr(etapas.codigo, "baixar_https", lambda url, dest, hosts, mx, *a, **k: dest.write_bytes(b"ZIP"))
    monkeypatch.setattr(etapas, "_sha256_publicado", lambda url: "0" * 64)
    with pytest.raises(ErroInstalacao, match="sha256"):
        etapas.obter_uv(ctx)
    assert not (ctx.raiz / "ferramentas" / "uv" / "uv.zip").exists()


def test_dependencias_usa_lockfile_congelado(ctx):
    ex = _executor(ctx)
    ctx.uv = r"C:\x\uv.exe"
    (ctx.raiz / ".venv" / "Scripts").mkdir(parents=True)
    (ctx.raiz / ".venv" / "Scripts" / "python.exe").write_text("")
    etapas.dependencias(ctx)
    assert ex.chamadas[-1][0][:4] == [r"C:\x\uv.exe", "sync", "--frozen", "--project"]


def test_dependencias_falha_se_o_venv_nao_nasceu(ctx):
    _executor(ctx)
    ctx.uv = "uv"
    with pytest.raises(ErroInstalacao, match="ambiente Python"):
        etapas.dependencias(ctx)


# ───────── Docker
def test_docker_pronto_nao_instala_nada(ctx, monkeypatch):
    monkeypatch.setattr(etapas, "docker_exe", lambda: "docker.exe")
    monkeypatch.setattr(etapas, "docker_pronto", lambda: True)
    ex = _executor(ctx)
    etapas.docker(ctx)
    assert ex.chamadas == []


def test_docker_ausente_instala_via_winget_elevado(ctx, monkeypatch):
    estado = {"instalado": False}
    monkeypatch.setattr(etapas, "docker_exe", lambda: "docker.exe" if estado["instalado"] else None)
    monkeypatch.setattr(etapas, "docker_pronto", lambda: estado["instalado"])
    monkeypatch.setattr(etapas, "docker_desktop_exe", lambda: None)
    monkeypatch.setattr(etapas, "_winget", lambda: r"C:\winget.exe")
    ex = _executor(ctx)

    def rodar(cmd, **kw):
        ex.chamadas.append((list(cmd), kw))
        estado["instalado"] = True
        return Resultado(0, "")
    ex.rodar = rodar
    etapas.docker(ctx)
    script = ex.chamadas[0][0][-1]
    assert "-Verb RunAs" in script and "Docker.DockerDesktop" in script and "--accept-license" in script


def test_docker_instalado_mas_que_nao_sobe_depois_de_instalar_pede_reinicio(ctx, monkeypatch):
    estado = {"instalado": False}
    monkeypatch.setattr(etapas, "docker_exe", lambda: "docker.exe" if estado["instalado"] else None)
    monkeypatch.setattr(etapas, "docker_pronto", lambda: False)
    monkeypatch.setattr(etapas, "docker_desktop_exe", lambda: None)
    monkeypatch.setattr(etapas, "_winget", lambda: r"C:\winget.exe")
    ex = _executor(ctx)

    def rodar(cmd, **kw):
        estado["instalado"] = True
        return Resultado(0, "")
    ex.rodar = rodar
    tempo = {"t": 0.0}
    ctx.agora = lambda: tempo["t"]
    ctx.esperar = lambda s: tempo.__setitem__("t", tempo["t"] + s)
    with pytest.raises(ReinicioNecessario):
        etapas.docker(ctx)


def test_docker_codigo_de_reinicio_do_instalador_pede_reinicio(ctx, monkeypatch):
    monkeypatch.setattr(etapas, "docker_exe", lambda: None)
    monkeypatch.setattr(etapas, "_winget", lambda: r"C:\winget.exe")
    ex = _executor(ctx)
    ex.rodar = lambda cmd, **kw: Resultado(3010, "")
    with pytest.raises(ReinicioNecessario):
        etapas.docker(ctx)


def test_docker_instalado_que_nao_sobe_orienta_o_usuario(ctx, monkeypatch):
    monkeypatch.setattr(etapas, "docker_exe", lambda: "docker.exe")
    monkeypatch.setattr(etapas, "docker_pronto", lambda: False)
    monkeypatch.setattr(etapas, "docker_desktop_exe", lambda: None)
    _executor(ctx)
    tempo = {"t": 0.0}
    ctx.agora = lambda: tempo["t"]
    ctx.esperar = lambda s: tempo.__setitem__("t", tempo["t"] + s)
    with pytest.raises(ErroInstalacao, match="aceite os termos"):
        etapas.docker(ctx)


def test_subir_stack_puxa_imagens_e_sobe_esperando_saude(ctx, monkeypatch):
    monkeypatch.setattr(etapas, "docker_exe", lambda: "docker.exe")
    ctx.o.projeto_compose = "teste"
    ex = _executor(ctx)
    etapas.subir_stack(ctx)
    pull, up = ex.comandos()
    assert "-p teste" in pull and "pull --ignore-buildable" in pull
    assert "up -d --build --wait --wait-timeout 900" in up and "--env-file" in up


def test_subir_stack_que_nao_fica_saudavel_mostra_o_estado(ctx, monkeypatch, falha_de_comando):
    monkeypatch.setattr(etapas, "docker_exe", lambda: "docker.exe")
    ex = _executor(ctx, [("up -d", falha_de_comando("container unhealthy"))])
    with pytest.raises(ErroInstalacao, match="saudável"):
        etapas.subir_stack(ctx)
    assert any(" ps -a" in c for c in ex.comandos())


# ───────── Keycloak, n8n, Ollama
def test_keycloak_extrai_a_senha_temporaria_sem_logar(ctx):
    saida = ("alterado: realm criado\nSenha temporária de admin@exemplo.com.br (exibida uma única vez; troca obrigatória no 1º login):\n"
             "Xy9-SENHA-temporaria_123\n")
    ex = _executor(ctx, [("provisionar", Resultado(0, saida))])
    etapas.keycloak(ctx)
    assert ctx.efemeros["admin_senha"] == "Xy9-SENHA-temporaria_123"
    assert "Xy9-SENHA-temporaria_123" not in "\n".join(ctx.logs)
    assert ctx.redator.limpar("senha Xy9-SENHA-temporaria_123") == "senha ***"
    assert ex.chamadas[-1][1]["sensivel"] is True


def test_keycloak_usuario_ja_existente_nao_tem_senha(ctx):
    _executor(ctx, [("provisionar", Resultado(0, "igual: nenhuma alteração necessária.\n"))])
    etapas.keycloak(ctx)
    assert "admin_senha" not in ctx.efemeros


def test_keycloak_existente_sem_nada_na_8180_falha_claro(ctx, monkeypatch):
    ctx.o.keycloak_existente, ctx.o.componentes = True, ["cerebro"]
    monkeypatch.setattr(etapas, "porta_ocupada", lambda p: False)
    _executor(ctx)
    tempo = {"t": 0.0}
    ctx.agora = lambda: tempo["t"]
    ctx.esperar = lambda s: tempo.__setitem__("t", tempo["t"] + s)
    with pytest.raises(ErroInstalacao, match="8180"):
        etapas.keycloak(ctx)


def test_ollama_instalado_define_pasta_de_modelos_e_sobe_o_servico(ctx, monkeypatch):
    monkeypatch.setattr(etapas, "ollama_exe", lambda: r"C:\o\ollama.exe")
    estado = {"sobe": False}
    monkeypatch.setattr(etapas, "porta_ocupada", lambda p: estado["sobe"])
    ex = _executor(ctx)
    ex.iniciar_solto = lambda cmd, **kw: (ex.soltos.append(cmd), estado.__setitem__("sobe", True))
    etapas.ollama(ctx)
    assert ["setx", "OLLAMA_MODELS", str(ctx.o.pesos_ollama)] in [c for c, _ in ex.chamadas]
    assert ex.soltos == [[r"C:\o\ollama.exe", "serve"]]


def test_ollama_ja_rodando_nao_sobe_outro(ctx, monkeypatch):
    monkeypatch.setattr(etapas, "ollama_exe", lambda: r"C:\o\ollama.exe")
    monkeypatch.setattr(etapas, "porta_ocupada", lambda p: True)
    ex = _executor(ctx)
    etapas.ollama(ctx)
    assert ex.soltos == [] and any("já está rodando" in x for x in ctx.logs)


def test_ollama_ausente_instala_pelo_winget_sem_elevacao(ctx, monkeypatch):
    achados = iter([None, r"C:\o\ollama.exe", r"C:\o\ollama.exe"])
    monkeypatch.setattr(etapas, "ollama_exe", lambda: next(achados, r"C:\o\ollama.exe"))
    monkeypatch.setattr(etapas, "_winget", lambda: r"C:\winget.exe")
    monkeypatch.setattr(etapas, "porta_ocupada", lambda p: True)
    ex = _executor(ctx)
    etapas.ollama(ctx)
    instalar = next(c for c in ex.comandos() if "winget" in c)
    assert "Ollama.Ollama" in instalar and "RunAs" not in instalar


def test_n8n_credencial_roda_o_script_do_projeto(ctx):
    ex = _executor(ctx)
    etapas.n8n_credencial(ctx)
    assert ex.chamadas[-1][0][-2:] == ["-m", "scripts.n8n.credencial_cerebro"]


# ───────── atalhos
def test_atalhos_usam_literais_com_aspas_simples_e_o_script_da_instalacao(ctx, tmp_path, monkeypatch):
    from tudoia_instalador import atalhos
    monkeypatch.setattr(atalhos, "pastas_de_atalho", lambda: [tmp_path / "Desktop"])
    (ctx.raiz / "scripts").mkdir(parents=True)
    for nome in ("iniciar.ps1", "parar.ps1", "desinstalar.ps1"):
        (ctx.raiz / "scripts" / nome).write_text("", encoding="utf-8")
    ex = _executor(ctx)
    atalhos.criar_atalhos(ctx)
    scripts = [c[-1] for c, _ in ex.chamadas]
    assert len(scripts) == 3 and all("CreateShortcut(" in s and "$s.Save()" in s for s in scripts)
    assert "iniciar.ps1" in scripts[0] and "-WindowStyle Hidden" in scripts[0] and "-WindowStyle" not in scripts[2]


def test_atalho_com_aspa_simples_na_pasta_nao_escapa_do_literal():
    from tudoia_instalador.atalhos import _script_criar
    s = _script_criar(Path(r"C:\x\a.lnk"), "powershell.exe", "-File 'x'; calc", Path(r"C:\d'ir"), "i.ico")
    assert "'-File ''x''; calc'" in s and "C:\\d''ir" in s


# ───────── painel
def test_painel_inicia_em_segundo_plano_e_espera_a_saude(ctx, monkeypatch):
    estado = {"no_ar": False}
    monkeypatch.setattr(etapas, "urllib_ok", lambda url: estado["no_ar"])
    ex = _executor(ctx)
    ex.iniciar_solto = lambda cmd, **kw: (ex.soltos.append(cmd), estado.__setitem__("no_ar", True))
    etapas.painel(ctx)
    assert ex.soltos[0][-3:] == ["-m", "tudoia_painel", "painel"]


def test_lista_de_etapas_tem_ids_unicos_e_ordem_segura():
    ids = [e.id for e in etapas.montar_etapas()]
    assert len(ids) == len(set(ids))
    ordem = {i: n for n, i in enumerate(ids)}
    assert ordem["verificacao"] < ordem["codigo"] < ordem["env"] < ordem["dependencias"] < ordem["segredos"] < ordem["stack"]
    assert ordem["uv"] < ordem["python"] < ordem["dependencias"]
    assert ordem["docker"] < ordem["stack"] < ordem["keycloak"] < ordem["n8n"] and ordem["config_litellm"] < ordem["stack"]
    assert ordem["env"] < ordem["docker"]    # o .env (e as chaves) já existem se o Docker pedir reinício


def test_etapas_opcionais_so_rodam_com_o_componente(opcoes):
    por_id = {e.id: e for e in etapas.montar_etapas()}
    opcoes.componentes = ["keycloak"]
    assert not por_id["ollama"].aplica(opcoes) and not por_id["comfyui"].aplica(opcoes) and not por_id["n8n"].aplica(opcoes)
    assert por_id["keycloak"].aplica(opcoes)
    opcoes.componentes = ["n8n", "cerebro", "ollama", "comfyui"]
    opcoes.keycloak_existente = True
    assert por_id["ollama"].aplica(opcoes) and por_id["n8n"].aplica(opcoes) and por_id["keycloak"].aplica(opcoes)
    assert not por_id["sync"].aplica(opcoes)    # clientes de IA só com consentimento explícito


# ───────── resiliência do ComfyUI e limpeza segura de arquivos
def test_remover_arquivo_seguro_trata_arquivo_somente_leitura(tmp_path):
    import os
    import stat
    arq = tmp_path / "ro.txt"
    arq.write_text("conteúdo")
    os.chmod(arq, stat.S_IREAD)
    assert etapas._remover_arquivo_seguro(arq) is True
    assert not arq.exists()


def test_remover_arquivo_seguro_tolera_falha_persistente_com_aviso(tmp_path, monkeypatch):
    arq = tmp_path / "bloqueado.txt"
    arq.write_text("conteúdo")
    avisos = []

    def unlink_falha(self, missing_ok=True):
        raise PermissionError("arquivo em uso")

    monkeypatch.setattr(Path, "unlink", unlink_falha)
    # Não deve estourar exceção, apenas logar aviso e devolver False
    assert etapas._remover_arquivo_seguro(arq, retentativas=2, espera=0.01, log=avisos.append) is False
    assert any("não consegui remover" in a for a in avisos)


def test_mover_pasta_segura_remove_destino_vazio_e_move(tmp_path):
    origem = tmp_path / "origem"
    origem.mkdir()
    (origem / "arquivo.txt").write_text("ok")
    destino = tmp_path / "destino"
    destino.mkdir()  # pasta vazia
    etapas._mover_pasta_segura(origem, destino)
    assert not origem.exists()
    assert (destino / "arquivo.txt").is_file()


def test_mover_pasta_segura_mescla_quando_destino_ja_existe_com_conteudo(tmp_path):
    origem = tmp_path / "ComfyUI_windows_portable"
    origem.mkdir()
    (origem / "run_nvidia_gpu.bat").write_text("@echo off")
    destino = tmp_path / "Modelos"
    destino.mkdir()
    (destino / "outro.txt").write_text("existente")
    etapas._mover_pasta_segura(origem, destino)
    assert not origem.exists()
    assert (destino / "run_nvidia_gpu.bat").is_file()
    assert not (destino / "ComfyUI_windows_portable").exists()


def test_comfyui_reaproveita_extracao_anterior_sem_baixar_novamente(ctx, tmp_path, monkeypatch):
    ctx.o.componentes = ["comfyui"]
    ctx.o.pasta_comfyui = str(tmp_path / "Modelos" / "ComfyUI")
    padrao = tmp_path / "Modelos" / "ComfyUI_windows_portable"
    padrao.mkdir(parents=True)
    (padrao / "run_nvidia_gpu.bat").write_text("@echo off")

    baixou = [False]
    def baixar_proibido(*a, **kw):
        baixou[0] = True
        raise AssertionError("não deveria baixar de novo")

    monkeypatch.setattr(etapas.codigo, "baixar_https", baixar_proibido)
    etapas.comfyui(ctx)
    assert baixou[0] is False
    assert (Path(ctx.o.pasta_comfyui) / "run_nvidia_gpu.bat").is_file()


def test_comfyui_resiste_a_permission_error_no_unlink_do_arquivo(ctx, tmp_path, monkeypatch):
    ctx.o.componentes = ["comfyui"]
    ctx.o.pasta_comfyui = str(tmp_path / "comfy_final")

    # Simula download criando arquivo falso
    def baixar_fake(url, destino, hosts, max_bytes):
        destino.write_bytes(b"conteudo-fake-7z")
        return destino

    # Simula extração criando a pasta esperada com run_nvidia_gpu.bat
    def extrair_fake(c, arquivo, destino):
        pasta_extraida = destino / "ComfyUI_windows_portable"
        pasta_extraida.mkdir(parents=True, exist_ok=True)
        (pasta_extraida / "run_nvidia_gpu.bat").write_text("@echo off")

    monkeypatch.setattr(etapas.codigo, "baixar_https", baixar_fake)
    monkeypatch.setattr(etapas, "_extrair_7z", extrair_fake)

    # Força _remover_arquivo_seguro a simular PermissionError persistente ao limpar o .7z
    monkeypatch.setattr(etapas, "_remover_arquivo_seguro", lambda caminho, **kw: False)

    etapas.comfyui(ctx)
    assert (Path(ctx.o.pasta_comfyui) / "run_nvidia_gpu.bat").is_file()


def test_passos_frontend_ordem_o_que_instalar_antes_de_onde_instalar():
    js = (Path(__file__).resolve().parent.parent.parent / "instalador" / "tudoia_instalador" / "static" / "instalador.js").read_text(encoding="utf-8")
    assert 'const PASSOS = ["Sistema", "O que instalar", "Onde instalar", "Conta e chaves", "Revisar", "Instalar"];' in js
    assert 'const telas = [telaSistema, telaComponentes, telaOnde, telaConta, telaRevisar, telaInstalar];' in js
    assert '1: ["componentes", "keycloak_existente", "keycloak_existente_admin", "keycloak_existente_senha"]' in js
    assert '2: ["pasta_instalacao", "pasta_dados", "pasta_pesos_ollama", "pasta_comfyui", "projeto_compose"]' in js
    assert 'mostrarCarregando' in js and 'esconderCarregando' in js
    assert 'cartao("Python"' in js


def test_python_info_detecta_versao():
    from tudoia_instalador import sistema
    def falso_executar(cmd, timeout=5.0):
        if cmd[0] == "python":
            return 0, "Python 3.12.3\n"
        return 127, ""
    instalado, versao = sistema.python_info(falso_executar)
    assert instalado is True and versao == "3.12.3"

    def nao_instalado(cmd, timeout=5.0):
        return 127, ""
    instalado2, versao2 = sistema.python_info(nao_instalado)
    assert instalado2 is False and versao2 == ""


def test_instalar_python_quando_ja_existe(ctx):
    from tudoia_instalador.execucao import Resultado
    ctx.uv = "uv.exe"
    ex = _executor(ctx, [("find 3.12", Resultado(0, "C:\\Python312\\python.exe\n"))])
    etapas.instalar_python(ctx)
    assert any("Python 3.12 já disponível" in linha for linha in ctx.logs)
    assert not any("install" in c for c in ex.comandos())


def test_instalar_python_quando_nao_encontrado(ctx):
    from tudoia_instalador.execucao import Resultado
    ctx.uv = "uv.exe"
    chamadas_find = [0]
    def falso_rodar(cmd, **kw):
        linha = " ".join(cmd)
        if "find 3.12" in linha:
            assert 2 in kw.get("aceitos", (0,)), "uv python find devolve código 2 quando não encontra o interpretador"
            chamadas_find[0] += 1
            if chamadas_find[0] == 1:
                return Resultado(2, "error: No interpreter found for Python 3.12")
            return Resultado(0, "C:\\Python312\\python.exe\n")
        if "install 3.12" in linha:
            return Resultado(0, "Installed Python 3.12.3")
        return Resultado(0, "")
    ex = _executor(ctx)
    ex.rodar = falso_rodar
    etapas.instalar_python(ctx)
    assert any("baixando e instalando" in linha for linha in ctx.logs)
    assert any("instalado com sucesso" in linha for linha in ctx.logs)

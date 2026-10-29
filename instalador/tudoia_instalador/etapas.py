"""As etapas da instalação, na ordem em que rodam. Cada uma é idempotente: rodar de novo depois de uma falha é seguro."""
from __future__ import annotations

import json
import os
import re
import shutil
import stat
import tempfile
import time
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from . import VERSAO, codigo, envfile
from .execucao import ErroComando
from .motor import Contexto, Etapa, ErroInstalacao, ReinicioNecessario
from .opcoes import validar
from .sistema import (docker_desktop_exe, docker_exe, docker_pronto, disco_livre_gb, espaco_necessario_gb, ollama_exe,
                      porta_ocupada, portas_necessarias)

MARCA = ".tudoia-instalacao.json"
UV_VERSAO = "0.13.0"
UV_URL = f"https://github.com/astral-sh/uv/releases/download/{UV_VERSAO}/uv-x86_64-pc-windows-msvc.zip"
UV_HOSTS = ("github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com")
COMFYUI_URL = "https://github.com/comfyanonymous/ComfyUI/releases/latest/download/ComfyUI_windows_portable_nvidia.7z"
COMFYUI_HOSTS = ("github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com")
SETUP_7Z_URL = "https://www.7-zip.org/a/7zr.exe"
DOCKER_INSTALADOR_URL = "https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe"
OLLAMA_INSTALADOR_URL = "https://ollama.com/download/OllamaSetup.exe"
COD_REINICIO = (3010, 1641)   # "reinicialização necessária" do instalador do Windows/MSI


def _remover_arquivo_seguro(caminho: Path, retentativas: int = 5, espera: float = 0.5,
                            log: Callable[[str], None] | None = None) -> bool:
    if not caminho.is_file():
        return True
    for tentativa in range(retentativas):
        try:
            caminho.unlink(missing_ok=True)
            return True
        except PermissionError:
            try:
                os.chmod(caminho, stat.S_IWRITE)
                caminho.unlink(missing_ok=True)
                return True
            except (PermissionError, OSError):
                pass
        except OSError:
            pass
        if tentativa < retentativas - 1:
            time.sleep(espera * (tentativa + 1))
    if log:
        log(f"aviso: não consegui remover arquivo temporário {caminho.name}; pode ser removido mais tarde")
    return False


def _mover_pasta_segura(origem: Path, destino: Path, log: Callable[[str], None] | None = None) -> None:
    if origem.resolve() == destino.resolve():
        return
    if destino.exists() and destino.is_dir() and not any(destino.iterdir()):
        try:
            destino.rmdir()
        except OSError:
            pass
    if not destino.exists():
        for tentativa in range(5):
            try:
                origem.rename(destino)
                return
            except (PermissionError, OSError):
                if tentativa < 4:
                    time.sleep(0.5 * (tentativa + 1))
    try:
        destino.mkdir(parents=True, exist_ok=True)
        for item in list(origem.iterdir()):
            alvo = destino / item.name
            if alvo.exists():
                if alvo.is_dir():
                    shutil.rmtree(alvo, ignore_errors=True)
                else:
                    _remover_arquivo_seguro(alvo, log=log)
            shutil.move(str(item), str(alvo))
        shutil.rmtree(origem, ignore_errors=True)
    except (PermissionError, OSError) as err_move:
        raise ErroInstalacao(f"não consegui mover {origem.name} para {destino}: {err_move}") from err_move


def _tem_instalacao_anterior(raiz: Path) -> bool:
    return (raiz / MARCA).is_file()


# ───────────────────────────────────────────────────────────── 1. verificação
def verificacao(c: Contexto) -> None:
    erros = validar(c.o)
    if erros:
        raise ErroInstalacao("; ".join(f"{campo}: {msg}" for campo, msg in erros))
    d = c.diagnostico()
    if not d.windows_ok:
        raise ErroInstalacao(f"Windows build {d.windows_build} é antigo demais: o Docker Desktop precisa do Windows 10 2004 (19041) ou mais novo")
    if not d.internet:
        raise ErroInstalacao("sem acesso à internet (github.com): o instalador baixa imagens Docker e dependências")
    livre, preciso = disco_livre_gb(c.o.pasta_instalacao), espaco_necessario_gb(c.o.componentes)
    if livre < preciso:
        raise ErroInstalacao(f"pouco espaço em disco: {livre:.0f} GB livres, a instalação precisa de uns {preciso} GB (sem os modelos)")
    if c.o.usa("comfyui") and not d.gpu_nome:
        raise ErroInstalacao("o ComfyUI portable é a versão NVIDIA e não encontrei GPU NVIDIA: desmarque o ComfyUI")
    atualizando = _tem_instalacao_anterior(c.raiz)
    em_uso = {n: p for n, p in portas_necessarias(c.o.componentes, c.o.keycloak_existente).items() if porta_ocupada(p)}
    if em_uso and not atualizando:
        lista = ", ".join(f"{n} ({p})" for n, p in em_uso.items())
        raise ErroInstalacao(f"portas em uso por outro programa: {lista}. Feche o que as usa ou desmarque o componente")
    if em_uso:
        c.log("reinstalação sobre uma instalação existente: as portas em uso são dela mesma")
    c.log(f"Windows {d.windows_build}, {livre:.0f} GB livres, GPU: {d.gpu_nome or 'não encontrada'}")


# ───────────────────────────────────────────────────────────── 2. código-fonte
def obter_codigo(c: Contexto) -> None:
    c.raiz.mkdir(parents=True, exist_ok=True)
    if c.o.fonte_codigo == "embutido":
        try:
            zip_path, info = codigo.payload_embutido()
        except codigo.ErroCodigo as e:
            raise ErroInstalacao(str(e)) from e
        c.log(f"código embutido, versão {info.get('versao', '?')} ({info.get('arquivos', '?')} arquivos)")
        prefixo = False
    else:
        zip_path = c.raiz / ".codigo-github.zip"
        c.log(f"baixando {c.o.github_repo}@{c.o.github_ref} do GitHub")
        try:
            codigo.baixar_github(c.o.github_repo, c.o.github_ref, zip_path)
        except codigo.ErroCodigo as e:
            raise ErroInstalacao(str(e)) from e
        prefixo = True
    try:
        n = codigo.instalar(zip_path, c.raiz, remover_prefixo=prefixo)
    except (codigo.ErroCodigo, zipfile.BadZipFile) as e:
        raise ErroInstalacao(f"pacote do código inválido: {e}") from e
    finally:
        if c.o.fonte_codigo == "github":
            _remover_arquivo_seguro(zip_path, log=c.log)
    if not (c.raiz / "runtime" / "docker-compose.yml").is_file() or not (c.raiz / ".env.example").is_file():
        raise ErroInstalacao("o pacote não parece ser o TudoIA (faltam runtime/docker-compose.yml ou .env.example)")
    c.log(f"{n} arquivos instalados em {c.raiz}")


# ───────────────────────────────────────────────────────────── 3. pastas
def _eh_juncao(p: Path) -> bool:
    return os.path.isjunction(p) if hasattr(os.path, "isjunction") else False


def pastas(c: Contexto) -> None:
    raiz, dados = c.raiz, Path(str(c.o.dados))
    for p in (dados, dados / "logs", dados / "cerebro", dados / "documentos", dados / "estudio", dados / "backups" / "env"):
        p.mkdir(parents=True, exist_ok=True)
    if c.o.usa("ollama"):
        Path(str(c.o.pesos_ollama)).mkdir(parents=True, exist_ok=True)
    if c.o.usa("comfyui"):
        Path(str(c.o.comfyui)).parent.mkdir(parents=True, exist_ok=True)
    elo = raiz / "dados"
    if dados.resolve() != elo.resolve():
        # O compose monta ../dados e o painel grava em <raiz>\dados: uma junção leva os dois para a pasta escolhida.
        if _eh_juncao(elo):
            if Path(os.path.realpath(elo)) != dados.resolve():
                os.rmdir(elo)
        elif elo.exists():
            if any(elo.iterdir()):
                raise ErroInstalacao(f"já existe {elo} com conteúdo; use essa mesma pasta de dados ou esvazie-a")
            elo.rmdir()
        if not elo.exists():
            c.executor.rodar(["cmd", "/c", "mklink", "/J", str(elo), str(dados)])
    (raiz / MARCA).write_text(json.dumps({
        "versao_instalador": VERSAO, "projeto_compose": c.o.projeto_compose, "pasta_dados": str(dados),
        "componentes": c.o.componentes, "instalado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }, ensure_ascii=False, indent=2), encoding="utf-8")


# ───────────────────────────────────────────────────────────── 4. .env
def _restringir_acesso(c: Contexto, arquivo: Path) -> None:
    usuario = os.environ.get("USERNAME", "")
    if not re.fullmatch(r"[\w .\-]{1,64}", usuario):
        c.log("aviso: não consegui restringir o acesso ao .env (usuário desconhecido)")
        return
    try:
        c.executor.rodar(["icacls", str(arquivo), "/inheritance:r", "/grant:r", f"{usuario}:F"], mostrar=False)
    except ErroComando:
        c.log("aviso: não consegui restringir o acesso ao .env; proteja a pasta da instalação")


def escrever_env(c: Contexto) -> None:
    alvo = c.raiz / ".env"
    c.redator.adicionar(*c.o.chaves_provedores.values(), c.o.keycloak_existente_senha)
    base = alvo.read_text(encoding="utf-8") if alvo.is_file() else (c.raiz / ".env.example").read_text(encoding="utf-8")
    texto = envfile.montar(base, c.o)
    tmp = alvo.with_suffix(".tmp")
    tmp.write_text(texto, encoding="utf-8", newline="\n")
    os.replace(tmp, alvo)
    _restringir_acesso(c, alvo)
    c.log(f".env gravado (perfis do compose: {','.join(c.o.perfis) or 'nenhum'})")


# ───────────────────────────────────────────────────────────── 5. uv e dependências Python
def obter_uv(c: Contexto) -> None:
    achado = shutil.which("uv")
    if achado:
        c.uv = achado
        c.log(f"uv já instalado: {achado}")
        return
    pasta = c.raiz / "ferramentas" / "uv"
    exe = pasta / "uv.exe"
    if not exe.is_file():
        pasta.mkdir(parents=True, exist_ok=True)
        zip_path = pasta / "uv.zip"
        try:
            codigo.baixar_https(UV_URL, zip_path, UV_HOSTS, 60 * 1024 ** 2)
            esperado = _sha256_publicado(UV_URL + ".sha256")
            if esperado and codigo.sha256_arquivo(zip_path) != esperado:
                raise ErroInstalacao("o uv baixado não confere com o sha256 publicado; tente de novo")
            codigo.extrair(zip_path, pasta)
        except codigo.ErroCodigo as e:
            raise ErroInstalacao(f"não consegui obter o uv: {e}") from e
        finally:
            _remover_arquivo_seguro(zip_path, log=c.log)
    c.uv = str(exe)
    c.log(f"uv {UV_VERSAO} em {exe}")


def _sha256_publicado(url: str) -> str | None:
    try:
        tmp = Path(tempfile.mkstemp(suffix=".sha256")[1])
        try:
            codigo.baixar_https(url, tmp, UV_HOSTS, 4096)
            m = re.match(r"([0-9a-fA-F]{64})", tmp.read_text(encoding="utf-8", errors="replace"))
            return m.group(1).lower() if m else None
        finally:
            _remover_arquivo_seguro(tmp)
    except codigo.ErroCodigo:
        return None


def instalar_python(c: Contexto) -> None:
    assert c.uv, "etapa do uv não rodou"
    r = c.executor.rodar([c.uv, "python", "find", "3.12", "--no-project"], aceitos=(0, 1, 2), mostrar=False)
    if r.codigo == 0 and r.saida.strip():
        c.log(f"Python 3.12 já disponível: {r.saida.strip().splitlines()[-1]}")
        return
    c.log("Python 3.12 não encontrado; baixando e instalando...")
    c.executor.rodar([c.uv, "python", "install", "3.12"], timeout=1800)
    r_pos = c.executor.rodar([c.uv, "python", "find", "3.12", "--no-project"], aceitos=(0, 1, 2), mostrar=False)
    if r_pos.codigo != 0 or not r_pos.saida.strip():
        raise ErroInstalacao("o Python 3.12 não foi encontrado após a instalação pelo uv")
    c.log(f"Python 3.12 instalado com sucesso: {r_pos.saida.strip().splitlines()[-1]}")


def dependencias(c: Contexto) -> None:
    assert c.uv, "etapa do uv não rodou"
    c.executor.rodar([c.uv, "sync", "--frozen", "--project", str(c.raiz)], cwd=c.raiz, timeout=1800)
    if not Path(c.python).is_file():
        raise ErroInstalacao("o uv terminou, mas o ambiente Python não foi criado")


def segredos_internos(c: Contexto) -> None:
    c.executor.rodar([c.python, "-m", "tudoia_painel", "segredos"], cwd=c.raiz, env=c.env_projeto, mostrar=False)
    c.log("segredos internos gerados no .env (nenhum valor é exibido)")


def config_litellm(c: Contexto) -> None:
    c.executor.rodar([c.python, "-m", "tudoia_painel", "gerar-config"], cwd=c.raiz, env=c.env_projeto)


# ───────────────────────────────────────────────────────────── 6. Docker
def _winget() -> str | None:
    return shutil.which("winget")


def _elevado(c: Contexto, exe: str, argumentos: list[str], descricao: str) -> int:
    """Roda `exe argumentos` com elevação (o Windows pede a confirmação ao usuário) e devolve o código de saída."""
    lista = ",".join("'" + a.replace("'", "''") + "'" for a in argumentos)
    script = (f"$p = Start-Process -FilePath '{exe}' -ArgumentList @({lista}) -Verb RunAs -Wait -PassThru; "
              "exit $p.ExitCode")
    c.log(f"{descricao}: o Windows vai pedir permissão de administrador; confirme a janela que aparecer")
    r = c.executor.rodar(["powershell", "-NoProfile", "-Command", script], timeout=3600, aceitos=tuple(range(0, 256)) + COD_REINICIO,
                         mostrar=False)
    return r.codigo


def _baixar_instalador(c: Contexto, url: str, hosts: tuple[str, ...], nome: str) -> Path:
    destino = Path(tempfile.gettempdir()) / "TudoIA-Setup" / nome
    destino.parent.mkdir(parents=True, exist_ok=True)
    c.log(f"baixando {nome} (sem verificação de hash: o winget não está disponível)")
    try:
        codigo.baixar_https(url, destino, hosts, 2 * 1024 ** 3)
    except codigo.ErroCodigo as e:
        raise ErroInstalacao(str(e)) from e
    return destino


def instalar_docker_desktop(c: Contexto) -> None:
    winget = _winget()
    if winget:
        cod = _elevado(c, winget, ["install", "-e", "--id", "Docker.DockerDesktop", "--silent",
                                   "--accept-package-agreements", "--accept-source-agreements",
                                   "--override", "install --quiet --accept-license --backend=wsl-2"],
                       "instalando o Docker Desktop")
    else:
        exe = _baixar_instalador(c, DOCKER_INSTALADOR_URL, ("desktop.docker.com",), "DockerDesktopInstaller.exe")
        cod = _elevado(c, str(exe), ["install", "--quiet", "--accept-license", "--backend=wsl-2"], "instalando o Docker Desktop")
    if cod in COD_REINICIO:
        raise ReinicioNecessario("o Docker Desktop foi instalado e o Windows precisa reiniciar; o instalador continua depois")
    if cod != 0 and not docker_exe():
        raise ErroInstalacao(f"a instalação do Docker Desktop falhou (código {cod}). Instale-o à mão e clique em Continuar")


def docker(c: Contexto) -> None:
    recem_instalado = False
    if not docker_exe():
        instalar_docker_desktop(c)
        recem_instalado = True
    if docker_pronto():
        c.log("Docker já está pronto")
        return
    desktop = docker_desktop_exe()
    if desktop:
        c.executor.iniciar_solto([desktop], cwd=None, env=None, arquivo_log=c.pasta_estado / "docker-desktop.log")
    c.log("esperando o Docker Desktop ficar pronto (a primeira vez demora; aceite os termos se a janela pedir)")
    if c.esperar_ate(docker_pronto, 420, "o Docker Desktop"):
        return
    if recem_instalado:
        raise ReinicioNecessario("o Docker Desktop não iniciou depois da instalação: provavelmente falta reiniciar o Windows (WSL2)")
    raise ErroInstalacao("o Docker Desktop não ficou pronto. Abra-o, aceite os termos, espere o ícone ficar verde e clique em Continuar")


def _compose(c: Contexto) -> list[str]:
    exe = docker_exe()
    if not exe:
        raise ErroInstalacao("docker não encontrado")
    return [exe, "compose", "-p", c.o.projeto_compose, "-f", str(c.raiz / "runtime" / "docker-compose.yml"),
            "--env-file", str(c.raiz / ".env")]


def subir_stack(c: Contexto) -> None:
    base = _compose(c)
    c.executor.rodar([*base, "pull", "--ignore-buildable"], cwd=c.raiz, timeout=7200)
    try:
        c.executor.rodar([*base, "up", "-d", "--build", "--wait", "--wait-timeout", "900"], cwd=c.raiz, timeout=7200)
    except ErroComando as e:
        c.executor.rodar([*base, "ps", "-a"], cwd=c.raiz, aceitos=(0, 1), timeout=60)
        raise ErroInstalacao("a stack Docker não ficou saudável (veja o registro acima). Corrija e clique em Continuar") from e


# ───────────────────────────────────────────────────────────── 7. Ollama
def ollama(c: Contexto) -> None:
    if not ollama_exe():
        winget = _winget()
        if winget:
            c.executor.rodar([winget, "install", "-e", "--id", "Ollama.Ollama", "--silent",
                              "--accept-package-agreements", "--accept-source-agreements"], timeout=1800)
        else:
            exe = _baixar_instalador(c, OLLAMA_INSTALADOR_URL, ("ollama.com", "github.com", "objects.githubusercontent.com",
                                                                "release-assets.githubusercontent.com"), "OllamaSetup.exe")
            c.executor.rodar([str(exe), "/SILENT"], timeout=1800)
    exe = ollama_exe()
    if not exe:
        raise ErroInstalacao("o Ollama foi instalado, mas não encontrei o ollama.exe. Abra um novo terminal e clique em Continuar")
    pesos = str(c.o.pesos_ollama)
    # O Ollama sobe sozinho com o Windows e olharia a pasta padrão de modelos: grava as duas variáveis para o usuário.
    c.executor.rodar(["setx", "OLLAMA_MODELS", pesos], mostrar=False)
    c.executor.rodar(["setx", "OLLAMA_HOST", "127.0.0.1:11434"], mostrar=False)
    if porta_ocupada(11434):
        c.log("o Ollama já está rodando; os modelos ficam onde ele estiver configurado (reinicie-o para usar a pasta nova)")
        return
    c.executor.iniciar_solto([exe, "serve"], cwd=None, env={"OLLAMA_HOST": "127.0.0.1:11434", "OLLAMA_MODELS": pesos},
                             arquivo_log=Path(str(c.o.dados)) / "logs" / "ollama.log")
    if not c.esperar_ate(lambda: porta_ocupada(11434), 60, "o Ollama"):
        raise ErroInstalacao("o Ollama não respondeu na porta 11434")


# ───────────────────────────────────────────────────────────── 8. Keycloak e n8n
_RE_SENHA = re.compile(r"Senha temporária de .*?:\s*\n(\S+)")


def keycloak(c: Contexto) -> None:
    if c.o.keycloak_existente:
        if not c.esperar_ate(lambda: porta_ocupada(8180), 60, "o Keycloak existente em localhost:8180", 5.0):
            raise ErroInstalacao("não há nada respondendo em localhost:8180; suba o Keycloak ou use o embutido")
    r = c.executor.rodar([c.python, "-m", "scripts.keycloak.provisionar", "--admin-inicial", c.o.admin_email],
                         cwd=c.raiz, env=c.env_projeto, timeout=600, sensivel=True)
    achou = _RE_SENHA.search(r.saida)
    if achou:
        c.efemeros["admin_senha"] = achou.group(1)
        c.redator.adicionar(achou.group(1))
    for linha in r.saida.splitlines():
        if linha.startswith(("alterado:", "igual:", "usuário")):
            c.log(linha)
    c.log("Keycloak provisionado (realm tudoia, clientes e papéis)")


def n8n_credencial(c: Contexto) -> None:
    c.executor.rodar([c.python, "-m", "scripts.n8n.credencial_cerebro"], cwd=c.raiz, env=c.env_projeto, mostrar=False)


# ───────────────────────────────────────────────────────────── 9. ComfyUI
def _extrair_7z(c: Contexto, arquivo: Path, destino: Path) -> None:
    tar = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "tar.exe"
    r = c.executor.rodar([str(tar), "-xf", str(arquivo), "-C", str(destino)], timeout=3600, aceitos=(0, 1, 2)) if tar.is_file() else None
    if r is not None and r.codigo == 0:
        return
    c.log("o tar do Windows não leu o .7z; usando o 7zr oficial")
    sete = destino / "7zr.exe"
    try:
        codigo.baixar_https(SETUP_7Z_URL, sete, ("www.7-zip.org",), 5 * 1024 ** 2)
    except codigo.ErroCodigo as e:
        raise ErroInstalacao(str(e)) from e
    try:
        c.executor.rodar([str(sete), "x", str(arquivo), f"-o{destino}", "-y"], timeout=3600)
    finally:
        _remover_arquivo_seguro(sete, log=c.log)


def comfyui(c: Contexto) -> None:
    portavel = Path(str(c.o.comfyui))
    if (portavel / "run_nvidia_gpu.bat").is_file():
        c.log("ComfyUI portable já está em " + str(portavel))
        return
    pai = portavel.parent
    pai.mkdir(parents=True, exist_ok=True)
    padrao = pai / "ComfyUI_windows_portable"
    if not (padrao / "run_nvidia_gpu.bat").is_file():
        arquivo = pai / "ComfyUI_windows_portable_nvidia.7z"
        c.log("baixando o ComfyUI portable (cerca de 2 GB)")
        try:
            codigo.baixar_https(COMFYUI_URL, arquivo, COMFYUI_HOSTS, 8 * 1024 ** 3)
            _extrair_7z(c, arquivo, pai)
        except codigo.ErroCodigo as e:
            raise ErroInstalacao(str(e)) from e
        finally:
            _remover_arquivo_seguro(arquivo, log=c.log)
    if padrao.is_dir() and padrao.resolve() != portavel.resolve():
        _mover_pasta_segura(padrao, portavel, c.log)
    if not (portavel / "run_nvidia_gpu.bat").is_file():
        raise ErroInstalacao("o ComfyUI foi extraído, mas não achei run_nvidia_gpu.bat")


# ───────────────────────────────────────────────────────────── 10. clientes de IA, atalhos e painel
def sincronizar_clientes(c: Contexto) -> None:
    c.executor.rodar([c.python, "-m", "tudoia_painel", "sync"], cwd=c.raiz, env=c.env_projeto)


def atalhos(c: Contexto) -> None:
    from .atalhos import criar_atalhos
    criar_atalhos(c)


def painel(c: Contexto) -> None:
    if urllib_ok("http://127.0.0.1:3100/saude"):
        c.log("o painel já está no ar")
        return
    c.executor.iniciar_solto([c.python, "-m", "tudoia_painel", "painel"], cwd=c.raiz, env=c.env_projeto,
                             arquivo_log=Path(str(c.o.dados)) / "logs" / "painel.log")
    if not c.esperar_ate(lambda: urllib_ok("http://127.0.0.1:3100/saude"), 120, "o painel", 2.0):
        raise ErroInstalacao("o painel não respondeu em 127.0.0.1:3100; veja dados\\logs\\painel.log")


def urllib_ok(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            return r.status == 200
    except (OSError, ValueError):
        return False


def montar_etapas() -> list[Etapa]:
    docker_uso = lambda o: True   # o núcleo (LiteLLM e Postgres) sempre usa Docker  # noqa: E731
    return [
        Etapa("verificacao", "Verificando o sistema", verificacao),
        Etapa("codigo", "Instalando os arquivos do TudoIA", obter_codigo),
        Etapa("pastas", "Preparando as pastas", pastas),
        Etapa("env", "Gravando a configuração (.env)", escrever_env),
        Etapa("uv", "Obtendo o uv (gerenciador Python)", obter_uv),
        Etapa("python", "Instalando o Python 3.12", instalar_python),
        Etapa("dependencias", "Instalando as dependências Python", dependencias),
        Etapa("segredos", "Gerando os segredos internos", segredos_internos),
        Etapa("docker", "Preparando o Docker Desktop", docker, docker_uso),
        Etapa("ollama", "Preparando o Ollama", ollama, lambda o: o.usa("ollama")),
        Etapa("config_litellm", "Gerando a configuração do gateway", config_litellm),
        Etapa("stack", "Baixando e iniciando os serviços Docker", subir_stack),
        Etapa("keycloak", "Configurando o login (Keycloak)", keycloak,
              lambda o: o.usa("keycloak") or o.keycloak_existente),
        Etapa("n8n", "Ligando o n8n ao Cérebro", n8n_credencial, lambda o: o.usa("n8n") and o.usa("cerebro")),
        Etapa("comfyui", "Instalando o ComfyUI portable", comfyui, lambda o: o.usa("comfyui")),
        Etapa("sync", "Configurando os clientes de IA", sincronizar_clientes, lambda o: o.configurar_clientes_ia),
        Etapa("atalhos", "Criando os atalhos", atalhos, lambda o: o.criar_atalhos),
        Etapa("painel", "Iniciando o painel", painel, lambda o: o.iniciar_ao_final),
    ]

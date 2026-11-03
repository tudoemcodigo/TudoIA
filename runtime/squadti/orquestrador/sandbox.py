"""
Sandbox de execução: o sistema que a Squad gerou roda isolado para ser atacado, estressado e usado "à força" sem risco.

- O sistema (e o banco dele) sobem numa REDE INTERNA do Docker (`--internal`): sem rota para a internet, sem porta publicada no host.
- As ferramentas (kit de ataque, k6, Playwright) rodam como containers irmãos NA MESMA rede e só alcançam o alvo.
- Tudo com teto de CPU, memória e processos, sem capabilities e com `no-new-privileges`. O sandbox é desmontado sempre (finally).

O Docker é usado pela CLI com argumentos montados SÓ por este módulo (nunca pelo modelo) e passados por um validador que recusa as
flags que quebram o isolamento (`--privileged`, `-v`, `--network host`, `--cap-add`...). O `docker.sock` está montado no container
da Squad por decisão do dono (ver docs/componentes/squadti.md): isto reduz o que ESTE código pode fazer, não protege de outro código.
"""
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

# Imagens fixadas por digest (reprodutível; a ferramenta não muda sozinha entre duas execuções).
IMAGEM_PYTHON = "python:3.12-slim@sha256:b18b261e1b4974b4f321451ad5251ded85abb22c2b8b262da527dda1d031ab30"
IMAGEM_K6 = "grafana/k6@sha256:3e4186aea62e11a45560bfc51e19eeafe82fc07ce069c78aff44b7ff893d9a5e"
IMAGEM_PLAYWRIGHT = "mcr.microsoft.com/playwright/python@sha256:35a390e70ab8ba7fbc909dc01af2329e287e89ccc8fb2f04a1a7ae94cacc5c30"
IMAGENS_BANCO = {
    "postgres": ("postgres:17-alpine@sha256:266d3c257594e195b309ae9d1805e54c788f1d7b375f56bf6c367aac6c917e7b", 5432),
}

SUBCOMANDOS = {"build", "network", "run", "create", "cp", "start", "logs", "rm", "inspect", "stats", "exec", "pull", "image", "kill",
               "wait", "info"}
# flags que quebram o isolamento: nunca passam, de onde quer que venham
PROIBIDAS = ("--privileged", "-v", "--volume", "--mount", "--pid", "--ipc", "--uts", "--userns", "--cap-add", "--device",
             "--volumes-from", "--security-opt=seccomp=unconfined", "--security-opt=apparmor=unconfined", "--add-host")
RE_NOME = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,62}$")
TIMEOUT_BUILD_S = 900
TIMEOUT_PADRAO_S = 120
MAX_SAIDA = 200_000


class SandboxFalhou(RuntimeError):
    """Algo do sandbox não subiu ou não respondeu: a etapa que o usa não pode concluir (falha fechado)."""

    def __init__(self, etapa: str, detalhe: str):
        super().__init__(f"{etapa}: {detalhe}")
        self.etapa, self.detalhe = etapa, detalhe


class ArgumentoProibido(RuntimeError):
    pass


def validar_argv(argv: List[str]) -> None:
    """Recusa subcomando fora da lista e flag que quebra o isolamento. `network host` também é proibido."""
    if len(argv) < 2 or argv[1] not in SUBCOMANDOS:
        raise ArgumentoProibido(f"subcomando do docker não permitido: {argv[1:2]}")
    for i, a in enumerate(argv):
        base = a.split("=", 1)[0]
        if a in PROIBIDAS or base in PROIBIDAS:
            raise ArgumentoProibido(f"argumento proibido no sandbox: {a}")
        if a in ("--network", "--net") and i + 1 < len(argv) and argv[i + 1] in ("host", "container"):
            raise ArgumentoProibido(f"rede proibida no sandbox: {argv[i + 1]}")
        if a.startswith(("--network=host", "--net=host")):
            raise ArgumentoProibido("rede proibida no sandbox: host")


class Docker:
    """CLI do docker com validação. `executor` é o seam dos testes: recebe (argv, timeout) e devolve (código, saída)."""

    def __init__(self, executavel: str = "docker", executor: Optional[Callable] = None):
        self.executavel = executavel
        self._executor = executor or self._subprocess

    @staticmethod
    def _subprocess(argv: List[str], timeout: int) -> Tuple[int, str]:
        try:
            r = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, check=False)
            return r.returncode, ((r.stdout or "") + (r.stderr or ""))[-MAX_SAIDA:]
        except subprocess.TimeoutExpired:
            return 124, f"timeout após {timeout}s"
        except OSError as e:
            return 127, f"não foi possível executar o docker: {e}"

    def executar(self, *args: str, timeout: int = TIMEOUT_PADRAO_S) -> Tuple[int, str]:
        argv = [self.executavel, *args]
        validar_argv(argv)
        return self._executor(argv, timeout)


def nome_seguro(prefixo: str, tarefa: str) -> str:
    nome = f"{prefixo}-{re.sub(r'[^a-z0-9]+', '-', tarefa.lower()).strip('-')}"[:60].rstrip("-.")
    if not RE_NOME.match(nome):
        raise SandboxFalhou("nome", f"nome inválido: {nome!r}")
    return nome


LIMITES_PADRAO = {"memoria": "1g", "cpus": "1.0", "pids": "512"}

# Sonda executada DENTRO da rede do sandbox: imprime o status HTTP (ou 0 se ninguém escuta). Qualquer status prova que o servidor responde.
SONDA_HTTP = (
    "import sys, urllib.request as u\n"
    "try:\n"
    "    print(u.urlopen(sys.argv[1], timeout=3).status)\n"
    "except Exception as e:\n"
    "    print(getattr(e, 'code', 0) or 0)\n"
)


def _limites(limites: Optional[dict] = None) -> List[str]:
    l = {**LIMITES_PADRAO, **(limites or {})}
    return ["--memory", str(l["memoria"]), "--cpus", str(l["cpus"]), "--pids-limit", str(l["pids"]), "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges:true"]


class Sandbox:
    """Ciclo de vida: construir a imagem, subir rede + banco + sistema, rodar ferramentas na rede, desmontar tudo."""

    def __init__(self, tarefa: str, workspace: Path, docker: Optional[Docker] = None, limites: Optional[dict] = None,
                 emitir: Optional[Callable[[str], None]] = None):
        self.tarefa, self.ws, self.docker = tarefa, Path(workspace), docker or Docker()
        self.limites = limites or {}
        self.emitir = emitir or (lambda texto: None)
        self.rede = nome_seguro("squadti-net", tarefa)
        self.imagem = nome_seguro("squadti-sut", tarefa)
        self.sut = nome_seguro("sut", tarefa)
        self.banco = nome_seguro("sut-db", tarefa)
        self.alvo: Optional[str] = None
        self._criados: List[str] = []   # containers a remover
        self._rede_criada = False
        self._imagem_construida = False

    # ------------------------------------------------------------ construção e subida
    def construir(self) -> None:
        if not (self.ws / "Dockerfile").is_file():
            raise SandboxFalhou("build", "o projeto não tem Dockerfile na raiz do workspace")
        self.emitir(f"[sandbox] construindo a imagem {self.imagem}")
        codigo, saida = self.docker.executar("build", "-t", self.imagem, "--pull=false", str(self.ws), timeout=TIMEOUT_BUILD_S)
        if codigo != 0:
            raise SandboxFalhou("build", f"docker build falhou ({codigo}): {saida[-1500:]}")
        self._imagem_construida = True

    def subir(self, porta: int = 8080, motor_banco: str = "nenhum", env: Optional[Dict[str, str]] = None,
              saude: str = "/", tentativas: int = 60, esperar_s: float = 1.0) -> str:
        """Cria a rede interna, sobe o banco (se o plano pede) e o sistema; espera ele responder. Devolve a URL interna do alvo."""
        codigo, saida = self.docker.executar("network", "create", "--internal", self.rede)
        if codigo != 0:
            raise SandboxFalhou("rede", f"não criou a rede interna: {saida[-500:]}")
        self._rede_criada = True
        ambiente = {"PORT": str(porta), "ASPNETCORE_URLS": f"http://0.0.0.0:{porta}", **(env or {})}
        if motor_banco in IMAGENS_BANCO:
            imagem_db, porta_db = IMAGENS_BANCO[motor_banco]
            senha = "sandbox-" + str(int(time.time()))
            self.emitir(f"[sandbox] subindo o banco {motor_banco}")
            codigo, saida = self.docker.executar("run", "-d", "--name", self.banco, "--network", self.rede, "--network-alias", "banco",
                                                 *_limites({"memoria": "512m"}), "-e", f"POSTGRES_PASSWORD={senha}", "-e", "POSTGRES_DB=app",
                                                 imagem_db, timeout=180)
            if codigo != 0:
                raise SandboxFalhou("banco", f"o banco não subiu: {saida[-500:]}")
            self._criados.append(self.banco)
            ambiente.setdefault("DATABASE_URL", f"postgresql://postgres:{senha}@banco:{porta_db}/app")
            self._esperar(lambda: self.docker.executar("exec", self.banco, "pg_isready", "-U", "postgres")[0] == 0, 60, 1.0, "o banco")
        elif motor_banco not in ("nenhum", ""):
            self.emitir(f"[sandbox] motor '{motor_banco}' sem imagem de sandbox: o sistema sobe sem banco")
        args = ["run", "-d", "--name", self.sut, "--network", self.rede, "--network-alias", "sut", *_limites(self.limites),
                *[x for k, v in sorted(ambiente.items()) for x in ("-e", f"{k}={v}")], self.imagem]
        codigo, saida = self.docker.executar(*args, timeout=180)
        if codigo != 0:
            raise SandboxFalhou("sut", f"o sistema não subiu: {saida[-500:]}")
        self._criados.append(self.sut)
        self.alvo = f"http://sut:{porta}"
        self.emitir(f"[sandbox] aguardando o sistema responder em {self.alvo}{saude}")
        if not self._esperar(lambda: self._responde(saude), tentativas, esperar_s, "o sistema"):
            _, logs = self.docker.executar("logs", "--tail", "40", self.sut)
            raise SandboxFalhou("sut", f"o sistema não respondeu em {tentativas}s. Últimas linhas: {logs[-1200:]}")
        return self.alvo

    def _esperar(self, condicao: Callable[[], bool], tentativas: int, intervalo: float, o_que: str) -> bool:
        for _ in range(tentativas):
            if condicao():
                return True
            time.sleep(intervalo)
        return False

    def _responde(self, caminho: str) -> bool:
        """O sistema está de pé se QUALQUER resposta HTTP volta (até um 404 prova que o servidor escuta)."""
        codigo, saida, _ = self.rodar_ferramenta(IMAGEM_PYTHON, ["python", "-c", SONDA_HTTP, f"{self.alvo}{caminho}"], timeout=30)
        ultima = (saida.strip().splitlines() or ["0"])[-1].strip()
        return codigo == 0 and ultima.isdigit() and int(ultima) > 0

    # ------------------------------------------------------------ ferramentas na rede do sandbox
    def rodar_ferramenta(self, imagem: str, comando: List[str], arquivos: Optional[Dict[str, bytes]] = None,
                         coletar: Optional[List[str]] = None, timeout: int = 300, limites: Optional[dict] = None,
                         ambiente: Optional[Dict[str, str]] = None) -> Tuple[int, str, Dict[str, bytes]]:
        """Roda UMA ferramenta como container na rede do sandbox: copia `arquivos` para dentro ({caminho no container: conteúdo}),
        executa, coleta `coletar` (caminhos no container) e remove o container. Devolve (código, saída, {caminho: conteúdo})."""
        nome = nome_seguro("sqt", f"{self.tarefa}-{int(time.time() * 1000) % 10_000_000}")
        codigo, saida = self.docker.executar("create", "--name", nome, "--network", self.rede, *_limites(limites),
                                             *[x for k, v in sorted((ambiente or {}).items()) for x in ("-e", f"{k}={v}")],
                                             imagem, *comando, timeout=300)
        if codigo != 0:
            return codigo, f"create falhou: {saida[-800:]}", {}
        coletados: Dict[str, bytes] = {}
        tmp = Path(tempfile.mkdtemp(prefix="sqt-"))
        try:
            for caminho, conteudo in (arquivos or {}).items():
                origem = tmp / "entrada" / caminho.lstrip("/")
                origem.parent.mkdir(parents=True, exist_ok=True)
                origem.write_bytes(conteudo)
                destino_dir = str(Path(caminho).parent).replace("\\", "/")
                c, s = self.docker.executar("cp", str(origem), f"{nome}:{destino_dir}/")
                if c != 0:
                    return c, f"cp (entrada) falhou: {s[-500:]}", {}
            codigo, saida = self.docker.executar("start", "-a", nome, timeout=timeout)
            for caminho in coletar or []:
                local = tmp / "saida" / Path(caminho).name
                local.parent.mkdir(parents=True, exist_ok=True)
                c, _ = self.docker.executar("cp", f"{nome}:{caminho}", str(local))
                if c == 0 and local.is_file():
                    coletados[caminho] = local.read_bytes()
            return codigo, saida, coletados
        finally:
            self.docker.executar("rm", "-f", nome)
            shutil.rmtree(tmp, ignore_errors=True)

    def estatisticas(self) -> Optional[dict]:
        """Uma amostra de CPU e memória do sistema (para o relatório de capacidade). None se o docker não responder."""
        codigo, saida = self.docker.executar("stats", "--no-stream", "--format", "{{.CPUPerc}}|{{.MemUsage}}|{{.MemPerc}}", self.sut)
        if codigo != 0 or "|" not in saida:
            return None
        cpu, mem, memp = (saida.strip().splitlines()[-1].split("|") + ["", "", ""])[:3]
        return {"cpu": cpu.strip(), "memoria": mem.strip(), "memoria_perc": memp.strip()}

    def logs_do_sistema(self, linhas: int = 60) -> str:
        return self.docker.executar("logs", "--tail", str(linhas), self.sut)[1]

    # ------------------------------------------------------------ desmontagem (sempre)
    def limpar(self) -> None:
        for nome in reversed(self._criados):
            self.docker.executar("rm", "-f", nome)
        if self._rede_criada:
            self.docker.executar("network", "rm", self.rede)
        if self._imagem_construida:
            self.docker.executar("image", "rm", "-f", self.imagem)
        self._criados, self._rede_criada, self._imagem_construida = [], False, False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.limpar()
        return False


def docker_disponivel(docker: Optional[Docker] = None) -> bool:
    """True se o docker responde (CLI instalada e daemon acessível). Sem isso a validação em execução não roda."""
    if docker is None and shutil.which(os.environ.get("DOCKER_BIN", "docker")) is None:
        return False
    codigo, saida = (docker or Docker()).executar("info", "--format", "{{.ServerVersion}}", timeout=20)
    return codigo == 0 and bool(saida.strip())

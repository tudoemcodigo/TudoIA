"""Estado e ações dos serviços: containers Docker (via compose) e processos do host."""
import logging
import os
import socket
import subprocess
from pathlib import Path

from .caminhos import comfyui_portable, pesos_ollama
from .envfile import ler_env

log = logging.getLogger(__name__)

DOCKER = ("litellm", "litellm-db", "cerebro", "searxng", "open-webui", "kokoro", "n8n", "keycloak", "keycloak-db")
HOST = {"ollama": 11434, "comfyui": 8188}
ACOES = {"start": ["up", "-d"], "stop": ["stop"], "restart": ["restart"]}

METADADOS = {
    "litellm": {"titulo": "LiteLLM Gateway", "desc": "Gateway unificado OpenAI-compatible, roteador kNN e quarentena", "porta": 4000, "url": "http://localhost:4000/ui"},
    "litellm-db": {"titulo": "LiteLLM Database", "desc": "PostgreSQL para métricas, chaves de API e contagem de tokens", "porta": 5433, "url": None},
    "cerebro": {"titulo": "Cérebro MCP", "desc": "Servidor MCP de memória persistente, vetores e indexação semântica", "porta": 8765, "url": "http://localhost:8765/saude"},
    "searxng": {"titulo": "SearXNG Metasearch", "desc": "Buscador de internet local privativo para agentes e Cérebro", "porta": 8080, "url": "http://localhost:8080"},
    "open-webui": {"titulo": "Open WebUI", "desc": "Interface de chat e agentes com suporte a Whisper e RAG", "porta": 3000, "url": "http://localhost:3000"},
    "kokoro": {"titulo": "Kokoro TTS", "desc": "Síntese de voz neural ultra-rápida em CPU (FastAPI)", "porta": 8880, "url": "http://localhost:8880/docs"},
    "n8n": {"titulo": "n8n Workflows", "desc": "Automação visual e orquestração de fluxos de IA", "porta": 5678, "url": "http://localhost:5678"},
    "keycloak": {"titulo": "Keycloak (login)", "desc": "Provedor de identidade OIDC do painel, do Cérebro e do n8n", "porta": 8180, "url": "http://localhost:8180"},
    "keycloak-db": {"titulo": "Keycloak Database", "desc": "PostgreSQL do Keycloak embutido", "porta": None, "url": None},
    "ollama": {"titulo": "Ollama Local LLMs", "desc": "Motor de inferência local para modelos GGUF acelerados em GPU", "porta": 11434, "url": "http://localhost:11434"},
    "comfyui": {"titulo": "ComfyUI Portable", "desc": "Estúdio nodal para geração e edição de imagens e vídeos (SDXL, FLUX, Wan e MiniMax)", "porta": 8188, "url": "http://localhost:8188"},
}


DETACHED_FLAGS = (
    subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
    if os.name == "nt"
    else 0
)


def porta_aberta(porta: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", porta)) == 0


class ServicosDocker:
    def __init__(self, raiz: Path):
        self.raiz = Path(raiz)

    @property
    def nomes(self) -> tuple[str, ...]:
        return DOCKER + tuple(HOST)

    def _compose(self, *args: str) -> subprocess.CompletedProcess:
        projeto = (ler_env(self.raiz / ".env").get("TUDOIA_COMPOSE_PROJETO") or "").strip() or "tudoia"
        base = ["docker", "compose", "-p", projeto, "-f", str(self.raiz / "runtime" / "docker-compose.yml"),
                "--env-file", str(self.raiz / ".env")]
        return subprocess.run(base + list(args), capture_output=True, text=True, timeout=300, check=False)

    def listar(self) -> list[dict]:
        try:
            r = subprocess.run(["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True,
                               timeout=10, check=False)
            rodando = set(r.stdout.split()) if r.returncode == 0 else set()
        except (OSError, subprocess.TimeoutExpired):
            rodando = set()

        saida = []
        for n in DOCKER:
            meta = METADADOS.get(n, {})
            saida.append({
                "nome": n,
                "titulo": meta.get("titulo", n),
                "descricao": meta.get("desc", ""),
                "porta": meta.get("porta"),
                "url": meta.get("url"),
                "tipo": "docker",
                "ativo": n in rodando
            })

        for nome, porta in HOST.items():
            meta = METADADOS.get(nome, {})
            saida.append({
                "nome": nome,
                "titulo": meta.get("titulo", nome),
                "descricao": meta.get("desc", ""),
                "porta": porta,
                "url": meta.get("url"),
                "tipo": "host",
                "ativo": porta_aberta(porta)
            })
        return saida

    def acao_todos(self, acao: str) -> None:
        if acao == "start":
            # 1. Inicia processos do host (Ollama e ComfyUI)
            if not porta_aberta(11434):
                try:
                    self._start_ollama()
                except Exception as e:
                    log.warning("não consegui iniciar o ollama (%s)", type(e).__name__)
            if not porta_aberta(8188):
                try:
                    self._start_comfyui()
                except Exception as e:
                    log.warning("não consegui iniciar o comfyui (%s)", type(e).__name__)
            # 2. Sobe containers Docker
            r = self._compose("up", "-d")
            if r.returncode != 0:
                raise RuntimeError((r.stderr or "falha ao iniciar stack docker").strip().splitlines()[-1][:300])
        elif acao == "stop":
            # 1. Encerra todos os serviços do host (Ollama e ComfyUI)
            for h in HOST:
                self._stop_host(h)
            # 2. Pausa os containers Docker
            r = self._compose("stop")
            if r.returncode != 0:
                raise RuntimeError((r.stderr or "falha ao pausar stack docker").strip().splitlines()[-1][:300])
        elif acao == "restart":
            # 1. Encerra e reinicia serviços do host (Ollama e ComfyUI)
            for h in HOST:
                self._stop_host(h)
            try:
                self._start_ollama()
            except Exception as e:
                log.warning("não consegui iniciar o ollama (%s)", type(e).__name__)
            try:
                self._start_comfyui()
            except Exception as e:
                log.warning("não consegui iniciar o comfyui (%s)", type(e).__name__)
            # 2. Reinicia os containers Docker
            r = self._compose("restart")
            if r.returncode != 0:
                raise RuntimeError((r.stderr or "falha ao reiniciar stack docker").strip().splitlines()[-1][:300])
        else:
            raise ValueError(f"ação global '{acao}' desconhecida (use start, stop ou restart)")

    def acao(self, nome: str, acao: str) -> None:
        if nome in DOCKER:
            if acao not in ACOES:
                raise ValueError(f"ação '{acao}' não suportada para container '{nome}'")
            r = self._compose(*ACOES[acao], nome)
            if r.returncode != 0:
                raise RuntimeError((r.stderr or "falha no docker compose").strip().splitlines()[-1][:300])
            return

        if nome in HOST:
            if acao == "start":
                if nome == "ollama":
                    self._start_ollama()
                elif nome == "comfyui":
                    self._start_comfyui()
            elif acao == "stop":
                self._stop_host(nome)
            elif acao == "restart":
                self._stop_host(nome)
                if nome == "ollama":
                    self._start_ollama()
                elif nome == "comfyui":
                    self._start_comfyui()
            else:
                raise ValueError(f"ação '{acao}' não suportada para '{nome}'")
            return

        raise ValueError(f"serviço '{nome}' desconhecido")

    def _start_ollama(self) -> None:
        env = os.environ.copy()
        env["OLLAMA_HOST"] = "127.0.0.1:11434"
        env["OLLAMA_MODELS"] = str(pesos_ollama(self.raiz))
        try:
            subprocess.Popen(
                ["ollama", "serve"],
                env=env,
                creationflags=DETACHED_FLAGS,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=(os.name != "nt"),
            )
        except OSError as e:
            raise RuntimeError(f"não foi possível iniciar ollama: {e}") from e

    def _start_comfyui(self) -> None:
        pasta = comfyui_portable(self.raiz)
        script = pasta / "run_nvidia_gpu.bat"
        if not script.is_file():
            raise RuntimeError(f"executável do ComfyUI não encontrado em {script}")
        log_dir = self.raiz / "dados" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "comfyui.log"
        exe_py = pasta / "python_embeded" / "python.exe"
        cmd = (
            [str(exe_py), "-s", str(pasta / "ComfyUI" / "main.py"), "--windows-standalone-build", "--disable-auto-launch"]
            if exe_py.is_file()
            else ["cmd.exe", "/c", str(script)]
        )
        with open(log_path, "a", encoding="utf-8") as log_f:
            subprocess.Popen(
                cmd,
                cwd=str(pasta),
                stdin=subprocess.DEVNULL,
                creationflags=DETACHED_FLAGS,
                stdout=log_f,
                stderr=subprocess.STDOUT,
            )

    def _stop_host(self, nome: str) -> None:
        porta = HOST.get(nome)
        if porta:
            cmd = f'Get-NetTCPConnection -LocalPort {porta} -ErrorAction SilentlyContinue | ForEach-Object {{ Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }}'
            subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, check=False)
        if nome == "ollama":
            subprocess.run(["taskkill", "/F", "/IM", "ollama.exe", "/T"], capture_output=True, check=False)
            subprocess.run(["taskkill", "/F", "/IM", "ollama_llama_server.exe", "/T"], capture_output=True, check=False)
        elif nome == "comfyui":
            # O caminho vai por variável de ambiente, nunca dentro do texto do comando: `$`, crase ou aspas numa pasta
            # virariam expansão do PowerShell. IndexOf compara texto puro (sem curinga, que -like e Escape tratam mal).
            cmd = ("$dir = $env:TUDOIA_COMFYUI_DIR; "
                   "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and "
                   "$_.CommandLine.IndexOf($dir, [StringComparison]::OrdinalIgnoreCase) -ge 0 } | "
                   "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }")
            env = {**os.environ, "TUDOIA_COMFYUI_DIR": str(comfyui_portable(self.raiz))}
            subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, check=False, env=env)

"""Opções que o usuário parametriza na tela e a validação delas.

Tudo que vira caminho, nome de projeto, URL ou linha de `.env` passa por aqui antes de qualquer ação: o instalador
roda comandos na máquina do usuário, então nenhuma opção chega ao motor sem validar.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field, fields
from pathlib import PureWindowsPath

# Componentes que o usuário liga ou desliga. O núcleo (painel, LiteLLM, Postgres) não é opcional.
COMPONENTES = {
    "cerebro": "Cérebro (memória e busca MCP) + SearXNG",
    "webui": "Open WebUI + Kokoro (voz)",
    "n8n": "n8n (automação)",
    "keycloak": "Keycloak embutido (login)",
    "ollama": "Ollama (LLMs locais e embeddings)",
    "comfyui": "ComfyUI portable (Estúdio de imagem e vídeo)",
}
PERFIS_COMPOSE = ("cerebro", "webui", "n8n", "keycloak")   # os componentes que são perfis do docker compose
PADRAO_COMPONENTES = ("cerebro", "webui", "n8n", "keycloak", "ollama")

# Chaves de provedor que a tela aceita (as mesmas do .env.example). Qualquer outro nome é recusado.
CHAVES_PROVEDORES = (
    "NVIDIA_NIM_API_KEY", "OPENROUTER_API_KEY", "GROQ_API_KEY", "GEMINI_API_KEY", "CLOUDFLARE_API_KEY",
    "CLOUDFLARE_ACCOUNT_ID", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY", "XAI_API_KEY", "HF_TOKEN",
)

PADRAO_PASTA = r"C:\TudoIA"
MAX_CAMINHO = 90          # o venv, o ComfyUI e o node_modules do n8n estouram o MAX_PATH do Windows além disso
RE_CAMINHO = re.compile(r"^[A-Za-z]:\\[\w .\-()\\]*$")   # \w inclui letras acentuadas; sem % $ ` ' ; & ^ ! " < > | ? *
RE_PROJETO = re.compile(r"^[a-z0-9][a-z0-9_-]{0,30}$")
RE_EMAIL = re.compile(r"^[A-Za-z0-9._%+\-]{1,64}@[A-Za-z0-9.\-]{1,190}\.[A-Za-z]{2,}$")
RE_FUSO = re.compile(r"^[A-Za-z_]+(/[A-Za-z0-9_+\-]+){0,2}$")
RE_REPO = re.compile(r"^[A-Za-z0-9._\-]{1,100}/[A-Za-z0-9._\-]{1,100}$")
RE_REF = re.compile(r"^[A-Za-z0-9._/\-]{1,100}$")
RE_USUARIO_KC = re.compile(r"^[A-Za-z0-9._@\-]{1,64}$")
PROIBIDAS_RAIZ = ("windows", "program files", "program files (x86)", "programdata")


@dataclass
class Opcoes:
    pasta_instalacao: str = PADRAO_PASTA
    pasta_dados: str = ""             # vazio = <instalação>\dados
    pasta_pesos_ollama: str = ""      # vazio = <instalação>\modelos\ollama\models
    pasta_comfyui: str = ""           # vazio = <instalação>\modelos\comfyui\ComfyUI_windows_portable
    projeto_compose: str = "tudoia"
    componentes: list[str] = field(default_factory=lambda: list(PADRAO_COMPONENTES))
    fonte_codigo: str = "embutido"    # "embutido" ou "github"
    github_repo: str = "tudoemcodigo/TudoIA"
    github_ref: str = "main"
    admin_email: str = ""
    fuso: str = "America/Sao_Paulo"
    keycloak_existente: bool = False  # True = usa o Keycloak que já roda em localhost:8180 (sem o embutido)
    keycloak_existente_admin: str = "admin"
    keycloak_existente_senha: str = ""        # nunca vai para disco nem para o log
    chaves_provedores: dict[str, str] = field(default_factory=dict)   # idem: só vai para o .env
    configurar_clientes_ia: bool = False      # roda o `sync` (grava regras/MCP no Claude Code, Cursor...)
    criar_atalhos: bool = True
    iniciar_ao_final: bool = True

    # ---- campos que nunca são gravados em estado.json
    SEGREDOS = ("keycloak_existente_senha", "chaves_provedores")

    def publico(self) -> dict:
        """Dicionário sem segredos, seguro para estado.json e para a tela de resumo."""
        d = asdict(self)
        d["chaves_provedores"] = sorted(d["chaves_provedores"])   # só os nomes
        d["keycloak_existente_senha"] = bool(self.keycloak_existente_senha)
        return d

    @classmethod
    def de_dict(cls, dados: dict) -> "Opcoes":
        """Cria a partir do JSON da tela. Campo desconhecido é erro: nada passa em silêncio."""
        conhecidos = {f.name for f in fields(cls)}
        extra = set(dados) - conhecidos
        if extra:
            raise ValueError(f"campo desconhecido: {', '.join(sorted(extra))}")
        return cls(**dados)

    # ---- caminhos efetivos
    @property
    def raiz(self) -> PureWindowsPath:
        return PureWindowsPath(self.pasta_instalacao)

    @property
    def dados(self) -> PureWindowsPath:
        return PureWindowsPath(self.pasta_dados) if self.pasta_dados.strip() else self.raiz / "dados"

    @property
    def pesos_ollama(self) -> PureWindowsPath:
        return PureWindowsPath(self.pasta_pesos_ollama) if self.pasta_pesos_ollama.strip() else self.raiz / "modelos" / "ollama" / "models"

    @property
    def comfyui(self) -> PureWindowsPath:
        if self.pasta_comfyui.strip():
            return PureWindowsPath(self.pasta_comfyui)
        return self.raiz / "modelos" / "comfyui" / "ComfyUI_windows_portable"

    @property
    def perfis(self) -> list[str]:
        """COMPOSE_PROFILES: os componentes marcados que são perfis do compose (o Keycloak existente não é perfil)."""
        return [p for p in PERFIS_COMPOSE if p in self.componentes and not (p == "keycloak" and self.keycloak_existente)]

    def usa(self, componente: str) -> bool:
        return componente in self.componentes


def _caminho_ok(valor: str, campo: str, erros: list[tuple[str, str]], obrigatorio: bool = True) -> None:
    v = valor.strip()
    if not v:
        if obrigatorio:
            erros.append((campo, "informe uma pasta"))
        return
    if not RE_CAMINHO.match(v):
        erros.append((campo, "use um caminho completo do Windows (ex.: C:\\TudoIA), sem os caracteres % $ ` ' ; & ^ ! \" < > | ? *"))
        return
    partes = [p for p in v.split("\\")[1:] if p]
    if any(p in (".", "..") or p != p.strip() or p.endswith(".") for p in partes):
        erros.append((campo, "nome de pasta inválido (sem '..', espaço ou ponto no fim)"))
        return
    if len(v) > MAX_CAMINHO:
        erros.append((campo, f"caminho longo demais ({len(v)} > {MAX_CAMINHO}): o Windows limita o tamanho dos caminhos"))
    if not partes:
        erros.append((campo, "escolha uma pasta, não a raiz do disco"))
    elif partes[0].lower() in PROIBIDAS_RAIZ:
        erros.append((campo, f"não instale dentro de '{partes[0]}': precisa de pasta que seu usuário possa escrever"))


def validar(o: Opcoes) -> list[tuple[str, str]]:
    """Lista de (campo, mensagem). Vazia = pode instalar."""
    erros: list[tuple[str, str]] = []
    _caminho_ok(o.pasta_instalacao, "pasta_instalacao", erros)
    _caminho_ok(o.pasta_dados, "pasta_dados", erros, obrigatorio=False)
    _caminho_ok(o.pasta_pesos_ollama, "pasta_pesos_ollama", erros, obrigatorio=False)
    _caminho_ok(o.pasta_comfyui, "pasta_comfyui", erros, obrigatorio=False)

    if not RE_PROJETO.match(o.projeto_compose):
        erros.append(("projeto_compose", "use minúsculas, números, - e _ (até 31 caracteres)"))
    desconhecidos = [c for c in o.componentes if c not in COMPONENTES]
    if desconhecidos or len(set(o.componentes)) != len(o.componentes):
        erros.append(("componentes", f"componente inválido ou repetido: {', '.join(desconhecidos) or 'repetido'}"))
    if o.fonte_codigo not in ("embutido", "github"):
        erros.append(("fonte_codigo", "escolha 'embutido' ou 'github'"))
    if o.fonte_codigo == "github":
        if not RE_REPO.match(o.github_repo):
            erros.append(("github_repo", "use o formato dono/repositório"))
        if not RE_REF.match(o.github_ref) or ".." in o.github_ref:
            erros.append(("github_ref", "branch ou tag inválida"))
    if not RE_FUSO.match(o.fuso):
        erros.append(("fuso", "fuso horário inválido (ex.: America/Sao_Paulo)"))

    usa_login = o.usa("keycloak") or o.keycloak_existente
    if usa_login and not RE_EMAIL.match(o.admin_email):
        erros.append(("admin_email", "e-mail inválido: ele vira o primeiro administrador do painel"))
    if o.keycloak_existente:
        if o.usa("keycloak"):
            erros.append(("keycloak_existente", "marque o Keycloak embutido OU o existente, não os dois"))
        if not RE_USUARIO_KC.match(o.keycloak_existente_admin):
            erros.append(("keycloak_existente_admin", "usuário inválido"))
        if not o.keycloak_existente_senha or "\n" in o.keycloak_existente_senha or "\r" in o.keycloak_existente_senha:
            erros.append(("keycloak_existente_senha", "informe a senha do admin do Keycloak (sem quebra de linha)"))
    if not usa_login:
        erros.append(("componentes", "o painel precisa de login: marque o Keycloak embutido ou use um existente"))

    for chave, valor in o.chaves_provedores.items():
        if chave not in CHAVES_PROVEDORES:
            erros.append(("chaves_provedores", f"chave não suportada: {chave}"))
        elif not isinstance(valor, str) or len(valor) > 512 or re.search(r"[\r\n\x00]", valor):
            erros.append(("chaves_provedores", f"valor inválido em {chave}"))
    return erros

"""SquadTI: o painel inicia, acompanha e aprova as tarefas da Squad pela API local do orquestrador.

O painel não executa a Squad nem lê o checkpoint dela: só repassa pedidos validados a `http://127.0.0.1:<porta>` com o token
de `TUDOIA_SQUADTI_TOKEN` (no `.env`). Sem token, ou com a API fora do ar, as rotas respondem 503 (falha fechado).
Papéis: leitor vê (tarefas, mensagens, auditoria, proveniência, log, configuração dos agentes); operador inicia, responde, fala com o
CHEFE, continua tarefa escalada e aprova (inclusive o release, que só gera notas: nada é commitado nem publicado); só o admin salva a
configuração dos agentes (modelo, temperatura, orçamento), porque ela decide o que pode sair da máquina e quanto a Squad gasta.
"""
import re
from typing import Literal
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Path, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..ambiente import Contexto
from ..envfile import ler_env
from ..erros import ErroApi

URL_PADRAO = "http://127.0.0.1:8790"
HOSTS_LOCAIS = {"127.0.0.1", "localhost"}
TIMEOUT_S = 15.0
TIMEOUT_MENSAGEM_S = 120.0  # o CHEFE chama o modelo antes de responder: só a rota de mensagem espera tanto
TRANSPORTE = None  # seam dos testes: httpx.MockTransport (o conftest bloqueia a rede real)
PERFIS = ("local-estrito", "local", "hibrido", "nuvem", "auto")  # `max` (pago) não é oferecido pelo painel
ID_TAREFA = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"
NOME_CHAVE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
MAX_MENSAGEM = 4000  # mesmo teto da API da Squad


class Orcamento(BaseModel):
    """Teto de consumo. Eixo ausente = não muda; `null` = sem limite. As faixas espelham as de `agentes.py` da Squad (que revalida)."""
    model_config = ConfigDict(extra="forbid")
    tokens: int | None = Field(default=None, ge=1_000, le=50_000_000)
    tempo_s: int | None = Field(default=None, ge=60, le=86_400)
    chamadas: int | None = Field(default=None, ge=1, le=10_000)


class NovaTarefa(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tarefa: str = Field(pattern=ID_TAREFA)
    briefing: str = Field(min_length=1, max_length=20000)
    perfil: str = "local-estrito"
    consentimento_nuvem: bool = False
    stack: Literal["dotnet", "python"] | None = None  # ausente = o CHEFE decide
    orcamento: Orcamento | None = None


class Mensagem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    texto: str = Field(min_length=1, max_length=MAX_MENSAGEM)


class Continuar(BaseModel):
    model_config = ConfigDict(extra="forbid")
    orcamento: Orcamento | None = None


class AgenteCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")
    perfil: str | None = None  # None = o da tarefa
    temperatura: float = Field(default=0.1, ge=0.0, le=1.5)
    max_tokens: int | None = Field(default=None, ge=256, le=32_000)


class Revisao(BaseModel):
    model_config = ConfigDict(extra="forbid")
    modo: Literal["simples", "dupla"] = "simples"


class ConfigAgentes(BaseModel):
    """Configuração dos agentes. Aqui só o formato é validado; nomes de agente, faixas e semântica a Squad valida de novo.
    `validacao` (validação em execução: modo, carga, SLO, macaco de UI) segue como objeto raso e limitado."""
    model_config = ConfigDict(extra="forbid")
    agentes: dict[str, AgenteCfg] | None = None
    revisao: Revisao | None = None
    validacao: dict | None = None
    orcamento: Orcamento | None = None

    @field_validator("agentes")
    @classmethod
    def _agentes(cls, v):
        if v is None:
            return v
        if len(v) > 32 or not all(NOME_CHAVE.match(k) for k in v):
            raise ValueError("nome de agente inválido ou agentes demais")
        for cfg in v.values():
            if cfg.perfil is not None and cfg.perfil not in PERFIS:
                raise ValueError(f"perfil deve ser um de {', '.join(PERFIS)}")
        return v

    @field_validator("validacao")
    @classmethod
    def _validacao(cls, v):
        def folha(x):
            return x is None or isinstance(x, (bool, int, float)) or (isinstance(x, str) and len(x) <= 64)

        def chave_ok(k):
            return isinstance(k, str) and NOME_CHAVE.match(k) is not None
        if v is None:
            return v
        ok = len(v) <= 16 and all(chave_ok(k) and (folha(x) or (
            isinstance(x, dict) and len(x) <= 16 and all(chave_ok(k2) and folha(x2) for k2, x2 in x.items())))
            for k, x in v.items())
        if not ok:
            raise ValueError("validacao deve ser um objeto raso (até 2 níveis, 16 chaves) com valores simples")
        return v


class Resposta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resposta: str = Field(min_length=1, max_length=20000)


def configuracao(raiz) -> tuple[str, str]:
    """(url, token) da API da Squad. Falha fechado: sem token ou com URL fora do loopback, nada é chamado."""
    env = ler_env(raiz / ".env")
    token = (env.get("TUDOIA_SQUADTI_TOKEN") or "").strip()
    if len(token) < 32:
        raise ErroApi(503, "indisponivel", "SquadTI não configurado: defina TUDOIA_SQUADTI_TOKEN (32+ caracteres) no .env")
    url = (env.get("TUDOIA_SQUADTI_URL") or URL_PADRAO).strip().rstrip("/")
    partes = urlparse(url)
    if partes.scheme != "http" or partes.hostname not in HOSTS_LOCAIS:
        raise ErroApi(503, "indisponivel", "TUDOIA_SQUADTI_URL deve ser http://127.0.0.1 ou http://localhost")
    return url, token


def chamar(raiz, metodo: str, caminho: str, json: dict | None = None, params: dict | None = None,
           timeout: float = TIMEOUT_S) -> dict:
    url, token = configuracao(raiz)
    try:
        with httpx.Client(timeout=timeout, transport=TRANSPORTE) as cliente:
            r = cliente.request(metodo, f"{url}{caminho}", json=json, params=params,
                                headers={"Authorization": f"Bearer {token}"})
    except httpx.HTTPError as e:
        raise ErroApi(503, "indisponivel", "a API da SquadTI não responde: ela está no ar? (Serviços → SquadTI)") from e
    try:
        corpo = r.json()
    except ValueError:
        corpo = {}
    if r.status_code >= 400:
        erro = corpo.get("erro") if isinstance(corpo, dict) else None
        codigo = (erro or {}).get("codigo") or "falha_squadti"
        mensagem = (erro or {}).get("mensagem") or f"a SquadTI respondeu {r.status_code}"
        if r.status_code == 401:  # token do painel diferente do da API: é configuração, não erro do usuário
            raise ErroApi(503, "indisponivel", "a SquadTI recusou o token: TUDOIA_SQUADTI_TOKEN difere do da API")
        if r.status_code >= 500:
            raise ErroApi(503, "indisponivel", "a SquadTI falhou ao processar o pedido")
        raise ErroApi(r.status_code, str(codigo), str(mensagem)[:500])
    return corpo


def criar_router(ctx: Contexto) -> APIRouter:
    router = APIRouter()
    raiz = ctx.raiz
    tarefa_path = Path(pattern=ID_TAREFA)

    @router.get("/api/squadti/estado")
    def estado():
        env = ler_env(raiz / ".env")
        configurado = len((env.get("TUDOIA_SQUADTI_TOKEN") or "").strip()) >= 32
        no_ar = False
        if configurado:
            try:
                url, _ = configuracao(raiz)
                with httpx.Client(timeout=2.0, transport=TRANSPORTE) as cliente:
                    no_ar = cliente.get(f"{url}/saude").status_code == 200
            except (httpx.HTTPError, ErroApi):
                no_ar = False
        return {"configurado": configurado, "no_ar": no_ar, "perfis": list(PERFIS)}

    @router.get("/api/squadti/tarefas")
    def listar():
        return chamar(raiz, "GET", "/api/tarefas")

    @router.get("/api/squadti/tarefas/{tarefa}")
    def detalhe(tarefa: str = tarefa_path):
        return chamar(raiz, "GET", f"/api/tarefas/{tarefa}")

    @router.get("/api/squadti/tarefas/{tarefa}/arquivo")
    def arquivo(tarefa: str = tarefa_path, caminho: str = Query(min_length=1, max_length=300)):
        return chamar(raiz, "GET", f"/api/tarefas/{tarefa}/arquivo", params={"caminho": caminho})

    @router.post("/api/squadti/tarefas", status_code=202)
    def iniciar(corpo: NovaTarefa):
        if corpo.perfil not in PERFIS:
            raise ErroApi(422, "validacao", f"perfil deve ser um de {', '.join(PERFIS)}", campo="perfil")
        if corpo.perfil != "local-estrito" and not corpo.consentimento_nuvem:  # `local` também: o gateway pode reenviar à nuvem
            raise ErroApi(422, "consentimento_nuvem",
                          "este perfil pode enviar código e esquema do projeto para a nuvem: confirme o consentimento",
                          campo="consentimento_nuvem")
        dados = corpo.model_dump(exclude={"stack", "orcamento"})
        if corpo.stack is not None:
            dados["stack"] = corpo.stack
        if corpo.orcamento is not None:
            dados["orcamento"] = corpo.orcamento.model_dump(exclude_unset=True)
        return chamar(raiz, "POST", "/api/tarefas", json=dados)

    @router.post("/api/squadti/tarefas/{tarefa}/responder", status_code=202)
    def responder(corpo: Resposta, tarefa: str = tarefa_path):
        return chamar(raiz, "POST", f"/api/tarefas/{tarefa}/responder", json=corpo.model_dump())

    @router.post("/api/squadti/tarefas/{tarefa}/aprovar", status_code=202)
    def aprovar(tarefa: str = tarefa_path):
        return chamar(raiz, "POST", f"/api/tarefas/{tarefa}/aprovar", json={})

    @router.post("/api/squadti/tarefas/{tarefa}/aprovar-release", status_code=202)
    def aprovar_release(tarefa: str = tarefa_path):
        return chamar(raiz, "POST", f"/api/tarefas/{tarefa}/aprovar-release", json={})

    # ---- v2: configuração dos agentes, CHEFE, auditoria, proveniência, log ao vivo e retomada
    @router.get("/api/squadti/agentes")
    def agentes_ler():
        return chamar(raiz, "GET", "/api/agentes")

    @router.post("/api/squadti/agentes")  # só admin: autenticacao.PREFIXOS_ESCRITA_SO_ADMIN
    def agentes_salvar(corpo: ConfigAgentes):
        return chamar(raiz, "POST", "/api/agentes", json=corpo.model_dump(exclude_unset=True))

    @router.get("/api/squadti/tarefas/{tarefa}/mensagens")
    def mensagens(tarefa: str = tarefa_path):
        return chamar(raiz, "GET", f"/api/tarefas/{tarefa}/mensagens")

    @router.post("/api/squadti/tarefas/{tarefa}/mensagem", status_code=202)
    def mensagem(corpo: Mensagem, tarefa: str = tarefa_path):
        return chamar(raiz, "POST", f"/api/tarefas/{tarefa}/mensagem", json=corpo.model_dump(), timeout=TIMEOUT_MENSAGEM_S)

    @router.get("/api/squadti/tarefas/{tarefa}/auditoria")
    def auditoria(tarefa: str = tarefa_path):
        return chamar(raiz, "GET", f"/api/tarefas/{tarefa}/auditoria")

    @router.get("/api/squadti/tarefas/{tarefa}/proveniencia")
    def proveniencia(tarefa: str = tarefa_path):
        return chamar(raiz, "GET", f"/api/tarefas/{tarefa}/proveniencia")

    @router.get("/api/squadti/tarefas/{tarefa}/log")
    def log(tarefa: str = tarefa_path, desde: int = Query(default=0, ge=0, le=1_000_000)):
        return chamar(raiz, "GET", f"/api/tarefas/{tarefa}/log", params={"desde": desde})

    @router.post("/api/squadti/tarefas/{tarefa}/continuar", status_code=202)
    def continuar(corpo: Continuar, tarefa: str = tarefa_path):
        dados = {"orcamento": corpo.orcamento.model_dump(exclude_unset=True)} if corpo.orcamento else {}
        return chamar(raiz, "POST", f"/api/tarefas/{tarefa}/continuar", json=dados)

    return router

"""SquadTI: o painel inicia, acompanha e aprova as tarefas da Squad pela API local do orquestrador.

O painel não executa a Squad nem lê o checkpoint dela: só repassa pedidos validados a `http://127.0.0.1:<porta>` com o token
de `TUDOIA_SQUADTI_TOKEN` (no `.env`). Sem token, ou com a API fora do ar, as rotas respondem 503 (falha fechado).
Papéis: leitor vê; operador inicia, responde e aprova (inclusive o release, que só gera notas: nada é commitado nem publicado).
"""
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Path, Query
from pydantic import BaseModel, ConfigDict, Field

from ..ambiente import Contexto
from ..envfile import ler_env
from ..erros import ErroApi

URL_PADRAO = "http://127.0.0.1:8790"
HOSTS_LOCAIS = {"127.0.0.1", "localhost"}
TIMEOUT_S = 15.0
TRANSPORTE = None  # seam dos testes: httpx.MockTransport (o conftest bloqueia a rede real)
PERFIS = ("local-estrito", "local", "hibrido", "nuvem")  # `max` (pago) não é oferecido pelo painel
ID_TAREFA = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"


class NovaTarefa(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tarefa: str = Field(pattern=ID_TAREFA)
    briefing: str = Field(min_length=1, max_length=20000)
    perfil: str = "local-estrito"
    consentimento_nuvem: bool = False


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


def chamar(raiz, metodo: str, caminho: str, json: dict | None = None, params: dict | None = None) -> dict:
    url, token = configuracao(raiz)
    try:
        with httpx.Client(timeout=TIMEOUT_S, transport=TRANSPORTE) as cliente:
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
        return chamar(raiz, "POST", "/api/tarefas", json=corpo.model_dump())

    @router.post("/api/squadti/tarefas/{tarefa}/responder", status_code=202)
    def responder(corpo: Resposta, tarefa: str = tarefa_path):
        return chamar(raiz, "POST", f"/api/tarefas/{tarefa}/responder", json=corpo.model_dump())

    @router.post("/api/squadti/tarefas/{tarefa}/aprovar", status_code=202)
    def aprovar(tarefa: str = tarefa_path):
        return chamar(raiz, "POST", f"/api/tarefas/{tarefa}/aprovar", json={})

    @router.post("/api/squadti/tarefas/{tarefa}/aprovar-release", status_code=202)
    def aprovar_release(tarefa: str = tarefa_path):
        return chamar(raiz, "POST", f"/api/tarefas/{tarefa}/aprovar-release", json={})

    return router

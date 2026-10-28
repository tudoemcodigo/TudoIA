"""Guarda da API /api e da SPA /app: Host, Origin, Sec-Fetch-Site, tipo de conteúdo e tamanho do corpo.

Ameaça: uma página maliciosa aberta no navegador do usuário (CSRF) ou um domínio que passa a resolver para
127.0.0.1 (DNS rebinding). Regras, nesta ordem:
1. Host exato: 127.0.0.1:<porta> ou localhost:<porta>, em TODA requisição a /api, /app e /auth (inclusive GET e SSE).
2. Métodos que mudam algo (POST/PUT/PATCH/DELETE) em /api:
   - Origin, se presente, igual a http://127.0.0.1:<porta> ou http://localhost:<porta> ("null" é recusado);
   - sem Origin, Referer (se presente) também precisa ser local;
   - Sec-Fetch-Site, se presente, só "same-origin" ou "none";
   - POST/PUT/PATCH exigem Content-Type: application/json (mesmo sem corpo: envie {}); DELETE com corpo também;
   - corpo de até 10 MB (upload do Estúdio: 140 MB), contado nos bytes recebidos (vale para corpo chunked).
3. Respostas de /api: Cache-Control: no-store, nosniff, no-referrer, CORP same-origin, X-Frame-Options DENY.
   Respostas de /app: as mesmas proteções e a CSP abaixo (sem origem remota nenhuma).
Exceção inesperada numa rota /api vira 500 no modelo de erro, só com o tipo da exceção (nunca a mensagem).
Não há CORS: a SPA é servida da mesma origem.
"""
import json
import logging
import uuid
from urllib.parse import urlsplit

from starlette.datastructures import Headers, MutableHeaders
from starlette.exceptions import HTTPException as StarletteHTTPException

from .contexto import porta_do_painel
from .erros import corpo_erro

log = logging.getLogger(__name__)

METODOS_SEGUROS = {"GET", "HEAD", "OPTIONS"}
SEC_FETCH_PERMITIDOS = {"same-origin", "none"}
LIMITE_CORPO = 10 * 1024 * 1024
# Upload do Estúdio vai em base64 dentro do JSON: 100 MB binários viram ~133 MB de corpo.
LIMITES_POR_ROTA = {"/api/estudio/upload": 140 * 1024 * 1024}

CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
       "font-src 'self' data:; connect-src 'self'; worker-src 'self' blob:; manifest-src 'self'; object-src 'none'; "
       "base-uri 'none'; frame-ancestors 'none'; form-action 'self'")

CABECALHOS_COMUNS = {
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
    "x-frame-options": "DENY",
    "cross-origin-resource-policy": "same-origin",
}
CABECALHOS_API = {**CABECALHOS_COMUNS, "cache-control": "no-store"}
CABECALHOS_SPA = {**CABECALHOS_COMUNS, "content-security-policy": CSP, "cross-origin-opener-policy": "same-origin"}


def hosts_permitidos(porta: int) -> set[str]:
    return {f"127.0.0.1:{porta}", f"localhost:{porta}"}


def origem_local(valor: str, porta: int) -> bool:
    """Esquema, host e porta exatos (startswith deixaria passar :31000 ou 127.0.0.1.mal.example)."""
    try:
        u = urlsplit(valor)
        return u.scheme == "http" and (u.hostname or "").lower() in ("127.0.0.1", "localhost") and u.port == porta
    except ValueError:
        return False


def _tipo_json(valor: str | None) -> bool:
    if not valor:
        return False
    base = valor.split(";", 1)[0].strip().lower()
    return base == "application/json"


def checar(metodo: str, headers: Headers, eh_api: bool, porta: int, caminho: str = "") -> tuple[int, str, str] | None:
    """None se passa; senão (status, codigo, mensagem)."""
    host = (headers.get("host") or "").lower()
    if host not in hosts_permitidos(porta):
        return 403, "host_recusado", f"host não permitido: use http://127.0.0.1:{porta}"
    if not eh_api or metodo in METODOS_SEGUROS:
        return None
    origem = headers.get("origin")
    if origem is not None and not origem_local(origem, porta):
        return 403, "origem_recusada", "origem não permitida: só o próprio painel pode mudar algo"
    referer = headers.get("referer")
    if origem is None and referer and not origem_local(referer, porta):
        return 403, "origem_recusada", "origem não permitida: só o próprio painel pode mudar algo"
    site = headers.get("sec-fetch-site")
    if site is not None and site.lower() not in SEC_FETCH_PERMITIDOS:
        return 403, "origem_recusada", f"pedido entre sites recusado (Sec-Fetch-Site: {site[:20]})"
    try:
        tamanho = int(headers.get("content-length") or 0)
    except ValueError:
        return 400, "requisicao_invalida", "Content-Length inválido"
    limite = LIMITES_POR_ROTA.get(caminho, LIMITE_CORPO)
    if tamanho > limite:
        return 413, "corpo_grande_demais", f"corpo maior que {limite // (1024 * 1024)} MB"
    tem_corpo = tamanho > 0 or "transfer-encoding" in headers
    if (metodo in ("POST", "PUT", "PATCH") or tem_corpo) and not _tipo_json(headers.get("content-type")):
        return 415, "tipo_de_conteudo", "envie o corpo como JSON (Content-Type: application/json; sem corpo, envie {})"
    return None


class GuardaApi:
    """Middleware ASGI puro (não bufferiza: o SSE passa direto)."""

    def __init__(self, app, porta: int | None = None):
        self.app = app
        self.porta = porta

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        caminho = scope.get("path", "")
        eh_api = caminho == "/api" or caminho.startswith("/api/")
        eh_spa = caminho == "/app" or caminho.startswith("/app/")
        # /auth: só a regra de Host (login e callback vão e voltam do Keycloak; o logout tem checagem de origem própria)
        eh_auth = caminho.startswith("/auth/")
        if not (eh_api or eh_spa or eh_auth):
            return await self.app(scope, receive, send)
        porta = self.porta or porta_do_painel()
        # Id do pedido: volta no cabeçalho X-Request-ID e liga a resposta ao log e à auditoria.
        scope["tudoia_id"] = id_pedido = uuid.uuid4().hex[:16]
        recusa = checar(scope["method"], Headers(scope=scope), eh_api, porta, caminho)
        extras = CABECALHOS_API if eh_api else (CABECALHOS_SPA if eh_spa else CABECALHOS_COMUNS)
        extras = {**extras, "x-request-id": id_pedido}
        if recusa:
            status, codigo, mensagem = recusa
            return await _enviar_json(send, status, corpo_erro(codigo, mensagem), extras)
        iniciou = False

        async def enviar(msg):
            nonlocal iniciou
            if msg["type"] == "http.response.start":
                iniciou = True
                h = MutableHeaders(scope=msg)
                for k, v in extras.items():
                    if k == "cache-control" and eh_api:
                        h[k] = v   # /api: sempre no-store (segredos mascarados e telemetria)
                    elif k not in h:
                        h[k] = v
            await send(msg)

        if not eh_api:
            return await self.app(scope, receive, enviar)
        try:
            await self.app(scope, _receive_limitado(receive, LIMITES_POR_ROTA.get(caminho, LIMITE_CORPO)), enviar)
        except Exception as e:   # noqa: BLE001 — a API nunca devolve o traceback nem a mensagem crua
            # Traceback só no log do servidor (com o id, para achar o pedido); o cliente recebe o tipo e o id.
            log.warning("Falha em %s %s [%s]: %s", scope["method"], caminho, id_pedido, type(e).__name__, exc_info=True)
            if not iniciou:
                await _enviar_json(send, 500, corpo_erro("falha_interna", f"falha interna do painel ({type(e).__name__}, "
                                                         f"pedido {id_pedido})"), extras)


def _receive_limitado(receive, limite: int):
    """Conta os bytes que chegam de fato. O Content-Length só vale quando existe: corpo chunked (sem ele) ou com
    Content-Length menor que o real passava sem limite e enchia a memória. HTTPException atravessa o parser de corpo
    do FastAPI (outra exceção vira 400 genérico) e sai como 413 no modelo de erro."""
    recebido = 0

    async def receber():
        nonlocal recebido
        msg = await receive()
        if msg["type"] == "http.request":
            recebido += len(msg.get("body", b""))
            if recebido > limite:
                raise StarletteHTTPException(413, f"corpo maior que {limite // (1024 * 1024)} MB")
        return msg
    return receber


async def _enviar_json(send, status: int, corpo: dict, cabecalhos: dict) -> None:
    dados = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
    h = [(b"content-type", b"application/json"), (b"content-length", str(len(dados)).encode())]
    h += [(k.encode(), v.encode()) for k, v in cabecalhos.items()]
    await send({"type": "http.response.start", "status": status, "headers": h})
    await send({"type": "http.response.body", "body": dados})

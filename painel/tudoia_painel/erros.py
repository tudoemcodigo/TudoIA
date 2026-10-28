"""Modelo único de erro da API: {"erro": {"codigo", "mensagem", "campo"?, "detalhes"?}} em pt-BR.

Os tratadores só valem para caminhos /api/: o painel clássico continua com as respostas padrão do FastAPI."""
from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

CODIGOS_HTTP = {
    400: "requisicao_invalida", 401: "nao_autorizado", 403: "proibido", 404: "nao_encontrado",
    405: "metodo_nao_permitido", 409: "conflito", 413: "corpo_grande_demais", 415: "tipo_de_conteudo",
422: "validacao", 429: "ocupado", 500: "falha_interna", 503: "indisponivel",
}
MENSAGENS_HTTP = {
    404: "recurso não encontrado", 405: "método não permitido neste endereço", 500: "falha interna do painel",
}


class ErroApi(Exception):
    def __init__(self, status: int, codigo: str, mensagem: str, campo: str | None = None,
                 detalhes: list[dict] | None = None, extras: dict | None = None):
        super().__init__(mensagem)
        self.status, self.codigo, self.mensagem, self.campo, self.detalhes = status, codigo, mensagem, campo, detalhes
        self.extras = extras


def corpo_erro(codigo: str, mensagem: str, campo: str | None = None, detalhes: list[dict] | None = None,
               extras: dict | None = None) -> dict:
    erro: dict = {"codigo": codigo, "mensagem": mensagem}
    if campo:
        erro["campo"] = campo
    if detalhes:
        erro["detalhes"] = detalhes
    if extras:
        erro["extras"] = extras   # contexto legível por máquina (ex.: {"servico_offline": "comfyui"})
    return {"erro": erro}


def resposta_erro(status: int, codigo: str, mensagem: str, campo: str | None = None,
                  detalhes: list[dict] | None = None, headers: dict | None = None,
                  extras: dict | None = None) -> JSONResponse:
    h = {"Cache-Control": "no-store"}
    h.update(headers or {})
    return JSONResponse(corpo_erro(codigo, mensagem, campo, detalhes, extras), status_code=status, headers=h)


def _campo(loc) -> str:
    """('body', 'ordem', 'tudoia-nuvem', 2) → 'ordem.tudoia-nuvem[2]'; ('query', 'periodo') → 'periodo'."""
    partes = [p for p in loc if p not in ("body", "query", "path", "header")]
    texto = ""
    for p in partes:
        if isinstance(p, int):
            texto += f"[{p}]"
        else:
            texto += ("." if texto else "") + str(p)
    return texto or "corpo"


_TRADUCOES = {
    "missing": "campo obrigatório", "extra_forbidden": "campo desconhecido", "string_too_long": "texto longo demais",
    "string_too_short": "texto curto demais", "int_parsing": "precisa ser um número inteiro",
    "float_parsing": "precisa ser um número", "bool_parsing": "precisa ser verdadeiro ou falso",
    "greater_than_equal": "valor abaixo do mínimo", "less_than_equal": "valor acima do máximo",
    "greater_than": "valor abaixo do mínimo", "less_than": "valor acima do máximo",
    "literal_error": "valor fora da lista permitida", "json_invalid": "JSON inválido", "dict_type": "precisa ser um objeto",
    "list_type": "precisa ser uma lista", "string_type": "precisa ser texto", "too_short": "lista curta demais",
    "too_long": "lista longa demais", "string_pattern_mismatch": "formato inválido",
    "model_attributes_type": "precisa ser um objeto JSON",
}


def _mensagem(e: dict) -> str:
    tipo = e.get("type", "")
    if tipo == "value_error":   # mensagens dos nossos validadores (já em pt-BR), sem o prefixo do Pydantic
        return str(e.get("msg", "")).removeprefix("Value error, ")
    base = _TRADUCOES.get(tipo)
    ctx = e.get("ctx") or {}
    if base and tipo in ("greater_than_equal", "greater_than"):
        return f"{base} ({ctx.get('ge', ctx.get('gt'))})"
    if base and tipo in ("less_than_equal", "less_than"):
        return f"{base} ({ctx.get('le', ctx.get('lt'))})"
    if base and tipo == "literal_error":
        return f"{base}: {ctx.get('expected', '')}".rstrip(": ")
    if base and tipo in ("string_too_long", "too_long"):
        return f"{base} (máximo {ctx.get('max_length')})"
    return base or str(e.get("msg", "valor inválido"))


def detalhes_de_validacao(erros: list[dict]) -> list[dict]:
    return [{"campo": _campo(e.get("loc", ())), "mensagem": _mensagem(e)} for e in erros]


def _eh_api(request: Request) -> bool:
    return request.url.path.startswith("/api/")


def instalar_tratadores(app: FastAPI) -> None:
    @app.exception_handler(ErroApi)
    async def _erro_api(request: Request, exc: ErroApi):
        return resposta_erro(exc.status, exc.codigo, exc.mensagem, exc.campo, exc.detalhes, extras=exc.extras)

    @app.exception_handler(RequestValidationError)
    async def _validacao(request: Request, exc: RequestValidationError):
        if not _eh_api(request):
            return await request_validation_exception_handler(request, exc)
        detalhes = detalhes_de_validacao(list(exc.errors()))
        primeiro = detalhes[0] if detalhes else {"campo": "corpo", "mensagem": "valor inválido"}
        return resposta_erro(422, "validacao", f"{primeiro['campo']}: {primeiro['mensagem']}", primeiro["campo"], detalhes)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        if not _eh_api(request):
            return await http_exception_handler(request, exc)
        codigo = CODIGOS_HTTP.get(exc.status_code, "erro")
        detalhe = exc.detail if isinstance(exc.detail, str) and exc.detail and exc.detail not in (
            "Not Found", "Method Not Allowed", "Internal Server Error") else MENSAGENS_HTTP.get(exc.status_code, "erro")
        return resposta_erro(exc.status_code, codigo, detalhe, headers=getattr(exc, "headers", None))
    # exceção inesperada em /api: tratada na GuardaApi (seguranca.py), que devolve 500 só com o tipo da exceção


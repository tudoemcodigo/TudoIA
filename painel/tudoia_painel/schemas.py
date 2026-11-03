"""Modelos de entrada da API (Pydantic). Todos recusam campo desconhecido, salvo exceção comentada."""
import re
from typing import Annotated, Any
from urllib.parse import urlsplit

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

class Valor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    valor: str = Field(max_length=4096)


class Ativo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ativo: bool


class NovaRegra(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=2, max_length=64)
    conteudo: str = Field(min_length=5, max_length=65536)
    ativo: bool = True


class NovaSkill(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=2, max_length=64)
    conteudo: str = Field(min_length=5, max_length=65536)
    ativo: bool = True


class ImportarSkill(BaseModel):
    model_config = ConfigDict(extra="forbid")
    comando: str | None = Field(default=None, max_length=1024)
    repo_url: str | None = Field(default=None, max_length=512)
    skill_nome: str | None = Field(default=None, max_length=64)
    ativo: bool = True


class NovoMcp(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=2, max_length=64)
    config: dict[str, Any]
    ativo: bool = True


class EditarConteudoGovernanca(BaseModel):
    model_config = ConfigDict(extra="forbid")
    conteudo: str = Field(min_length=1, max_length=1048576)


class NovaInstanciaGovernanca(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=2, max_length=64)
    cliente: str = Field(min_length=2, max_length=32)
    nome: str = Field(min_length=1, max_length=128)
    caminho: str = Field(min_length=1, max_length=512)
    config_json: str | None = Field(default=None, max_length=512)
    ativo: bool = True


class EditarInstanciaGovernanca(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nome: str | None = Field(default=None, max_length=128)
    caminho: str | None = Field(default=None, max_length=512)
    config_json: str | None = Field(default=None, max_length=512)
    ativo: bool | None = None


class TesteRoteador(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mensagem: str = Field(min_length=1, max_length=4000)
    modelo: str = Field(default="tudoia-auto", max_length=64)


class TesteModelo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    modelo: str = Field(min_length=1, max_length=256)
    tipo: str = Field(default="auto", max_length=32)


RE_API_BASE_ENV = re.compile(r"^os\.environ/[A-Z][A-Z0-9_]{0,63}$")


def url_http(valor: str) -> str:
    """URL http(s) com host, ou "" para limpar. O painel usa esses valores como link (href): `javascript:` e afins
    não podem entrar no catálogo. Espaço e caractere de controle também não (quebrariam o link e o YAML)."""
    valor = valor.strip()
    if not valor:
        return ""
    if any(c.isspace() or ord(c) < 32 for c in valor):
        raise ValueError("URL não pode ter espaço nem caractere de controle")
    partes = urlsplit(valor)
    if partes.scheme not in ("http", "https") or not partes.hostname:
        raise ValueError("precisa ser uma URL http:// ou https://")
    return valor


def api_base_valida(valor: str) -> str:
    """api_base é URL http(s) ou referência `os.environ/NOME` (o LiteLLM resolve a variável do .env)."""
    if RE_API_BASE_ENV.match(valor.strip()):
        return valor.strip()
    try:
        return url_http(valor)
    except ValueError:
        raise ValueError("precisa ser uma URL http(s) ou os.environ/NOME_DA_VARIAVEL") from None


UrlHttp = Annotated[str, Field(max_length=512), AfterValidator(url_http)]
ApiBase = Annotated[str, Field(max_length=512), AfterValidator(api_base_valida)]


class CorpoNovoProvedor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=64)
    nome: str = Field(min_length=1, max_length=128)
    tier: str = Field(pattern="^(FREE|PAID)$")
    chave: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    valor_chave: str | None = None
    site_chave: UrlHttp | None = None
    site_limites: UrlHttp | None = None
    api_base: ApiBase | None = None
    url_modelos: UrlHttp | None = None
    fonte_limites: str | None = None
    limites: dict[str, Any] | None = None


class LimitesProvedor(BaseModel):
    """Só as chaves que o painel conhece. strict: recusa true/"10" onde se espera número."""
    model_config = ConfigDict(extra="forbid")
    rpm: float | None = Field(default=None, ge=0, strict=True)
    rpd: float | None = Field(default=None, ge=0, strict=True)
    tpm: float | None = Field(default=None, ge=0, strict=True)
    tpd: float | None = Field(default=None, ge=0, strict=True)
    usd_dia: float | None = Field(default=None, ge=0, strict=True)
    neurons_dia: float | None = Field(default=None, ge=0, strict=True)
    reset: str | None = Field(default=None, max_length=32)


class CorpoEditarProvedor(BaseModel):
    """Edição parcial: campo ausente (ou null) não muda; "" limpa os campos de URL e a fonte dos limites.
    `limites` substitui o bloco inteiro ({} limpa)."""
    model_config = ConfigDict(extra="forbid")
    nome: str | None = Field(default=None, min_length=1, max_length=128)
    tier: str | None = Field(default=None, pattern="^(FREE|PAID)$")
    site_chave: UrlHttp | None = None
    site_limites: UrlHttp | None = None
    api_base: ApiBase | None = None
    url_modelos: UrlHttp | None = None
    fonte_limites: str | None = Field(default=None, max_length=1024)
    limites: LimitesProvedor | None = None


class CorpoEditarModeloProvedor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ativo: bool | None = None
    papeis: list[Annotated[str, Field(min_length=1, max_length=32)]] | None = Field(default=None, max_length=16)
    contexto: int | None = Field(default=None, gt=0, le=100_000_000, strict=True)


class CorpoNovoModeloProvedor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nome: str = Field(min_length=1, max_length=128)
    id: str = Field(min_length=1, max_length=256)
    papeis: list[str] = Field(default_factory=list)  # vazio: inferido pelo ID do modelo
    contexto: int | None = None
    ativo: bool = True


class CorpoSincronizacao(BaseModel):
    model_config = ConfigDict(extra="forbid")
    aplicar: bool = False  # False: só calcula o que mudaria


class ItemModeloLote(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provedor: str = Field(min_length=1, max_length=64)
    nome: str = Field(min_length=1, max_length=128)
    id: str = Field(min_length=1, max_length=256)
    papeis: list[str] = Field(default_factory=list, max_length=8)
    contexto: int | None = None


class CorpoModelosLote(BaseModel):
    model_config = ConfigDict(extra="forbid")
    itens: list[ItemModeloLote] = Field(min_length=1, max_length=500)


class CorpoTestarModelos(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Até 40: o teste é sequencial (20 s de timeout cada) e espaçado pelo rpm do provedor.
    ids: list[Annotated[str, Field(min_length=1, max_length=256)]] = Field(min_length=1, max_length=40)


class CorpoOrdemGrupos(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ordem: dict[str, list[str]]


class ChatMsg(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: str = Field(pattern=r"^(system|user|assistant)$")
    content: str = Field(min_length=1, max_length=65536)


class ChatReq(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str = Field(default="tudoia-auto", max_length=128)
    messages: list[ChatMsg] = Field(min_length=1, max_length=100)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, ge=16, le=16384)


class GerarImagemReq(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str = Field(min_length=1, max_length=4096)
    prompt_negativo: str = Field(default="", max_length=4096)
    motor: str = Field(default="auto", max_length=64)
    modelo: str = Field(default="flux", max_length=128)
    aspect_ratio: str = Field(default="1:1", pattern=r"^(1:1|16:9|9:16|4:3|3:4)$")
    seed: int | None = Field(default=None, ge=0, le=2**32 - 1)
    steps: int = Field(default=20, ge=1, le=100)
    # Reescrever o prompt com um LLM só quando a pessoa pede (o texto pode ir para a nuvem, se houver chave do Groq).
    otimizar_prompt: bool = False


class GerarVideoReq(BaseModel):
    model_config = ConfigDict(extra="ignore")
    prompt: str = Field(min_length=1, max_length=4096)
    motor: str = Field(default="auto", max_length=64)
    modelo: str = Field(default="video-minimax-h3", max_length=128)
    duracao_segundos: int = Field(default=5, ge=1, le=60)
    resolucao: str = Field(default="720p", pattern=r"^(480p|720p|1080p)$")
    fps: int = Field(default=24, ge=8, le=60)
    seed: int | None = Field(default=None, ge=0, le=2**32 - 1)
    modo_origem: str = Field(default="t2v", pattern=r"^(t2v|i2v|v2v)$")
    arquivo_referencia: str | None = Field(default=None, max_length=1024)
    modo_execucao: str = Field(default="sync", pattern=r"^(sync|async)$")
    # Reescrever o prompt com um LLM só quando a pessoa pede (o texto pode ir para a nuvem, se houver chave do Groq).
    otimizar_prompt: bool = False


class VideoLongoReq(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str = Field(min_length=1, max_length=4096)
    motor: str = Field(default="comfyui", pattern=r"^(comfyui|nuvem)$")
    modelo: str = Field(min_length=1, max_length=128)
    duracao_segundos: int = Field(ge=1, le=60)
    resolucao: str = Field(default="720p", pattern=r"^(480p|720p)$")
    modo: str = Field(default="continuo", pattern=r"^(continuo|cenas)$")
    # Roteiro opcional, uma descrição por clipe (até 12); sem ele o modo "cenas" pede o roteiro ao Ollama local.
    cenas: list[Annotated[str, Field(min_length=1, max_length=2000)]] | None = Field(default=None, max_length=12)
    seed: int | None = Field(default=None, ge=0, le=2**32 - 1)
    arquivo_referencia: str | None = Field(default=None, max_length=1024)
    trilha: str | None = Field(default=None, max_length=255)   # nome de um arquivo do Estúdio de música
    otimizar_prompt: bool = False
    # Na nuvem o pedido só sai da máquina (e só gasta) com esta confirmação explícita, a cada pedido.
    confirmar_nuvem: bool = False


class RetomarVideoLongoReq(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmar_nuvem: bool = False


class GerarMusicaReq(BaseModel):
    model_config = ConfigDict(extra="forbid")
    style: str = Field(min_length=1, max_length=4096)
    lyrics: str = Field(default="[instrumental]", max_length=8192)
    motor: str = Field(default="comfyui", max_length=64)
    modelo: str = Field(default="musica-yue2", max_length=128)
    duracao_segundos: float = Field(default=30.0, ge=5.0, le=360.0)
    modo: str = Field(default="full", pattern=r"^(full|melody)$")   # o nó YuE2 só aceita full e melody
    seed: int | None = Field(default=None, ge=0, le=2**32 - 1)
    # Reescrever o prompt com um LLM só quando a pessoa pede (o texto pode ir para a nuvem, se houver chave do Groq).
    otimizar_prompt: bool = False


class CancelarEstudioReq(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Sem prompt_id, interrompe o que estiver rodando (comportamento antigo). Com ele, só aquele trabalho.
    prompt_id: str | None = Field(default=None, pattern=r"^[0-9a-fA-F-]{8,64}$")


class UploadMidiaReq(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nome_arquivo: str = Field(min_length=1, max_length=256)
    # ~100 MB binários em base64; o teto da rota no middleware (140 MB) é o limite do corpo inteiro
    conteudo_base64: str = Field(min_length=1, max_length=140 * 1024 * 1024)
    tipo: str = Field(default="imagem", pattern=r"^(imagem|video)$")


class InpaintImagemReq(BaseModel):
    model_config = ConfigDict(extra="forbid")
    imagem_base: str = Field(min_length=1, max_length=1024)
    mascara_base64: str = Field(min_length=1)
    prompt: str = Field(min_length=1, max_length=4096)
    prompt_negativo: str = Field(default="", max_length=1024)
    modelo: str = Field(default="auto", max_length=128)
    denoise: float = Field(default=0.75, ge=0.05, le=1.0)
    seed: int | None = Field(default=None, ge=0, le=2**32 - 1)
    steps: int = Field(default=25, ge=1, le=100)
    # Reescrever o prompt com um LLM só quando a pessoa pede (o texto pode ir para a nuvem, se houver chave do Groq).
    otimizar_prompt: bool = False


class CorpoCriarGrupo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9_-]+$")
    titulo: str = Field(min_length=2, max_length=128)
    descricao: str = Field(default="", max_length=512)
    tier: str = Field(default="FREE", pattern=r"^(FREE|PAID|LOCAL)$")
    papeis: list[str] = Field(default_factory=list, max_length=16)
    modelos: list[str] = Field(default_factory=list)


class CorpoEditarGrupo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    titulo: str | None = Field(default=None, max_length=128)
    descricao: str | None = Field(default=None, max_length=512)
    tier: str | None = Field(default=None, pattern=r"^(FREE|PAID|LOCAL)$")
    papeis: list[str] | None = Field(default=None, max_length=16)
    ativo: bool | None = None
    modelos: list[str] | None = None


class CorpoBaixarModeloLocal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nome: str = Field(min_length=2, max_length=128)


class OtimizarPromptReq(BaseModel):
    prompt: str
    model_config = ConfigDict(extra="forbid")

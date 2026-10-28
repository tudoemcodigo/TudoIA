"""Modelos de entrada da API (Pydantic). Todos recusam campo desconhecido, salvo exceção comentada."""
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

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


class CorpoNovoProvedor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=64)
    nome: str = Field(min_length=1, max_length=128)
    tier: str = Field(pattern="^(FREE|PAID)$")
    chave: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    valor_chave: str | None = None
    site_chave: str | None = None
    api_base: str | None = None
    url_modelos: str | None = None
    fonte_limites: str | None = None
    limites: dict[str, Any] | None = None


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
    seed: int | None = None
    steps: int = Field(default=20, ge=1, le=100)


class GerarVideoReq(BaseModel):
    model_config = ConfigDict(extra="ignore")
    prompt: str = Field(min_length=1, max_length=4096)
    motor: str = Field(default="auto", max_length=64)
    modelo: str = Field(default="fluxo:video-minimax-h3", max_length=128)
    duracao_segundos: int = Field(default=5, ge=1, le=60)
    resolucao: str = Field(default="720p", pattern=r"^(480p|720p|1080p)$")
    fps: int = Field(default=24, ge=8, le=60)
    seed: int | None = None
    modo_origem: str = Field(default="t2v", pattern=r"^(t2v|i2v|v2v)$")
    arquivo_referencia: str | None = Field(default=None, max_length=1024)
    modo_execucao: str = Field(default="sync", pattern=r"^(sync|async)$")


class GerarMusicaReq(BaseModel):
    model_config = ConfigDict(extra="forbid")
    style: str = Field(min_length=1, max_length=4096)
    lyrics: str = Field(default="[instrumental]", max_length=8192)
    motor: str = Field(default="comfyui", max_length=64)
    modelo: str = Field(default="musica-yue2", max_length=128)
    duracao_segundos: float = Field(default=30.0, ge=5.0, le=360.0)
    modo: str = Field(default="full", pattern=r"^(full|melody|off)$")
    seed: int | None = None


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
    seed: int | None = None
    steps: int = Field(default=25, ge=1, le=100)


class CorpoCriarGrupo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9_-]+$")
    titulo: str = Field(min_length=2, max_length=128)
    descricao: str = Field(default="", max_length=512)
    modelos: list[str] = Field(default_factory=list)


class CorpoEditarGrupo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    titulo: str | None = Field(default=None, max_length=128)
    descricao: str | None = Field(default=None, max_length=512)
    ativo: bool | None = None
    modelos: list[str] | None = None


class CorpoBaixarModeloLocal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nome: str = Field(min_length=2, max_length=128)


class OtimizarPromptReq(BaseModel):
    prompt: str
    model_config = ConfigDict(extra="forbid")

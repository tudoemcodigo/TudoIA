"""Vídeo na nuvem pelo LiteLLM (/v1/videos): catálogo (config/video-nuvem.yaml), deployments do config gerado e o
cliente HTTP que o vídeo longo usa.

Cada modelo vira "video/<nome>" (texto) e "video/<nome>-i2v" (com quadro inicial) no LiteLLM, só com a chave no .env.
O pedido vai fixado nesse nome: nada de grupo nem fallback, para nenhum segundo pago sair para outro provedor.
"""
import base64
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import yaml

from . import upstreams

PREFIXO = "video/"
TIMEOUT_CRIAR = 60          # o provedor só enfileira; a geração em si é consultada depois
TIMEOUT_CONSULTA = 30
TIMEOUT_DOWNLOAD = 600
LIMITE_DOWNLOAD = 1_000_000_000   # 1 GB: clipe de 30 s em 1080p fica muito abaixo disso
LIMITE_IMAGEM = 8_000_000         # quadro inicial em JPEG; data URI grande deixa o pedido lento (doc da fal)


@dataclass(frozen=True)
class ModeloVideoNuvem:
    nome: str
    rotulo: str
    provedor: str
    chave: str
    t2v: str
    i2v: str | None
    campo_imagem: str | None
    duracao_min: int
    duracao_max: int
    duracao_valores: tuple[int, ...]
    duracao_tipo: str
    resolucoes: dict[str, str]
    preco_usd_s: dict[str, float]
    parametros: dict[str, Any] = field(default_factory=dict)
    parametros_t2v: dict[str, Any] = field(default_factory=dict)
    fonte_preco: str = ""

    def duracoes_validas(self) -> tuple[int, ...]:
        return self.duracao_valores or tuple(range(self.duracao_min, self.duracao_max + 1))

    def preco(self, resolucao: str) -> float:
        return float(self.preco_usd_s.get(resolucao, self.preco_usd_s.get("padrao", 0.0)))

    def nome_litellm(self, com_imagem: bool) -> str:
        return f"{PREFIXO}{self.nome}-i2v" if com_imagem and self.i2v else f"{PREFIXO}{self.nome}"


def carregar_catalogo_video(caminho: Path) -> list[ModeloVideoNuvem]:
    if not caminho.is_file():
        return []
    dados = yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}
    saida: list[ModeloVideoNuvem] = []
    nomes: set[str] = set()
    for m in dados.get("modelos") or []:
        nome = str(m["nome"])
        if nome in nomes or not nome.replace("-", "").isalnum():
            raise ValueError(f"video-nuvem: nome inválido ou repetido: {nome!r}")
        nomes.add(nome)
        dur = m.get("duracao") or {}
        valores = tuple(sorted(int(v) for v in dur.get("valores") or ()))
        dmin = int(dur.get("min", valores[0] if valores else 1))
        dmax = int(dur.get("max", valores[-1] if valores else dmin))
        if dmin < 1 or dmax < dmin or dur.get("tipo", "int") not in ("int", "str"):
            raise ValueError(f"video-nuvem: duração inválida em {nome}")
        if m.get("provedor") != "fal":
            raise ValueError(f"video-nuvem: provedor sem suporte em {nome} (só fal)")
        saida.append(ModeloVideoNuvem(
            nome=nome, rotulo=str(m.get("rotulo") or nome), provedor="fal", chave=str(m["chave"]),
            t2v=str(m["t2v"]), i2v=m.get("i2v"), campo_imagem=m.get("campo_imagem"),
            duracao_min=dmin, duracao_max=dmax, duracao_valores=valores, duracao_tipo=dur.get("tipo", "int"),
            resolucoes={str(k): str(v) for k, v in (m.get("resolucoes") or {}).items()},
            preco_usd_s={str(k): float(v) for k, v in (m.get("preco_usd_s") or {}).items()},
            parametros=dict(m.get("parametros") or {}), parametros_t2v=dict(m.get("parametros_t2v") or {}),
            fonte_preco=str(m.get("fonte_preco") or ""),
        ))
    return saida


def catalogo_video(raiz: Path) -> list[ModeloVideoNuvem]:
    return carregar_catalogo_video(raiz / "config" / "video-nuvem.yaml")


def deployments_video(modelos: list[ModeloVideoNuvem], env: dict[str, str]) -> list[dict]:
    """Entradas do model_list do LiteLLM para os modelos com chave no .env."""
    saida = []
    for m in modelos:
        if not (env.get(m.chave) or "").strip():
            continue
        custo = {f"output_cost_per_second_{res}": p for res, p in m.preco_usd_s.items() if res != "padrao"}
        custo["output_cost_per_second"] = m.preco("720p")
        for com_imagem, endpoint in ((False, m.t2v), (True, m.i2v)):
            if not endpoint:
                continue
            nome = m.nome_litellm(com_imagem)
            saida.append({
                "model_name": nome,
                "litellm_params": {"model": f"fal_ai/{endpoint}", "api_key": f"os.environ/{m.chave}",
                                   "timeout": TIMEOUT_CRIAR},
                "model_info": {"plano": "PAID", "provedor": m.provedor, "papeis": ["video"], "membro": nome, **custo},
            })
    return saida


def imagem_data_uri(caminho: Path) -> str:
    dados = caminho.read_bytes()
    if len(dados) > LIMITE_IMAGEM:
        raise ValueError("quadro inicial grande demais para enviar")
    tipo = "image/png" if dados.startswith(b"\x89PNG") else "image/jpeg"
    return f"data:{tipo};base64,{base64.b64encode(dados).decode('ascii')}"


def corpo_pedido(m: ModeloVideoNuvem, prompt: str, duracao_s: int, resolucao: str, seed: int | None,
                 imagem: Path | None) -> dict:
    """Corpo de POST /v1/videos. Os parâmetros do provedor vão em extra_body com o tipo que o esquema exige: o
    `seconds`/`size` do OpenAI o LiteLLM converteria para string e a fal recusaria nos campos inteiros."""
    com_imagem = imagem is not None and bool(m.i2v and m.campo_imagem)
    extra: dict[str, Any] = dict(m.parametros)
    if not com_imagem:
        extra.update(m.parametros_t2v)
    extra["duration"] = str(duracao_s) if m.duracao_tipo == "str" else int(duracao_s)
    if resolucao in m.resolucoes:
        extra["resolution"] = m.resolucoes[resolucao]
    if seed is not None:
        extra["seed"] = int(seed)
    if com_imagem:
        extra[m.campo_imagem] = imagem_data_uri(imagem)
    return {"model": m.nome_litellm(com_imagem), "prompt": prompt, "extra_body": extra}


class ErroNuvem(RuntimeError):
    def __init__(self, mensagem: str, transitorio: bool = False):
        super().__init__(mensagem)
        self.transitorio = transitorio


def _mensagem_erro(resp: httpx.Response) -> str:
    try:
        d = resp.json()
        erro = d.get("error") if isinstance(d, dict) else None
        msg = (erro.get("message") if isinstance(erro, dict) else erro) or d.get("detail") or resp.text
    except ValueError:
        msg = resp.text
    return f"LiteLLM HTTP {resp.status_code}: {str(msg).strip()[:300]}"


def _verificar(resp: httpx.Response) -> None:
    if resp.status_code < 400:
        return
    transitorio = resp.status_code in (408, 409, 425, 429) or resp.status_code >= 500
    raise ErroNuvem(_mensagem_erro(resp), transitorio=transitorio)


class ClienteVideoLiteLLM:
    """Um httpx.Client para o processo (pool de conexões compartilhado); a chave mestra fica só no cabeçalho."""

    def __init__(self, chave_mestra: str, base: str = upstreams.LITELLM, transporte: httpx.BaseTransport | None = None):
        self._base = base.rstrip("/")
        self._cabecalhos = {"Authorization": f"Bearer {chave_mestra}"}
        self._cliente = httpx.Client(timeout=TIMEOUT_CONSULTA, transport=transporte)

    def criar(self, corpo: dict) -> str:
        try:
            r = self._cliente.post(f"{self._base}/v1/videos", json=corpo, headers=self._cabecalhos, timeout=TIMEOUT_CRIAR)
        except httpx.ConnectError as e:   # não chegou ao LiteLLM: nada foi cobrado, pode tentar de novo
            raise ErroNuvem("LiteLLM (:4000) fora do ar", transitorio=True) from e
        except httpx.TimeoutException as e:   # pode ter chegado ao provedor: repetir arrisca pagar duas vezes
            raise ErroNuvem("o LiteLLM não respondeu ao pedido de vídeo a tempo") from e
        _verificar(r)
        vid = (r.json() or {}).get("id")
        if not isinstance(vid, str) or not vid:
            raise ErroNuvem("o LiteLLM não devolveu o id do vídeo")
        return vid

    def status(self, video_id: str) -> tuple[str, str | None]:
        """("andamento" | "pronto" | "erro", mensagem)."""
        try:
            r = self._cliente.get(f"{self._base}/v1/videos/{video_id}", headers=self._cabecalhos)
        except httpx.HTTPError as e:
            raise ErroNuvem(f"consulta do vídeo falhou: {type(e).__name__}", transitorio=True) from e
        _verificar(r)
        d = r.json() or {}
        estado = d.get("status")
        if estado == "completed":
            return "pronto", None
        if estado == "failed":
            erro = d.get("error") or {}
            return "erro", str(erro.get("message") if isinstance(erro, dict) else erro or "o provedor falhou")[:300]
        return "andamento", None

    def baixar(self, video_id: str, destino: Path) -> int:
        tmp = destino.with_name(destino.name + ".parcial")
        total = 0
        try:
            with self._cliente.stream("GET", f"{self._base}/v1/videos/{video_id}/content", headers=self._cabecalhos,
                                      timeout=TIMEOUT_DOWNLOAD) as r:
                if r.status_code >= 400:
                    r.read()
                    _verificar(r)
                with tmp.open("wb") as f:
                    for bloco in r.iter_bytes(1 << 20):
                        total += len(bloco)
                        if total > LIMITE_DOWNLOAD:
                            raise ErroNuvem("vídeo da nuvem maior que o limite de 1 GB")
                        f.write(bloco)
        except httpx.HTTPError as e:
            tmp.unlink(missing_ok=True)
            raise ErroNuvem(f"download do vídeo falhou: {type(e).__name__}", transitorio=True) from e
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        if total == 0:
            tmp.unlink(missing_ok=True)
            raise ErroNuvem("o provedor devolveu um vídeo vazio", transitorio=True)
        tmp.replace(destino)
        return total

    def fechar(self) -> None:
        self._cliente.close()

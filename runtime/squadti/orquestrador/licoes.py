"""
Livro de Lições da SquadTI: transforma achados dos agentes em prevenção, no lugar certo (ver docs/squadti/LICOES.md).

API pura: sem rede, sem modelo, sem tocar no grafo. O livro é um JSONL append-only (`SQUADTI_LICOES_ARQUIVO`, padrão
`licoes.jsonl`) e o estado das lições é sempre o resultado de reler o arquivo (não há cache que possa divergir).

Guardrails (todos testados):
1. O texto de uma lição nunca vem de prosa de modelo. Só entram campos estruturados e VALIDADOS (agente e categoria de vocabulário
   fechado, ID em formato fixo, severidade, stack, tarefa) e o texto sai de modelos fixos de frase, sanitizado e com tamanho máximo.
   Endpoint e método do achado viram um hash curto; o texto deles nunca é gravado.
2. Lição só vale depois de aprovação humana explícita (`aprovar` exige `quem`).
3. Cada lição guarda origem rastreável (tarefas, contagem, primeira/última ocorrência, hash das evidências), sem prompt, resposta nem segredo.
4. Promoção à Doutrina exige reincidência e produz só uma PROPOSTA em arquivo; este módulo nunca escreve na Doutrina.
5. Dedup por impressão digital (agente + id + categoria + stack); a contagem é por tarefa distinta, não por achado repetido.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import threading
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

import entrada

_log = logging.getLogger("squadti.licoes")

# ---------------------------------------------------------------- vocabulários e limites
ESTADOS = ("pendente", "aprovada", "rejeitada", "desativada", "promovida")
SEVERIDADES = ("CRITICO", "ALTO", "MEDIO", "BAIXO")
_ORDEM_SEV = {s: i for i, s in enumerate(SEVERIDADES)}
DESTINOS = ("squad_prompt", "doutrina_esclarecimento", "doutrina_regra_nova", "squad_verificacao", "projeto", "squad_config",
            "componente")

AGENTES_CONHECIDOS = frozenset({"hacker", "macaco", "revisor", "senior", "qa", "qualidade", "appsec", "devops", "chefe", "analista",
                                "arquiteto", "dba", "backend", "frontend", "documentacao"})

# Categoria -> família da Doutrina sugerida (None = categoria conhecida, mas sem família geral). Vocabulário FECHADO: texto fora
# daqui vira "outra", para que prosa de modelo não chegue ao livro nem às propostas.
_FAMILIA_DA_CATEGORIA = {
    "seguranca": "SEC", "autenticacao": "SEC", "autorizacao": "SEC", "injecao": "SEC", "erros": "SEC", "cors": "SEC",
    "headers": "SEC", "rate-limit": "SEC", "mass-assignment": "SEC", "idor": "SEC", "segredos": "SEC", "dockerfile": "SEC",
    "qualidade": "QUA", "complexidade": "QUA", "duplicacao": "QUA", "testes": "QUA",
    "dados": "DAD", "frontend": "FRT", "ui": "FRT", "usabilidade": "FRT", "acessibilidade": "FRT",
    "documentacao": "DOC", "requisitos": "REQ", "arquitetura": "ARQ",
    "componente": None, "projeto": None, "regra-de-negocio": None, "comportamento": None, "formato": None, "comando": None,
    "desempenho": None, "outra": None,
}
CATEGORIAS = frozenset(_FAMILIA_DA_CATEGORIA)
_ALIAS_CATEGORIA = {"security": "seguranca", "auth": "autenticacao", "injection": "injecao", "secrets": "segredos",
                    "segredo": "segredos", "documentation": "documentacao", "docs": "documentacao", "tests": "testes",
                    "teste": "testes", "quality": "qualidade", "error": "erros", "erro": "erros", "ratelimit": "rate-limit",
                    "regra-negocio": "regra-de-negocio", "negocio": "regra-de-negocio", "headers-http": "headers"}
_NOME_FAMILIA = {"SEC": "segurança", "QUA": "qualidade e testes", "DAD": "dados", "FRT": "frontend", "DOC": "documentação",
                 "REQ": "requisitos", "ARQ": "arquitetura"}
_FAMILIAS_DOUTRINA = frozenset({"REQ", "DAD", "FRT", "QUA", "SEC", "DOC", "ARQ", "CMP", "IA", "ECO"})
_CATEGORIAS_DETECTAVEIS = frozenset({"segredos", "dockerfile", "complexidade", "duplicacao"})
_CATEGORIAS_CONFIG = frozenset({"comportamento", "formato", "comando"})

_PREFIXOS_KIT = frozenset({"AUTH", "INJ", "ERR", "CORS", "MASS", "LIM", "HDR", "MET", "RATE", "IDOR"})
_ROLES_DA_FAMILIA = {"SEC": ("backend", "frontend"), "ARQ": ("backend",), "DAD": ("dba",), "FRT": ("frontend",),
                     "QUA": ("backend", "frontend"), "DOC": ("documentacao",), "REQ": ("analista",), "CMP": ("backend",),
                     "IA": ("backend",), "ECO": ("arquiteto",)}

MAX_LICOES = 2_000          # impressões digitais distintas no livro
MAX_TAREFAS_POR_LICAO = 25  # tarefas distintas guardadas por lição (a contagem para aqui; reincidência só precisa de 2)
MAX_BYTES_LIVRO = 8 * 1024 * 1024
MAX_LINHA = 2_048           # bytes por linha; maior que isso é ignorada na leitura
MAX_QUEM = 80
MAX_TEXTO = 300             # caracteres do texto de uma lição no prompt
LIMIAR_REINCIDENCIA = 2     # tarefas distintas para candidatar à Doutrina (ou 1 CRITICO de segurança)

_RE_ID_ACHADO = re.compile(r"^[A-Z]{2,5}(?:-[A-Z]{2,5})?-\d{2,3}$")
_RE_TAREFA = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$")
_RE_STACK = re.compile(r"^[a-z0-9][a-z0-9.+-]{0,19}$")
_RE_LICAO = re.compile(r"^L-[0-9a-f]{16}$")
_RE_QUANDO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_RE_HASH = re.compile(r"^[0-9a-f]{16}$")

_TRAVA = threading.RLock()  # um processo escritor por livro (o orquestrador); threads são serializadas aqui


class LicaoInexistente(KeyError):
    """ID de lição que não existe no livro."""


class TransicaoInvalida(ValueError):
    """Mudança de estado não permitida, ou sem responsável identificado."""


class NaoCandidata(ValueError):
    """Lição sem reincidência suficiente (ou sem destino na Doutrina): não gera proposta."""


def _agora() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------- normalização (tudo passa por aqui antes de tocar o livro)
def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))


def _limpo(valor, maximo: int) -> str:
    texto, _ = entrada.sanitizar(valor)
    return " ".join(texto.split())[:maximo]


def _categoria(valor) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", _sem_acento(_limpo(valor, 60)).lower()).strip("-")
    slug = _ALIAS_CATEGORIA.get(slug, slug)
    return slug if slug in CATEGORIAS else "outra"


def _impressao(agente: str, achado_id: str, categoria: str, stack: str) -> str:
    return hashlib.sha256(f"{agente}|{achado_id}|{categoria}|{stack}".encode("utf-8")).hexdigest()[:16]


def _hash_evidencia(endpoint, metodo) -> str:
    """Só o hash do (método, endpoint): permite contar evidências distintas sem guardar o texto do alvo."""
    bruto = f"{_limpo(metodo, 12).upper()}|{_limpo(endpoint, 300)}"
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()[:16]


def _ocorrencia(achado, tarefa: str, stack: str) -> tuple[Optional[dict], Optional[str]]:
    """(ocorrência normalizada, None) ou (None, motivo). BAIXO e malformado não entram."""
    if not isinstance(achado, dict):
        return None, "achado malformado (não é um objeto)"
    sev = _sem_acento(_limpo(achado.get("severidade"), 12)).upper()
    if sev not in _ORDEM_SEV:
        return None, "severidade inválida"
    if sev == "BAIXO":
        return None, "severidade BAIXO não vira lição"
    agente = _sem_acento(_limpo(achado.get("agente"), 20)).lower()
    if agente not in AGENTES_CONHECIDOS:
        return None, "agente desconhecido"
    achado_id = _sem_acento(_limpo(achado.get("id"), 20)).upper()
    if not _RE_ID_ACHADO.match(achado_id):
        return None, "ID de achado em formato inválido"
    categoria = _categoria(achado.get("categoria"))
    dout = achado.get("na_doutrina")
    return {"fp": _impressao(agente, achado_id, categoria, stack), "tarefa": tarefa, "agente": agente, "id": achado_id,
            "categoria": categoria, "stack": stack, "sev": sev, "ev": _hash_evidencia(achado.get("endpoint"), achado.get("metodo")),
            "dout": dout if isinstance(dout, bool) else None}, None


def _ocorrencia_de_linha(d: dict) -> Optional[dict]:
    """Revalida uma linha lida do disco com as mesmas regras (livro adulterado não injeta texto): None se não passar."""
    try:
        o = {"fp": d["fp"], "tarefa": d["tarefa"], "agente": d["agente"], "id": d["id"], "categoria": d["categoria"],
             "stack": d["stack"], "sev": d["sev"], "ev": d["ev"], "dout": d.get("dout"), "quando": d["quando"]}
    except (KeyError, TypeError):
        return None
    ok = (isinstance(o["tarefa"], str) and _RE_TAREFA.match(o["tarefa"]) and isinstance(o["stack"], str)
          and _RE_STACK.match(o["stack"]) and o["agente"] in AGENTES_CONHECIDOS and isinstance(o["id"], str)
          and _RE_ID_ACHADO.match(o["id"]) and o["categoria"] in CATEGORIAS and o["sev"] in _ORDEM_SEV and o["sev"] != "BAIXO"
          and isinstance(o["ev"], str) and _RE_HASH.match(o["ev"]) and isinstance(o["quando"], str)
          and _RE_QUANDO.match(o["quando"]) and (o["dout"] is None or isinstance(o["dout"], bool))
          and o["fp"] == _impressao(o["agente"], o["id"], o["categoria"], o["stack"]))
    return o if ok else None


# ---------------------------------------------------------------- persistência
def caminho_do_livro(livro=None) -> Path:
    """`livro` explícito > SQUADTI_LICOES_ARQUIVO > licoes.jsonl."""
    return Path(livro) if livro else Path(os.getenv("SQUADTI_LICOES_ARQUIVO", "licoes.jsonl"))


# Transições permitidas (de, para). `rejeitada` e `promovida` são finais: a decisão humana não se desfaz por reincidência.
_TRANSICOES = frozenset({("pendente", "aprovada"), ("desativada", "aprovada"), ("pendente", "rejeitada"),
                         ("aprovada", "desativada"), ("aprovada", "promovida")})


def _chave_poda(l: dict) -> tuple:
    """Menor = mais descartável: menos grave, menos recorrente, mais antiga."""
    return (-_ORDEM_SEV[_sev_max(l)], len(l["por_tarefa"]), l["ultima"])


def _sev_max(l: dict) -> str:
    return min((v["sev"] for v in l["por_tarefa"].values()), key=lambda s: _ORDEM_SEV[s])


def _aplicar_ocorrencia(licoes: dict, o: dict) -> bool:
    """Dobra uma ocorrência no estado. False se não mudou nada (tarefa já registrada sem severidade maior, ou limite)."""
    l = licoes.get(o["fp"])
    if l is None:
        l = licoes[o["fp"]] = {"fp": o["fp"], "agente": o["agente"], "achado_id": o["id"], "categoria": o["categoria"],
                               "stack": o["stack"], "por_tarefa": {}, "na_doutrina": None, "estado": "pendente",
                               "primeira": o["quando"], "ultima": o["quando"],
                               "historico": [{"de": None, "para": "pendente", "quem": "sistema", "quando": o["quando"]}]}
    atual = l["por_tarefa"].get(o["tarefa"])
    if atual is None:
        if len(l["por_tarefa"]) >= MAX_TAREFAS_POR_LICAO:
            return False
    elif _ORDEM_SEV[o["sev"]] >= _ORDEM_SEV[atual["sev"]]:
        return False
    l["por_tarefa"][o["tarefa"]] = {"sev": o["sev"], "ev": o["ev"], "quando": o["quando"]}
    l["primeira"], l["ultima"] = min(l["primeira"], o["quando"]), max(l["ultima"], o["quando"])
    if o["dout"] is not None:
        l["na_doutrina"] = o["dout"]
    return True


def _aplicar_transicao(licoes: dict, d: dict) -> bool:
    try:
        alvo = next((l for l in licoes.values() if "L-" + l["fp"] == d["lic"]), None)
        quem, quando, para = d["quem"], d["quando"], d["para"]
    except (KeyError, TypeError):
        return False
    if (alvo is None or not isinstance(quem, str) or not quem.strip() or len(quem) > MAX_QUEM or not isinstance(quando, str)
            or not _RE_QUANDO.match(quando) or (alvo["estado"], para) not in _TRANSICOES):
        return False
    reg = {"de": alvo["estado"], "para": para, "quem": quem, "quando": quando}
    if isinstance(d.get("ev"), str) and _RE_HASH.match(d["ev"]):
        reg["evidencia_hash"] = d["ev"]
    alvo["historico"].append(reg)
    alvo["estado"] = para
    return True


def _carregar(caminho: Path) -> dict:
    """Relê o livro. Linha quebrada, grande demais ou inválida é ignorada com aviso; as demais continuam valendo."""
    licoes: dict = {}
    if not caminho.is_file():
        return licoes
    ignoradas = 0
    with open(caminho, "rb") as f:
        for numero, bruto in enumerate(f, 1):
            if not bruto.strip():
                continue
            ok = False
            if len(bruto) <= MAX_LINHA:
                try:
                    d = json.loads(bruto.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    d = None
                if isinstance(d, dict) and d.get("t") == "o":
                    o = _ocorrencia_de_linha(d)
                    if o is not None:
                        _aplicar_ocorrencia(licoes, o)
                        ok = True
                elif isinstance(d, dict) and d.get("t") == "x":
                    ok = _aplicar_transicao(licoes, d)
            if not ok:
                ignoradas += 1
                _log.warning("livro de lições %s: linha %d ignorada (quebrada, grande demais ou inválida)", caminho.name, numero)
    if ignoradas:
        _log.warning("livro de lições %s: %d linha(s) ignorada(s); as demais foram preservadas", caminho.name, ignoradas)
    return licoes


def _linhas(o: dict) -> bytes:
    campos = {"t": "o", "fp": o["fp"], "tarefa": o["tarefa"], "agente": o["agente"], "id": o["id"], "categoria": o["categoria"],
              "stack": o["stack"], "sev": o["sev"], "ev": o["ev"], "dout": o["dout"], "quando": o["quando"]}
    return (json.dumps(campos, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def _anexar(caminho: Path, blocos: list[bytes]) -> None:
    """Append atômico: um único write em O_APPEND; se o arquivo terminou sem quebra de linha (queda no meio de uma escrita),
    começa por uma, para não colar na linha quebrada."""
    if not blocos:
        return
    caminho.parent.mkdir(parents=True, exist_ok=True)
    dados = b"".join(blocos)
    if caminho.is_file() and caminho.stat().st_size:
        with open(caminho, "rb") as f:
            f.seek(-1, os.SEEK_END)
            if f.read(1) != b"\n":
                dados = b"\n" + dados
    fd = os.open(caminho, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, dados)
        os.fsync(fd)
    finally:
        os.close(fd)


def _reescrever(caminho: Path, licoes: dict) -> None:
    """Compactação: forma canônica (uma linha por tarefa, mais as transições), cópia do original em `<arquivo>.1` e troca atômica."""
    tmp = caminho.with_name(caminho.name + ".tmp")
    with open(tmp, "wb") as f:
        for l in sorted(licoes.values(), key=lambda x: x["primeira"]):
            for tarefa, v in l["por_tarefa"].items():
                f.write(_linhas({"fp": l["fp"], "tarefa": tarefa, "agente": l["agente"], "id": l["achado_id"],
                                 "categoria": l["categoria"], "stack": l["stack"], "sev": v["sev"], "ev": v["ev"],
                                 "dout": l["na_doutrina"], "quando": v["quando"]}))
            for h in l["historico"][1:]:
                x = {"t": "x", "lic": "L-" + l["fp"], "para": h["para"], "quem": h["quem"], "quando": h["quando"]}
                if "evidencia_hash" in h:
                    x["ev"] = h["evidencia_hash"]
                f.write((json.dumps(x, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"))
        f.flush()
        os.fsync(f.fileno())
    if caminho.is_file():
        shutil.copyfile(caminho, caminho.with_name(caminho.name + ".1"))
    os.replace(tmp, caminho)


def _podar(licoes: dict, alvo: int) -> int:
    """Remove lições PENDENTES (as menos graves, menos recorrentes e mais antigas) até sobrarem `alvo`. Decididas nunca saem."""
    candidatas = sorted((l for l in licoes.values() if l["estado"] == "pendente"), key=_chave_poda)
    removidas = 0
    while len(licoes) > alvo and candidatas:
        del licoes[candidatas.pop(0)["fp"]]
        removidas += 1
    return removidas


def _publica(l: dict) -> dict:
    t = sorted(l["por_tarefa"])
    pares = sorted(f"{k}:{v['ev']}:{v['sev']}" for k, v in l["por_tarefa"].items())
    return {"id": "L-" + l["fp"], "agente": l["agente"], "achado_id": l["achado_id"], "categoria": l["categoria"],
            "stack": l["stack"], "severidade_max": _sev_max(l), "contagem": len(t), "tarefas": t,
            "primeira_ocorrencia": l["primeira"], "ultima_ocorrencia": l["ultima"],
            "evidencia_hash": hashlib.sha256("\n".join(pares).encode("utf-8")).hexdigest()[:32],
            "na_doutrina": l["na_doutrina"], "estado": l["estado"], "historico": [dict(h) for h in l["historico"]]}


# ---------------------------------------------------------------- registrar / listar / estados
def registrar(livro, tarefa, stack, achados) -> dict:
    """Acrescenta as ocorrências ao livro. Devolve {registradas, ignoradas, avisos}. Nunca levanta por dado ruim (só por erro de E/S).

    Ignora BAIXO e achado malformado. A mesma impressão digital na mesma tarefa conta 1 (a severidade maior prevalece).
    Limites: MAX_LICOES (poda pendentes menos relevantes; sem espaço, ignora a nova), MAX_TAREFAS_POR_LICAO, MAX_BYTES_LIVRO
    (compacta e, se preciso, poda pendentes). O original compactado fica em `<arquivo>.1`."""
    caminho = caminho_do_livro(livro)
    avisos: list[str] = []
    t = _limpo(tarefa, 80)
    s = _limpo(stack, 20).lower()
    if not _RE_TAREFA.match(t) or not _RE_STACK.match(s):
        return {"registradas": 0, "ignoradas": 0, "avisos": ["tarefa ou stack em formato inválido; nada registrado"]}
    if not isinstance(achados, (list, tuple)):
        return {"registradas": 0, "ignoradas": 0, "avisos": ["achados não é uma lista; nada registrado"]}
    quando = _agora()
    agregadas: dict = {}
    ignoradas = 0
    for a in achados:
        o, motivo = _ocorrencia(a, t, s)
        if o is None:
            ignoradas += 1
            if motivo != "severidade BAIXO não vira lição":
                avisos.append(motivo)
            continue
        o["quando"] = quando
        antes = agregadas.get(o["fp"])
        if antes is None:
            agregadas[o["fp"]] = o
        elif _ORDEM_SEV[o["sev"]] < _ORDEM_SEV[antes["sev"]]:
            agregadas[o["fp"]] = {**o, "ev": antes["ev"]}
    registradas = 0
    with _TRAVA:
        licoes = _carregar(caminho)
        novas = [o for o in agregadas.values() if o["fp"] not in licoes]
        if len(licoes) + len(novas) > MAX_LICOES:
            podadas = _podar(licoes, MAX_LICOES - len(novas))
            if podadas:
                avisos.append(f"livro cheio: {podadas} lição(ões) pendente(s) menos relevante(s) podada(s)")
                _reescrever(caminho, licoes)
        blocos = []
        for o in agregadas.values():
            if o["fp"] not in licoes and len(licoes) >= MAX_LICOES:
                avisos.append("livro cheio de lições decididas; ocorrência nova ignorada")
                ignoradas += 1
                continue
            if _aplicar_ocorrencia(licoes, o):
                blocos.append(_linhas(o))
                registradas += 1
        _anexar(caminho, blocos)
        if caminho.is_file() and caminho.stat().st_size > MAX_BYTES_LIVRO:
            _reescrever(caminho, licoes)
            if caminho.stat().st_size > MAX_BYTES_LIVRO:
                _podar(licoes, max(1, int(len(licoes) * 0.8)))
                _reescrever(caminho, licoes)
                avisos.append("livro acima do limite de tamanho: lições pendentes menos relevantes podadas")
    return {"registradas": registradas, "ignoradas": ignoradas, "avisos": avisos}


def listar(estado: Optional[str] = None, livro=None) -> list[dict]:
    """Lições do livro (mais recentes primeiro), opcionalmente filtradas por estado."""
    if estado is not None and estado not in ESTADOS:
        raise ValueError(f"estado inválido: {estado!r} (use um de {list(ESTADOS)})")
    with _TRAVA:
        licoes = _carregar(caminho_do_livro(livro))
    saida = [_publica(l) for l in licoes.values() if estado is None or l["estado"] == estado]
    return sorted(saida, key=lambda x: (x["ultima_ocorrencia"], x["id"]), reverse=True)


def obter(licao_id, livro=None) -> dict:
    for l in listar(livro=livro):
        if l["id"] == licao_id:
            return l
    raise LicaoInexistente(licao_id if isinstance(licao_id, str) and _RE_LICAO.match(licao_id) else "ID inválido")


def _transitar(licao_id, para: str, quem, livro) -> dict:
    responsavel = _limpo(quem, MAX_QUEM)
    if not responsavel:
        raise TransicaoInvalida("a decisão precisa de um responsável humano identificado (quem)")
    if not isinstance(licao_id, str) or not _RE_LICAO.match(licao_id):
        raise LicaoInexistente("ID inválido")
    caminho = caminho_do_livro(livro)
    with _TRAVA:
        licoes = _carregar(caminho)
        alvo = licoes.get(licao_id[2:])
        if alvo is None:
            raise LicaoInexistente(licao_id)
        if (alvo["estado"], para) not in _TRANSICOES:
            raise TransicaoInvalida(f"{licao_id}: de {alvo['estado']} para {para} não é permitido")
        ev = _publica(alvo)["evidencia_hash"][:16]
        linha = {"t": "x", "lic": licao_id, "para": para, "quem": responsavel, "quando": _agora(), "ev": ev}
        _anexar(caminho, [(json.dumps(linha, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")])
        _aplicar_transicao(licoes, linha)
        return _publica(licoes[licao_id[2:]])


def aprovar(licao_id, quem, livro=None) -> dict:
    """pendente|desativada -> aprovada. O hash das evidências no momento da aprovação fica no histórico."""
    return _transitar(licao_id, "aprovada", quem, livro)


def rejeitar(licao_id, quem, livro=None) -> dict:
    """pendente -> rejeitada (final)."""
    return _transitar(licao_id, "rejeitada", quem, livro)


def desativar(licao_id, quem, livro=None) -> dict:
    """aprovada -> desativada (sai do prompt; pode ser reaprovada)."""
    return _transitar(licao_id, "desativada", quem, livro)


def promover(licao_id, quem, livro=None) -> dict:
    """aprovada -> promovida: o humano registra que a regra entrou na Doutrina. Exige candidata_doutrina."""
    lic = obter(licao_id, livro)
    if not triar(lic)["candidata_doutrina"]:
        raise NaoCandidata(f"{licao_id}: sem reincidência suficiente para promoção")
    return _transitar(licao_id, "promovida", quem, livro)


# ---------------------------------------------------------------- triagem
def _prefixo(achado_id: str) -> str:
    return achado_id.rsplit("-", 1)[0]


def _familia_do_id(achado_id: str) -> Optional[str]:
    primeiro = achado_id.split("-", 1)[0]
    return primeiro if primeiro in _FAMILIAS_DOUTRINA and achado_id.count("-") == 2 else None


def familia_sugerida(licao: dict) -> Optional[str]:
    """Família da Doutrina sugerida: pela categoria (SEC, QUA, DAD, FRT, DOC, REQ, ARQ) e, sem ela, pelo prefixo do ID."""
    return _FAMILIA_DA_CATEGORIA.get(licao["categoria"]) or _familia_do_id(licao["achado_id"])


def papel_alvo(licao: dict) -> list[str]:
    """Quais papéis recebem a lição. Kit de ataque -> backend; MAC/UI -> frontend; QC-* -> backend e frontend; ID da Doutrina -> papéis
    da família; senão pela família da categoria; senão backend."""
    ident = licao["achado_id"]
    prefixo = ident.split("-", 1)[0]
    if prefixo in _PREFIXOS_KIT:
        return ["backend"]
    if prefixo in ("MAC", "UI"):
        return ["frontend"]
    if prefixo == "QC":
        return ["backend", "frontend"]
    fam = _familia_do_id(ident) or _FAMILIA_DA_CATEGORIA.get(licao["categoria"])
    return list(_ROLES_DA_FAMILIA.get(fam, ("backend",)))


def _candidata(licao: dict, destino: str) -> bool:
    if destino not in ("doutrina_esclarecimento", "doutrina_regra_nova"):
        return False
    seguranca = familia_sugerida(licao) == "SEC"
    return licao["contagem"] >= LIMIAR_REINCIDENCIA or (licao["severidade_max"] == "CRITICO" and seguranca)


def triar(licao: dict, ids_doutrina: Optional[Iterable[str]] = None) -> dict:
    """Decide o destino da prevenção (determinístico). `ids_doutrina` (opcional) é o conjunto de IDs que a Doutrina tem
    (`doutrina_tec.ids_existentes`); sem ele vale a marca `na_doutrina` que o registro trouxe e, na falta dela, presume-se que existe.
    Devolve {destino, motivo, papel_alvo, candidata_doutrina}."""
    ident, cat = licao["achado_id"], licao["categoria"]

    def r(destino: str, motivo: str) -> dict:
        return {"destino": destino, "motivo": motivo, "papel_alvo": papel_alvo(licao),
                "candidata_doutrina": _candidata(licao, destino)}

    if cat == "componente":
        return r("componente", "defeito de componente TEC.*: pedido formal ao repositório do componente (ECO-MAP-02)")
    if cat in ("projeto", "regra-de-negocio"):
        return r("projeto", "regra de negócio do projeto gerado: vai para a spec/ADR do projeto e nunca generaliza")
    if cat in _CATEGORIAS_CONFIG:
        return r("squad_config", "comportamento do agente (formato ou comando): ajuste de configuração da Squad")
    if _prefixo(ident) in _PREFIXOS_KIT or ident.startswith("QC-") or cat in _CATEGORIAS_DETECTAVEIS:
        return r("squad_verificacao", "detectável por código: verificação determinística nova mais caso de regressão")
    familia_id = _familia_do_id(ident)
    if familia_id:
        existe = (ident in set(ids_doutrina)) if ids_doutrina is not None else (licao.get("na_doutrina") is not False)
        if existe:
            if licao["contagem"] >= LIMIAR_REINCIDENCIA:
                return r("doutrina_esclarecimento", f"a regra {ident} existe e os agentes a violam em {licao['contagem']} tarefas "
                                                    "mesmo citada: esclarecer o texto da regra")
            return r("squad_prompt", f"violação da regra {ident}, que já existe: lição no prompt do papel e caso de regressão")
    if familia_sugerida(licao) is not None:
        return r("doutrina_regra_nova", "falta norma geral: o achado não tem regra na Doutrina e a categoria é generalizável")
    return r("squad_prompt", "achado sem regra na Doutrina e sem categoria generalizável: lição no prompt do papel")


# ---------------------------------------------------------------- texto fixo
_FRASE_POR_ID = {
    "AUTH-01": "em endpoints protegidos, validar a credencial ANTES de qualquer leitura ou escrita; sem credencial válida a "
               "resposta é 401 e nenhum dado é tocado",
    "ERR-01": "erros devolvem envelope padronizado e genérico: nunca expor stack trace, SQL, caminho interno ou mensagem de "
              "exceção ao cliente",
    "CORS-01": "CORS com lista explícita de origens permitidas; nunca curinga (*) junto com credenciais",
    "MASS-01": "vincular só os campos permitidos de cada DTO de entrada; papel, dono e preço nunca vêm do corpo da requisição",
    "LIM-01": "limitar tamanho de corpo, de página e de listagem em toda entrada; recusar o que passar do limite",
    "MET-01": "cada rota aceita só os métodos previstos; os demais respondem 405",
    "RATE-01": "aplicar limite de taxa nas rotas sensíveis (login, cadastro, recuperação de senha) e responder 429 acima dele",
    "IDOR-01": "toda leitura ou alteração de recurso confere se ele pertence ao usuário autenticado, não só se há autenticação",
    "QC-CPX-01": "manter funções simples: dividir a que passar do limite de complexidade ciclomática da Squad",
    "QC-LEN-01": "manter funções curtas: dividir a que passar do limite de linhas da Squad",
    "QC-PAR-01": "limitar os parâmetros de cada função; agrupar em objeto o que passar do limite",
    "QC-DUP-01": "extrair para uma função única o trecho de código duplicado",
    "QC-DOC-01": "documentar todo símbolo público com propósito, parâmetros e erros",
}
_FRASE_POR_PREFIXO = {
    "INJ": "tratar toda entrada externa como dado: validar tipo, tamanho e formato e usar consulta parametrizada, nunca "
           "concatenar texto em SQL, comando ou caminho",
    "HDR": "responder com os cabeçalhos de segurança HTTP padrão (HSTS, X-Content-Type-Options, CSP, X-Frame-Options)",
    "MAC": "a interface e a API devem resistir a uso caótico (clique repetido, entrada extrema, ordem inesperada) sem quebrar nem "
           "perder dado",
    "UI": "toda tela trata os estados de carregando, vazio e erro e bloqueia a ação duplicada",
    "QC-GAM": "não contornar a verificação de qualidade: a correção vale pelo comportamento, não por satisfazer a métrica",
}
_FRASE_POR_FAMILIA = {
    "SEC": "tratar este ponto como risco de segurança e aplicar os controles da família SEC da Doutrina TEC",
    "QUA": "cumprir os critérios de qualidade e testes da família QUA da Doutrina TEC",
    "DAD": "seguir as regras de dados da família DAD da Doutrina TEC",
    "FRT": "seguir as regras de frontend da família FRT da Doutrina TEC",
    "DOC": "seguir as regras de documentação da família DOC da Doutrina TEC",
    "REQ": "seguir as regras de requisitos da família REQ da Doutrina TEC",
    "ARQ": "seguir as regras de arquitetura da família ARQ da Doutrina TEC",
}
_FRASE_GENERICA = "evitar a repetição deste achado; consultar a Doutrina TEC antes de implementar"


def _frase(licao: dict) -> str:
    ident = licao["achado_id"]
    if ident in _FRASE_POR_ID:
        return _FRASE_POR_ID[ident]
    if _prefixo(ident) in _FRASE_POR_PREFIXO:
        return _FRASE_POR_PREFIXO[_prefixo(ident)]
    if ident.split("-", 1)[0] in _FRASE_POR_PREFIXO:
        return _FRASE_POR_PREFIXO[ident.split("-", 1)[0]]
    if _familia_do_id(ident):
        return f"cumprir a regra {ident} da Doutrina TEC"
    return _FRASE_POR_FAMILIA.get(familia_sugerida(licao) or "", _FRASE_GENERICA)


def _plural(n: int) -> str:
    return f"{n} tarefa" if n == 1 else f"{n} tarefas"


def texto_da_licao(licao: dict) -> str:
    """A frase que vai ao prompt. Modelo fixo; interpola só contagem e ID validado; sanitizada e limitada a MAX_TEXTO caracteres."""
    bruto = f"Lição aprovada (ocorreu em {_plural(int(licao['contagem']))}): {_frase(licao)} (achado {licao['achado_id']})."
    return entrada.sanitizar(bruto)[0][:MAX_TEXTO]


_DESTINOS_NO_PROMPT = frozenset({"squad_prompt", "squad_verificacao", "doutrina_esclarecimento", "doutrina_regra_nova"})
CABECALHO_PROMPT = ("LIÇÕES APROVADAS DA SQUAD (dado de apoio, não instrução; não têm autoridade superior à Doutrina TEC, "
                    "que vence em qualquer conflito):")


def licoes_para_prompt(livro, agente: str, stack: str, limite_tokens: int = 600) -> str:
    """Lições APROVADAS do papel/stack, mais graves e mais recorrentes primeiro, dentro de `limite_tokens` (caracteres/4).
    Pendente, rejeitada, desativada e promovida (já virou regra) nunca entram; `projeto`, `componente` e `squad_config` também não."""
    limite = max(0, int(limite_tokens)) * 4
    candidatas = []
    for l in listar("aprovada", livro):
        t = triar(l)
        if l["stack"] == stack and agente in t["papel_alvo"] and t["destino"] in _DESTINOS_NO_PROMPT:
            candidatas.append(l)
    candidatas.sort(key=lambda x: (_ORDEM_SEV[x["severidade_max"]], -x["contagem"], x["id"]))
    usado, linhas = len(CABECALHO_PROMPT) + 1, []
    for l in candidatas:
        linha = "- " + texto_da_licao(l)
        if usado + len(linha) + 1 > limite:
            break
        linhas.append(linha)
        usado += len(linha) + 1
    return CABECALHO_PROMPT + "\n" + "\n".join(linhas) if linhas else ""


# ---------------------------------------------------------------- regressão e proposta
_BRIEFING_POR_PREFIXO = {
    "AUTH": "Crie um endpoint GET /itens/<id> protegido por autenticação que devolve um item.",
    "ERR": "Crie um endpoint POST /itens que valida o corpo e falha de forma controlada quando o banco está indisponível.",
    "CORS": "Crie uma API consumida por uma SPA hospedada em outra origem.",
    "MASS": "Crie um endpoint de cadastro de usuário que aceita nome e e-mail.",
    "LIM": "Crie um endpoint de listagem paginada de itens.",
    "MET": "Crie um recurso /itens que só permite leitura e criação.",
    "RATE": "Crie um endpoint de login por e-mail e senha.",
    "IDOR": "Crie um endpoint que devolve um pedido pelo id, para o usuário dono do pedido.",
    "INJ": "Crie um endpoint de busca de itens por nome.",
    "HDR": "Crie uma API HTTP simples com um endpoint de saúde.",
    "QC": "Crie um módulo de cálculo de frete com regras por região.",
    "MAC": "Crie uma tela de cadastro com formulário e listagem.",
    "UI": "Crie uma tela de cadastro com formulário e listagem.",
}


def _verificador(licao: dict) -> dict:
    ident, prefixo = licao["achado_id"], licao["achado_id"].split("-", 1)[0]
    if prefixo in _PREFIXOS_KIT:
        tipo = "kit_ataque"
    elif prefixo == "QC":
        tipo = "qualidade"
    elif prefixo in ("MAC", "UI"):
        tipo = "macaco"
    else:
        tipo = "revisor"
    return {"tipo": tipo, "exige": "nenhum achado com o ID de origem", "id_proibido": ident}


def caso_de_regressao(licao: dict) -> dict:
    """Caso para o sistema de evals: briefing mínimo de modelo fixo e o verificador esperado por categoria. JSON puro."""
    ident = licao["achado_id"]
    briefing = _BRIEFING_POR_PREFIXO.get(ident.split("-", 1)[0])
    if briefing is None:
        briefing = f"Crie um serviço com um recurso simples de cadastro e consulta, aplicando a regra {ident}." \
            if _familia_do_id(ident) else "Crie um serviço com um recurso simples de cadastro e consulta."
    return {"versao": 1, "id": "reg-" + licao["id"], "licao": licao["id"], "stack": licao["stack"],
            "origem": {"agente": licao["agente"], "achado_id": ident, "categoria": licao["categoria"],
                       "severidade_max": licao["severidade_max"]},
            "papel_alvo": papel_alvo(licao), "briefing": briefing, "verificador": _verificador(licao)}


def proposta_doutrina(licao: dict, ids_doutrina: Optional[Iterable[str]] = None) -> str:
    """Markdown de proposta para revisão humana (regra rascunho, ADR rascunho e checklist). Só dados estruturados e frases fixas.
    Levanta NaoCandidata se não houver reincidência suficiente ou se o destino não for a Doutrina."""
    t = triar(licao, ids_doutrina)
    if not t["candidata_doutrina"]:
        raise NaoCandidata(f"{licao['id']}: destino {t['destino']} ou reincidência insuficiente (mínimo {LIMIAR_REINCIDENCIA} "
                           "tarefas, ou 1 CRITICO de segurança)")
    ident, esclarece = licao["achado_id"], t["destino"] == "doutrina_esclarecimento"
    fam = familia_sugerida(licao)
    nivel = "MUST" if licao["severidade_max"] in ("CRITICO", "ALTO") else "SHOULD"
    tarefas = ", ".join(f"`{x}`" for x in licao["tarefas"])
    titulo = f"Esclarecer a regra {ident}" if esclarece else f"Nova regra geral a partir do achado {ident}"
    L = [f"# Proposta de Doutrina: {titulo}", "",
         "> Rascunho gerado por modelo fixo de frases a partir de dados estruturados do Livro de Lições. Não altera a Doutrina: "
         "um humano revisa, escreve a regra e abre o PR no repositório da Doutrina.", "",
         "## Evidência", "",
         f"- Lição: `{licao['id']}` (estado: {licao['estado']})",
         f"- Agente de origem: {licao['agente']} · achado `{ident}` · categoria `{licao['categoria']}` · stack `{licao['stack']}`",
         f"- Ocorrências: {_plural(licao['contagem'])} distintas (limiar: {LIMIAR_REINCIDENCIA}, ou 1 CRITICO de segurança)",
         f"- Tarefas: {tarefas}",
         f"- Severidade máxima: {licao['severidade_max']}",
         f"- Primeira e última ocorrência: {licao['primeira_ocorrencia']} / {licao['ultima_ocorrencia']}",
         f"- Hash do conjunto de evidências: `{licao['evidencia_hash']}`",
         f"- Triagem: `{t['destino']}` — {t['motivo']}", ""]
    if esclarece:
        L += ["## Diff sugerido na regra existente", "",
              f"Regra: **{ident}**. Os agentes a violaram em {_plural(licao['contagem'])} mesmo com ela citada; o texto atual "
              "provavelmente é ambíguo.", "", "```diff",
              f"- - **{ident}** <MUST|SHOULD> — <texto atual da regra, copiar da Doutrina> · verif: <manter>",
              f"+ - **{ident}** <MUST|SHOULD> — <texto atual da regra> <esclarecimento a redigir pelo humano> · verif: <manter>",
              "```", ""]
    else:
        L += ["## Regra rascunho", "",
              f"Família sugerida: {fam or '<FAMILIA>'}" + (f" ({_NOME_FAMILIA[fam]})" if fam in _NOME_FAMILIA else "") + ". "
              "O ID definitivo e a área são escolhidos pelo revisor da Doutrina.", "", "```markdown",
              f"- **<FAMILIA>-<AREA>-<NN>** {nivel} — {_frase(licao)[0].upper() + _frase(licao)[1:]} · verif: revisao · evidencia: {licao['id']}",
              "```", ""]
    L += ["## Rascunho de ADR", "",
          f"- **Contexto:** o achado `{ident}` apareceu em {_plural(licao['contagem'])} da Squad "
          f"(severidade máxima {licao['severidade_max']}) e a prevenção local no prompt não bastou ou não existe.",
          "- **Decisão:** " + ("esclarecer o texto da regra existente, conforme o diff acima." if esclarece
                              else "adotar a regra rascunhada acima na família indicada."),
          "- **Consequências:** os agentes e revisores passam a ter a norma na fonte da verdade; exige regerar e redistribuir a "
          "Doutrina; a lição deixa de precisar do prompt depois da distribuição.",
          "- **Alternativas:** manter só a lição no prompt da Squad (não generaliza para outros consumidores); criar verificação "
          "determinística na Squad (não cobre o que não é detectável por código); não fazer nada (o achado volta).", "",
          "## Checklist", "",
          "- [ ] Revisão humana do rascunho e escolha do ID definitivo",
          "- [ ] Escrever a regra no padrão da família, sem copiar texto de modelo",
          "- [ ] Rodar `validar` na Doutrina",
          "- [ ] Rodar `gerar` na Doutrina",
          "- [ ] Rodar os testes da Doutrina",
          "- [ ] Distribuir a nova versão aos consumidores (Squad e demais)",
          f"- [ ] Marcar a lição `{licao['id']}` como promovida no Livro de Lições", ""]
    return "\n".join(L)


def exportar_propostas(livro, pasta, ids_doutrina: Optional[Iterable[str]] = None) -> dict:
    """Grava `proposta-<id>.md` para cada lição candidata em estado aprovada/promovida. Nome estável; arquivo que já existe não é
    tocado (pode ter edição humana). Devolve {criadas, existentes}."""
    destino = Path(pasta)
    destino.mkdir(parents=True, exist_ok=True)
    ids = list(ids_doutrina) if ids_doutrina is not None else None
    criadas, existentes = [], []
    for l in listar(livro=livro):
        if l["estado"] not in ("aprovada", "promovida") or not triar(l, ids)["candidata_doutrina"]:
            continue
        arquivo = destino / f"proposta-{l['id']}.md"
        try:
            with open(arquivo, "x", encoding="utf-8", newline="\n") as f:
                f.write(proposta_doutrina(l, ids))
            criadas.append(str(arquivo))
        except FileExistsError:
            existentes.append(str(arquivo))
    return {"criadas": criadas, "existentes": existentes}

"""
Verificadores em código da qualidade da entrega da SquadTI. Só stdlib, sem modelo e sem rede.

Cada verificador é uma função pura `(workspace, api, caso) -> {"nome", "passou", "detalhe"}`:
- `workspace`: pasta com os arquivos da tarefa (o driver a monta a partir de `/arquivo`; nos testes é uma pasta falsa);
- `api`: o que a API respondeu: `detalhe` (GET /api/tarefas/{id}), `auditoria`, `mensagens` e `duracao_s` (relógio do driver);
- `caso`: o caso dourado (limites, cobertura mínima, verificadores extras).

Regras de projeto:
- Falha fechada: relatório ausente, corrompido, grande demais ou fora do workspace = não passou. Nenhum verificador levanta exceção.
- Nada de valor de segredo no resultado: segredos aparecem só como tipo e arquivo:linha.
- Entrada hostil (caminho com `..`, link simbólico para fora, JSON enorme) é recusada por `_seguro`/`_ler_json`.
- Os relatórios hacker/macaco/carga ainda não têm formato fixado no orquestrador: o leitor é tolerante (ver `_graves`) e exige
  só que existam, sejam JSON válido e não declarem `aprovado: false`.
"""
import functools
import json
import re
import unicodedata
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Dict, List, Optional, Tuple

MAX_JSON = 2_000_000
MAX_TEXTO = 1_000_000
MAX_ARQUIVOS_VARRIDOS = 5000
MAX_DETALHE = 500
RELATORIOS = "tests/reports/"
PORTOES_COM_APROVADO = ("qa_report.json", "security_report.json", "devops_report.json")  # `aprovado` obrigatório e verdadeiro
PORTOES_DE_EXECUCAO = ("hacker_report.json", "macaco_report.json", "carga_report.json")   # existir e não declarar aprovado: false
GRAVES = {"CRITICO", "CRITICAL", "ALTO", "ALTA", "HIGH"}
PASTAS_IGNORADAS = {"node_modules", ".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "dist", "build"}
MARCADOR_API = "[linha omitida: possível segredo]"  # o que GET /arquivo põe no lugar de uma linha com padrão de segredo

# Mesmos padrões do orquestrador (segredos.py), copiados de propósito: este pacote não importa módulos do orquestrador.
PADROES_SEGREDO = {
    "chave-privada": re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"),
    "chave-aws": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "token-github": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    "token-slack": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),
    "chave-api-sk": re.compile(r"\bsk-[A-Za-z0-9_-]{24,}\b"),
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    "senha-em-connection-string": re.compile(r"(?i)\b(?:password|pwd)\s*=\s*(?!\s*[;\"'<{$%])[^;\s\"']{4,}"),
    "senha-literal": re.compile(r"""(?i)\b(?:password|passwd|senha|secret|api[_-]?key|token)\b["']?\s*[:=]\s*["'](?!\s*["'])(?!\$\{|<|\{\{|%|your|change|xxx|example|exemplo)[^"'\s]{8,}["']"""),
}

OBRIGATORIOS: Dict[str, Tuple[str, ...]] = {
    "README": ("README.md",),
    "PRD técnico": ("docs/arquitetura/PRD_TECNICO.md", "docs/arquitetura/prd_tecnico.md"),
    "OpenAPI": ("contracts/openapi.yaml", "contracts/openapi.yml", "contracts/openapi.json", "openapi.yaml", "openapi.yml", "openapi.json"),
    "Dockerfile": ("Dockerfile",),
    ".gitignore": (".gitignore",),
    "proveniência": ("docs/proveniencia.json",),
}


class EntradaInvalida(Exception):
    """Entrada recusada (caminho fora do workspace, arquivo grande demais, JSON inválido). A mensagem é segura para exibir."""


# ---------------------------------------------------------------- leitura segura
def _seguro(ws: Path, rel: str) -> Path:
    """Resolve `rel` dentro de `ws` ou levanta EntradaInvalida (absoluto, '..', unidade, link que escapa)."""
    bruto = (rel or "").strip().replace("\\", "/")
    if not bruto or bruto.startswith("/") or ":" in bruto or ".." in PurePosixPath(bruto).parts:
        raise EntradaInvalida(f"caminho recusado: {rel!r}")
    destino = ws / bruto
    raiz = ws.resolve()
    resolvido = destino.resolve()
    if raiz not in resolvido.parents:
        raise EntradaInvalida(f"caminho fora do workspace: {rel!r}")
    return resolvido


def _ler_texto(ws: Path, rel: str, limite: int = MAX_TEXTO) -> str:
    destino = _seguro(ws, rel)
    if not destino.is_file():
        raise EntradaInvalida(f"arquivo ausente: {rel}")
    if destino.stat().st_size > limite:
        raise EntradaInvalida(f"arquivo grande demais (> {limite} bytes): {rel}")
    return destino.read_text(encoding="utf-8", errors="replace")


def _ler_json(ws: Path, rel: str) -> Any:
    texto = _ler_texto(ws, rel, MAX_JSON)
    try:
        return json.loads(texto)
    except ValueError as e:
        raise EntradaInvalida(f"JSON corrompido: {rel}") from e


def _norm(texto: Any) -> str:
    base = unicodedata.normalize("NFKD", str(texto))
    return "".join(c for c in base if not unicodedata.combining(c)).upper().strip()


def _achar(ws: Path, candidatos: Tuple[str, ...]) -> Optional[str]:
    for rel in candidatos:
        try:
            destino = _seguro(ws, rel)
        except EntradaInvalida:
            continue
        if destino.is_file() and destino.stat().st_size > 0:
            return rel
    return None


def _arquivos_de_texto(ws: Path, padroes: List[str], maximo: int = 200) -> List[str]:
    """Arquivos do workspace que casam com algum glob (relativo, sem '..'), sem links e sem pastas de dependência."""
    achados: List[str] = []
    for padrao in padroes:
        if not isinstance(padrao, str) or not padrao or padrao.startswith("/") or ".." in PurePosixPath(padrao).parts or ":" in padrao:
            raise EntradaInvalida(f"glob recusado: {padrao!r}")
        for p in sorted(ws.glob(padrao)):
            rel = p.relative_to(ws).as_posix()
            if p.is_file() and not p.is_symlink() and not (PASTAS_IGNORADAS & set(p.relative_to(ws).parts)) and rel not in achados:
                achados.append(rel)
            if len(achados) >= maximo:
                return achados
    return achados


# ---------------------------------------------------------------- decorador
Resultado = Dict[str, Any]


def verificador(nome: str) -> Callable:
    """Envolve a função `(ws, api, caso) -> (passou, detalhe)` no contrato público e garante que nunca levanta exceção."""
    def deco(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def interno(ws, api, caso) -> Resultado:
            try:
                passou, detalhe = fn(Path(ws), api if isinstance(api, dict) else {}, caso if isinstance(caso, dict) else {})
            except EntradaInvalida as e:
                passou, detalhe = False, str(e)
            except Exception as e:  # um verificador com defeito reprova o caso; não derruba a rodada nem vaza texto da exceção
                passou, detalhe = False, f"erro inesperado no verificador: {type(e).__name__}"
            return {"nome": nome, "passou": bool(passou), "detalhe": str(detalhe)[:MAX_DETALHE]}
        interno.nome = nome  # type: ignore[attr-defined]
        return interno
    return deco


def _detalhe_api(api: dict) -> dict:
    d = api.get("detalhe")
    return d if isinstance(d, dict) else {}


# ---------------------------------------------------------------- verificadores gerais
@verificador("desfecho_concluida")
def desfecho_concluida(ws, api, caso):
    sit = _detalhe_api(api).get("situacao")
    estado = sit.get("estado") if isinstance(sit, dict) else None
    return estado == "concluida", f"estado final: {estado}"


@verificador("build_e_testes")
def build_e_testes(ws, api, caso):
    rel = _ler_json(ws, RELATORIOS + "qa_report.json")
    etapas = rel.get("etapas") if isinstance(rel, dict) else None
    if not isinstance(etapas, list):
        return False, "qa_report.json sem lista de etapas"
    por_nome = {e.get("etapa"): e for e in etapas if isinstance(e, dict)}
    faltando = [n for n in ("backend-build", "backend-testes") if n not in por_nome]
    if faltando:
        return False, f"etapas ausentes no QA: {', '.join(faltando)}"
    ruins = [n for n in ("backend-build", "backend-testes") if por_nome[n].get("codigo") != 0]
    return not ruins, "build e testes passaram" if not ruins else f"etapas com falha: {', '.join(ruins)}"


@verificador("cobertura")
def cobertura(ws, api, caso):
    minimo = caso.get("cobertura_minima", 90)
    if isinstance(minimo, bool) or not isinstance(minimo, (int, float)) or not 0 < minimo <= 100:
        minimo = 90
    rel = _ler_json(ws, RELATORIOS + "qa_report.json")
    etapas = rel.get("etapas") if isinstance(rel, dict) else None
    etapa = next((e for e in etapas if isinstance(e, dict) and e.get("etapa") == "cobertura"), None) if isinstance(etapas, list) else None
    det = etapa.get("detalhe") if isinstance(etapa, dict) else None
    if not isinstance(det, dict):
        return False, "qa_report.json sem etapa de cobertura"
    linha, ramo = det.get("linha"), det.get("ramo")
    nums = [v for v in (linha, ramo) if isinstance(v, (int, float)) and not isinstance(v, bool)]
    if not nums or not isinstance(linha, (int, float)) or isinstance(linha, bool):
        return False, "cobertura não medida (sem percentual de linha)"
    if det.get("minimo") == 0:
        return False, "gate de cobertura foi desligado na configuração (minimo = 0)"
    ok = linha >= minimo and all(v >= minimo for v in nums)
    return ok, f"linha {linha}%, ramo {ramo if ramo is not None else 'n/d'}% (mínimo {minimo}%)"


def _graves(obj: Any, prof: int = 0) -> int:
    """Quantos achados CRITICO/ALTO há no JSON: dicionários com `severidade`/`severity` e resumos do tipo {"ALTO": 2}."""
    if prof > 20:
        return 0
    total = 0
    if isinstance(obj, dict):
        sev = obj.get("severidade", obj.get("severity"))
        if isinstance(sev, str) and _norm(sev) in GRAVES:
            total += 1
        for chave, valor in obj.items():
            if isinstance(chave, str) and _norm(chave) in GRAVES:
                if isinstance(valor, int) and not isinstance(valor, bool) and valor > 0:
                    total += valor
                elif isinstance(valor, list):
                    total += len(valor)
            total += _graves(valor, prof + 1)
    elif isinstance(obj, list):
        total += sum(_graves(v, prof + 1) for v in obj[:5000])
    return total


@verificador("sem_achados_graves")
def sem_achados_graves(ws, api, caso):
    contagem = {}
    for nome in ("hacker_report.json", "macaco_report.json"):
        contagem[nome] = _graves(_ler_json(ws, RELATORIOS + nome))  # ausente/corrompido levanta e reprova
    ruins = {n: c for n, c in contagem.items() if c}
    return not ruins, ("nenhum achado CRITICO/ALTO em hacker e macaco" if not ruins
                       else "achados CRITICO/ALTO: " + ", ".join(f"{n}={c}" for n, c in ruins.items()))


@verificador("portoes_verdes")
def portoes_verdes(ws, api, caso):
    falhas: List[str] = []
    ver = _detalhe_api(api).get("verificacoes")
    ver = ver if isinstance(ver, dict) else {}
    for campo in ("tests_passed", "review_passed", "security_passed", "devops_passed"):
        if ver.get(campo) is not True:
            falhas.append(f"estado.{campo}")
    for nome in PORTOES_COM_APROVADO + PORTOES_DE_EXECUCAO:
        try:
            rel = _ler_json(ws, RELATORIOS + nome)
        except EntradaInvalida as e:
            falhas.append(str(e))
            continue
        aprovado = rel.get("aprovado") if isinstance(rel, dict) else None
        if not isinstance(rel, dict):
            falhas.append(f"{nome}: não é um objeto JSON")
        elif (nome in PORTOES_COM_APROVADO and aprovado is not True) or aprovado is False:
            falhas.append(f"{nome}: aprovado={aprovado}")
    return not falhas, "todos os portões verdes" if not falhas else "; ".join(falhas)


@verificador("arquivos_obrigatorios")
def arquivos_obrigatorios(ws, api, caso):
    ausentes = [rotulo for rotulo, candidatos in OBRIGATORIOS.items() if _achar(ws, candidatos) is None]
    return not ausentes, "todos presentes" if not ausentes else f"ausentes ou vazios: {', '.join(ausentes)}"


def varrer_segredos(ws: Path) -> List[Dict[str, Any]]:
    """[{tipo, arquivo, linha}] com padrões de segredo no workspace. Nunca guarda o valor achado."""
    achados: List[Dict[str, Any]] = []
    raiz = ws.resolve()
    vistos = 0
    for p in sorted(ws.rglob("*")):
        rel_partes = p.relative_to(ws).parts
        if PASTAS_IGNORADAS & set(rel_partes) or p.is_symlink() or not p.is_file():
            continue
        vistos += 1
        if vistos > MAX_ARQUIVOS_VARRIDOS:
            achados.append({"tipo": "limite-de-arquivos-varridos", "arquivo": "", "linha": 0})
            break
        rel = p.relative_to(ws).as_posix()
        try:
            if raiz not in p.resolve().parents:
                continue
            if p.stat().st_size > MAX_TEXTO:
                achados.append({"tipo": "arquivo-grande-demais-para-varrer", "arquivo": rel, "linha": 0})
                continue
            texto = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for n, linha in enumerate(texto.splitlines(), 1):
            if MARCADOR_API in linha:
                achados.append({"tipo": "marcador-da-api", "arquivo": rel, "linha": n})
                continue
            tipo = next((t for t, rx in PADROES_SEGREDO.items() if rx.search(linha)), None)
            if tipo:
                achados.append({"tipo": tipo, "arquivo": rel, "linha": n})
    return achados


@verificador("sem_segredos")
def sem_segredos(ws, api, caso):
    achados = varrer_segredos(ws)
    if not achados:
        return True, "nenhum padrão de segredo encontrado"
    return False, "; ".join(f"{a['tipo']} em {a['arquivo']}:{a['linha']}" for a in achados[:10])


@verificador("proveniencia_doutrina")
def proveniencia_doutrina(ws, api, caso):
    prov = _ler_json(ws, "docs/proveniencia.json")
    usada = _detalhe_api(api).get("doutrina")
    if not isinstance(prov, dict) or not isinstance(usada, dict):
        return False, "proveniência ou Doutrina da tarefa ilegível"
    d = prov.get("doutrina") if isinstance(prov.get("doutrina"), dict) else {}
    if not usada.get("hash") or not usada.get("versao"):
        return False, "a API não informou versão e hash da Doutrina usada"
    ok = d.get("hash") == usada.get("hash") and d.get("versao") == usada.get("versao")
    return ok, "versão e hash da Doutrina batem" if ok else "a proveniência cita outra versão/hash da Doutrina que a tarefa usou"


def _numero(valor: Any) -> Optional[float]:
    return float(valor) if isinstance(valor, (int, float)) and not isinstance(valor, bool) else None


@verificador("limites_tokens_tempo")
def limites_tokens_tempo(ws, api, caso):
    lim = caso.get("limites") if isinstance(caso.get("limites"), dict) else {}
    lim_tokens, lim_tempo = _numero(lim.get("tokens")), _numero(lim.get("tempo_s"))
    if lim_tokens is None or lim_tempo is None:
        return False, "o caso não declara limites.tokens e limites.tempo_s"
    totais = (api.get("auditoria") or {}).get("totais") if isinstance(api.get("auditoria"), dict) else None
    tokens = _numero((totais or {}).get("tokens"))
    tempo = _numero(api.get("duracao_s"))
    if tokens is None or tempo is None:
        return False, "tokens ou duração não medidos"
    falhas = []
    if tokens > lim_tokens:
        falhas.append(f"tokens {int(tokens)} > {int(lim_tokens)}")
    if tempo > lim_tempo:
        falhas.append(f"tempo {round(tempo)}s > {int(lim_tempo)}s")
    return not falhas, "; ".join(falhas) or f"tokens {int(tokens)}/{int(lim_tokens)}, tempo {round(tempo)}s/{int(lim_tempo)}s"


@verificador("conversa_com_chefe")
def conversa_com_chefe(ws, api, caso):
    msgs = (api.get("mensagens") or {}).get("mensagens") if isinstance(api.get("mensagens"), dict) else None
    if not isinstance(msgs, list):
        return False, "conversa com o CHEFE indisponível"
    do_chefe = sum(1 for m in msgs if isinstance(m, dict) and m.get("de") == "chefe" and str(m.get("texto") or "").strip())
    do_usuario = sum(1 for m in msgs if isinstance(m, dict) and m.get("de") == "usuario")
    return do_chefe > 0 and do_usuario > 0, f"mensagens do CHEFE: {do_chefe}, do usuário: {do_usuario}"


# ---------------------------------------------------------------- verificador parametrizável dos casos
def conteudo_contem(ws: Path, api: dict, caso: dict, params: dict) -> Resultado:
    """Verificador por caso: arquivos que casam com `glob` (lista) devem conter todos os `termos_todos` e algum dos `termos_qualquer`
    (sem diferenciar maiúsculas). O texto de todos os arquivos casados é considerado junto."""
    nome = str(params.get("nome") or "conteudo_contem")[:80]

    @verificador(nome)
    def _interno(ws, api, caso):
        globs = params.get("glob")
        if isinstance(globs, str):
            globs = [globs]
        if not isinstance(globs, list) or not globs:
            return False, "verificador do caso sem `glob`"
        arquivos = _arquivos_de_texto(ws, globs)
        if not arquivos:
            return False, f"nenhum arquivo casa com {globs}"
        texto = "\n".join(_ler_texto(ws, a) for a in arquivos).lower()
        todos = [str(t).lower() for t in params.get("termos_todos") or []]
        algum = [str(t).lower() for t in params.get("termos_qualquer") or []]
        faltam = [t for t in todos if t not in texto]
        if faltam:
            return False, f"termos ausentes: {', '.join(faltam)}"
        if algum and not any(t in texto for t in algum):
            return False, f"nenhum destes termos aparece: {', '.join(algum)}"
        return True, f"{len(arquivos)} arquivo(s) conferidos"
    return _interno(ws, api, caso)


TIPOS_DO_CASO = {"conteudo_contem": conteudo_contem}

GERAIS = [desfecho_concluida, build_e_testes, cobertura, sem_achados_graves, portoes_verdes, arquivos_obrigatorios, sem_segredos,
          proveniencia_doutrina, limites_tokens_tempo, conversa_com_chefe]


def executar(ws, api: dict, caso: dict) -> List[Resultado]:
    """Roda os verificadores gerais e os do caso. Nunca levanta: um verificador do caso malformado vira uma reprovação."""
    saida = [v(ws, api, caso) for v in GERAIS]
    extras = caso.get("verificadores_extra") if isinstance(caso, dict) else None
    for params in extras if isinstance(extras, list) else []:
        tipo = params.get("tipo") if isinstance(params, dict) else None
        fn = TIPOS_DO_CASO.get(tipo)
        if fn is None:
            saida.append({"nome": "verificador_do_caso", "passou": False, "detalhe": f"tipo de verificador desconhecido: {str(tipo)[:40]!r}"})
            continue
        try:
            saida.append(fn(Path(ws), api, caso, params))
        except Exception as e:
            saida.append({"nome": "verificador_do_caso", "passou": False, "detalhe": f"erro inesperado: {type(e).__name__}"})
    return saida

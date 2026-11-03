"""
Métricas determinísticas de qualidade de código: o que o Sênior Master mede ANTES de pedir opinião a um modelo.

Complexidade, tamanho de função, parâmetros, duplicação, documentação da API pública e "gambiarras" (catch vazio, TODO, código comentado,
`as any`, sobras de depuração). Python é analisado pela AST; C# e TypeScript por varredura de chaves (aproximada, mas estável e sem
dependência). Cada violação tem ID próprio (QC-*), severidade e arquivo:linha: o modelo não é necessário para saber que uma função tem 300 linhas.
"""
import ast
import hashlib
import re
from pathlib import Path
from typing import Dict, List, Tuple

PREFIXOS = ("src/", "app/", "frontend/src/")
EXTENSOES = {".py": "python", ".cs": "csharp", ".ts": "typescript", ".tsx": "typescript", ".js": "typescript", ".jsx": "typescript"}
IGNORAR = ("/node_modules/", "/bin/", "/obj/", "/migrations/", "/Migrations/", "/dist/", "/.venv/", ".g.cs", ".Designer.cs", ".d.ts")
MAX_ARQUIVOS = 400
MAX_BYTES = 400_000

# limites: (aviso, bloqueia). Acima do primeiro vira achado MEDIO; acima do segundo, ALTO (bloqueia a entrega).
LIMITES = {"complexidade": (12, 20), "linhas_funcao": (60, 120), "parametros": (6, 10), "duplicacao_perc": (5.0, 15.0), "sem_doc_perc": (20.0, 50.0)}
JANELA_DUPLICACAO = 6
IDS = frozenset({"QC-CPX-01", "QC-LEN-01", "QC-PAR-01", "QC-DUP-01", "QC-DOC-01", "QC-GAM-01", "QC-GAM-02", "QC-GAM-03", "QC-GAM-04"})

_RE_RAMOS_C = re.compile(r"\b(if|for|foreach|while|case|catch)\b|&&|\|\||\?\s*[^?:]+:")
_RE_METODO_CS = re.compile(r"^[ \t]*(?:\[[^\]]*\]\s*)*(?:public|private|protected|internal)[^;{=()]*\([^;{}]*\)\s*(?:where [^{]+)?\{", re.MULTILINE)
_RE_FUNCAO_TS = re.compile(r"^[ \t]*(?:export\s+)?(?:async\s+)?function\s+\w+[^{;]*\{|^[ \t]*(?:export\s+)?const\s+\w+\s*=\s*(?:async\s*)?\([^)]*\)[^={;]*=>\s*\{",
                           re.MULTILINE)
_RE_GAMBIARRA = [
    ("QC-GAM-01", "BAIXO", re.compile(r"\b(TODO|FIXME|HACK|XXX)\b"), "marcador de pendência ou gambiarra no código"),
    ("QC-GAM-02", "ALTO", re.compile(r"catch\s*(\([^)]*\))?\s*\{\s*\}|except\s*(\w+(\s+as\s+\w+)?)?\s*:\s*pass\b|except\s*:\s*$"),
     "tratamento de erro engolido (catch/except vazio ou genérico sem ação)"),
    ("QC-GAM-03", "MEDIO", re.compile(r"\bas\s+any\b|:\s*any\b|# type:\s*ignore|#pragma warning disable|eslint-disable|# noqa\b"),
     "supressão de verificação do compilador ou linter"),
    ("QC-GAM-04", "BAIXO", re.compile(r"\bConsole\.WriteLine\(|\bconsole\.log\(|^\s*print\("), "sobra de depuração no código de produção"),
]
_RE_CODIGO_COMENTADO = re.compile(r"^\s*(//|#)\s*(?:[\w.\[\]\"']+\s*=\s*.+|\w+\(.*\)\s*;?|(?:if|for|while|return|var|let|const|def|class)\b.*)$")


def arquivos_de_codigo(raiz: Path) -> List[Path]:
    saida = []
    for p in sorted(raiz.rglob("*")):
        rel = "/" + p.relative_to(raiz).as_posix()
        if p.suffix not in EXTENSOES or not p.is_file() or p.is_symlink() or any(i in rel for i in IGNORAR):
            continue
        r = rel.lstrip("/")
        if r.startswith(PREFIXOS) and "/tests/" not in rel and "/test/" not in rel and not r.startswith("tests/"):
            if p.stat().st_size <= MAX_BYTES:
                saida.append(p)
    return saida[:MAX_ARQUIVOS]


def _sev(valor: float, chave: str) -> str:
    aviso, bloqueia = LIMITES[chave]
    return "ALTO" if valor > bloqueia else "MEDIO" if valor > aviso else ""


class Violacao(dict):
    pass


def _v(id_: str, sev: str, arquivo: str, linha: int, desc: str) -> dict:
    return {"id": id_, "severidade": sev, "arquivo": arquivo, "linha": linha, "descricao": desc}


# ---------------------------------------------------------------- Python
def _complexidade_py(no: ast.AST) -> int:
    n = 1
    for f in ast.walk(no):
        if isinstance(f, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler, ast.IfExp, ast.With, ast.AsyncWith, ast.Assert)):
            n += 1
        elif isinstance(f, ast.BoolOp):
            n += len(f.values) - 1
        elif isinstance(f, ast.comprehension):
            n += 1 + len(f.ifs)
    return n


def analisar_python(rel: str, texto: str) -> Tuple[List[dict], int, int]:
    """(violações, APIs públicas, APIs públicas sem docstring)."""
    try:
        arvore = ast.parse(texto)
    except SyntaxError as e:
        return [_v("QC-CPX-01", "ALTO", rel, e.lineno or 1, "o arquivo não é Python válido (erro de sintaxe)")], 0, 0
    achados, publicas, sem_doc = [], 0, 0
    for no in ast.walk(arvore):
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fim = getattr(no, "end_lineno", no.lineno)
            linhas = fim - no.lineno + 1
            cpx = _complexidade_py(no)
            pars = len(no.args.args) + len(no.args.kwonlyargs) - (1 if no.args.args and no.args.args[0].arg in ("self", "cls") else 0)
            if (s := _sev(cpx, "complexidade")):
                achados.append(_v("QC-CPX-01", s, rel, no.lineno, f"{no.name}: complexidade ciclomática {cpx} (limite {LIMITES['complexidade'][0]})"))
            if (s := _sev(linhas, "linhas_funcao")):
                achados.append(_v("QC-LEN-01", s, rel, no.lineno, f"{no.name}: {linhas} linhas (limite {LIMITES['linhas_funcao'][0]})"))
            if (s := _sev(pars, "parametros")):
                achados.append(_v("QC-PAR-01", s, rel, no.lineno, f"{no.name}: {pars} parâmetros (limite {LIMITES['parametros'][0]})"))
            if not no.name.startswith("_"):
                publicas += 1
                if not ast.get_docstring(no):
                    sem_doc += 1
        elif isinstance(no, ast.ClassDef) and not no.name.startswith("_"):
            publicas += 1
            if not ast.get_docstring(no):
                sem_doc += 1
    return achados, publicas, sem_doc


# ---------------------------------------------------------------- C# e TypeScript
def _corpo_por_chaves(texto: str, inicio_chave: int) -> int:
    """Índice do fecho da chave que abre em `inicio_chave` (ignora texto entre aspas de forma simples). -1 se não fecha."""
    nivel = 0
    em_texto = None
    i = inicio_chave
    while i < len(texto):
        c = texto[i]
        if em_texto:
            if c == "\\":
                i += 1
            elif c == em_texto:
                em_texto = None
        elif c in "\"'`":
            em_texto = c
        elif c == "{":
            nivel += 1
        elif c == "}":
            nivel -= 1
            if nivel == 0:
                return i
        i += 1
    return -1


def analisar_chaves(rel: str, texto: str, linguagem: str) -> Tuple[List[dict], int, int]:
    padrao = _RE_METODO_CS if linguagem == "csharp" else _RE_FUNCAO_TS
    achados, publicas, sem_doc = [], 0, 0
    for m in padrao.finditer(texto):
        abre = m.end() - 1
        fecha = _corpo_por_chaves(texto, abre)
        if fecha < 0:
            continue
        corpo = texto[abre:fecha]
        linha = texto.count("\n", 0, m.start()) + 1
        linhas = corpo.count("\n") + 1
        cpx = 1 + len(_RE_RAMOS_C.findall(corpo))
        assinatura = texto[m.start():abre]
        nome = (re.search(r"(\w+)\s*\(", assinatura) or re.search(r"(\w+)\s*=", assinatura) or re.search(r"function\s+(\w+)", assinatura))
        nome = nome.group(1) if nome else "?"
        pars = len([p for p in re.search(r"\(([^)]*)\)", assinatura).group(1).split(",") if p.strip()]) if re.search(r"\(([^)]*)\)", assinatura) else 0
        if (s := _sev(cpx, "complexidade")):
            achados.append(_v("QC-CPX-01", s, rel, linha, f"{nome}: complexidade ciclomática aproximada {cpx} (limite {LIMITES['complexidade'][0]})"))
        if (s := _sev(linhas, "linhas_funcao")):
            achados.append(_v("QC-LEN-01", s, rel, linha, f"{nome}: {linhas} linhas (limite {LIMITES['linhas_funcao'][0]})"))
        if (s := _sev(pars, "parametros")):
            achados.append(_v("QC-PAR-01", s, rel, linha, f"{nome}: {pars} parâmetros (limite {LIMITES['parametros'][0]})"))
        publico = ("public" in assinatura.split("(")[0]) if linguagem == "csharp" else ("export" in assinatura)
        if publico:
            publicas += 1
            antes = texto[max(0, m.start() - 400):m.start()].rstrip()
            documentado = antes.endswith("*/") or antes.splitlines()[-1:] and antes.splitlines()[-1].lstrip().startswith("///")
            if not documentado:
                sem_doc += 1
    return achados, publicas, sem_doc


# ---------------------------------------------------------------- gambiarras e duplicação
def gambiarras(rel: str, texto: str) -> List[dict]:
    achados, comentadas = [], 0
    for numero, linha in enumerate(texto.splitlines(), 1):
        for id_, sev, rx, desc in _RE_GAMBIARRA:
            if rx.search(linha):
                achados.append(_v(id_, sev, rel, numero, desc))
        if _RE_CODIGO_COMENTADO.match(linha):
            comentadas += 1
    if comentadas >= 5:
        achados.append(_v("QC-GAM-01", "MEDIO", rel, 1, f"{comentadas} linhas de código comentado (apague: o git guarda o histórico)"))
    return achados


def _normalizar(linha: str) -> str:
    return re.sub(r"\s+", " ", linha.strip())


def duplicacao(arquivos: Dict[str, str]) -> Tuple[float, List[dict]]:
    """Percentual de linhas em janelas repetidas (>= JANELA_DUPLICACAO linhas significativas iguais em dois lugares) e os pares mais graves."""
    janelas: Dict[str, List[Tuple[str, int]]] = {}
    total = 0
    for rel, texto in arquivos.items():
        linhas = [(i + 1, _normalizar(l)) for i, l in enumerate(texto.splitlines())]
        sig = [(i, l) for i, l in linhas if len(l) > 3 and not l.startswith(("//", "#", "*", "/*", "import ", "using ", "from ", "}", "{", ")"))]
        total += len(sig)
        for k in range(0, max(0, len(sig) - JANELA_DUPLICACAO + 1)):
            h = hashlib.sha1("\n".join(l for _, l in sig[k:k + JANELA_DUPLICACAO]).encode("utf-8")).hexdigest()
            janelas.setdefault(h, []).append((rel, sig[k][0]))
    repetidas = {h: lugares for h, lugares in janelas.items() if len(lugares) > 1}
    cobertas = set()
    achados = []
    for lugares in repetidas.values():
        for rel, linha in lugares:
            for d in range(JANELA_DUPLICACAO):
                cobertas.add((rel, linha + d))
        a, b = lugares[0], lugares[1]
        achados.append(_v("QC-DUP-01", "MEDIO", a[0], a[1], f"bloco de {JANELA_DUPLICACAO}+ linhas repetido em {b[0]}:{b[1]}"))
    perc = round(100.0 * len(cobertas) / total, 1) if total else 0.0
    if perc > LIMITES["duplicacao_perc"][0]:
        sev = "ALTO" if perc > LIMITES["duplicacao_perc"][1] else "MEDIO"
        achados.insert(0, _v("QC-DUP-01", sev, "-", 0, f"duplicação de {perc}% do código (limite {LIMITES['duplicacao_perc'][0]}%)"))
    return perc, achados[:40]


def medir(raiz: Path) -> dict:
    """Relatório completo: métricas agregadas e todas as violações, ordenadas da mais grave para a mais leve."""
    textos: Dict[str, str] = {}
    violacoes: List[dict] = []
    publicas = sem_doc = 0
    for p in arquivos_de_codigo(raiz):
        rel = p.relative_to(raiz).as_posix()
        try:
            texto = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        textos[rel] = texto
        linguagem = EXTENSOES[p.suffix]
        v, pu, sd = analisar_python(rel, texto) if linguagem == "python" else analisar_chaves(rel, texto, linguagem)
        violacoes += v + gambiarras(rel, texto)
        publicas, sem_doc = publicas + pu, sem_doc + sd
    perc_dup, achados_dup = duplicacao(textos)
    violacoes += achados_dup
    perc_sem_doc = round(100.0 * sem_doc / publicas, 1) if publicas else 0.0
    if publicas and (s := _sev(perc_sem_doc, "sem_doc_perc")):
        violacoes.append(_v("QC-DOC-01", s, "-", 0, f"{perc_sem_doc}% da API pública sem documentação ({sem_doc} de {publicas}); limite {LIMITES['sem_doc_perc'][0]}%"))
    ordem = {"ALTO": 0, "MEDIO": 1, "BAIXO": 2}
    violacoes.sort(key=lambda x: (ordem.get(x["severidade"], 3), x["arquivo"], x["linha"]))
    return {"arquivos": len(textos), "linhas": sum(t.count("\n") + 1 for t in textos.values()), "duplicacao_perc": perc_dup,
            "api_publica": publicas, "api_publica_sem_doc": sem_doc, "sem_doc_perc": perc_sem_doc, "violacoes": violacoes,
            "bloqueantes": [v for v in violacoes if v["severidade"] == "ALTO"]}

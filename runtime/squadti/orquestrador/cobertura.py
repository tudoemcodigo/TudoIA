"""
Gate de cobertura sobre relatórios Cobertura (XML): .NET (`--coverage --coverage-output-format cobertura`) e Vitest.

QUA-PIR-01 / QUA-EXE-05 da Doutrina: o gate é um passo que lê o Cobertura CONSOLIDADO e falha abaixo do mínimo em linha E em
ramo. Consolida por linha (arquivo, número): vários projetos de teste cobrindo o mesmo código não se somam em dobro.
Falha fechado: sem relatório, relatório ilegível ou grande demais = cobertura não medida = reprovado.
"""
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from xml.etree import ElementTree

PADROES = ("**/*.cobertura.xml", "**/cobertura.xml", "**/cobertura-coverage.xml", "**/coverage.cobertura.xml", "**/coverage.xml")  # coverage.xml: pytest-cov
IGNORAR = {"node_modules", ".git", "bin", "obj", ".venv", "venv"}
MAX_BYTES = 30_000_000
MAX_ARQUIVOS = 200
_RE_COND = re.compile(r"\((\d+)/(\d+)\)")


class CoberturaIndisponivel(RuntimeError):
    """Nenhum relatório utilizável: a cobertura não foi medida."""


def achar_relatorios(raiz: Path) -> List[Path]:
    raiz = raiz.resolve()
    achados = {}
    for padrao in PADROES:
        for p in raiz.glob(padrao):
            if p.is_file() and not p.is_symlink() and not (IGNORAR & set(p.relative_to(raiz).parts)):
                achados[p] = None
    return sorted(achados)[:MAX_ARQUIVOS]


def _ler(caminho: Path) -> Dict[Tuple[str, int], Tuple[int, int, int]]:
    """{(arquivo, linha): (acertos, ramos_cobertos, ramos_total)} de um relatório."""
    if caminho.stat().st_size > MAX_BYTES:
        raise CoberturaIndisponivel(f"{caminho.name}: relatório maior que {MAX_BYTES} bytes")
    try:
        raiz = ElementTree.parse(caminho).getroot()
    except (ElementTree.ParseError, OSError) as e:
        raise CoberturaIndisponivel(f"{caminho.name}: relatório ilegível ({type(e).__name__})") from e
    linhas = {}
    for classe in raiz.iter("class"):
        arquivo = (classe.get("filename") or "").replace("\\", "/")
        for linha in classe.iter("line"):
            try:
                n, hits = int(linha.get("number")), int(linha.get("hits", "0"))
            except (TypeError, ValueError):
                continue
            cob = tot = 0
            m = _RE_COND.search(linha.get("condition-coverage") or "")
            if linha.get("branch") == "true" and m:
                cob, tot = int(m.group(1)), int(m.group(2))
            chave = (arquivo, n)
            ant = linhas.get(chave, (0, 0, 0))
            linhas[chave] = (max(ant[0], hits), max(ant[1], cob), max(ant[2], tot))
    return linhas


def consolidar(relatorios: List[Path]) -> Dict[str, float]:
    """{'linha': %, 'ramo': %} do conjunto. Sem relatório ou sem nenhuma linha instrumentada: CoberturaIndisponivel."""
    if not relatorios:
        raise CoberturaIndisponivel("nenhum relatório Cobertura encontrado")
    juntos: Dict[Tuple[str, int], Tuple[int, int, int]] = {}
    for rel in relatorios:
        for chave, (h, c, t) in _ler(rel).items():
            ant = juntos.get(chave, (0, 0, 0))
            juntos[chave] = (max(ant[0], h), max(ant[1], c), max(ant[2], t))
    if not juntos:
        raise CoberturaIndisponivel("relatórios sem nenhuma linha instrumentada")
    linhas_cob = sum(1 for h, _, _ in juntos.values() if h > 0)
    ramos_tot = sum(t for _, _, t in juntos.values())
    ramos_cob = sum(c for _, c, _ in juntos.values())
    return {"linha": round(100.0 * linhas_cob / len(juntos), 2),
            "ramo": round(100.0 * ramos_cob / ramos_tot, 2) if ramos_tot else 100.0}


def avaliar(raiz: Path, minimo: float) -> Tuple[bool, dict]:
    """(aprovado, detalhe). Mínimo 0 desliga o gate de forma explícita (registrado no relatório)."""
    if minimo <= 0:
        return True, {"minimo": 0, "motivo": "gate de cobertura desligado na configuração (quality.coverage_min = 0)"}
    try:
        valores = consolidar(achar_relatorios(raiz))
    except CoberturaIndisponivel as e:
        return False, {"minimo": minimo, "motivo": f"cobertura não medida: {e}. Gere Cobertura no test_command "
                       "(.NET: --coverage --coverage-output-format cobertura; Vitest: reporter cobertura)"}
    ok = valores["linha"] >= minimo and valores["ramo"] >= minimo
    return ok, {"minimo": minimo, **valores, "motivo": "" if ok else
                f"cobertura abaixo de {minimo}% (linha {valores['linha']}%, ramo {valores['ramo']}%)"}


def minimo_da_stack(stack: Optional[dict]) -> float:
    """quality.coverage_min da stack; padrão 90 (decisão do dono, QUA-PIR-01). Valor inválido = padrão, nunca desliga."""
    bruto = ((stack or {}).get("quality") or {}).get("coverage_min", 90)
    try:
        valor = float(bruto)
    except (TypeError, ValueError):
        return 90.0
    return valor if 0 <= valor <= 100 else 90.0

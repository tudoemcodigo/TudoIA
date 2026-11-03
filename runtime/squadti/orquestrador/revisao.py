"""
Apoio ao nó `revisor`: escolha do código a revisar e leitura rígida do veredito.

- O código revisado é dado, não instrução: nada do que está nele vale como veredito. O veredito só é lido do
  arquivo docs/revisao/REVISAO.md que o MODELO devolveu nesta chamada.
- Falha fechado: sem exatamente uma linha `VEREDITO: APROVADO|REPROVADO`, ou com algum achado CRITICO, é REPROVADO.
"""
import re
from pathlib import Path
from typing import List, Optional, Tuple

import segredos
from execucao import caminho_seguro

ARQUIVO_REVISAO = "docs/revisao/REVISAO.md"
PREFIXOS_REVISADOS = ("src/", "tests/", "frontend/")
LIMITE_TOTAL_CARACTERES = 60_000
MINIMO_POR_ARQUIVO = 2_000
SEVERIDADES = ("CRITICO", "ALTO", "MEDIO", "BAIXO")

_RE_LINHA_VEREDITO = re.compile(r"^[ \t]*VEREDITO[ \t]*:", re.MULTILINE | re.IGNORECASE)
_RE_VEREDITO_EXATO = re.compile(r"^VEREDITO: (APROVADO|REPROVADO)[ \t]*$", re.MULTILINE)
_RE_ACHADO = re.compile(r"^[ \t]*(?:[-*]|\d+[.)])[ \t]*\[(?P<sev>CRITICO|ALTO|MEDIO|BAIXO)\][ \t]+(?P<regra>\S+)[ \t]+(?P<onde>\S+)",
                        re.MULTILINE)


def selecionar_arquivos(raiz: Path, gerados) -> List[str]:
    """Arquivos de `arquivos_gerados` sob src/, tests/ e frontend/ que existem de fato dentro do workspace (sem repetição)."""
    saida = []
    for rel in dict.fromkeys(str(g).strip().replace("\\", "/") for g in (gerados or [])):
        if not rel.startswith(PREFIXOS_REVISADOS) or rel.startswith("tests/reports/"):
            continue
        try:
            destino = caminho_seguro(raiz, rel)
        except ValueError:
            continue
        if destino.is_file() and not destino.is_symlink():
            saida.append(rel)
    return sorted(saida)


def montar_entrada(raiz: Path, arquivos: List[str], limite_total: int = LIMITE_TOTAL_CARACTERES) -> Tuple[str, List[str]]:
    """(texto do prompt, avisos). Linhas com padrão de segredo são trocadas por marcador (IA-PRV-03); arquivo grande é
    truncado e o corte vai declarado no texto E nos avisos; o que não coube no total fica listado como não incluído."""
    por_arquivo = max(MINIMO_POR_ARQUIVO, limite_total // max(1, len(arquivos)))
    restante, partes, avisos = limite_total, [], []
    for rel in arquivos:
        if restante <= 0:
            avisos.append(f"{rel}: NÃO incluído (limite total de {limite_total} caracteres)")
            partes.append(f"=== ARQUIVO: {rel} === [NÃO INCLUÍDO: limite total de caracteres; revisão incompleta]")
            continue
        teto = min(por_arquivo, restante)
        with open(caminho_seguro(raiz, rel), "r", encoding="utf-8", errors="replace") as f:
            texto = f.read(teto + 1)
        truncado = len(texto) > teto
        texto = texto[:teto]
        texto, ocultas = segredos.redigir(texto)
        restante -= len(texto)
        aviso = ""
        if truncado:
            aviso = f" [TRUNCADO em {teto} caracteres; o restante NÃO foi revisado]"
            avisos.append(f"{rel}: truncado em {teto} caracteres")
        if ocultas:
            aviso += f" [{ocultas} linha(s) omitida(s) por possível segredo]"
        partes.append(f"=== ARQUIVO: {rel} ==={aviso}\n{texto}\n=== FIM DE {rel} ===")
    return "\n\n".join(partes), avisos


def ler_veredito(texto: Optional[str]) -> Tuple[bool, List[dict], str]:
    """(aprovado, achados, motivo). `achados` = [{'severidade','regra','arquivo','linha'}]. Só `aprovado` True se houver
    exatamente uma linha de veredito, ela for APROVADO e não houver achado CRITICO."""
    if not texto or not texto.strip():
        return False, [], "REVISAO.md ausente ou vazio"
    achados = []
    for m in _RE_ACHADO.finditer(texto):
        arquivo, _, linha = m.group("onde").rpartition(":")
        if not arquivo or not linha.isdigit():
            arquivo, linha = m.group("onde"), "0"
        achados.append({"severidade": m.group("sev"), "regra": m.group("regra"), "arquivo": arquivo.strip("`'\"()"),
                        "linha": int(linha)})
    linhas = _RE_LINHA_VEREDITO.findall(texto)
    exatas = _RE_VEREDITO_EXATO.findall(texto)
    if len(linhas) != 1 or len(exatas) != 1:
        return False, achados, f"veredito ausente, repetido ou fora do formato ({len(linhas)} linha(s) 'VEREDITO:')"
    if exatas[0] != "APROVADO":
        return False, achados, "modelo reprovou"
    if any(a["severidade"] == "CRITICO" for a in achados):
        return False, achados, "há achado CRITICO: a regra vence o veredito do modelo"
    return True, achados, "aprovado"


def origem_da_falha(achados: List[dict]) -> str:
    """'frontend' só se TODOS os achados CRITICO/ALTO forem em frontend/; qualquer outra situação (inclusive nenhum) = 'backend'."""
    graves = [a for a in achados if a["severidade"] in ("CRITICO", "ALTO")]
    if graves and all(a["arquivo"].replace("\\", "/").startswith("frontend/") for a in graves):
        return "frontend"
    return "backend"


def resumo_para_dev(achados: List[dict], motivo: str, limite: int = 2000) -> str:
    """Texto curto devolvido ao dev: só severidade, regra e arquivo:linha dos achados CRITICO/ALTO (sem a prosa do modelo)."""
    linhas = [f"- [{a['severidade']}] {a['regra']} {a['arquivo']}:{a['linha']}"
              for a in achados if a["severidade"] in ("CRITICO", "ALTO")]
    corpo = "\n".join(linhas) or "(sem achado CRITICO/ALTO detalhado; veja docs/revisao/REVISAO.md)"
    texto = f"REVISÃO DE CÓDIGO REPROVADA ({motivo}). Corrija a causa-raiz dos achados:\n{corpo}"[:limite]
    return segredos.redigir(texto)[0]


def contagem(achados: List[dict]) -> str:
    return ", ".join(f"{s}={sum(1 for a in achados if a['severidade'] == s)}" for s in SEVERIDADES)

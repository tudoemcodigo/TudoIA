"""
Agregação das rodadas: pass@k, pass^k, comparação com a rodada anterior e o RELATORIO.md. Só stdlib, sem rede.

- pass@k: chance de PELO MENOS UMA de k tentativas passar (mede capacidade).
- pass^k: chance de TODAS as k tentativas passarem (mede confiabilidade: é o que importa para entregar sem supervisão).
Com n execuções por caso e c aprovadas, usa-se o estimador combinatório: pass@k = 1 - C(n-c, k)/C(n, k) e pass^k = C(c, k)/C(n, k).
Com k = n (o que `--k N` faz) viram "alguma passou" e "todas passaram".
"""
import json
from math import comb
from pathlib import Path
from typing import Any, Dict, List, Optional

LIMIAR_TOKENS = 0.30   # +30% de tokens (média por execução) é regressão
LIMIAR_TEMPO = 0.30    # +30% de duração (média por execução) é regressão


def pass_at_k(n: int, c: int, k: int) -> float:
    if n <= 0 or k <= 0 or k > n or not 0 <= c <= n:
        raise ValueError("exige 0 <= c <= n e 1 <= k <= n")
    return 1.0 if n - c < k else 1.0 - comb(n - c, k) / comb(n, k)


def pass_hat_k(n: int, c: int, k: int) -> float:
    if n <= 0 or k <= 0 or k > n or not 0 <= c <= n:
        raise ValueError("exige 0 <= c <= n e 1 <= k <= n")
    return comb(c, k) / comb(n, k)


def _media(valores: List[Optional[float]]) -> Optional[float]:
    v = [x for x in valores if isinstance(x, (int, float)) and not isinstance(x, bool)]
    return round(sum(v) / len(v), 1) if v else None


def agregar(resultados: List[dict], k: Optional[int] = None) -> Dict[str, dict]:
    """{caso: resumo} com pass@k/pass^k (k padrão = nº de execuções do caso), verificadores que falharam, tokens, duração e nós lentos."""
    por_caso: Dict[str, List[dict]] = {}
    for r in resultados:
        por_caso.setdefault(r["caso"], []).append(r)
    saida = {}
    for caso, rs in sorted(por_caso.items()):
        n, c = len(rs), sum(1 for r in rs if r.get("passou"))
        kk = k if k and 1 <= k <= n else n
        falhas: Dict[str, int] = {}
        for r in rs:
            for v in r.get("verificadores") or []:
                if not v.get("passou"):
                    falhas[v["nome"]] = falhas.get(v["nome"], 0) + 1
        nos: Dict[str, List[float]] = {}
        for r in rs:
            for no in r.get("nos_lentos") or []:
                nos.setdefault(str(no.get("no")), []).append(float(no.get("duracao_s") or 0))
        lentos = sorted(((no, round(sum(d) / len(d), 1)) for no, d in nos.items()), key=lambda x: -x[1])[:3]
        saida[caso] = {"execucoes": n, "aprovadas": c, "k": kk, "pass_at_k": round(pass_at_k(n, c, kk), 4),
                       "pass_hat_k": round(pass_hat_k(n, c, kk), 4), "verificadores_que_falharam": falhas,
                       "desfechos": sorted({r.get("desfecho", "?") for r in rs if not r.get("passou")}),
                       "tokens_medios": _media([r.get("tokens") for r in rs]), "duracao_media_s": _media([r.get("duracao_s") for r in rs]),
                       "nos_mais_lentos": [{"no": no, "duracao_s": d} for no, d in lentos]}
    return saida


def comparar(atual: Dict[str, dict], anterior: Optional[Dict[str, dict]]) -> Dict[str, Any]:
    """Regressões e melhorias frente à rodada anterior. Um caso "passava" quando todas as suas execuções passaram (pass^k = 1)."""
    if not anterior:
        return {"anterior": False, "regressoes": [], "melhorias": [], "novos_casos": sorted(atual)}
    regressoes, melhorias = [], []
    for caso, a in atual.items():
        p = anterior.get(caso)
        if p is None:
            continue
        passava, passa = p["pass_hat_k"] == 1.0, a["pass_hat_k"] == 1.0
        if passava and not passa:
            novos = sorted(set(a["verificadores_que_falharam"]) - set(p["verificadores_que_falharam"]))
            regressoes.append({"caso": caso, "tipo": "passava_e_agora_falha",
                               "detalhe": "verificadores novos falhando: " + (", ".join(novos) or "nenhum (falha de desfecho)")
                                          + (f"; desfechos: {', '.join(a['desfechos'])}" if a["desfechos"] else "")})
        if not passava and passa:
            melhorias.append({"caso": caso, "tipo": "falhava_e_agora_passa"})
        for chave, limiar, rotulo in (("tokens_medios", LIMIAR_TOKENS, "tokens"), ("duracao_media_s", LIMIAR_TEMPO, "duração")):
            antes, agora = p.get(chave), a.get(chave)
            if antes and agora and agora > antes * (1 + limiar):
                regressoes.append({"caso": caso, "tipo": f"{rotulo}_acima_do_limiar",
                                   "detalhe": f"{rotulo}: {antes} -> {agora} (+{round(100 * (agora / antes - 1))}%, limiar {int(limiar * 100)}%)"})
    return {"anterior": True, "regressoes": regressoes, "melhorias": melhorias,
            "novos_casos": sorted(set(atual) - set(anterior))}


def rodada_anterior(raiz: Path, atual: str) -> Optional[Dict[str, Any]]:
    """`resumo.json` da rodada mais recente em `raiz` anterior a `atual` (nomes de pasta ordenam por data). None se não houver/ilegível."""
    if not raiz.is_dir():
        return None
    for pasta in sorted((p for p in raiz.iterdir() if p.is_dir() and p.name < atual), key=lambda p: p.name, reverse=True):
        arq = pasta / "resumo.json"
        if arq.is_file() and arq.stat().st_size < 5_000_000:
            try:
                dado = json.loads(arq.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(dado, dict) and isinstance(dado.get("casos"), dict):
                dado["_pasta"] = pasta.name
                return dado
    return None


def _celula(texto: Any) -> str:
    return str(texto).replace("|", "\\|").replace("\n", " ")


def gerar_markdown(rodada: str, resultados: List[dict], resumo: Dict[str, dict], comparacao: Dict[str, Any],
                   anterior: Optional[str], k: int) -> str:
    linhas = [f"# Relatório de evals da SquadTI ({rodada})", "",
              "> **MODO EVAL**: a especificação e o release foram aprovados AUTOMATICAMENTE pelo driver de teste. "
              "Nenhum humano revisou estas entregas.", "",
              f"Execuções por caso (k): {k}. pass@k = alguma execução passou; pass^k = todas passaram.", "",
              "| Caso | Passou | pass@k | pass^k | Verificadores que falharam | Tokens (média) | Duração (média) | Nós mais lentos |",
              "|---|---|---|---|---|---|---|---|"]
    for caso, r in resumo.items():
        falhas = ", ".join(f"{n} ({q}x)" if r["execucoes"] > 1 else n for n, q in sorted(r["verificadores_que_falharam"].items())) or "-"
        if r["desfechos"]:
            falhas += f" [desfecho: {', '.join(r['desfechos'])}]"
        lentos = ", ".join(f"{x['no']} {x['duracao_s']}s" for x in r["nos_mais_lentos"]) or "-"
        dur = f"{round(r['duracao_media_s'] / 60, 1)} min" if r["duracao_media_s"] is not None else "-"
        linhas.append(f"| {caso} | {r['aprovadas']}/{r['execucoes']} {'SIM' if r['aprovadas'] == r['execucoes'] else 'NÃO'} | "
                      f"{r['pass_at_k']} | {r['pass_hat_k']} | {_celula(falhas)} | "
                      f"{r['tokens_medios'] if r['tokens_medios'] is not None else '-'} | {dur} | {_celula(lentos)} |")
    motivos = [r for r in resultados if not r.get("passou") and r.get("motivo")]
    if motivos:
        linhas += ["", "## Motivos de parada", ""]
        linhas += [f"- `{r['caso']}-{r['n']}` ({r['desfecho']}): {_celula(r['motivo'])}" for r in motivos]
    falhos = [(r, v) for r in resultados for v in r.get("verificadores") or [] if not v.get("passou")]
    if falhos:
        linhas += ["", "## Detalhe das falhas", ""]
        linhas += [f"- `{r['caso']}-{r['n']}` **{v['nome']}**: {_celula(v['detalhe'])}" for r, v in falhos]
    linhas += ["", "## Comparação com a rodada anterior", ""]
    if not comparacao["anterior"]:
        linhas.append("Não há rodada anterior para comparar.")
    else:
        linhas.append(f"Rodada anterior: `{anterior}`.")
        linhas += [f"- REGRESSÃO `{x['caso']}` ({x['tipo']}): {_celula(x['detalhe'])}" for x in comparacao["regressoes"]]
        linhas += [f"- melhoria `{x['caso']}`: {x['tipo']}" for x in comparacao["melhorias"]]
        linhas += [f"- caso novo: `{c}`" for c in comparacao["novos_casos"]]
        if not (comparacao["regressoes"] or comparacao["melhorias"] or comparacao["novos_casos"]):
            linhas.append("Sem mudanças relevantes.")
    return "\n".join(linhas) + "\n"

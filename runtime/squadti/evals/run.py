"""
CLI dos evals da SquadTI (precisa da API no ar e de um modelo real; consome tokens).

    TUDOIA_SQUADTI_TOKEN=<token> python -m evals.run [--caso ID ...] [--k N] [--saida PASTA] [--url http://127.0.0.1:8790]

O token vem SÓ do ambiente. Saída: <saida>/<rodada>/<caso>-<n>.json, a cópia do workspace em <saida>/<rodada>/<caso>-<n>/workspace,
<saida>/<rodada>/resumo.json e <saida>/<rodada>/RELATORIO.md (com a comparação contra a rodada anterior).
Código de saída: 0 todos os casos passaram, 1 algum falhou, 2 uso/configuração inválidos.
MODO EVAL: o driver aprova sozinho a especificação e o release; isso fica registrado nos resultados.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import List, Optional

from . import driver, relatorio

PASTA_CASOS = Path(__file__).resolve().parent / "casos"
URL_PADRAO = "http://127.0.0.1:8790"
SAIDA_PADRAO = "evals/resultados"


def _escrever_json(caminho: Path, dado: object, token: str) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(dado, ensure_ascii=False, indent=2).replace(token, "***"), encoding="utf-8")


def rodar_rodada(cliente: driver.Cliente, casos: List[dict], k: int, saida: Path, *, rodada: Optional[str] = None,
                 intervalo_s: float = 2.0, timeout_s: Optional[float] = None, espera_inicial_s: float = 600.0) -> dict:
    """Roda cada caso k vezes (em série: a Squad executa uma tarefa por vez) e grava resultados, resumo e RELATORIO.md."""
    rodada = rodada or time.strftime("%Y-%m-%d_%H%M%S")
    pasta = saida / rodada
    pasta.mkdir(parents=True, exist_ok=True)
    anterior = relatorio.rodada_anterior(saida, rodada)
    resultados = []
    for caso in casos:
        for n in range(1, k + 1):
            destino = pasta / f"{caso['id']}-{n}"
            try:
                r = driver.executar_caso(cliente, caso, n, rodada, destino, intervalo_s=intervalo_s, timeout_s=timeout_s,
                                         espera_inicial_s=espera_inicial_s)
            except Exception as e:  # defeito do driver: a execução reprova com o tipo do erro, e a rodada continua
                r = {"caso": caso["id"], "n": n, "rodada": rodada, "modo_eval": True, "aprovacoes_automaticas": [], "passou": False,
                     "desfecho": "erro_do_driver", "motivo": cliente.limpar(f"{type(e).__name__}: {e}")[:300], "duracao_s": None,
                     "verificadores": [{"nome": "execucao", "passou": False, "detalhe": "erro interno do driver"}]}
            _escrever_json(pasta / f"{caso['id']}-{n}.json", r, cliente._token)
            resultados.append(r)
    resumo = relatorio.agregar(resultados, k)
    comparacao = relatorio.comparar(resumo, anterior["casos"] if anterior else None)
    _escrever_json(pasta / "resumo.json", {"rodada": rodada, "k": k, "modo_eval": True, "casos": resumo, "comparacao": comparacao},
                   cliente._token)
    texto = relatorio.gerar_markdown(rodada, resultados, resumo, comparacao, anterior.get("_pasta") if anterior else None, k)
    (pasta / "RELATORIO.md").write_text(texto.replace(cliente._token, "***"), encoding="utf-8")
    return {"rodada": rodada, "pasta": pasta, "resultados": resultados, "resumo": resumo, "comparacao": comparacao}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--caso", action="append", help="id do caso (repita para vários); padrão: todos")
    ap.add_argument("--k", type=int, default=1, help="execuções por caso, para pass@k e pass^k (padrão 1)")
    ap.add_argument("--saida", default=os.getenv("SQUADTI_EVALS_SAIDA", SAIDA_PADRAO), help=f"pasta dos resultados (padrão {SAIDA_PADRAO})")
    ap.add_argument("--url", default=os.getenv("TUDOIA_SQUADTI_URL", URL_PADRAO), help="URL da API (só loopback)")
    ap.add_argument("--casos-dir", default=str(PASTA_CASOS))
    ap.add_argument("--timeout-s", type=float, default=None, help="prazo global por execução (padrão: o do caso)")
    ap.add_argument("--intervalo-s", type=float, default=5.0, help="intervalo do polling")
    args = ap.parse_args(argv)
    if not 1 <= args.k <= 20:
        print("--k deve estar entre 1 e 20", file=sys.stderr)
        return 2
    try:
        casos = driver.carregar_casos(Path(args.casos_dir), args.caso)
        cliente = driver.Cliente(args.url, os.getenv("TUDOIA_SQUADTI_TOKEN", ""))
        cliente.requisitar("GET", "/saude")
    except (driver.ErroCaso, driver.ErroApi) as e:
        print(f"erro: {getattr(e, 'mensagem', None) or e}", file=sys.stderr)
        return 2
    print(f"MODO EVAL: spec e release serão aprovados automaticamente. {len(casos)} caso(s) x k={args.k}.", flush=True)
    r = rodar_rodada(cliente, casos, args.k, Path(args.saida), intervalo_s=args.intervalo_s, timeout_s=args.timeout_s)
    for caso, s in r["resumo"].items():
        print(f"{caso}: {s['aprovadas']}/{s['execucoes']} passou | pass@k={s['pass_at_k']} pass^k={s['pass_hat_k']}", flush=True)
    for x in r["comparacao"]["regressoes"]:
        print(f"REGRESSAO {x['caso']}: {x['detalhe']}", flush=True)
    print(f"Relatório: {r['pasta'] / 'RELATORIO.md'}", flush=True)
    return 0 if all(s["aprovadas"] == s["execucoes"] for s in r["resumo"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())

"""
Teste de carga e capacidade (papel do DevOps/SRE): sobe usuários simultâneos em degraus e diz até onde o sistema aguenta.

Gerador de carga: k6 (container na rede interna do sandbox). O alvo roda com teto de CPU e memória (sandbox), então o número que sai é
CAPACIDADE RELATIVA àquele teto, útil para comparar uma versão com a anterior e achar o gargalo; não é a capacidade de produção.
O perfil `escalado` (padrão) sobe até centenas de usuários simultâneos; o `completo` chega a 10 mil e só faz sentido com o gerador de
carga numa máquina separada do alvo (aqui os dois disputam a mesma CPU).

Cada degrau é uma execução curta e independente: no primeiro que viola o SLO a subida PARA (não adianta continuar).
"""
import json
import threading
import time
from typing import Callable, List, Optional

import sandbox as sb

PERFIS_CARGA = {
    "escalado": [25, 50, 100, 200, 400],
    "completo": [500, 1000, 2500, 5000, 10000],
}
# SLO padrão: p95 e p99 em milissegundos, taxa de erro (5xx e falha de conexão) em fração. Configurável por tarefa.
SLO_PADRAO = {"p95_ms": 800.0, "p99_ms": 2000.0, "erro_max": 0.01}
# VUs que o sistema precisa sustentar dentro do SLO para o portão passar, por tamanho do plano do CHEFE.
MINIMO_POR_TAMANHO = {"trivial": 25, "pequeno": 50, "padrao": 100, "grande": 200}
DURACAO_DEGRAU_S = 40
RAMPA_S = 10
MAX_ALVOS = 20


def alvos_seguros(spec: dict) -> List[str]:
    """Caminhos que a carga pode martelar sem efeito colateral: GET sem parâmetro de caminho obrigatório, mais a raiz."""
    caminhos = ["/"]
    for caminho, item in (spec.get("paths") or {}).items():
        op = (item or {}).get("get")
        if not isinstance(op, dict) or "{" in caminho:
            continue
        if any(p.get("required") and p.get("in") == "query" for p in (op.get("parameters") or []) if isinstance(p, dict)):
            continue
        caminhos.append(caminho)
    return list(dict.fromkeys(caminhos))[:MAX_ALVOS]


def gerar_script_k6(alvo: str, caminhos: List[str], vus: int, slo: Optional[dict] = None, duracao_s: int = DURACAO_DEGRAU_S) -> str:
    """Script k6: rampa até `vus`, sustenta e desce. Cada usuário simula pensar entre as requisições (1 a 3 s)."""
    slo = {**SLO_PADRAO, **(slo or {})}
    sustento = max(5, duracao_s - RAMPA_S * 2)
    return (
        "import http from 'k6/http';\n"
        "import { check, sleep } from 'k6';\n"
        f"const ALVO = {json.dumps(alvo)};\n"
        f"const CAMINHOS = {json.dumps(caminhos)};\n"
        "export const options = {\n"
        f"  stages: [{{ duration: '{RAMPA_S}s', target: {int(vus)} }}, {{ duration: '{sustento}s', target: {int(vus)} }}, "
        f"{{ duration: '{RAMPA_S}s', target: 0 }}],\n"
        "  summaryTrendStats: ['avg', 'p(95)', 'p(99)', 'max'],\n"
        "  noConnectionReuse: false,\n"
        "};\n"
        "export default function () {\n"
        "  const caminho = CAMINHOS[Math.floor(Math.random() * CAMINHOS.length)];\n"
        "  const r = http.get(ALVO + caminho, { timeout: '10s' });\n"
        "  check(r, { 'sem erro de servidor': (x) => x.status > 0 && x.status < 500 });\n"
        "  sleep(1 + Math.random() * 2);\n"
        "}\n"
    )


def _num(metricas: dict, nome: str, chaves: tuple) -> Optional[float]:
    """Lê uma métrica do resumo do k6 aceitando os dois formatos (`values` aninhado e plano)."""
    m = metricas.get(nome) or {}
    base = m.get("values") if isinstance(m.get("values"), dict) else m
    for k in chaves:
        if isinstance(base.get(k), (int, float)):
            return float(base[k])
    return None


def interpretar(resumo: dict, vus: int, slo: Optional[dict] = None) -> dict:
    """Resultado de um degrau: latências, erro, vazão e se cumpriu o SLO. Métrica ausente = degrau reprovado (falha fechado)."""
    slo = {**SLO_PADRAO, **(slo or {})}
    metricas = resumo.get("metrics") or {}
    p95 = _num(metricas, "http_req_duration", ("p(95)",))
    p99 = _num(metricas, "http_req_duration", ("p(99)",))
    falha = _num(metricas, "http_req_failed", ("rate", "value"))
    checks = metricas.get("checks") or {}
    base_checks = checks.get("values") if isinstance(checks.get("values"), dict) else checks
    taxa_check = base_checks.get("rate", base_checks.get("value")) if isinstance(base_checks, dict) else None
    erro = 1.0 - taxa_check if isinstance(taxa_check, (int, float)) else falha
    rps = _num(metricas, "http_reqs", ("rate",))
    total = _num(metricas, "http_reqs", ("count",))
    motivos = []
    if p95 is None or p99 is None or erro is None:
        motivos.append("o k6 não devolveu as métricas esperadas")
    else:
        if p95 > slo["p95_ms"]:
            motivos.append(f"p95 {p95:.0f} ms acima de {slo['p95_ms']:.0f} ms")
        if p99 > slo["p99_ms"]:
            motivos.append(f"p99 {p99:.0f} ms acima de {slo['p99_ms']:.0f} ms")
        if erro > slo["erro_max"]:
            motivos.append(f"erro {erro * 100:.1f}% acima de {slo['erro_max'] * 100:.1f}%")
    return {"vus": vus, "p95_ms": p95, "p99_ms": p99, "erro": erro, "rps": rps, "requisicoes": total, "passou": not motivos,
            "motivos": motivos}


def diagnosticar(degrau: dict, stats: Optional[dict], oom: bool) -> str:
    """Gargalo provável no degrau que saturou: recurso do alvo saturado, queda do processo ou limite de aplicação/banco/E-S."""
    if oom:
        return "o container do sistema foi morto por falta de memória (OOM): aumente o limite ou reduza o consumo por requisição"
    if stats:
        def perc(txt):
            try:
                return float(str(txt).replace("%", "").strip())
            except ValueError:
                return 0.0
        if perc(stats.get("cpu")) >= 85:
            return f"CPU do sistema saturada ({stats['cpu']} do limite): custo por requisição alto ou pouco paralelismo"
        if perc(stats.get("memoria_perc")) >= 85:
            return f"memória do sistema quase no limite ({stats['memoria_perc']}): vazamento ou cache sem teto"
    if degrau.get("erro") and degrau["erro"] > 0.05:
        return "muitas falhas com CPU e memória folgadas: limite de conexões, pool do banco ou timeout em cadeia"
    return "latência subiu com CPU e memória folgadas: espera por banco, bloqueio ou E/S (veja pool de conexões e consultas lentas)"


def executar(box, spec: dict, perfil: str = "escalado", slo: Optional[dict] = None, minimo_vus: int = 50,
             emitir: Optional[Callable[[str], None]] = None, passos: Optional[List[int]] = None) -> dict:
    """Roda os degraus no sandbox já de pé. Devolve o relatório de capacidade (nunca levanta por falha de degrau)."""
    emitir = emitir or (lambda t: None)
    degraus_vus = passos or PERFIS_CARGA.get(perfil)
    if not degraus_vus:
        raise ValueError(f"perfil de carga desconhecido: {perfil!r} (use {sorted(PERFIS_CARGA)})")
    caminhos = alvos_seguros(spec)
    degraus: List[dict] = []
    estavel, saturou_em, gargalo = 0, None, None
    for vus in degraus_vus:
        emitir(f"[carga] degrau de {vus} usuários simultâneos")
        script = gerar_script_k6(box.alvo, caminhos, vus, slo)
        amostras: List[dict] = []
        parar = threading.Event()

        def amostrar(amostras=amostras, parar=parar):  # ligados por valor: cada degrau tem os seus
            time.sleep(RAMPA_S + 5)
            while not parar.is_set():
                s = box.estatisticas()
                if s:
                    amostras.append(s)
                parar.wait(5)
        t = threading.Thread(target=amostrar, daemon=True)
        t.start()
        try:
            codigo, saida, arquivos = box.rodar_ferramenta(
                sb.IMAGEM_K6, ["run", "--quiet", "--summary-export=/tmp/resumo.json", "/tmp/carga.js"],
                arquivos={"/tmp/carga.js": script.encode("utf-8")}, coletar=["/tmp/resumo.json"], timeout=DURACAO_DEGRAU_S + 120,
                limites={"memoria": "2g" if vus <= 1000 else "6g", "cpus": "2.0" if vus <= 1000 else "4.0", "pids": "4096"})
        finally:
            parar.set()
            t.join(timeout=2)
        try:
            resumo = json.loads(arquivos.get("/tmp/resumo.json", b"{}").decode("utf-8"))
        except ValueError:
            resumo = {}
        degrau = interpretar(resumo, vus, slo)
        pico = max(amostras, key=lambda a: float(str(a.get("cpu", "0")).replace("%", "") or 0), default=None) if amostras else None
        degrau["recursos_do_alvo"] = pico
        if codigo not in (0, 99):  # 99 = thresholds do k6 cruzados (não usamos); outro código = falha da ferramenta
            degrau["passou"], degrau["motivos"] = False, degrau["motivos"] + [f"o k6 saiu com código {codigo}: {saida[-300:]}"]
        degraus.append(degrau)
        if degrau["passou"]:
            estavel = vus
            continue
        oom = box.docker.executar("inspect", "--format", "{{.State.OOMKilled}}", box.sut)[1].strip().lower() == "true"
        saturou_em, gargalo = vus, diagnosticar(degrau, pico, oom)
        emitir(f"[carga] saturou com {vus} usuários: {', '.join(degrau['motivos'])}")
        break
    return {"perfil": perfil, "slo": {**SLO_PADRAO, **(slo or {})}, "degraus": degraus, "estavel_ate_vus": estavel,
            "saturou_em_vus": saturou_em, "gargalo": gargalo, "minimo_vus": minimo_vus, "aprovado": estavel >= minimo_vus,
            "nota": "capacidade relativa ao teto de CPU/memória do sandbox; não é a capacidade de produção"}

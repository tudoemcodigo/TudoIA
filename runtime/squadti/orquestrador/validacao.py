"""
Validação em execução: o sistema gerado roda num sandbox isolado e três agentes tentam quebrá-lo.

- **Macaco (QA):** usa o sistema "à força": entrada errada de todo jeito, tipos trocados, texto hostil, JSON malformado, e (se o sistema serve
  uma tela) cliques e digitação aleatórios na interface, até achar erro.
- **Hacker (AppSec):** ataca o sistema rodando: autenticação, injeção, vazamento de erro, CORS, atribuição em massa, limites, cabeçalhos.
- **Carga (DevOps/SRE):** sobe usuários simultâneos em degraus até o sistema violar o SLO, e diz o gargalo.

Os cenários são verificações fixas (kits em `kits/`, container na rede do sandbox); o modelo só entra para o modelo de ameaças, nunca para
escolher comando ou alvo. Achado CRITICO ou ALTO confirmado BLOQUEIA a entrega e volta ao desenvolvimento com o relatório; MEDIO e BAIXO
ficam registrados. O sandbox é desmontado sempre.
"""
import json
import time
from pathlib import Path
from typing import List, Optional

import agentes
import auditoria
import carga
import doutrina_tec as dout
import nodes
import sandbox as sb
import segredos
from auditoria import EscaladaHumana, auditar
from execucao import caminho_seguro, workspace
from state import SquadState

KITS = Path(__file__).resolve().parent / "kits"
BLOQUEIAM = ("CRITICO", "ALTO")
LIMITE_RODADAS = 3
RELATORIOS = {"hacker": "tests/reports/hacker_report.json", "macaco": "tests/reports/macaco_report.json",
              "carga": "tests/reports/carga_report.json"}
ARQUIVO_AMEACAS = "docs/seguranca/MODELO_DE_AMEACAS.md"
FABRICA_DOCKER = sb.Docker   # seam dos testes


def _kit(nome: str) -> bytes:
    return (KITS / nome).read_bytes()


def _spec_json(ws: Path, state: dict) -> Optional[bytes]:
    """Contrato OpenAPI do projeto em JSON (o kit só usa a biblioteca padrão). None se o projeto não tem contrato legível."""
    relativo = state.get("openapi_file")
    if not relativo:
        return None
    try:
        import yaml
        doc = yaml.safe_load(caminho_seguro(ws, relativo).read_text(encoding="utf-8", errors="replace"))
    except Exception:  # YAML ilegível: sem contrato utilizável (o gate do CHEFE já recusa contrato inválido)
        return None
    return json.dumps(doc).encode("utf-8") if isinstance(doc, dict) else None


def _registro(no: str, papel: str, inicio: float, detalhe: Optional[list] = None) -> dict:
    return {"no": no, "papel": papel, "inicio": inicio, "duracao_s": round(time.time() - inicio, 2), "chamadas": len(detalhe or []),
            "tokens_entrada": sum(int(c.get("tokens_entrada") or 0) for c in detalhe or []),
            "tokens_saida": sum(int(c.get("tokens_saida") or 0) for c in detalhe or []),
            "modelos": sorted({c["modelo"] for c in detalhe or [] if c.get("modelo")}), "detalhe": detalhe or []}


def _kit_api(box: sb.Sandbox, modo: str, spec: bytes, limite: int) -> dict:
    codigo, saida, arquivos = box.rodar_ferramenta(
        sb.IMAGEM_PYTHON, ["python", "/tmp/kit_api.py", modo, box.alvo, "/tmp/openapi.json", "/tmp/saida.json", "--max-requisicoes", str(limite)],
        arquivos={"/tmp/kit_api.py": _kit("kit_api.py"), "/tmp/openapi.json": spec}, coletar=["/tmp/saida.json"], timeout=900,
        limites={"memoria": "512m", "cpus": "1.0"})
    if codigo != 0 or "/tmp/saida.json" not in arquivos:
        raise sb.SandboxFalhou(modo, f"o kit saiu com código {codigo}: {saida[-500:]}")
    return json.loads(arquivos["/tmp/saida.json"].decode("utf-8"))


def _serve_html(box: sb.Sandbox) -> bool:
    codigo, saida, _ = box.rodar_ferramenta(
        sb.IMAGEM_PYTHON, ["python", "-c", "import sys,urllib.request as u\ntry:\n print(u.urlopen(sys.argv[1], timeout=5).headers.get('content-type',''))\n"
                           "except Exception as e:\n print(getattr(e,'headers',{}).get('content-type','') if hasattr(e,'headers') else '')", f"{box.alvo}/"],
        timeout=30)
    return codigo == 0 and "html" in saida.lower()


def _kit_ui(box: sb.Sandbox, segundos: int) -> dict:
    codigo, saida, arquivos = box.rodar_ferramenta(
        sb.IMAGEM_PLAYWRIGHT, ["python", "/tmp/kit_ui.py", box.alvo, "/tmp/saida.json", str(segundos)],
        arquivos={"/tmp/kit_ui.py": _kit("kit_ui.py")}, coletar=["/tmp/saida.json"], timeout=segundos + 180,
        limites={"memoria": "2g", "cpus": "2.0", "pids": "2048"})
    if codigo != 0 or "/tmp/saida.json" not in arquivos:
        raise sb.SandboxFalhou("macaco-ui", f"o macaco de interface saiu com código {codigo}: {saida[-500:]}")
    return json.loads(arquivos["/tmp/saida.json"].decode("utf-8"))


def _modelo_de_ameacas(state: SquadState, ws: Path) -> Optional[str]:
    """Documento de ameaças do sistema (o que falta no AppSec automático). Não bloqueia: falha do modelo só pula o documento."""
    try:
        spec = caminho_seguro(ws, state["business_spec_file"]).read_text(encoding="utf-8", errors="replace")[:12_000]
        contrato = caminho_seguro(ws, state["openapi_file"]).read_text(encoding="utf-8", errors="replace")[:12_000] if state.get("openapi_file") else ""
        instrucao = ("Você é o Hacker da Squad (AppSec ofensivo). Escreva docs/seguranca/MODELO_DE_AMEACAS.md: ativos, fronteiras de "
                     "confiança, ameaças por endpoint em STRIDE, abusos de regra de negócio (ex.: pular etapa, repetir operação, "
                     "escalar privilégio) e a mitigação esperada de cada um. Só o que decorre dos artefatos recebidos; sem inventar "
                     "endpoint. Um único arquivo, em bloco.")
        resposta = nodes._chamar("appsec", state, instrucao, f"Requisitos:\n{spec}\n\nContrato:\n{contrato}", agente="hacker")
        gravados = nodes.escrever_arquivos(resposta, ws, ("docs/seguranca/",))[0]
        return ARQUIVO_AMEACAS if ARQUIVO_AMEACAS in gravados else None
    except (EscaladaHumana, OSError, KeyError, RuntimeError):
        return None


def resumo_para_dev(achados: List[dict], titulo: str, limite: int = 2000) -> str:
    """Texto devolvido ao desenvolvimento: só os achados que bloqueiam, com como reproduzir. Sem segredo (IA-PRV-03)."""
    linhas = [f"- [{a['severidade']}] {a['id']} {a['metodo']} {a['endpoint']}: {a['evidencia']} | reproduzir: {a['reproducao']}"
              for a in achados if a["severidade"] in BLOQUEIAM]
    texto = f"{titulo}. Corrija a causa-raiz de cada achado:\n" + "\n".join(linhas)
    return segredos.redigir(texto[:limite])[0]


def _estruturar(agente: str, achados: List[dict]) -> List[dict]:
    """Achados com o agente de origem, para o livro de lições (estrutura fixa: nada de prosa livre do modelo)."""
    return [{"agente": agente, "id": a["id"], "severidade": a["severidade"], "categoria": a["categoria"], "endpoint": a["endpoint"],
             "metodo": a["metodo"]} for a in achados]


def _pulada(motivo: str) -> dict:
    return {"current_phase": "VALIDACAO_RUNTIME_PULADA", "validacao_executada": False, "validacao_motivo": motivo,
            "hacker_passed": None, "macaco_passed": None, "carga_passed": None}


def _falha_do_sandbox(state: SquadState, e: sb.SandboxFalhou, rodadas: int) -> dict:
    """O sistema não construiu ou não subiu: é defeito do desenvolvimento (Dockerfile, porta, saúde, migrations)."""
    erro = f"validação em execução: {e.etapa} falhou. {e.detalhe}"[:2000]
    saida = {"current_phase": "VALIDACAO_RUNTIME_FALHOU", "validacao_executada": True, "hacker_passed": False, "macaco_passed": False,
             "carga_passed": None, "last_error_log": segredos.redigir(erro)[0], "falha_origem": "backend", "rodadas_runtime": rodadas + 1}
    assinatura = auditoria.assinatura_do_erro(erro)
    saida["assinaturas_erro"] = auditoria.registrar_assinatura(state, assinatura)
    if auditoria.estagnou(state, assinatura):
        saida["escalada"] = "estagnacao: o sistema gerado continua sem subir no sandbox pela mesma causa"
    return saida


@auditar("validacao_runtime", "hacker")
def node_validacao_runtime(state: SquadState) -> dict:
    dout.verificar_versao(state)
    ws = workspace(state)
    cfg = agentes.do_estado(state)["validacao"]
    rodadas = int(state.get("rodadas_runtime") or 0)
    tarefa = state.get("task_id")
    def emitir(texto: str) -> None:
        auditoria.emitir(tarefa, texto)

    if cfg["modo"] == "nunca":
        return _pulada("desligada na configuração (validacao.modo = nunca)")
    box = sb.Sandbox(tarefa, ws, docker=FABRICA_DOCKER(), emitir=emitir)
    if not sb.docker_disponivel(box.docker):
        if cfg["modo"] == "sempre":
            raise EscaladaHumana("a validação em execução exige o Docker, que não respondeu (validacao.modo = sempre)", "docker")
        return _pulada("o Docker não respondeu: o sistema NÃO foi validado em execução")

    plano = state.get("plano") or {}
    relatorios, registros, extras = {}, [], []
    try:
        box.construir()
        box.subir(porta=8080, motor_banco=plano.get("motor_banco", "nenhum") if plano.get("precisa_banco") else "nenhum", saude="/saude")
        spec = _spec_json(ws, state)

        # ---- macaco (QA)
        t0 = time.time()
        achados_macaco: List[dict] = []
        if spec:
            achados_macaco += _kit_api(box, "macaco", spec, 600)["achados"]
        if plano.get("precisa_frontend") and _serve_html(box):
            try:
                achados_macaco += _kit_ui(box, cfg["ui_segundos"])["achados"]
            except sb.SandboxFalhou as e:  # imagem pesada ou ferramenta indisponível: registra e segue
                extras.append(f"macaco de interface não rodou: {e.detalhe[:200]}")
        relatorios["macaco"] = {"achados": achados_macaco, "executado": bool(spec) or bool(plano.get("precisa_frontend")), "notas": extras}
        registros.append(_registro("qa_macaco", "qa", t0))

        # ---- hacker (AppSec)
        t0 = time.time()
        ameacas = _modelo_de_ameacas(state, ws)  # as chamadas ao modelo entram na auditoria do nó (tokens contados uma vez só)
        achados_hacker = _kit_api(box, "ataque", spec, 400)["achados"] if spec else []
        relatorios["hacker"] = {"achados": achados_hacker, "executado": bool(spec), "modelo_de_ameacas": ameacas,
                                "notas": [] if spec else ["sem contrato OpenAPI: só o modelo de ameaças foi produzido"]}
        registros.append(_registro("hacker", "hacker", t0))

        # ---- carga (DevOps/SRE)
        t0 = time.time()
        tamanho = plano.get("tamanho", "padrao")
        faz_carga = spec and cfg["carga"] != "nunca" and (tamanho != "trivial" or cfg["carga"] == "completo")
        if faz_carga:
            relatorios["carga"] = carga.executar(box, json.loads(spec), cfg["carga"], cfg["slo"],
                                                 carga.MINIMO_POR_TAMANHO.get(tamanho, 50), emitir)
            registros.append(_registro("carga_devops", "devops", t0))
        else:
            relatorios["carga"] = {"executado": False, "motivo": "desligada, sem contrato ou sistema trivial"}
    except sb.SandboxFalhou as e:
        emitir(f"[validacao] {e.etapa}: {e.detalhe[:200]}")
        return _falha_do_sandbox(state, e, rodadas)
    finally:
        box.limpar()

    # ---- veredito, relatórios e retorno ao desenvolvimento
    bloq_h = [a for a in relatorios["hacker"]["achados"] if a["severidade"] in BLOQUEIAM]
    bloq_m = [a for a in relatorios["macaco"]["achados"] if a["severidade"] in BLOQUEIAM]
    carga_ok = None if not relatorios["carga"].get("executado", True) or "aprovado" not in relatorios["carga"] else relatorios["carga"]["aprovado"]
    hacker_ok, macaco_ok = not bloq_h, not bloq_m
    aprovado = hacker_ok and macaco_ok and carga_ok is not False
    relatorios["hacker"]["aprovado"], relatorios["macaco"]["aprovado"] = hacker_ok, macaco_ok
    arquivos = list(state.get("arquivos_gerados") or [])
    for nome, relativo in RELATORIOS.items():
        destino = caminho_seguro(ws, relativo)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(json.dumps(relatorios[nome], ensure_ascii=False, indent=1), encoding="utf-8")
        arquivos.append(relativo)
    if relatorios["hacker"].get("modelo_de_ameacas"):
        arquivos.append(relatorios["hacker"]["modelo_de_ameacas"])
    achados_tudo = _estruturar("hacker", relatorios["hacker"]["achados"]) + _estruturar("qa_macaco", relatorios["macaco"]["achados"])
    saida = {"current_phase": "VALIDACAO_RUNTIME_APROVADA" if aprovado else "VALIDACAO_RUNTIME_REPROVADA", "validacao_executada": True,
             "hacker_passed": hacker_ok, "macaco_passed": macaco_ok, "carga_passed": carga_ok, "hacker_report_file": RELATORIOS["hacker"],
             "macaco_report_file": RELATORIOS["macaco"], "carga_report_file": RELATORIOS["carga"], "arquivos_gerados": arquivos,
             "achados_agentes": achados_tudo, "auditoria": registros, "rodadas_runtime": 0 if aprovado else rodadas + 1}
    if aprovado:
        saida.update({"last_error_log": None, "falha_origem": None})
        return saida
    partes = []
    if bloq_h:
        partes.append(resumo_para_dev(bloq_h, "O HACKER invadiu ou abusou do sistema"))
    if bloq_m:
        partes.append(resumo_para_dev(bloq_m, "O MACACO (QA) quebrou o sistema"))
    if carga_ok is False:
        c = relatorios["carga"]
        partes.append(f"CARGA: o sistema só sustentou {c['estavel_ate_vus']} usuários simultâneos (mínimo {c['minimo_vus']}); saturou em "
                      f"{c['saturou_em_vus']}. Gargalo provável: {c['gargalo']}")
    erro = segredos.redigir("\n".join(partes))[0][:2400]
    origem_ui = all(a["categoria"] == "interface" for a in bloq_h + bloq_m) and bool(bloq_h + bloq_m) and carga_ok is not False
    assinatura = auditoria.assinatura_do_erro(erro)
    saida.update({"last_error_log": erro, "falha_origem": "frontend" if origem_ui else "backend",
                  "assinaturas_erro": auditoria.registrar_assinatura(state, assinatura)})
    if auditoria.estagnou(state, assinatura):
        saida["escalada"] = "estagnacao: os mesmos achados da validação em execução voltaram sem correção"
    elif rodadas + 1 >= LIMITE_RODADAS:
        saida["escalada"] = f"a validação em execução reprovou {LIMITE_RODADAS} vezes: o desenvolvimento não está resolvendo os achados"
    return saida

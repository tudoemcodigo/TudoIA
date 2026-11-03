"""
CHEFE (Tech Lead e orquestrador): o canal único entre o usuário e os demais agentes.

O usuário fala só com o CHEFE. Ele recebe a demanda, planeja (tamanho, stack, o que o sistema precisa), repassa o que os agentes
precisam saber, confere os critérios de pronto de cada fase ANTES de a fase seguinte começar e, quando a execução para (QA
reprovou três vezes, estagnação, orçamento, bloqueio), escreve o relatório de escalada para o humano decidir.

O que o CHEFE faz com modelo (planejar e conversar) fica em fronteiras estritas: o plano é validado campo a campo e cai num plano
padrão conservador se o modelo errar; a conversa nunca altera portão, aprovação nem configuração (só o comando explícito `/ajuste`
vira instrução, como DADO, para as fases seguintes). Os critérios de pronto são verificações em código, não opinião de modelo.
"""
import json
import re
import time
from typing import Optional

import auditoria
import doutrina_tec as dout
import entrada
import nodes
import segredos
import stacks
from auditoria import auditar
from execucao import RE_BLOCO, caminho_seguro, workspace
from state import SquadState

ARQUIVO_PLANO = "docs/chefe/PLANO.json"
ARQUIVO_PLANO_MD = "docs/chefe/PLANO.md"
ARQUIVO_ESCALADA = "docs/chefe/ESCALADA.md"
LIMITE_RODADAS_GATE = 2
TAMANHOS = ("trivial", "pequeno", "padrao", "grande")
MOTORES = ("mssql", "postgres", "mysql", "sqlite", "nenhum")

_RE_DADO = re.compile(r"^\W*(Dado|Given)\b", re.IGNORECASE | re.MULTILINE)
_RE_QUANDO = re.compile(r"^\W*(Quando|When)\b", re.IGNORECASE | re.MULTILINE)
_RE_ENTAO = re.compile(r"^\W*(Então|Entao|Then)\b", re.IGNORECASE | re.MULTILINE)
_RE_CENARIO = re.compile(r"^\W*(Cenário|Cenario|Scenario)\b", re.IGNORECASE | re.MULTILINE)
_RE_ERRO_NOMEADO = re.compile(r"\b[A-Z][A-Z0-9]{2,}(?:_[A-Z0-9]+)+\b")
_RE_PENDENCIA = re.compile(r"\b(TODO|TBD|A DEFINIR|\?\?\?)\b", re.IGNORECASE)


def _msg(de: str, para: str, texto: str) -> dict:
    return {"de": de, "para": para, "texto": texto[:4000], "em": time.time()}


# ---------------------------------------------------------------- plano
class PlanoInvalido(ValueError):
    pass


def validar_plano(bruto) -> dict:
    """Plano do CHEFE validado campo a campo. Qualquer desvio levanta PlanoInvalido: plano malformado nunca vira estado."""
    if not isinstance(bruto, dict):
        raise PlanoInvalido("o plano deve ser um objeto JSON")
    tamanho = bruto.get("tamanho")
    if tamanho not in TAMANHOS:
        raise PlanoInvalido(f"tamanho deve ser um de {list(TAMANHOS)}")
    stack = stacks.APELIDOS.get(str(bruto.get("stack", "")).strip().lower())
    if stack is None:
        raise PlanoInvalido(f"stack deve ser uma de {sorted(stacks.STACKS)}")
    for campo in ("precisa_banco", "precisa_frontend", "precisa_api"):
        if not isinstance(bruto.get(campo), bool):
            raise PlanoInvalido(f"{campo} deve ser true ou false")
    motor = str(bruto.get("motor_banco", "nenhum")).strip().lower()
    if motor not in MOTORES:
        raise PlanoInvalido(f"motor_banco deve ser um de {list(MOTORES)}")
    resumo = bruto.get("resumo")
    if not isinstance(resumo, str) or not resumo.strip():
        raise PlanoInvalido("resumo é obrigatório")
    riscos = bruto.get("riscos", [])
    if not isinstance(riscos, list) or not all(isinstance(r, str) for r in riscos) or len(riscos) > 8:
        raise PlanoInvalido("riscos deve ser uma lista de até 8 textos")
    return {"tamanho": tamanho, "stack": stack, "precisa_banco": bruto["precisa_banco"],
            "motor_banco": motor if bruto["precisa_banco"] else "nenhum", "precisa_frontend": bruto["precisa_frontend"],
            "precisa_api": bruto["precisa_api"], "resumo": resumo.strip()[:500], "riscos": [r.strip()[:200] for r in riscos]}


def plano_padrao(state: SquadState) -> dict:
    """Plano conservador quando o modelo não entrega um plano válido: tudo que um sistema empresarial costuma ter."""
    stack = stacks.resolver(state)
    declarado = ((state.get("target_stack") or {}).get("database") or {}).get("engine") or "postgres"
    motor = declarado if declarado in MOTORES else "postgres"
    return {"tamanho": "padrao", "stack": stack, "precisa_banco": True, "motor_banco": motor,
            "precisa_frontend": bool((state.get("target_stack") or {}).get("frontend")), "precisa_api": True,
            "resumo": "Plano padrão (o CHEFE não conseguiu planejar com o modelo): sistema com API e banco.", "riscos": [],
            "origem": "padrao"}


def _json_do_plano(resposta: str) -> dict:
    for m in RE_BLOCO.finditer(resposta or ""):
        if m.group("caminho").strip() == ARQUIVO_PLANO:
            return json.loads(m.group("corpo"))
    achado = re.search(r"\{.*\}", resposta or "", re.DOTALL)
    if not achado:
        raise PlanoInvalido("a resposta não trouxe um objeto JSON")
    return json.loads(achado.group(0))


def _ajustar_stack(target_stack: dict, plano: dict) -> dict:
    """Alinha a configuração da stack ao plano: se o CHEFE escolheu outra tecnologia, os comandos .NET da configuração saem de cena
    (valem os do adaptador); sem frontend no plano, a stack não declara frontend."""
    alvo = json.loads(json.dumps(target_stack or {}))
    backend = alvo.get("backend") or {}
    declarada = stacks.APELIDOS.get(str(backend.get("language", "")).strip().lower())
    if declarada != plano["stack"]:
        alvo["backend"] = {"language": plano["stack"]}
    else:
        backend.setdefault("language", plano["stack"])
        alvo["backend"] = backend
    if not plano["precisa_frontend"]:
        alvo.pop("frontend", None)
    if plano["precisa_banco"]:
        alvo.setdefault("database", {})["engine"] = plano["motor_banco"]
    else:
        alvo.pop("database", None)
    return alvo


@auditar("chefe_intake", "chefe")
def node_chefe_intake(state: SquadState) -> dict:
    """Recebe a demanda, planeja e decide o que a Squad vai (e não vai) fazer. É o primeiro passo de toda tarefa."""
    dout.verificar_versao(state)
    briefing, avisos = entrada.limpar_entrada(state["user_initial_briefing"], 20_000)
    instrucao = (
        "Você é o CHEFE da Squad de TI (Tech Lead): o único canal do usuário com os demais agentes. Planeje a demanda. Entregue UM "
        f"arquivo, {ARQUIVO_PLANO}, em bloco, com um objeto JSON com EXATAMENTE estes campos: "
        '"tamanho" ("trivial"|"pequeno"|"padrao"|"grande": pela quantidade de funcionalidades, integrações e risco), '
        f'"stack" (uma de {sorted(stacks.STACKS)}: .NET para serviço corporativo no padrão TEC; python para os demais), '
        '"precisa_banco" (bool), "motor_banco" ("mssql"|"postgres"|"mysql"|"sqlite"|"nenhum"), "precisa_frontend" (bool), '
        '"precisa_api" (bool), "resumo" (até 400 caracteres: o que será construído), "riscos" (até 8 textos curtos). '
        "Não escreva mais nada além do bloco.")
    fixa = state.get("stack_id") if state.get("stack_fixa") else None
    humano = f"Demanda do usuário:\n{briefing}" + (f"\nO usuário FIXOU a stack: {fixa}." if fixa else "")
    plano, erro = None, None
    for _ in (1, 2):
        resposta = nodes._chamar("chefe", state, instrucao + (f"\nO plano anterior foi recusado: {erro}. Corrija." if erro else ""),
                                 humano, agente="chefe")
        try:
            plano = validar_plano(_json_do_plano(resposta))
            break
        except (PlanoInvalido, ValueError) as e:
            erro = str(e)[:200]
    if plano is None:
        plano = plano_padrao(state)
    if fixa:
        plano["stack"] = fixa
    ws = workspace(state)
    destino = caminho_seguro(ws, ARQUIVO_PLANO)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(plano, ensure_ascii=False, indent=1), encoding="utf-8")
    md = [f"# Plano do CHEFE: {state.get('project_name', '')}", "", f"- Tamanho: {plano['tamanho']}", f"- Stack: {plano['stack']}",
          f"- Banco: {plano['motor_banco'] if plano['precisa_banco'] else 'não precisa'}",
          f"- Frontend: {'sim' if plano['precisa_frontend'] else 'não'}", f"- API: {'sim' if plano['precisa_api'] else 'não'}", "",
          "## Resumo", "", plano["resumo"], "", "## Riscos", "", *([f"- {r}" for r in plano["riscos"]] or ["- nenhum apontado"]), ""]
    if plano.get("origem") == "padrao":
        md += ["> Plano padrão: o modelo não entregou um plano válido nas duas tentativas.", ""]
    if avisos:
        md += ["## Avisos de entrada", "", *[f"- {a}" for a in avisos], ""]
    caminho_seguro(ws, ARQUIVO_PLANO_MD).write_text("\n".join(md), encoding="utf-8", newline="\n")
    fala = (f"Entendi. Vou tratar como um sistema {plano['tamanho']} em {stacks.STACKS[plano['stack']]['nome']}"
            f"{', com banco ' + plano['motor_banco'] if plano['precisa_banco'] else ', sem banco'}"
            f"{', com frontend' if plano['precisa_frontend'] else ', sem frontend'}. {plano['resumo']}")
    estado = {"current_phase": "PLANEJADO", "plano": plano, "stack_id": plano["stack"],
              "doutrina_excluir": list(stacks.STACKS[plano["stack"]]["excluir_familias"]),
              "target_stack": _ajustar_stack(state.get("target_stack") or {}, plano),
              "mensagens": [_msg("chefe", "usuario", fala)],
              "arquivos_gerados": [*(state.get("arquivos_gerados") or []), ARQUIVO_PLANO, ARQUIVO_PLANO_MD]}
    return estado


# ---------------------------------------------------------------- critérios de pronto (verificações em código)
def avaliar_requisitos(texto: str) -> list:
    """Pendências da BUSINESS_SPEC contra o critério de pronto. Lista vazia = pronta para o usuário aprovar."""
    falhas = []
    if len(texto.strip()) < 400:
        falhas.append("a especificação é curta demais para um sistema (menos de 400 caracteres)")
    if not _RE_CENARIO.search(texto):
        falhas.append("nenhum cenário (Cenário/Scenario) encontrado")
    faltam = [n for n, rx in (("Dado", _RE_DADO), ("Quando", _RE_QUANDO), ("Então", _RE_ENTAO)) if not rx.search(texto)]
    if faltam:
        falhas.append(f"cenários sem {', '.join(faltam)} (formato Dado-Quando-Então)")
    if not _RE_ERRO_NOMEADO.search(texto):
        falhas.append("nenhum erro de negócio nomeado em SCREAMING_SNAKE")
    if _RE_PENDENCIA.search(texto):
        falhas.append("há pendência em aberto (TODO, TBD, 'a definir' ou ???)")
    return falhas


def avaliar_design(prd: str, openapi: Optional[str], precisa_api: bool) -> list:
    falhas = []
    if len(prd.strip()) < 300:
        falhas.append("o PRD técnico é curto demais (menos de 300 caracteres)")
    if precisa_api:
        if not openapi or not openapi.strip():
            falhas.append("contrato OpenAPI ausente ou vazio")
        else:
            try:
                import yaml
                doc = yaml.safe_load(openapi)
            except Exception as e:  # YAML inválido é só um motivo de recusa (qualquer erro do parser)
                falhas.append(f"o OpenAPI não é um YAML válido ({type(e).__name__})")
                doc = None
            if doc is not None:
                if not isinstance(doc, dict) or not str(doc.get("openapi", "")).startswith("3."):
                    falhas.append("o OpenAPI não declara a versão 3.x")
                elif not doc.get("paths"):
                    falhas.append("o OpenAPI não tem nenhum caminho (paths)")
    return falhas


@auditar("chefe_gate_requisitos", "chefe")
def node_chefe_gate_requisitos(state: SquadState) -> dict:
    """Confere a especificação antes de o usuário aprová-la: devolve ao analista com a lista de pendências (até 2 rodadas)."""
    ws = workspace(state)
    texto = caminho_seguro(ws, state["business_spec_file"]).read_text(encoding="utf-8", errors="replace")
    falhas = avaliar_requisitos(texto)
    rodadas = int(state.get("rodadas_gate") or 0)
    if not falhas:
        return {"current_phase": "APROVACAO_REQUISITOS", "feedback_chefe": None, "rodadas_gate": 0,
                "mensagens": [_msg("chefe", "usuario", "A especificação passou nos critérios de pronto. Leia e aprove para eu seguir "
                                   "com a arquitetura.")]}
    if rodadas >= LIMITE_RODADAS_GATE:
        return {"escalada": "requisitos: a especificação não atingiu o critério de pronto em " f"{LIMITE_RODADAS_GATE} rodadas: "
                + "; ".join(falhas), "mensagens": [_msg("chefe", "usuario", "Não consegui fechar a especificação com o analista: "
                                                         + "; ".join(falhas))]}
    return {"feedback_chefe": "\n".join(f"- {f}" for f in falhas), "rodadas_gate": rodadas + 1, "business_spec_approved": False,
            "mensagens": [_msg("chefe", "usuario", f"Devolvi a especificação ao analista (rodada {rodadas + 1}): " + "; ".join(falhas))]}


@auditar("chefe_gate_design", "chefe")
def node_chefe_gate_design(state: SquadState) -> dict:
    """Confere o PRD e o contrato antes de o código começar. Reprovou = escala (a arquitetura não volta sozinha: ela exige aprovação)."""
    ws = workspace(state)
    prd = caminho_seguro(ws, state["technical_prd_file"]).read_text(encoding="utf-8", errors="replace")
    openapi = None
    if state.get("openapi_file"):
        openapi = caminho_seguro(ws, state["openapi_file"]).read_text(encoding="utf-8", errors="replace")
    falhas = avaliar_design(prd, openapi, (state.get("plano") or {}).get("precisa_api", True))
    if falhas:
        return {"escalada": "design: " + "; ".join(falhas),
                "mensagens": [_msg("chefe", "usuario", "A arquitetura não passou nos critérios de pronto: " + "; ".join(falhas))]}
    return {"current_phase": "DESIGN_APROVADO_PELO_CHEFE",
            "mensagens": [_msg("chefe", "usuario", "Arquitetura conferida (PRD e contrato válidos). Seguindo para o código.")]}


# ---------------------------------------------------------------- escalada
def _motivo_da_parada(state: SquadState) -> str:
    if state.get("escalada"):
        return str(state["escalada"])
    fase = state.get("current_phase")
    if fase == "ENTREGA_BLOQUEADA":
        quem = "AppSec" if state.get("security_passed") is False else "DevOps"
        return f"{quem} reprovou a entrega"
    if state.get("tests_passed") is False and state.get("iteration_count", 0) >= 3:
        return "o QA reprovou 3 vezes"
    if state.get("review_passed") is False and state.get("iteration_count", 0) >= 3:
        return "a revisão de código reprovou até o limite de iterações"
    return f"a execução parou na fase {fase}"


@auditar("chefe_escalada", "chefe")
def node_chefe_escalada(state: SquadState) -> dict:
    """Relatório para o humano quando a Squad não consegue seguir sozinha: o que parou, por quê, quanto gastou e o que decidir."""
    motivo = _motivo_da_parada(state)
    uso = auditoria.totais(state)
    erro = segredos.redigir(str(state.get("last_error_log") or "(sem log de erro)"))[0][:1500]
    linhas = [f"# Escalada: {state.get('project_name', '')}", "", f"- Tarefa: {state.get('task_id')}", f"- Fase: {state.get('current_phase')}",
              f"- Motivo: {motivo}", f"- Iterações de verificação: {state.get('iteration_count', 0)}",
              f"- Consumo: {uso['tokens']} tokens, {uso['chamadas']} chamadas, {uso['tempo_s']} s", "",
              "## Último erro (sem segredos)", "", "```", erro, "```", "",
              "## O que você pode decidir", "",
              "- Ajustar o briefing ou a especificação e iniciar uma nova tarefa.",
              "- Trocar o modelo do agente que está falhando (painel, Agentes) ou subir o orçamento e continuar.",
              "- Assumir a correção manualmente a partir dos artefatos em `workspace/` e dos relatórios em `tests/reports/`.", ""]
    destino = caminho_seguro(workspace(state), ARQUIVO_ESCALADA)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text("\n".join(linhas), encoding="utf-8", newline="\n")
    return {"escalada": state.get("escalada") or motivo, "mensagens": [_msg("chefe", "usuario", f"Parei e escalei para você: {motivo}. "
                                                                           f"Relatório em {ARQUIVO_ESCALADA}.")],
            "arquivos_gerados": [*(state.get("arquivos_gerados") or []), ARQUIVO_ESCALADA]}


# ---------------------------------------------------------------- conversa (canal único)
_RE_STATUS = re.compile(r"\b(status|andamento|como est[aá]|onde est[aá]|o que falta|progresso)\b", re.IGNORECASE)


def resumo_de_status(state: dict) -> str:
    """Resposta determinística (sem modelo) sobre o andamento: fase, portões, consumo e pendências."""
    uso = auditoria.totais(state)
    portoes = ", ".join(f"{n}: {'ok' if state.get(k) is True else 'pendente'}" for n, k in
                        (("testes", "tests_passed"), ("revisão", "review_passed"), ("segurança", "security_passed"), ("devops", "devops_passed")))
    base = f"Fase: {state.get('current_phase')}. Portões: {portoes}. Consumo: {uso['tokens']} tokens, {uso['chamadas']} chamadas."
    if state.get("escalada"):
        base += f" PARADA: {state['escalada']}."
    return base


def responder(state: dict, texto: str, tarefa_aguarda_resposta: bool) -> dict:
    """Mensagem do usuário ao CHEFE. Devolve as atualizações de estado (só trilhas que acrescentam). NUNCA mexe em aprovação, portão
    ou configuração. `/ajuste <texto>` é a única forma de virar instrução, sempre como dado sanitizado."""
    limpo, avisos = entrada.limpar_entrada(texto, 4000)
    entrou = _msg("usuario", "chefe", limpo)
    if limpo.strip().lower().startswith("/ajuste"):
        instrucao = limpo.strip()[len("/ajuste"):].strip()
        if not instrucao:
            return {"mensagens": [entrou, _msg("chefe", "usuario", "Escreva a instrução depois de /ajuste.")]}
        return {"mensagens": [entrou, _msg("chefe", "usuario", "Anotei como instrução para as próximas fases. Ela não altera "
                                           "aprovações nem portões.")], "observacoes_usuario": [instrucao]}
    if _RE_STATUS.search(limpo):
        return {"mensagens": [entrou, _msg("chefe", "usuario", resumo_de_status(state))]}
    if tarefa_aguarda_resposta:
        return {"mensagens": [entrou, _msg("chefe", "usuario", "Recebi a resposta e vou repassá-la ao analista.")]}
    resposta = nodes._chamar("chefe", state, "Você é o CHEFE da Squad de TI, o único canal do usuário. Responda em português, em até 6 "
                             "linhas, só sobre esta tarefa, usando apenas o resumo abaixo. Não prometa mudar aprovações, portões ou "
                             "configuração: isso o usuário faz no painel.", f"Resumo da tarefa: {resumo_de_status(state)}\n"
                             f"Plano: {json.dumps(state.get('plano') or {}, ensure_ascii=False)}\nMensagem do usuário: {limpo}",
                             com_nucleo=False, agente="chefe", com_regras=False)
    return {"mensagens": [entrou, _msg("chefe", "usuario", resposta[:2000])]}

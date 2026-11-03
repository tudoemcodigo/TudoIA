"""
CLI da Squad de TI (LangGraph). Uma tarefa é uma conversa com checkpoint em SQLite, retomável entre execuções:

    python main.py iniciar   --tarefa TASK-001 --briefing "..." [--config stack_config.json]
                             [--perfil local-estrito|local|hibrido|nuvem|max | --modelo NOME]
    python main.py responder --tarefa TASK-001 --resposta "..."   # responde às perguntas do Analista de Requisitos
    python main.py aprovar   --tarefa TASK-001                    # aprova o BUSINESS_SPEC e libera a arquitetura
    python main.py aprovar-release --tarefa TASK-001              # aprova o release (só gera notas; sem git, tag nem publicação)
    python main.py estado    --tarefa TASK-001

Privacidade: por padrão só modelo local (ver nodes.py). `--modelo` define TUDOIA_MODEL antes de carregar os nós.
"""
import argparse
import json
import os
import sys

from perfis import PERFIS
from servico import ErroUso, cfg_da_tarefa, montar_entrada, situacao, tarefa_valida  # noqa: F401 (ErroUso e tarefa_valida são API do módulo)

DB_PADRAO = "squad_state.db"
CONFIG_PADRAO = "stack_config.example.json"


def carregar_stack_config(caminho: str = CONFIG_PADRAO) -> dict:
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        raise ErroUso(f"configuração de stack ilegível ({caminho}): {e}") from e


def explicar_falha(e: Exception) -> str | None:
    """Mensagem acionável para falhas do gateway; None para o resto. Nunca repete o corpo da resposta:
    o LiteLLM devolve ali pedaços e o hash da chave usada."""
    try:
        import openai
    except ImportError:
        return None
    modelo = os.getenv("TUDOIA_MODEL", "tudoia-local")
    if isinstance(e, openai.AuthenticationError):
        return ("o gateway recusou a chave. Defina TUDOIA_API_KEY com uma chave virtual do LiteLLM "
                "(o padrão 'sk-tudoia-local' é só um exemplo e não é aceito).")
    if isinstance(e, openai.PermissionDeniedError):
        return (f"a chave em TUDOIA_API_KEY não tem acesso ao modelo '{modelo}'. "
                "Use uma chave virtual que liste esse modelo (ou outro --perfil).")
    if isinstance(e, openai.NotFoundError):
        return (f"o gateway não conhece o modelo '{modelo}'. Gere o config.yaml do TudoIA "
                "(painel, aba Roteador) e reinicie o LiteLLM.")
    if isinstance(e, (openai.APIConnectionError, openai.APITimeoutError)):
        url = os.getenv("TUDOIA_GATEWAY_URL", "http://localhost:4000/v1")
        return f"não consegui falar com o gateway do TudoIA em {url}. O LiteLLM está no ar?"
    return None


def construir_app(db_path: str = DB_PADRAO):
    from graph import build_squad_graph  # import tardio: carrega os nós só depois de TUDOIA_MODEL estar definido
    return build_squad_graph(db_path)


def _executar(app, entrada, cfg) -> None:
    for evento in app.stream(entrada, cfg):
        for no, atualizacao in evento.items():
            if no.startswith("__"):
                continue
            print(f"\n---> [Nó Executado]: {no}")
            for pergunta in (atualizacao or {}).get("interview_questions") or []:
                print(f"[Perguntas do Analista de Requisitos]:\n{pergunta}")
    _situacao(app, cfg)


PREFIXO_SITUACAO = {
    "aguardando_aprovacao_spec": "Pausada", "aguardando_aprovacao_release": "Pausada", "concluida": "Concluída",
    "bloqueada": "Bloqueada", "escalada_qa": "Escalação humana", "escalada_revisao": "Escalação humana",
    "aguardando_respostas": "Aguardando o usuário",
}


def _situacao(app, cfg) -> None:
    s = situacao(app, cfg)
    if s["estado"] == "inexistente":
        print("\n[Tarefa inexistente]")
        return
    prefixo = "Pausada" if s["estado"] == "em_fase" and s["aguardando"] else PREFIXO_SITUACAO.get(s["estado"], "Fase")
    print(f"\n[{prefixo}]: {s['mensagem']}")


def cmd_iniciar(app, args) -> None:
    cfg = {"configurable": {"thread_id": tarefa_valida(args.tarefa)}}
    if app.get_state(cfg).values:
        raise ErroUso(f"a tarefa {args.tarefa} já existe; use `responder`, `aprovar` ou outro identificador")
    config = carregar_stack_config(args.config)
    entrada = montar_entrada(args.tarefa, args.briefing, config)
    print(f"[Iniciando Tarefa]: {args.tarefa} para o projeto {config['project_name']}")
    _executar(app, entrada, cfg)


def cmd_responder(app, args) -> None:
    cfg = {"configurable": {"thread_id": tarefa_valida(args.tarefa)}}
    valores = app.get_state(cfg).values
    if not valores:
        raise ErroUso(f"tarefa inexistente: {args.tarefa}")
    if not args.resposta.strip():
        raise ErroUso("a resposta não pode ser vazia")
    _executar(app, {"interview_answers": [*valores.get("interview_answers", []), args.resposta]}, cfg)


def cmd_aprovar(app, args) -> None:
    cfg = {"configurable": {"thread_id": tarefa_valida(args.tarefa)}}
    snap = app.get_state(cfg)
    if "arquiteto" not in snap.next:
        raise ErroUso("nada a aprovar: a tarefa não está pausada antes do arquiteto")
    app.update_state(cfg, {"business_spec_approved": True})
    _executar(app, None, cfg)


def cmd_aprovar_release(app, args) -> None:
    cfg = {"configurable": {"thread_id": tarefa_valida(args.tarefa)}}
    snap = app.get_state(cfg)
    if "release" not in snap.next:
        raise ErroUso("nada a aprovar: a tarefa não está pausada antes do release")
    app.update_state(cfg, {"release_approved": True})
    _executar(app, None, cfg)


def cmd_estado(app, args) -> None:
    _situacao(app, {"configurable": {"thread_id": tarefa_valida(args.tarefa)}})


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for nome, funcao in (("iniciar", cmd_iniciar), ("responder", cmd_responder), ("aprovar", cmd_aprovar),
                         ("aprovar-release", cmd_aprovar_release), ("estado", cmd_estado)):
        p = sub.add_parser(nome)
        p.add_argument("--tarefa", required=True)
        p.add_argument("--db", default=DB_PADRAO)
        p.set_defaults(funcao=funcao)
        if nome == "iniciar":
            p.add_argument("--briefing", required=True)
            p.add_argument("--config", default=CONFIG_PADRAO)
            destino = p.add_mutually_exclusive_group()
            destino.add_argument("--perfil", choices=sorted(PERFIS),
                                 help="perfil de destino do TudoIA; hibrido, nuvem e max exigem TUDOIA_PERMITIR_NUVEM=1")
            destino.add_argument("--modelo", help="define TUDOIA_MODEL diretamente (padrão: tudoia-local)")
        if nome == "responder":
            p.add_argument("--resposta", required=True)
    args = ap.parse_args(argv)
    if getattr(args, "perfil", None):
        os.environ["TUDOIA_MODEL"] = PERFIS[args.perfil]
    elif getattr(args, "modelo", None):
        os.environ["TUDOIA_MODEL"] = args.modelo
    try:
        args.funcao(construir_app(args.db), args)
    except ErroUso as e:
        print(f"erro: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # falha fechada e visível: doutrina ilegível, modelo de nuvem sem consentimento, saída inválida
        print(f"erro: {explicar_falha(e) or f'{type(e).__name__}: {e}'}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

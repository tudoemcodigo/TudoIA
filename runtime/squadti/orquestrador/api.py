"""
API local da Squad de TI (para o painel do TudoIA). Só stdlib, loopback por padrão, sempre com token.

    TUDOIA_SQUADTI_TOKEN=<32+ caracteres> python api.py [--host 127.0.0.1|0.0.0.0] [--porta 8790] [--db squad_state.db]

Rotas (JSON; tudo em /api exige `Authorization: Bearer <token>`):
    GET  /saude                                  sem token
    GET  /api/tarefas                            lista com situação e execução
    GET  /api/tarefas/{id}                       detalhe: situação, perguntas, arquivos, execução
    GET  /api/tarefas/{id}/arquivo?caminho=...   texto de um arquivo do workspace (limitado, segredos omitidos)
    POST /api/tarefas                            {tarefa, briefing, perfil?, consentimento_nuvem?}
    POST /api/tarefas/{id}/responder             {resposta}
    POST /api/tarefas/{id}/aprovar               aprova o BUSINESS_SPEC
    POST /api/tarefas/{id}/aprovar-release       aprova o release
As ações respondem 202 e rodam em segundo plano, uma tarefa por vez (409 se houver outra rodando).

Fronteiras: Host só loopback, POST só application/json até 64 KB, comparação do token em tempo constante, caminho de arquivo
validado por `caminho_seguro`, perfil só entre os da Squad, e perfil que sai da máquina só com `consentimento_nuvem: true`.
"""
import argparse
import hmac
import json
import os
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import agentes
import auditoria
import chefe
import proveniencia
from execucao import workspace
from state import RESET
from perfis import PERFIS, modelo_e_local
from servico import ErroUso, aprovar_release, aprovar_spec, cfg_da_tarefa, montar_entrada, situacao, tarefa_valida

PORTA_PADRAO = 8790
TOKEN_MIN = 32
MAX_CORPO = 64 * 1024
MAX_ARQUIVO = 200_000
MAX_LISTA = 200
MAX_ERRO = 500
MAX_EVENTOS = 500
MAX_MENSAGEM = 4000
PERFIL_PADRAO = "local-estrito"
HOSTS_DE_BIND = ("127.0.0.1", "0.0.0.0")  # nada além disso: a API nunca escuta numa interface escolhida por texto livre
RE_TAREFA_ROTA = r"(?P<id>[A-Za-z0-9][A-Za-z0-9._-]{0,63})"


class ErroHttp(Exception):
    def __init__(self, status: int, codigo: str, mensagem: str):
        super().__init__(mensagem)
        self.status, self.codigo, self.mensagem = status, codigo, mensagem


class Execucoes:
    """Uma execução por vez (o grafo compartilha um checkpoint SQLite e o modelo local é um só). O registro é só informativo:
    a verdade da tarefa é o checkpoint."""

    def __init__(self):
        self._trava = threading.Lock()
        self.registros: dict = {}

    def iniciar(self, tarefa: str, acao: str, trabalho) -> None:
        if not self._trava.acquire(blocking=False):
            ocupada = next((t for t, r in self.registros.items() if r["estado"] == "rodando"), "outra tarefa")
            raise ErroHttp(409, "ocupado", f"já há uma execução em andamento ({ocupada}); aguarde terminar")
        registro = {"estado": "rodando", "acao": acao, "inicio": time.time(), "fim": None, "nos": [], "erro": None,
                    "eventos": []}
        self.registros[tarefa] = registro

        def evento(texto):
            registro["eventos"].append({"em": time.time(), "texto": texto})
            del registro["eventos"][:-MAX_EVENTOS]  # só os últimos: o log ao vivo não cresce sem limite

        def corpo():
            auditoria.registrar_sink(tarefa, evento)
            try:
                resultado = trabalho(lambda no: registro["nos"].append(no))
                if isinstance(resultado, tuple) and resultado and resultado[0] == "escalada":
                    registro["estado"], registro["erro"] = "escalada", str(resultado[1])[:MAX_ERRO]
                else:
                    registro["estado"] = "ok"
            except Exception as e:  # falha fechada e visível: doutrina ilegível, modelo sem consentimento, saída inválida
                from main import explicar_falha
                registro["estado"] = "erro"
                registro["erro"] = (explicar_falha(e) or f"{type(e).__name__}: {e}")[:MAX_ERRO]
            finally:
                auditoria.registrar_sink(tarefa, None)
                registro["fim"] = time.time()
                self._trava.release()

        threading.Thread(target=corpo, name=f"squad-{tarefa}", daemon=True).start()

    def de(self, tarefa: str):
        r = self.registros.get(tarefa)
        return None if r is None else {**{k: v for k, v in r.items() if k != "eventos"}, "nos": list(r["nos"])}

    def eventos(self, tarefa: str, desde: int = 0) -> list:
        r = self.registros.get(tarefa)
        return [] if r is None else list(r["eventos"])[max(0, desde):]


class Servico:
    def __init__(self, app, config_stack: dict, token: str):
        self.app, self.config_stack, self.token = app, config_stack, token
        self.execucoes = Execucoes()

    # ------------------------------------------------------------ leitura
    def tarefas(self) -> list:
        conn = self.app.checkpointer.conn
        self.app.checkpointer.setup()  # banco novo ainda não tem a tabela de checkpoints
        with self.app.checkpointer.lock:
            ids = [r[0] for r in conn.execute("SELECT DISTINCT thread_id FROM checkpoints ORDER BY thread_id").fetchall()]
        return [self.resumo(t) for t in ids[:MAX_LISTA]]

    def resumo(self, tarefa: str) -> dict:
        cfg = cfg_da_tarefa(tarefa)
        v = self.app.get_state(cfg).values or {}
        return {"tarefa": tarefa, "projeto": v.get("project_name"), "modelo": v.get("modelo"),
                "situacao": situacao(self.app, cfg), "execucao": self.execucoes.de(tarefa)}

    def detalhe(self, tarefa: str) -> dict:
        cfg = cfg_da_tarefa(tarefa)
        v = self.app.get_state(cfg).values or {}
        if not v:
            raise ErroHttp(404, "nao_encontrado", f"tarefa inexistente: {tarefa}")
        return {**self.resumo(tarefa), "briefing": v.get("user_initial_briefing"),
                "perguntas": v.get("interview_questions") or [], "respostas": v.get("interview_answers") or [],
                "iteracao": v.get("iteration_count", 0), "arquivos": v.get("arquivos_gerados") or [],
                "doutrina": {"versao": v.get("doutrina_versao"), "hash": v.get("doutrina_hash")},
                "verificacoes": {k: v.get(k) for k in ("tests_passed", "review_passed", "security_passed", "devops_passed")},
                "falha_origem": v.get("falha_origem"), "consentimento_nuvem": v.get("consentimento_nuvem") is True}

    def arquivo(self, tarefa: str, caminho: str) -> dict:
        from execucao import caminho_seguro
        from segredos import redigir
        cfg = cfg_da_tarefa(tarefa)
        v = self.app.get_state(cfg).values or {}
        if not v:
            raise ErroHttp(404, "nao_encontrado", f"tarefa inexistente: {tarefa}")
        raiz = (Path.cwd() / v["workspace_dir"]).resolve()
        try:
            destino = caminho_seguro(raiz, caminho or "")
        except ValueError as e:
            raise ErroHttp(422, "validacao", str(e)) from e
        if not destino.is_file():
            raise ErroHttp(404, "nao_encontrado", "arquivo inexistente")
        bruto = destino.read_bytes()[:MAX_ARQUIVO + 1]
        try:
            texto = bruto.decode("utf-8")
        except UnicodeDecodeError as e:
            raise ErroHttp(415, "binario", "o arquivo não é texto") from e
        truncado = len(bruto) > MAX_ARQUIVO
        texto, omitidas = redigir(texto[:MAX_ARQUIVO])
        return {"caminho": caminho, "conteudo": texto, "truncado": truncado, "linhas_omitidas": omitidas}

    # ------------------------------------------------------------ ações
    def _perfil(self, corpo: dict) -> tuple[str, bool]:
        perfil = corpo.get("perfil") or PERFIL_PADRAO
        if perfil not in PERFIS:
            raise ErroHttp(422, "validacao", f"perfil inválido: use um de {sorted(PERFIS)}")
        modelo = PERFIS[perfil]
        consentimento = corpo.get("consentimento_nuvem")
        if consentimento is not None and not isinstance(consentimento, bool):
            raise ErroHttp(422, "validacao", "consentimento_nuvem deve ser true ou false")
        if not modelo_e_local(modelo) and consentimento is not True:
            raise ErroHttp(422, "consentimento_nuvem",
                           f"o perfil '{perfil}' pode enviar código e esquema para a nuvem; envie consentimento_nuvem: true")
        return modelo, consentimento is True

    def _consentimento_dos_agentes(self, cfg_agentes: dict, consentimento: bool) -> None:
        """Agente configurado com perfil que pode sair da máquina só vale se a tarefa trouxe o consentimento explícito."""
        fora = agentes.modelos_que_saem_da_maquina(cfg_agentes)
        if fora and not consentimento:
            raise ErroHttp(422, "consentimento_nuvem", f"os agentes {fora} usam perfil que pode sair da máquina; "
                                                       "envie consentimento_nuvem: true")

    def agentes_cfg(self) -> dict:
        try:
            return agentes.carregar()
        except agentes.ConfigInvalida as e:
            raise ErroHttp(500, "config_invalida", str(e)) from e

    def salvar_agentes(self, corpo: dict) -> dict:
        try:
            return agentes.salvar(corpo)
        except agentes.ConfigInvalida as e:
            raise ErroHttp(422, "validacao", str(e)) from e

    def iniciar(self, corpo: dict) -> dict:
        tarefa = tarefa_valida(str(corpo.get("tarefa", "")))
        briefing = corpo.get("briefing")
        if not isinstance(briefing, str) or not briefing.strip() or len(briefing) > 20_000:
            raise ErroHttp(422, "validacao", "briefing obrigatório, texto de até 20000 caracteres")
        modelo, consentimento = self._perfil(corpo)
        cfg = cfg_da_tarefa(tarefa)
        if self.app.get_state(cfg).values:
            raise ErroHttp(409, "conflito", f"a tarefa {tarefa} já existe")
        cfg_agentes = self.agentes_cfg()
        if isinstance(corpo.get("orcamento"), dict):  # teto desta tarefa (substitui o padrão da configuração)
            cfg_agentes = {**cfg_agentes, "orcamento": agentes.validar({"orcamento": corpo["orcamento"]})["orcamento"]}
        self._consentimento_dos_agentes(cfg_agentes, consentimento)
        stack = corpo.get("stack")
        entrada = montar_entrada(tarefa, briefing, self.config_stack, modelo, consentimento, stack, cfg_agentes)
        self._rodar(tarefa, "iniciar", entrada, cfg)
        # o primeiro checkpoint ainda não existe: o que se sabe agora vem da entrada
        return {"tarefa": tarefa, "projeto": entrada["project_name"], "modelo": modelo,
                "situacao": {"estado": "em_fase", "fase": None, "aguardando": [], "mensagem": "iniciando"},
                "execucao": self.execucoes.de(tarefa)}

    def responder(self, tarefa: str, corpo: dict) -> dict:
        resposta = corpo.get("resposta")
        if not isinstance(resposta, str) or not resposta.strip() or len(resposta) > 20_000:
            raise ErroHttp(422, "validacao", "resposta obrigatória, texto de até 20000 caracteres")
        cfg = cfg_da_tarefa(tarefa)
        v = self.app.get_state(cfg).values
        if not v:
            raise ErroHttp(404, "nao_encontrado", f"tarefa inexistente: {tarefa}")
        self._rodar(tarefa, "responder", {"interview_answers": [*v.get("interview_answers", []), resposta]}, cfg)
        return self.resumo(tarefa)

    def aprovar(self, tarefa: str, no: str, campo: str, acao: str) -> dict:
        cfg = cfg_da_tarefa(tarefa)
        snap = self.app.get_state(cfg)
        if not snap.values:
            raise ErroHttp(404, "nao_encontrado", f"tarefa inexistente: {tarefa}")
        if no not in snap.next:
            raise ErroHttp(409, "estado_invalido", f"nada a aprovar: a tarefa não está pausada antes de {no}")

        def antes():
            # o sim vale para o CONTEÚDO que o usuário viu: grava o hash junto (aprovacao.py)
            (aprovar_spec if no == "arquiteto" else aprovar_release)(self.app, cfg)
        self._rodar(tarefa, acao, None, cfg, antes)
        return self.resumo(tarefa)

    def continuar(self, tarefa: str, corpo: dict) -> dict:
        """Retoma uma tarefa escalada (orçamento, estagnação, saída inválida) depois de o humano decidir: limpa a parada, opcionalmente
        sobe o orçamento e re-executa a partir do checkpoint. Não passa por cima de aprovação nem de portão."""
        cfg = cfg_da_tarefa(tarefa)
        v = self.app.get_state(cfg).values
        if not v:
            raise ErroHttp(404, "nao_encontrado", f"tarefa inexistente: {tarefa}")
        if not v.get("escalada"):
            raise ErroHttp(409, "estado_invalido", "a tarefa não está escalada")
        mudancas = {"escalada": None, "assinaturas_erro": [RESET]}
        if isinstance(corpo.get("orcamento"), dict):
            mudancas["orcamento"] = agentes.validar({"orcamento": corpo["orcamento"]})["orcamento"]

        def antes():
            self.app.update_state(cfg, mudancas)
        self._rodar(tarefa, "continuar", None, cfg, antes)
        return self.resumo(tarefa)

    # ------------------------------------------------------------ CHEFE (canal único), auditoria, proveniência, log
    def mensagens(self, tarefa: str) -> dict:
        cfg = cfg_da_tarefa(tarefa)
        v = self.app.get_state(cfg).values or {}
        if not v:
            raise ErroHttp(404, "nao_encontrado", f"tarefa inexistente: {tarefa}")
        return {"mensagens": v.get("mensagens") or [], "observacoes": v.get("observacoes_usuario") or []}

    def mensagem(self, tarefa: str, corpo: dict) -> dict:
        """O usuário fala com o CHEFE. Resposta à entrevista segue ao analista; `/ajuste` vira instrução; o resto o CHEFE responde.
        Nunca altera aprovação, portão nem configuração."""
        texto = corpo.get("texto")
        if not isinstance(texto, str) or not texto.strip() or len(texto) > MAX_MENSAGEM:
            raise ErroHttp(422, "validacao", f"texto obrigatório, de até {MAX_MENSAGEM} caracteres")
        cfg = cfg_da_tarefa(tarefa)
        v = self.app.get_state(cfg).values
        if not v:
            raise ErroHttp(404, "nao_encontrado", f"tarefa inexistente: {tarefa}")
        aguarda = situacao(self.app, cfg)["estado"] == "aguardando_respostas"
        try:
            atualizacao = chefe.responder(v, texto, aguarda)
        except auditoria.EscaladaHumana as e:
            raise ErroHttp(503, "indisponivel", f"o CHEFE não conseguiu responder: {e.motivo}") from e
        self.app.update_state(cfg, atualizacao)
        if aguarda:
            limpo = atualizacao["mensagens"][0]["texto"]
            self._rodar(tarefa, "responder", {"interview_answers": [*v.get("interview_answers", []), limpo]}, cfg)
        return {"mensagens": atualizacao["mensagens"]}

    def auditoria(self, tarefa: str) -> dict:
        cfg = cfg_da_tarefa(tarefa)
        v = self.app.get_state(cfg).values or {}
        if not v:
            raise ErroHttp(404, "nao_encontrado", f"tarefa inexistente: {tarefa}")
        nos = [{k: r.get(k) for k in ("no", "papel", "inicio", "duracao_s", "chamadas", "tokens_entrada", "tokens_saida", "modelos")}
               for r in v.get("auditoria") or []]
        return {"totais": auditoria.totais(v), "orcamento": v.get("orcamento") or {}, "nos": nos,
                "chamadas": [{"no": r.get("no"), **{k: c.get(k) for k in ("agente", "modelo", "tentativa", "tokens_entrada",
                                                                          "tokens_saida", "duracao_s", "prompt_sha")}}
                             for r in v.get("auditoria") or [] for c in r.get("detalhe") or []]}

    def proveniencia(self, tarefa: str) -> dict:
        cfg = cfg_da_tarefa(tarefa)
        v = self.app.get_state(cfg).values or {}
        if not v:
            raise ErroHttp(404, "nao_encontrado", f"tarefa inexistente: {tarefa}")
        return proveniencia.gerar(v, workspace(v))

    def log(self, tarefa: str, desde: int) -> dict:
        tarefa_valida(tarefa)
        eventos = self.execucoes.eventos(tarefa, 0)
        return {"eventos": eventos[desde:], "proximo": len(eventos)}

    def _rodar(self, tarefa, acao, entrada, cfg, antes=None) -> None:
        def trabalho(registrar):
            try:
                if antes:
                    antes()
                for evento in self.app.stream(entrada, cfg):
                    for no in evento:
                        if not no.startswith("__"):
                            registrar({"no": no, "em": time.time()})
            except auditoria.EscaladaHumana as e:
                # o nó não terminou: o checkpoint fica antes dele; o estado marca a parada e `continuar` retoma
                self.app.update_state(cfg, {"escalada": e.motivo})
                return ("escalada", e.motivo)
        self.execucoes.iniciar(tarefa, acao, trabalho)


def _inteiro(texto: str) -> int:
    try:
        return max(0, int(texto))
    except ValueError:
        return 0


def criar_handler(servico: Servico, porta: int):
    hosts_ok = {f"127.0.0.1:{porta}", f"localhost:{porta}", "127.0.0.1", "localhost"}
    rotas_get = [
        (re.compile(r"^/api/tarefas$"), lambda m, q: {"tarefas": servico.tarefas()}),
        (re.compile(rf"^/api/tarefas/{RE_TAREFA_ROTA}$"), lambda m, q: servico.detalhe(m["id"])),
        (re.compile(rf"^/api/tarefas/{RE_TAREFA_ROTA}/arquivo$"),
         lambda m, q: servico.arquivo(m["id"], (q.get("caminho") or [""])[0])),
        (re.compile(r"^/api/agentes$"), lambda m, q: servico.agentes_cfg()),
        (re.compile(rf"^/api/tarefas/{RE_TAREFA_ROTA}/mensagens$"), lambda m, q: servico.mensagens(m["id"])),
        (re.compile(rf"^/api/tarefas/{RE_TAREFA_ROTA}/auditoria$"), lambda m, q: servico.auditoria(m["id"])),
        (re.compile(rf"^/api/tarefas/{RE_TAREFA_ROTA}/proveniencia$"), lambda m, q: servico.proveniencia(m["id"])),
        (re.compile(rf"^/api/tarefas/{RE_TAREFA_ROTA}/log$"),
         lambda m, q: servico.log(m["id"], _inteiro((q.get("desde") or ["0"])[0]))),
    ]
    rotas_post = [
        (re.compile(r"^/api/tarefas$"), lambda m, c: servico.iniciar(c)),
        (re.compile(rf"^/api/tarefas/{RE_TAREFA_ROTA}/responder$"), lambda m, c: servico.responder(m["id"], c)),
        (re.compile(rf"^/api/tarefas/{RE_TAREFA_ROTA}/aprovar$"),
         lambda m, c: servico.aprovar(m["id"], "arquiteto", "business_spec_approved", "aprovar")),
        (re.compile(rf"^/api/tarefas/{RE_TAREFA_ROTA}/aprovar-release$"),
         lambda m, c: servico.aprovar(m["id"], "release", "release_approved", "aprovar-release")),
        (re.compile(rf"^/api/tarefas/{RE_TAREFA_ROTA}/mensagem$"), lambda m, c: servico.mensagem(m["id"], c)),
        (re.compile(rf"^/api/tarefas/{RE_TAREFA_ROTA}/continuar$"), lambda m, c: servico.continuar(m["id"], c)),
        (re.compile(r"^/api/agentes$"), lambda m, c: servico.salvar_agentes(c)),
    ]

    class Handler(BaseHTTPRequestHandler):
        server_version = "SquadTI"
        sys_version = ""

        def log_message(self, *args):  # sem log de acesso: a URL pode trazer nomes de tarefa e de arquivo
            pass

        def _enviar(self, status: int, corpo: dict):
            dados = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(dados)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(dados)

        def _autorizar(self):
            if self.headers.get("Host", "") not in hosts_ok:
                raise ErroHttp(403, "host_recusado", "Host não permitido")
            cab = self.headers.get("Authorization", "")
            esperado = f"Bearer {servico.token}"
            if not hmac.compare_digest(cab.encode("utf-8"), esperado.encode("utf-8")):
                raise ErroHttp(401, "nao_autenticado", "token ausente ou inválido")

        def _tratar(self, metodo: str):
            try:
                url = urlparse(self.path)
                if metodo == "GET" and url.path == "/saude":
                    if self.headers.get("Host", "") not in hosts_ok:
                        raise ErroHttp(403, "host_recusado", "Host não permitido")
                    return self._enviar(200, {"ok": True})
                if not url.path.startswith("/api/"):
                    raise ErroHttp(404, "nao_encontrado", "rota inexistente")
                self._autorizar()
                corpo = {}
                if metodo == "POST":
                    if (self.headers.get("Content-Type", "").split(";")[0].strip().lower()) != "application/json":
                        raise ErroHttp(415, "tipo_de_conteudo", "use application/json")
                    try:
                        tamanho = int(self.headers.get("Content-Length", "0"))
                    except ValueError as e:
                        raise ErroHttp(400, "requisicao_invalida", "Content-Length inválido") from e
                    if tamanho < 0 or tamanho > MAX_CORPO:
                        raise ErroHttp(413, "corpo_grande_demais", f"corpo acima de {MAX_CORPO} bytes")
                    try:
                        corpo = json.loads(self.rfile.read(tamanho) or b"{}")
                    except ValueError as e:
                        raise ErroHttp(400, "requisicao_invalida", "JSON inválido") from e
                    if not isinstance(corpo, dict):
                        raise ErroHttp(422, "validacao", "o corpo deve ser um objeto JSON")
                for padrao, funcao in (rotas_get if metodo == "GET" else rotas_post):
                    m = padrao.match(url.path)
                    if m:
                        arg = parse_qs(url.query) if metodo == "GET" else corpo
                        resultado = funcao(m.groupdict(), arg)
                        return self._enviar(202 if metodo == "POST" else 200, resultado)
                raise ErroHttp(404, "nao_encontrado", "rota inexistente")
            except ErroHttp as e:
                self._enviar(e.status, {"erro": {"codigo": e.codigo, "mensagem": e.mensagem}})
            except ErroUso as e:
                self._enviar(422, {"erro": {"codigo": "validacao", "mensagem": str(e)}})
            except Exception as e:
                self._enviar(500, {"erro": {"codigo": "falha_interna", "mensagem": f"falha interna: {type(e).__name__}"}})

        def do_GET(self):
            self._tratar("GET")

        def do_POST(self):
            self._tratar("POST")

    return Handler


def token_do_ambiente() -> str:
    token = os.getenv("TUDOIA_SQUADTI_TOKEN", "")
    if len(token) < TOKEN_MIN:
        raise SystemExit(f"TUDOIA_SQUADTI_TOKEN ausente ou com menos de {TOKEN_MIN} caracteres: a API não sobe sem token")
    return token


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default=os.getenv("TUDOIA_SQUADTI_HOST", "127.0.0.1"), choices=HOSTS_DE_BIND,
                    help="127.0.0.1 (padrão). 0.0.0.0 só dentro do container, cuja porta é publicada só em loopback no host")
    ap.add_argument("--porta", type=int, default=int(os.getenv("TUDOIA_SQUADTI_PORTA", PORTA_PADRAO)))
    ap.add_argument("--db", default=os.getenv("SQUADTI_DB", "squad_state.db"))
    ap.add_argument("--config", default=os.getenv("SQUADTI_STACK_CONFIG", "stack_config.example.json"))
    args = ap.parse_args(argv)
    token = token_do_ambiente()
    os.environ.setdefault("TUDOIA_MODEL", PERFIS[PERFIL_PADRAO])
    from main import carregar_stack_config, construir_app
    servico = Servico(construir_app(args.db), carregar_stack_config(args.config), token)
    httpd = ThreadingHTTPServer((args.host, args.porta), criar_handler(servico, args.porta))
    print(f"SquadTI API em http://{args.host}:{args.porta} (token por TUDOIA_SQUADTI_TOKEN)", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())

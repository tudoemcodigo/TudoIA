"""Assistente local: HTTP em 127.0.0.1 que serve a tela e a API do instalador.

O instalador executa comandos e grava arquivos na máquina, então qualquer página aberta no navegador não pode
conseguir dirigi-lo. Defesas: escuta só em loopback; token aleatório por execução (cabeçalho X-Token, comparado em
tempo constante); `Host` exato; `Origin`, se presente, local; corpo JSON de até 256 KB; nada de CORS.
"""
from __future__ import annotations

import hmac
import json
import os
import secrets
import string
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import VERSAO
from .etapas import montar_etapas
from .execucao import Redator
from .motor import Contexto, Motor, Estado, pasta_estado_padrao
from .opcoes import (CHAVES_PROVEDORES, COMPONENTES, PADRAO_COMPONENTES, Opcoes, validar)
from .sistema import (Diagnostico, GB_POR_COMPONENTE, diagnosticar, disco_livre_gb, espaco_necessario_gb, portas_necessarias)

LIMITE_CORPO = 256 * 1024
ESTATICOS = {"instalador.css": "text/css; charset=utf-8", "instalador.js": "text/javascript; charset=utf-8",
             "logo.svg": "image/svg+xml", "favicon.ico": "image/x-icon", "logo-512.png": "image/png"}
CSP = ("default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'self'; "
       "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
URL_PAINEL = "http://127.0.0.1:3100/app/"


def _fuso_padrao() -> str:
    return "America/Sao_Paulo"


class Aplicacao:
    """Estado do assistente: o token, o diagnóstico e o motor da instalação em andamento."""

    def __init__(self, pasta_estado: Path | None = None, diagnostico=diagnosticar, montar=montar_etapas):
        self.token = secrets.token_urlsafe(24)
        self.pasta_estado = pasta_estado or pasta_estado_padrao()
        self._diagnostico = diagnostico
        self._montar = montar
        self.motor: Motor | None = None
        self.opcoes: Opcoes | None = None
        self.redator = Redator()
        self.contexto: Contexto | None = None
        self._thread: threading.Thread | None = None
        self.senha_admin_entregue = False
        self.encerrar = threading.Event()
        self.porta = 0

    # ---- dados para a tela
    def diagnostico(self) -> dict:
        d: Diagnostico = self._diagnostico()
        anterior = Estado(self.pasta_estado).dados
        return {
            "versao": VERSAO, "sistema": d.como_dict(),
            "componentes": [{"id": k, "nome": v, "padrao": k in PADRAO_COMPONENTES, "gb": GB_POR_COMPONENTE.get(k, 0)}
                            for k, v in COMPONENTES.items()],
            "chaves_provedores": list(CHAVES_PROVEDORES),
            "padroes": Opcoes(fuso=_fuso_padrao()).publico(),
            "anterior": anterior.get("opcoes") if any(v == "ok" for v in anterior.get("etapas", {}).values()) else None,
            "reinicio": bool(anterior.get("reinicio")),
            "embutido": _tem_embutido(),
        }

    def validar(self, dados: dict) -> dict:
        try:
            o = Opcoes.de_dict(dados)
        except (TypeError, ValueError) as e:
            return {"erros": [{"campo": "", "mensagem": str(e)}]}
        erros = [{"campo": c, "mensagem": m} for c, m in validar(o)]
        if o.fonte_codigo == "embutido" and not _tem_embutido():
            erros.append({"campo": "fonte_codigo", "mensagem": "este instalador não traz o código embutido; use a fonte GitHub"})
        d = self._diagnostico()
        portas = portas_necessarias(o.componentes, o.keycloak_existente)
        resumo = {
            "espaco_gb": espaco_necessario_gb(o.componentes), "livre_gb": round(disco_livre_gb(o.pasta_instalacao), 1),
            "portas": portas, "portas_ocupadas": {n: p for n, p in portas.items() if n in d.portas_ocupadas},
            "perfis": o.perfis, "pasta_dados": str(o.dados), "pasta_pesos": str(o.pesos_ollama) if o.usa("ollama") else "",
            "pasta_comfyui": str(o.comfyui) if o.usa("comfyui") else "",
            "gpu": d.gpu_nome, "docker_instalado": d.docker_instalado, "ollama_instalado": d.ollama_instalado,
        }
        return {"erros": erros, "resumo": resumo}

    # ---- execução
    def instalar(self, dados: dict) -> dict:
        if self._thread and self._thread.is_alive():
            return {"erro": "já existe uma instalação em andamento"}
        try:
            o = Opcoes.de_dict(dados)
        except (TypeError, ValueError) as e:
            return {"erro": str(e)}
        erros = validar(o)
        if erros:
            return {"erro": "; ".join(f"{c}: {m}" for c, m in erros)}
        self.opcoes = o
        self.redator.adicionar(*o.chaves_provedores.values(), o.keycloak_existente_senha)
        self.contexto = Contexto(o=o, redator=self.redator, log=lambda _t: None, pasta_estado=self.pasta_estado)
        self.motor = Motor(self.contexto, self._montar(), arquivo_log=self.pasta_estado / "instalador.log")
        self._lancar()
        return {"ok": True}

    def retomar(self) -> dict:
        if not self.motor or (self._thread and self._thread.is_alive()):
            return {"erro": "nada para retomar"}
        self._lancar()
        return {"ok": True}

    def _lancar(self) -> None:
        assert self.motor is not None
        self._thread = threading.Thread(target=self.motor.rodar, name="instalacao", daemon=True)
        self._thread.start()

    def progresso(self, desde: int) -> dict:
        if not self.motor:
            return {"ativo": False}
        r = self.motor.instantaneo(desde)
        r["ativo"] = True
        concluiu = r["terminou"] and not r["falhou"] and not r["reinicio"]
        if concluiu:
            r["resultado"] = self._resultado()
        return r

    def _resultado(self) -> dict:
        o, ctx = self.opcoes, self.contexto
        assert o and ctx
        res = {"painel": URL_PAINEL, "admin_email": o.admin_email, "pasta": o.pasta_instalacao,
               "ollama": o.usa("ollama"), "modelos_pendentes": True}
        senha = ctx.efemeros.get("admin_senha")
        if senha and not self.senha_admin_entregue:
            res["admin_senha_temporaria"] = senha     # entregue uma única vez; depois some da memória
            self.senha_admin_entregue = True
            ctx.efemeros.pop("admin_senha", None)
        return res


def _tem_embutido() -> bool:
    from . import codigo
    try:
        codigo.payload_embutido()
        return True
    except codigo.ErroCodigo:
        return False


def listar_pastas(caminho: str) -> dict:
    """Subpastas de `caminho` (só nomes de pasta; nunca arquivos nem conteúdo). Vazio = as unidades do Windows."""
    unidades = [f"{letra}:\\" for letra in string.ascii_uppercase if os.path.isdir(f"{letra}:\\")]
    if not caminho:
        return {"atual": "", "pai": "", "itens": [{"nome": u, "caminho": u} for u in unidades], "unidades": unidades}
    p = Path(caminho)
    if not p.is_absolute() or ".." in p.parts or not p.is_dir():
        return {"erro": "pasta inválida", "unidades": unidades}
    itens = []
    try:
        for filho in sorted(p.iterdir(), key=lambda x: x.name.lower()):
            try:
                if filho.is_dir() and not filho.name.startswith(("$", ".")) and not filho.is_symlink():
                    itens.append({"nome": filho.name, "caminho": str(filho)})
            except OSError:
                continue
    except OSError:
        return {"erro": "sem permissão para listar essa pasta", "unidades": unidades}
    pai = "" if p == Path(p.anchor) else str(p.parent)
    return {"atual": str(p), "pai": pai, "itens": itens[:300], "unidades": unidades}


class Manipulador(BaseHTTPRequestHandler):
    app: Aplicacao
    server_version = "TudoIA-Setup"
    sys_version = ""

    def log_message(self, formato, *args):   # silencioso: o log do instalador é o do motor
        return

    # ---- helpers
    def _hosts(self) -> set[str]:
        return {f"127.0.0.1:{self.app.porta}", f"localhost:{self.app.porta}"}

    def _cabecalhos_comuns(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Content-Security-Policy", CSP)

    def _json(self, status: int, corpo: dict) -> None:
        dados = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(dados)))
        self._cabecalhos_comuns()
        self.end_headers()
        self.wfile.write(dados)

    def _arquivo(self, caminho: Path, tipo: str) -> None:
        dados = caminho.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(dados)))
        self._cabecalhos_comuns()
        self.end_headers()
        self.wfile.write(dados)

    def _host_ok(self) -> bool:
        return (self.headers.get("Host") or "").lower() in self._hosts()

    def _token_ok(self) -> bool:
        return hmac.compare_digest((self.headers.get("X-Token") or "").encode(), self.app.token.encode())

    def _origem_ok(self) -> bool:
        origem = self.headers.get("Origin")
        return origem is None or origem.lower() in {f"http://{h}" for h in self._hosts()}

    def _corpo(self) -> dict | None:
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return None
        if n > LIMITE_CORPO or n < 0:
            return None
        bruto = self.rfile.read(n)    # sempre lê (até o limite): fechar com corpo não lido manda RST e o cliente perde o 400
        if (self.headers.get("Content-Type") or "").split(";")[0].strip().lower() != "application/json":
            return None
        try:
            dados = json.loads(bruto or b"{}")
        except ValueError:
            return None
        return dados if isinstance(dados, dict) else None

    def _estaticos(self) -> Path:
        base = getattr(sys, "_MEIPASS", None)
        return (Path(base) / "static") if base else Path(__file__).resolve().parent / "static"

    # ---- roteamento
    def do_GET(self) -> None:   # noqa: N802
        if not self._host_ok():
            return self._json(403, {"erro": "host recusado"})
        u = urlsplit(self.path)
        if u.path == "/":
            if not hmac.compare_digest(parse_qs(u.query).get("t", [""])[0].encode(), self.app.token.encode()):
                return self._json(403, {"erro": "abra o endereço completo que o instalador mostrou (com ?t=...)"})
            return self._arquivo(self._estaticos() / "index.html", "text/html; charset=utf-8")
        if u.path.startswith("/static/"):
            nome = u.path.removeprefix("/static/")
            if nome in ESTATICOS and (self._estaticos() / nome).is_file():
                return self._arquivo(self._estaticos() / nome, ESTATICOS[nome])
            return self._json(404, {"erro": "não encontrado"})
        if not u.path.startswith("/api/"):
            return self._json(404, {"erro": "não encontrado"})
        if not self._token_ok():
            return self._json(401, {"erro": "token inválido"})
        consulta = parse_qs(u.query)
        if u.path == "/api/diagnostico":
            return self._json(200, self.app.diagnostico())
        if u.path == "/api/progresso":
            try:
                desde = max(0, int(consulta.get("desde", ["0"])[0]))
            except ValueError:
                desde = 0
            return self._json(200, self.app.progresso(desde))
        if u.path == "/api/pastas":
            return self._json(200, listar_pastas(consulta.get("caminho", [""])[0]))
        return self._json(404, {"erro": "não encontrado"})

    def do_POST(self) -> None:   # noqa: N802
        if not self._host_ok() or not self._origem_ok():
            return self._json(403, {"erro": "origem recusada"})
        u = urlsplit(self.path)
        if not u.path.startswith("/api/"):
            return self._json(404, {"erro": "não encontrado"})
        if not self._token_ok():
            return self._json(401, {"erro": "token inválido"})
        try:
            tamanho = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            tamanho = 0
        if tamanho > LIMITE_CORPO:
            self.close_connection = True      # não lê o corpo: quem manda lixo enorme perde a conexão
            return self._json(413, {"erro": "corpo maior que 256 KB"})
        corpo = self._corpo()
        if corpo is None:
            return self._json(400, {"erro": "envie JSON (Content-Type: application/json, até 256 KB)"})
        if u.path == "/api/validar":
            return self._json(200, self.app.validar(corpo))
        if u.path == "/api/instalar":
            r = self.app.instalar(corpo)
            return self._json(409 if "erro" in r else 200, r)
        if u.path == "/api/retomar":
            r = self.app.retomar()
            return self._json(409 if "erro" in r else 200, r)
        if u.path == "/api/abrir-painel":
            webbrowser.open(URL_PAINEL)    # URL fixa: a tela não escolhe o que abrir
            return self._json(200, {"ok": True})
        if u.path == "/api/encerrar":
            self.app.encerrar.set()
            return self._json(200, {"ok": True})
        return self._json(404, {"erro": "não encontrado"})


def criar_servidor(app: Aplicacao, porta: int = 0) -> ThreadingHTTPServer:
    """Servidor em loopback. `porta=0` escolhe uma livre."""
    classe = type("ManipuladorLigado", (Manipulador,), {"app": app})
    srv = ThreadingHTTPServer(("127.0.0.1", porta), classe)
    app.porta = srv.server_address[1]
    return srv


def servir(app: Aplicacao, abrir_navegador: bool = True) -> int:
    srv = criar_servidor(app)
    url = f"http://127.0.0.1:{app.porta}/?t={app.token}"
    print(f"TudoIA Setup {VERSAO}: assistente em {url}", flush=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    if abrir_navegador:
        webbrowser.open(url)
    try:
        app.encerrar.wait()
    except KeyboardInterrupt:
        pass
    srv.shutdown()
    return 0

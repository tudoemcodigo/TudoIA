"""Kit de ataque e macaco de API contra servidores REAIS (em processo): um vulnerável de propósito e um endurecido.

O vulnerável existe só aqui, em 127.0.0.1, para provar que o kit enxerga o que deve; o endurecido prova que ele não inventa achado."""
import importlib.util
import json
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent / "kits" / "kit_api.py"
spec_mod = importlib.util.spec_from_file_location("kit_api", KIT)
kit = importlib.util.module_from_spec(spec_mod)
sys.modules["kit_api"] = kit
spec_mod.loader.exec_module(kit)

SPEC = {
    "openapi": "3.1.0", "info": {"title": "t", "version": "1"}, "security": [{"bearer": []}],
    "paths": {
        "/tarefas": {"get": {"parameters": [{"name": "q", "in": "query", "schema": {"type": "string"}}]},
                     "post": {"requestBody": {"content": {"application/json": {"schema": {
                         "type": "object", "properties": {"titulo": {"type": "string"}, "prioridade": {"type": "integer"}}}}}}}},
        "/tarefas/{id}": {"get": {"parameters": [{"name": "id", "in": "path", "required": True, "schema": {"type": "integer"}}]}},
        "/arquivo": {"get": {"security": [], "parameters": [{"name": "nome", "in": "query", "schema": {"type": "string"}}]}},
        "/busca": {"get": {"security": [], "parameters": [{"name": "q", "in": "query", "schema": {"type": "string"}}]}},
    },
}


def servir(handler):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def parar(httpd):
    httpd.shutdown()      # primeiro para o laço; só depois fecha o soquete (a ordem inversa derruba a thread do servidor)
    httpd.server_close()


class Vulneravel(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def responder(self, status, corpo, tipo="application/json", extra=None):
        dados = corpo.encode() if isinstance(corpo, str) else corpo
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Server", "Werkzeug/3.0.1 Python/3.12")   # revela versão
        self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin", "*"))
        self.send_header("Access-Control-Allow-Credentials", "true")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def corpo(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n).decode("utf-8", "replace") if n else ""

    def do_TRACE(self):
        self.responder(200, "trace ok")

    def do_GET(self):
        from urllib.parse import parse_qs, urlparse
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path.startswith("/tarefas/"):               # AUTH-01: rota protegida sem checar credencial
            return self.responder(200, json.dumps({"id": 1, "titulo": "x"}))
        if u.path == "/tarefas":
            termo = (q.get("q") or [""])[0]
            if "'" in termo or '"' in termo:                # INJ-01: erro de banco vaza
                return self.responder(500, 'psycopg.errors.SyntaxError: syntax error at or near "OR"\nTraceback (most recent call last):')
            return self.responder(200, "[]")
        if u.path == "/arquivo":
            nome = (q.get("nome") or [""])[0]
            if "../" in nome:                               # INJ-03: path traversal
                return self.responder(200, "root:x:0:0:root:/root:/bin/bash")
            return self.responder(200, "ok")
        if u.path == "/busca":
            termo = (q.get("q") or [""])[0]
            return self.responder(200, f"<html>resultado: {termo}</html>", "text/html")
        return self.responder(404, "{}")

    def do_POST(self):
        corpo = self.corpo()
        try:
            dados = json.loads(corpo)
        except ValueError:
            return self.responder(500, "Traceback (most recent call last):\n  File \"/app/main.py\", line 10\nJSONDecodeError")
        if not isinstance(dados, dict):
            return self.responder(500, "TypeError em /app/main.py")
        if not isinstance(dados.get("titulo", ""), str) or not isinstance(dados.get("prioridade", 0), int):
            return self.responder(500, "erro interno")      # MAC-01: tipo errado = 500
        return self.responder(201, json.dumps(dados))        # MASS-01 e LIM-01: aceita tudo e devolve tudo


class Endurecido(BaseHTTPRequestHandler):
    contador = 0

    def log_message(self, *a):
        pass

    def responder(self, status, corpo="{}", tipo="application/json"):
        dados = corpo.encode()
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'none'")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def do_TRACE(self):
        self.responder(405, json.dumps({"erro": "METODO_NAO_PERMITIDO"}))

    def do_GET(self):
        Endurecido.contador += 1
        if Endurecido.contador > 20:
            return self.responder(429, json.dumps({"erro": "MUITAS_REQUISICOES"}))
        if self.path.startswith(("/arquivo", "/busca")):
            return self.responder(400, json.dumps({"erro": "PARAMETRO_INVALIDO"}))
        if "Authorization" not in self.headers:
            return self.responder(401, json.dumps({"erro": "NAO_AUTENTICADO"}))
        self.responder(200, "[]")

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 100_000:
            return self.responder(413, json.dumps({"erro": "CORPO_GRANDE_DEMAIS"}))
        self.rfile.read(n)
        self.responder(401, json.dumps({"erro": "NAO_AUTENTICADO"}))


class KitDeApi(unittest.TestCase):
    def rodar(self, handler, modo):
        httpd = servir(handler)
        self.addCleanup(parar, httpd)
        with tempfile.TemporaryDirectory() as d:
            spec = Path(d) / "spec.json"
            spec.write_text(json.dumps(SPEC), encoding="utf-8")
            saida = Path(d) / "saida.json"
            kit.main(["kit", modo, f"http://127.0.0.1:{httpd.server_address[1]}", str(spec), str(saida), "--max-requisicoes", "700"])
            return json.loads(saida.read_text(encoding="utf-8"))

    def ids(self, rel):
        return {a["id"] for a in rel["achados"]}

    def test_hacker_encontra_o_que_o_servidor_vulneravel_tem(self):
        rel = self.rodar(Vulneravel, "ataque")
        esperados = {"AUTH-01", "ERR-01", "INJ-01", "INJ-03", "INJ-02", "CORS-01", "MET-01", "HDR-01", "HDR-03", "MASS-01", "LIM-01", "RATE-01"}
        faltando = esperados - self.ids(rel)
        self.assertFalse(faltando, f"o kit não achou: {faltando}; achou: {self.ids(rel)}")
        graves = [a for a in rel["achados"] if a["severidade"] in ("CRITICO", "ALTO")]
        self.assertTrue(graves)
        self.assertTrue(all(a["reproducao"].startswith("curl") for a in rel["achados"] if a["metodo"] != "-"))

    def test_hacker_nao_acusa_o_servidor_endurecido(self):
        Endurecido.contador = 0
        rel = self.rodar(Endurecido, "ataque")
        graves = [a for a in rel["achados"] if a["severidade"] in ("CRITICO", "ALTO", "MEDIO")]
        self.assertEqual(graves, [], graves)

    def test_macaco_acha_5xx_com_entrada_invalida_e_json_malformado(self):
        rel = self.rodar(Vulneravel, "macaco")
        self.assertIn("MAC-01", self.ids(rel))
        self.assertTrue(any(a["id"] == "MAC-01" and a["severidade"] == "ALTO" for a in rel["achados"]))
        self.assertIn("ERR-01", self.ids(rel))

    def test_macaco_no_servidor_endurecido_nao_acha_5xx(self):
        Endurecido.contador = 0
        rel = self.rodar(Endurecido, "macaco")
        self.assertEqual([a for a in rel["achados"] if a["id"].startswith("MAC-0") and a["severidade"] in ("CRITICO", "ALTO")], [])

    def test_servidor_que_cai_e_reportado_como_critico(self):
        class Cai(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")

            def do_POST(self):
                self.connection.close()   # derruba a conexão: o servidor "caiu"
        rel = self.rodar(Cai, "macaco")
        self.assertIn("MAC-03", self.ids(rel))

    def test_orcamento_de_requisicoes_limita_a_bateria_e_marca_incompleto(self):
        httpd = servir(Vulneravel)
        self.addCleanup(parar, httpd)
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "s.json").write_text(json.dumps(SPEC), encoding="utf-8")
            kit.main(["kit", "ataque", f"http://127.0.0.1:{httpd.server_address[1]}", str(Path(d) / "s.json"), str(Path(d) / "o.json"),
                      "--max-requisicoes", "15"])
            rel = json.loads((Path(d) / "o.json").read_text(encoding="utf-8"))
        self.assertLessEqual(rel["requisicoes"], 15)
        self.assertTrue(rel["incompleto"])

    def test_resultado_e_deterministico(self):
        a = self.rodar(Vulneravel, "macaco")
        b = self.rodar(Vulneravel, "macaco")
        self.assertEqual([(x["id"], x["endpoint"]) for x in a["achados"]], [(x["id"], x["endpoint"]) for x in b["achados"]])

    def test_exemplo_de_schema_gera_valor_valido_e_resolve_ref(self):
        raiz = {"components": {"schemas": {"Item": {"type": "object", "properties": {"n": {"type": "integer", "minimum": 5}}}}}}
        self.assertEqual(kit.exemplo({"$ref": "#/components/schemas/Item"}, raiz), {"n": 5})
        self.assertEqual(kit.exemplo({"type": "string", "format": "uuid"}, {}), "3fa85f64-5717-4562-b3fc-2c963f66afa6")
        self.assertEqual(kit.exemplo({"enum": ["a", "b"]}, {}), "a")

    def test_uso_incorreto_devolve_2(self):
        self.assertEqual(kit.main(["kit"]), 2)


if __name__ == "__main__":
    unittest.main()

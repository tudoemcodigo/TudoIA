#!/usr/bin/env python3
"""
Kit de teste de API da Squad: "hacker" (ataque) e "macaco" (entrada errada de todo jeito). Só biblioteca padrão, determinístico.

Roda DENTRO de um container na rede interna do sandbox (copiado pela Squad para /tmp); fala só com o alvo informado. Lê o contrato
OpenAPI em JSON e escreve um relatório JSON. Nada aqui chama modelo: os cenários são verificações fixas, com semente fixa, e cada
achado traz o comando de reprodução (sem credenciais).

Uso:
    python kit_api.py ataque ALVO OPENAPI.json SAIDA.json [--max-requisicoes 400] [--token TOKEN]
    python kit_api.py macaco ALVO OPENAPI.json SAIDA.json [--max-requisicoes 600]
"""
import http.client
import json
import random
import re
import sys
import time
import urllib.parse

SEMENTE = 20261103
METODOS = ("get", "post", "put", "patch", "delete")
SEV_ORDEM = {"CRITICO": 0, "ALTO": 1, "MEDIO": 2, "BAIXO": 3}
VAZAMENTO = re.compile(r"Traceback \(most recent call last\)|\n\s+at [\w.$<>]+\(|System\.\w+Exception|NullReferenceException|"
                       r"sqlalchemy|psycopg|SqlException|SQLSTATE|You have an error in your SQL|ORA-\d{5}|"
                       r"File \"/|/app/|/usr/(?:local/)?lib/|C:\\\\|stack trace|Microsoft\.AspNetCore", re.IGNORECASE)
ERRO_DE_BANCO = re.compile(r"syntax error at or near|unterminated quoted string|SQLSTATE|psycopg|sqlalchemy\.exc|SqlException|"
                           r"You have an error in your SQL|ORA-\d{5}|near \"[^\"]*\": syntax error|sqlite3\.", re.IGNORECASE)
STRINGS_HOSTIS = [
    "", " ", "a" * 5000, "\u0000", "null", "undefined", "NaN", "-1", "0", "9" * 40, "1e999", "true", "[]", "{}",
    "'", "\"", "' OR '1'='1", "<script>alert(1)</script>", "../../../../etc/passwd", "%00", "%s%s%s%n", "${7*7}", "{{7*7}}",
    "\u202eevil", "\U0001f4a9", "Robert'); DROP TABLE users;--", "\r\nX-Injected: 1", "😀" * 200, "ñ\u00e7\u00e3o", "\t\n",
]


class Alvo:
    """Cliente HTTP mínimo com orçamento de requisições, timeout e registro do que foi enviado."""

    def __init__(self, base, limite):
        u = urllib.parse.urlparse(base)
        self.host, self.porta, self.https = u.hostname, u.port or (443 if u.scheme == "https" else 80), u.scheme == "https"
        self.limite, self.feitas, self.estourou = limite, 0, False

    def req(self, metodo, caminho, corpo=None, cab=None, timeout=10.0):
        if self.feitas >= self.limite:
            self.estourou = True
            return None
        self.feitas += 1
        cab = dict(cab or {})
        dados = None
        if corpo is not None:
            dados = corpo if isinstance(corpo, (bytes, str)) else json.dumps(corpo)
            if isinstance(dados, str):
                dados = dados.encode("utf-8", "replace")
            cab.setdefault("Content-Type", "application/json")
        cab.setdefault("User-Agent", "squadti-kit/1")
        inicio = time.time()
        con = None
        try:
            con = (http.client.HTTPSConnection if self.https else http.client.HTTPConnection)(self.host, self.porta, timeout=timeout)
            con.request(metodo, caminho, body=dados, headers=cab)
            r = con.getresponse()
            corpo_resp = r.read(40_000).decode("utf-8", "replace")
            return {"status": r.status, "cab": {k.lower(): v for k, v in r.getheaders()}, "corpo": corpo_resp,
                    "tempo": time.time() - inicio}
        except (OSError, http.client.HTTPException) as e:
            return {"status": 0, "cab": {}, "corpo": "", "tempo": time.time() - inicio, "erro": type(e).__name__}
        finally:
            if con is not None:
                con.close()


# ------------------------------------------------------------------ contrato
def exemplo(schema, raiz, fundo=0):
    """Valor válido mínimo para um schema OpenAPI (suficiente para uma requisição que o servidor aceite)."""
    if not isinstance(schema, dict) or fundo > 6:
        return "teste"
    if "$ref" in schema:
        no = raiz
        for parte in schema["$ref"].lstrip("#/").split("/"):
            no = no.get(parte, {}) if isinstance(no, dict) else {}
        return exemplo(no, raiz, fundo + 1)
    for chave in ("example", "default"):
        if chave in schema:
            return schema[chave]
    if schema.get("enum"):
        return schema["enum"][0]
    for chave in ("allOf", "oneOf", "anyOf"):
        if schema.get(chave):
            return exemplo(schema[chave][0], raiz, fundo + 1)
    tipo = schema.get("type")
    if tipo == "object" or "properties" in schema:
        return {k: exemplo(v, raiz, fundo + 1) for k, v in (schema.get("properties") or {}).items()}
    if tipo == "array":
        return [exemplo(schema.get("items", {}), raiz, fundo + 1)]
    if tipo == "integer":
        return max(1, int(schema.get("minimum", 1) or 1))
    if tipo == "number":
        return 1.5
    if tipo == "boolean":
        return True
    fmt = schema.get("format")
    return {"uuid": "3fa85f64-5717-4562-b3fc-2c963f66afa6", "date": "2026-01-15", "date-time": "2026-01-15T10:00:00Z",
            "email": "teste@exemplo.com", "uri": "https://exemplo.com"}.get(fmt, "teste")


def operacoes(spec):
    saida = []
    seguranca_global = bool(spec.get("security"))
    for caminho, item in (spec.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        comuns = item.get("parameters") or []
        for metodo in METODOS:
            op = item.get(metodo)
            if not isinstance(op, dict):
                continue
            params = [p for p in comuns + (op.get("parameters") or []) if isinstance(p, dict)]
            corpo = None
            conteudo = ((op.get("requestBody") or {}).get("content") or {}).get("application/json")
            if conteudo:
                corpo = exemplo(conteudo.get("schema", {}), spec)
            protegida = bool(op.get("security")) or (seguranca_global and op.get("security") != [])
            saida.append({"caminho": caminho, "metodo": metodo.upper(), "params": params, "corpo": corpo, "protegida": protegida})
    return saida


def montar(op, caminho_params=None, query=None):
    """Caminho concreto da operação: parâmetros de caminho substituídos, de query anexados."""
    caminho = op["caminho"]
    valores = dict(caminho_params or {})
    for p in op["params"]:
        if p.get("in") == "path":
            nome = p.get("name", "id")
            caminho = caminho.replace("{" + nome + "}", urllib.parse.quote(str(valores.get(nome, exemplo(p.get("schema", {}), {}))), safe=""))
    qs = {p["name"]: exemplo(p.get("schema", {}), {}) for p in op["params"] if p.get("in") == "query" and p.get("required")}
    qs.update(query or {})
    return caminho + ("?" + urllib.parse.urlencode(qs) if qs else "")


def campos_de_texto(op):
    """Lugares onde um texto do atacante entra: ('path'|'query'|'corpo', nome)."""
    alvos = [(p["in"], p["name"]) for p in op["params"] if p.get("in") in ("path", "query")]
    if isinstance(op["corpo"], dict):
        alvos += [("corpo", k) for k, v in op["corpo"].items() if isinstance(v, str)]
    return alvos


def com_valor(op, onde, nome, valor):
    """(caminho, corpo) com `valor` no campo `nome`."""
    if onde == "corpo":
        corpo = dict(op["corpo"])
        corpo[nome] = valor
        return montar(op), corpo
    if onde == "path":
        return montar(op, caminho_params={nome: valor}), op["corpo"]
    return montar(op, query={nome: valor}), op["corpo"]


# ------------------------------------------------------------------ relatório
class Relatorio:
    def __init__(self, alvo):
        self.alvo, self.achados, self._vistos = alvo, [], set()

    def achar(self, id_, sev, categoria, op, evidencia, repro):
        chave = (id_, op["metodo"] if op else "", op["caminho"] if op else "")
        if chave in self._vistos:
            return
        self._vistos.add(chave)
        self.achados.append({"id": id_, "severidade": sev, "categoria": categoria, "endpoint": op["caminho"] if op else "-",
                             "metodo": op["metodo"] if op else "-", "evidencia": str(evidencia)[:300], "reproducao": repro[:300]})

    def salvar(self, caminho, extra):
        self.achados.sort(key=lambda a: (SEV_ORDEM.get(a["severidade"], 9), a["id"], a["endpoint"]))
        doc = {"achados": self.achados, "requisicoes": self.alvo.feitas, "incompleto": self.alvo.estourou, **extra}
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=1)


def repro(op, caminho, corpo=None, cab=None):
    partes = [f"curl -i -X {op['metodo']} '<ALVO>{caminho}'"]
    for k, v in (cab or {}).items():
        if k.lower() not in ("authorization", "cookie"):
            partes.append(f"-H '{k}: {v}'")
    if corpo is not None:
        texto = corpo if isinstance(corpo, str) else json.dumps(corpo, ensure_ascii=False)
        partes.append("-d '" + texto[:120].replace("'", "'\\''") + "'")
    return " ".join(partes)


# ------------------------------------------------------------------ hacker
def ataque(alvo, spec, relatorio, token):
    ops = operacoes(spec)
    tem_seguranca = bool(spec.get("security")) or any(o["protegida"] for o in ops)
    if not tem_seguranca and any(o["metodo"] != "GET" for o in ops):
        relatorio.achar("AUTH-00", "MEDIO", "autenticação", None, "o contrato não declara nenhum esquema de segurança",
                        "revise `security` no OpenAPI")
    amostra = None
    for op in ops:
        caminho = montar(op)
        r = alvo.req(op["metodo"], caminho, op["corpo"])
        if r is None:
            return
        if amostra is None and r["status"]:
            amostra = r
        # AUTH-01: rota protegida respondendo sem credencial
        if op["protegida"] and 200 <= r["status"] < 300:
            relatorio.achar("AUTH-01", "ALTO", "autenticação", op, f"respondeu {r['status']} sem credencial",
                            repro(op, caminho, op["corpo"]))
        # ERR-01: vazamento de detalhe interno em qualquer resposta
        if VAZAMENTO.search(r["corpo"] or "") and r["status"] >= 400:
            relatorio.achar("ERR-01", "ALTO", "vazamento de informação", op, "a resposta de erro traz detalhe interno (stack, caminho ou SQL)",
                            repro(op, caminho, op["corpo"]))
    # ERR-01 também com corpo malformado: o tratamento de erro não pode devolver detalhe interno
    for op in ops:
        if op["metodo"] in ("POST", "PUT", "PATCH"):
            caminho = montar(op)
            r = alvo.req(op["metodo"], caminho, "{nao-e-json")
            if r is None:
                return
            if r["status"] >= 400 and VAZAMENTO.search(r["corpo"] or ""):
                relatorio.achar("ERR-01", "ALTO", "vazamento de informação", op, "o erro de JSON malformado traz detalhe interno",
                                repro(op, caminho, "{nao-e-json"))
    if amostra:
        c = amostra["cab"]
        if c.get("x-content-type-options", "").lower() != "nosniff":
            relatorio.achar("HDR-01", "MEDIO", "cabeçalhos", None, "falta X-Content-Type-Options: nosniff", "curl -i <ALVO>/")
        if "content-security-policy" not in c and "x-frame-options" not in c:
            relatorio.achar("HDR-02", "BAIXO", "cabeçalhos", None, "falta Content-Security-Policy ou X-Frame-Options", "curl -i <ALVO>/")
        if re.search(r"\d", c.get("server", "")) or "x-powered-by" in c:
            relatorio.achar("HDR-03", "BAIXO", "cabeçalhos", None, "a resposta revela tecnologia e versão (Server/X-Powered-By)",
                            "curl -i <ALVO>/")
    # CORS
    primeiro_get = next((o for o in ops if o["metodo"] == "GET"), None)
    if primeiro_get:
        caminho = montar(primeiro_get)
        r = alvo.req("GET", caminho, cab={"Origin": "https://evil.example"})
        if r and r["status"]:
            origem = r["cab"].get("access-control-allow-origin", "")
            cred = r["cab"].get("access-control-allow-credentials", "").lower() == "true"
            if origem == "https://evil.example" or (origem == "*" and cred):
                relatorio.achar("CORS-01", "ALTO", "CORS", primeiro_get, f"aceita origem arbitrária ({origem}) com credenciais={cred}",
                                repro(primeiro_get, caminho, cab={"Origin": "https://evil.example"}))
            elif origem == "*":
                relatorio.achar("CORS-02", "BAIXO", "CORS", primeiro_get, "Access-Control-Allow-Origin: * (sem credenciais)",
                                repro(primeiro_get, caminho))
        t = alvo.req("TRACE", caminho)
        if t and 200 <= t["status"] < 300:
            relatorio.achar("MET-01", "MEDIO", "métodos HTTP", primeiro_get, "o método TRACE está habilitado", f"curl -i -X TRACE '<ALVO>{caminho}'")
    # injeções
    for op in ops:
        for onde, nome in campos_de_texto(op):
            base_caminho, base_corpo = com_valor(op, onde, nome, "normal")
            base = alvo.req(op["metodo"], base_caminho, base_corpo)
            if base is None:
                return
            for classe, sev, payload, prova in (
                ("INJ-01", "CRITICO", "' OR '1'='1' --", ERRO_DE_BANCO), ("INJ-01", "CRITICO", "\"", ERRO_DE_BANCO),
                ("INJ-03", "CRITICO", "../../../../etc/passwd", re.compile(r"root:[x*]:0:0")),
                ("INJ-04", "CRITICO", ";id", re.compile(r"uid=\d+\(")), ("INJ-05", "ALTO", "{{7*7}}", re.compile(r"(?<!\d)49(?!\d)")),
                ("INJ-02", "MEDIO", "<script>alert(1)</script>", re.compile(r"<script>alert\(1\)</script>")),
            ):
                caminho, corpo = com_valor(op, onde, nome, payload)
                r = alvo.req(op["metodo"], caminho, corpo)
                if r is None:
                    return
                if not r["status"]:
                    continue
                achou = prova.search(r["corpo"] or "")
                if classe == "INJ-05" and (achou and "{{7*7}}" not in r["corpo"] and not prova.search(base["corpo"] or "")):
                    relatorio.achar(classe, sev, "injeção de template", op, f"{nome}: {{{{7*7}}}} avaliado como 49", repro(op, caminho, corpo))
                elif classe == "INJ-02" and achou and "html" in r["cab"].get("content-type", ""):
                    relatorio.achar(classe, sev, "XSS refletido", op, f"{nome}: o texto volta sem escape em HTML", repro(op, caminho, corpo))
                elif classe in ("INJ-01", "INJ-03", "INJ-04") and achou:
                    relatorio.achar(classe, sev, "injeção", op, f"{nome}: resposta confirma a injeção ({classe})", repro(op, caminho, corpo))
                elif classe == "INJ-01" and r["status"] >= 500 and base["status"] < 500:
                    relatorio.achar("INJ-01", "ALTO", "injeção", op, f"{nome}: o payload SQL gera 5xx (entrada não tratada)",
                                    repro(op, caminho, corpo))
    # mass assignment
    for op in ops:
        if op["metodo"] in ("POST", "PUT", "PATCH") and isinstance(op["corpo"], dict):
            corpo = {**op["corpo"], "isAdmin": True, "role": "admin", "is_admin": True}
            caminho = montar(op)
            r = alvo.req(op["metodo"], caminho, corpo)
            if r and 200 <= r["status"] < 300 and re.search(r'"(isAdmin|is_admin)"\s*:\s*true|"role"\s*:\s*"admin"', r["corpo"] or ""):
                relatorio.achar("MASS-01", "ALTO", "atribuição em massa", op, "campos privilegiados enviados pelo cliente foram aceitos e devolvidos",
                                repro(op, caminho, corpo))
    # limites
    for op in ops:
        if op["metodo"] in ("POST", "PUT", "PATCH") and isinstance(op["corpo"], dict) and campos_de_texto(op):
            onde, nome = next((c for c in campos_de_texto(op) if c[0] == "corpo"), (None, None))
            if not nome:
                continue
            caminho, corpo = com_valor(op, onde, nome, "A" * 2_000_000)
            r = alvo.req(op["metodo"], caminho, corpo, timeout=20)
            if r and 200 <= r["status"] < 300:
                relatorio.achar("LIM-01", "MEDIO", "limites", op, "aceitou um campo de 2 MB (sem limite de tamanho)", repro(op, caminho, "<2MB>"))
            aninhado = "[" * 300 + "]" * 300
            r = alvo.req(op["metodo"], montar(op), aninhado)
            if r and r["status"] >= 500:
                relatorio.achar("LIM-02", "MEDIO", "limites", op, "JSON profundamente aninhado gera 5xx", repro(op, montar(op), "[[[...]]]"))
    # taxa de requisições
    if primeiro_get:
        caminho = montar(primeiro_get)
        codigos = []
        for _ in range(60):
            r = alvo.req("GET", caminho)
            if r is None:
                break
            codigos.append(r["status"])
        if codigos and 429 not in codigos and all(c == 200 for c in codigos[:5]):
            relatorio.achar("RATE-01", "BAIXO", "limite de taxa", primeiro_get, "60 requisições seguidas sem nenhum 429", repro(primeiro_get, caminho))
    # token (opcional): recurso que não existe não pode devolver dado de outro
    if token:
        for op in ops:
            if op["metodo"] == "GET" and any(p.get("in") == "path" for p in op["params"]):
                nome = next(p["name"] for p in op["params"] if p.get("in") == "path")
                c1 = montar(op, caminho_params={nome: 99999999})
                r = alvo.req("GET", c1, cab={"Authorization": f"Bearer {token}"})
                if r and r["status"] == 200:
                    relatorio.achar("IDOR-01", "ALTO", "controle de acesso", op, "id inexistente devolveu 200 (verifique propriedade do recurso)",
                                    repro(op, c1))


# ------------------------------------------------------------------ macaco
def macaco(alvo, spec, relatorio):
    rng = random.Random(SEMENTE)
    ops = operacoes(spec)
    for op in ops:
        base = alvo.req(op["metodo"], montar(op), op["corpo"])
        if base is None:
            return
        if not base["status"]:
            relatorio.achar("MAC-03", "CRITICO", "disponibilidade", op, f"o servidor não respondeu ({base.get('erro')}) à requisição válida",
                            repro(op, montar(op), op["corpo"]))
            continue
        for onde, nome in campos_de_texto(op):
            textos = STRINGS_HOSTIS[:]
            rng.shuffle(textos)
            for texto in textos[:14]:
                caminho, corpo = com_valor(op, onde, nome, texto)
                r = alvo.req(op["metodo"], caminho, corpo, timeout=8)
                if r is None:
                    return
                if r["status"] == 0:
                    relatorio.achar("MAC-03", "CRITICO", "disponibilidade", op,
                                    f"o servidor caiu ou travou ({r.get('erro')}) com {nome}={texto[:30]!r}", repro(op, caminho, corpo))
                    break
                if r["status"] >= 500:
                    relatorio.achar("MAC-01", "ALTO", "robustez", op, f"{nome}={texto[:30]!r} gerou {r['status']} (entrada não tratada)",
                                    repro(op, caminho, corpo))
                if r["tempo"] > 6:
                    relatorio.achar("MAC-02", "MEDIO", "desempenho", op, f"{nome}={texto[:30]!r} levou {r['tempo']:.1f}s", repro(op, caminho, corpo))
                if r["status"] >= 400 and VAZAMENTO.search(r["corpo"] or ""):
                    relatorio.achar("ERR-01", "ALTO", "vazamento de informação", op, "o erro devolve detalhe interno", repro(op, caminho, corpo))
        if op["metodo"] in ("POST", "PUT", "PATCH"):
            for ruim in ("{nao-e-json", "", "null", "[1,2,3]", "\"so uma string\"", "{\"a\":" * 50):
                r = alvo.req(op["metodo"], montar(op), ruim, timeout=8)
                if r is None:
                    return
                if r["status"] >= 500:
                    relatorio.achar("MAC-01", "ALTO", "robustez", op, f"corpo malformado {ruim[:20]!r} gerou {r['status']}", repro(op, montar(op), ruim))
                elif r["status"] == 0:
                    relatorio.achar("MAC-03", "CRITICO", "disponibilidade", op, "o servidor caiu com corpo malformado", repro(op, montar(op), ruim))
                    break
                elif 200 <= r["status"] < 300 and ruim.startswith("{nao"):
                    relatorio.achar("MAC-04", "MEDIO", "validação", op, "JSON inválido foi aceito como sucesso", repro(op, montar(op), ruim))
            for campo, valor in ((k, v) for k, v in (op["corpo"] or {}).items()) if isinstance(op["corpo"], dict) else []:
                for tipo_errado in (None, [], {}, True, -1, 10 ** 30, "x" * 300):
                    if type(tipo_errado) is type(valor) and tipo_errado == valor:
                        continue
                    corpo = {**op["corpo"], campo: tipo_errado}
                    r = alvo.req(op["metodo"], montar(op), corpo, timeout=8)
                    if r is None:
                        return
                    if r["status"] >= 500:
                        relatorio.achar("MAC-01", "ALTO", "robustez", op, f"{campo} com tipo/valor inválido gerou {r['status']}",
                                        repro(op, montar(op), corpo))
                        break
    # depois de tudo, o servidor ainda precisa estar de pé
    if ops:
        vivo = alvo.req("GET", "/", timeout=5) or {"status": 1}
        if vivo["status"] == 0:
            relatorio.achar("MAC-05", "CRITICO", "disponibilidade", None, "o servidor não responde depois da bateria", "curl -i <ALVO>/")


def main(argv):
    if len(argv) < 5 or argv[1] not in ("ataque", "macaco"):
        print(__doc__)
        return 2
    modo, base, openapi, saida = argv[1:5]
    limite = int(argv[argv.index("--max-requisicoes") + 1]) if "--max-requisicoes" in argv else (400 if modo == "ataque" else 600)
    token = argv[argv.index("--token") + 1] if "--token" in argv else None
    with open(openapi, encoding="utf-8") as f:
        spec = json.load(f)
    alvo = Alvo(base, limite)
    rel = Relatorio(alvo)
    random.seed(SEMENTE)
    inicio = time.time()
    (ataque(alvo, spec, rel, token) if modo == "ataque" else macaco(alvo, spec, rel))
    rel.salvar(saida, {"modo": modo, "endpoints": len(operacoes(spec)), "duracao_s": round(time.time() - inicio, 1), "semente": SEMENTE})
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

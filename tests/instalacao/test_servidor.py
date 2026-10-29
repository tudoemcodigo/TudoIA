"""O assistente roda no navegador e dirige um instalador que executa comandos: a fronteira HTTP precisa ser dura."""
import http.client
import json
import threading
import time

import pytest

from tudoia_instalador import servidor
from tudoia_instalador.motor import Etapa

from .duplos import diag


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(servidor, "_tem_embutido", lambda: True)
    monkeypatch.setattr("tudoia_instalador.opcoes.MAX_CAMINHO", 400)
    a = servidor.Aplicacao(pasta_estado=tmp_path / "estado", diagnostico=lambda: diag(),
                           montar=lambda: [Etapa("a", "Etapa A", lambda c: c.log("rodei a")),
                                           Etapa("b", "Etapa B", lambda c: c.efemeros.update(admin_senha="Temp-Senha-123"))])
    srv = servidor.criar_servidor(a)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield a
    srv.shutdown()
    srv.server_close()


def req(app, metodo, caminho, corpo=None, token=True, host=None, origem=None, tipo="application/json", bruto=None):
    c = http.client.HTTPConnection("127.0.0.1", app.porta, timeout=10)
    cab = {"Host": host or f"127.0.0.1:{app.porta}"}
    if token:
        cab["X-Token"] = app.token
    if origem:
        cab["Origin"] = origem
    dados = bruto if bruto is not None else (json.dumps(corpo).encode() if corpo is not None else None)
    if dados is not None:
        cab["Content-Type"] = tipo
        cab["Content-Length"] = str(len(dados))
    c.request(metodo, caminho, body=dados, headers=cab)
    r = c.getresponse()
    texto = r.read()
    c.close()
    try:
        return r.status, json.loads(texto), r
    except ValueError:
        return r.status, texto, r


OPCOES = {"pasta_instalacao": r"C:\TudoIATeste", "admin_email": "admin@exemplo.com.br"}


def test_pagina_inicial_exige_o_token_na_url(app):
    s, _, _ = req(app, "GET", "/", token=False)
    assert s == 403
    s, corpo, r = req(app, "GET", f"/?t={app.token}", token=False)
    assert s == 200 and b"TudoIA" in corpo
    assert "default-src 'self'" in r.getheader("Content-Security-Policy") and r.getheader("Referrer-Policy") == "no-referrer"
    assert r.getheader("X-Frame-Options") == "DENY"


def test_token_errado_na_url_e_recusado(app):
    assert req(app, "GET", "/?t=errado", token=False)[0] == 403


def test_api_sem_token_ou_com_token_errado_e_401(app):
    assert req(app, "GET", "/api/diagnostico", token=False)[0] == 401
    c = http.client.HTTPConnection("127.0.0.1", app.porta)
    c.request("GET", "/api/diagnostico", headers={"X-Token": "x" * len(app.token)})
    assert c.getresponse().status == 401


def test_host_diferente_e_recusado_contra_dns_rebinding(app):
    assert req(app, "GET", "/api/diagnostico", host="evil.example")[0] == 403
    assert req(app, "GET", "/api/diagnostico", host=f"evil.example:{app.porta}")[0] == 403
    assert req(app, "GET", "/api/diagnostico", host=f"localhost:{app.porta}")[0] == 200


def test_post_com_origem_de_outro_site_e_recusado(app):
    assert req(app, "POST", "/api/validar", {}, origem="https://evil.example")[0] == 403
    assert req(app, "POST", "/api/validar", {}, origem=f"http://127.0.0.1:{app.porta}")[0] == 200
    assert req(app, "POST", "/api/validar", {}, origem="null")[0] == 403


def test_post_exige_json_e_limita_o_tamanho(app):
    assert req(app, "POST", "/api/validar", bruto=b"a=b", tipo="application/x-www-form-urlencoded")[0] == 400
    assert req(app, "POST", "/api/validar", bruto=b"{nao json")[0] == 400
    assert req(app, "POST", "/api/validar", bruto=b"[1,2]")[0] == 400
    try:
        assert req(app, "POST", "/api/validar", bruto=b'{"a":"' + b"x" * (servidor.LIMITE_CORPO + 10) + b'"}')[0] == 413
    except ConnectionError:
        pass    # o servidor fechou a conexão sem ler o corpo: também é recusar


def test_estaticos_so_os_da_lista(app):
    assert req(app, "GET", "/static/instalador.js", token=False)[0] == 200
    assert req(app, "GET", "/static/../servidor.py", token=False)[0] == 404
    assert req(app, "GET", "/static/%2e%2e/servidor.py", token=False)[0] == 404
    assert req(app, "GET", "/static/index.html", token=False)[0] == 404


def test_diagnostico_traz_componentes_padroes_e_chaves(app):
    s, d, _ = req(app, "GET", "/api/diagnostico")
    assert s == 200 and {c["id"] for c in d["componentes"]} >= {"cerebro", "keycloak", "ollama", "comfyui"}
    assert "GROQ_API_KEY" in d["chaves_provedores"] and d["padroes"]["projeto_compose"] == "tudoia" and d["embutido"]


def test_validar_devolve_erros_por_campo_e_resumo(app):
    s, d, _ = req(app, "POST", "/api/validar", {**OPCOES, "pasta_instalacao": r"C:\Windows\x"})
    assert any(e["campo"] == "pasta_instalacao" for e in d["erros"])
    s, d, _ = req(app, "POST", "/api/validar", OPCOES)
    assert d["erros"] == [] and "keycloak" in d["resumo"]["perfis"] and d["resumo"]["portas"]["painel"] == 3100


def test_validar_campo_desconhecido_e_erro_e_nao_excecao(app):
    s, d, _ = req(app, "POST", "/api/validar", {**OPCOES, "comando": "calc"})
    assert s == 200 and d["erros"][0]["mensagem"].startswith("campo desconhecido")


def test_validar_sem_codigo_embutido_orienta_o_github(app, monkeypatch):
    monkeypatch.setattr(servidor, "_tem_embutido", lambda: False)
    _, d, _ = req(app, "POST", "/api/validar", OPCOES)
    assert any(e["campo"] == "fonte_codigo" for e in d["erros"])
    _, d, _ = req(app, "POST", "/api/validar", {**OPCOES, "fonte_codigo": "github"})
    assert not any(e["campo"] == "fonte_codigo" for e in d["erros"])


def _esperar_fim(app):
    for _ in range(100):
        _, p, _ = req(app, "GET", "/api/progresso?desde=0")
        if p.get("terminou"):
            return p
        time.sleep(0.05)
    raise AssertionError("instalação não terminou")


def test_instalar_executa_e_entrega_a_senha_temporaria_uma_unica_vez(app):
    s, r, _ = req(app, "POST", "/api/instalar", OPCOES)
    assert s == 200 and r == {"ok": True}
    p = _esperar_fim(app)
    assert not p["falhou"] and p["resultado"]["admin_email"] == "admin@exemplo.com.br"
    assert p["resultado"]["admin_senha_temporaria"] == "Temp-Senha-123"
    _, depois, _ = req(app, "GET", "/api/progresso?desde=0")
    assert "admin_senha_temporaria" not in depois["resultado"]
    assert "Temp-Senha-123" not in json.dumps(depois)


def test_instalar_com_opcoes_invalidas_nao_inicia(app):
    s, r, _ = req(app, "POST", "/api/instalar", {**OPCOES, "pasta_instalacao": "relativa"})
    assert s == 409 and "pasta_instalacao" in r["erro"] and app.motor is None


def test_instalar_duas_vezes_ao_mesmo_tempo_e_recusado(app):
    app._montar = lambda: [Etapa("lenta", "Lenta", lambda c: time.sleep(0.5))]
    assert req(app, "POST", "/api/instalar", OPCOES)[0] == 200
    s, r, _ = req(app, "POST", "/api/instalar", OPCOES)
    assert s == 409 and "em andamento" in r["erro"]
    _esperar_fim(app)


def test_retomar_sem_instalacao_e_recusado(app):
    assert req(app, "POST", "/api/retomar", {})[0] == 409


def test_pastas_lista_so_diretorios_e_recusa_caminho_estranho(app, tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "arquivo.txt").write_text("x")
    (tmp_path / ".oculta").mkdir()
    s, d, _ = req(app, "GET", "/api/pastas?caminho=" + str(tmp_path).replace("\\", "%5C"))
    nomes = [i["nome"] for i in d["itens"]]
    assert "sub" in nomes and "arquivo.txt" not in nomes and ".oculta" not in nomes
    _, d, _ = req(app, "GET", "/api/pastas?caminho=..%5C..")
    assert "erro" in d
    _, d, _ = req(app, "GET", "/api/pastas?caminho=relativo")
    assert "erro" in d
    _, d, _ = req(app, "GET", "/api/pastas")
    assert d["unidades"] and d["atual"] == ""


def test_encerrar_sinaliza_o_fim(app):
    assert req(app, "POST", "/api/encerrar", {})[0] == 200 and app.encerrar.is_set()


def test_abrir_painel_so_abre_a_url_fixa(app, monkeypatch):
    abertas = []
    monkeypatch.setattr(servidor.webbrowser, "open", lambda u: abertas.append(u))
    assert req(app, "POST", "/api/abrir-painel", {"url": "https://evil.example"})[0] == 200
    assert abertas == [servidor.URL_PAINEL]


def test_escuta_so_em_loopback(app):
    assert app.porta > 0
    # a ligação é em 127.0.0.1 (criar_servidor); uma conexão ao IP da LAN nem existe para testar aqui, então confere o código
    import inspect
    assert '("127.0.0.1", porta)' in inspect.getsource(servidor.criar_servidor)


def test_corpo_recusado_e_sempre_lido_antes_de_responder(app):
    """Responder 400 sem ler o corpo e fechar o socket manda um RST no Windows: o cliente perde a resposta."""
    for _ in range(100):
        assert req(app, "POST", "/api/validar", bruto=b"a=b" * 80000, tipo="application/x-www-form-urlencoded")[0] == 400
        assert req(app, "POST", "/api/validar", bruto=b"{nao json" * 2000)[0] == 400

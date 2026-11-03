#!/usr/bin/env python3
"""
Macaco de interface da Squad: usa o sistema "à força" como o pior usuário possível, até achar erro.

Roda DENTRO do container do Playwright (rede interna do sandbox) e só fala com o alvo informado. Clica em tudo que é clicável, digita
texto hostil em todo campo, aperta teclas aleatórias, volta e avança, redimensiona a janela. Semente fixa: a mesma sequência de ações
se repete, e cada achado traz as últimas ações para reproduzir.

Uso:  python kit_ui.py ALVO SAIDA.json [SEGUNDOS]
"""
import json
import random
import sys
import time

SEMENTE = 20261103
TEXTOS = ["", " ", "a" * 3000, "<script>alert(1)</script>", "' OR '1'='1", "‮evil", "😀" * 100, "-1", "0", "9" * 30, "null",
          "ñção", "../../etc/passwd", "{{7*7}}", "\t\n", "x@y", "1e999"]
TECLAS = ["Enter", "Escape", "Tab", "ArrowDown", "ArrowUp", "Backspace", "Delete", "Space"]
CLICAVEIS = "a, button, [role=button], input[type=checkbox], input[type=radio], input[type=submit], select, summary, [onclick]"
CAMPOS = "input:not([type=checkbox]):not([type=radio]):not([type=submit]):not([type=file]), textarea"


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    alvo, saida = argv[1], argv[2]
    segundos = int(argv[3]) if len(argv) > 3 else 60
    from playwright.sync_api import sync_playwright
    rng = random.Random(SEMENTE)
    achados, acoes, vistos = [], [], set()

    def achar(id_, sev, titulo, evidencia):
        chave = (id_, titulo[:80])
        if chave in vistos:
            return
        vistos.add(chave)
        achados.append({"id": id_, "severidade": sev, "categoria": "interface", "endpoint": "-", "metodo": "-",
                        "evidencia": str(evidencia)[:300], "reproducao": " → ".join(acoes[-8:])[:300] or "abrir a página inicial"})

    with sync_playwright() as p:
        nav = p.chromium.launch(args=["--no-sandbox"])
        pagina = nav.new_page(viewport={"width": 1280, "height": 800})
        pagina.on("pageerror", lambda e: achar("UI-01", "ALTO", f"erro não tratado: {str(e)[:60]}", e))
        pagina.on("console", lambda m: m.type == "error" and achar("UI-03", "MEDIO", f"console: {m.text[:60]}", m.text))
        pagina.on("requestfailed", lambda r: achar("UI-04", "MEDIO", f"requisição falhou: {r.url[-60:]}", r.failure))
        pagina.on("response", lambda r: r.status >= 500 and achar("UI-02", "ALTO", f"{r.status} em {r.url[-60:]}", f"{r.request.method} {r.url}"))
        pagina.goto(alvo, timeout=20000)
        fim = time.time() + segundos
        while time.time() < fim:
            try:
                acao = rng.choice(["clicar", "clicar", "digitar", "digitar", "tecla", "voltar", "redimensionar"])
                if acao == "clicar":
                    itens = pagina.query_selector_all(CLICAVEIS)
                    if itens:
                        alvo_el = rng.choice(itens)
                        rotulo = (alvo_el.inner_text() or alvo_el.get_attribute("id") or alvo_el.get_attribute("name") or "").strip()
                        acoes.append(f"clicar em {rotulo[:20]!r}")
                        alvo_el.click(timeout=1500, force=True)
                elif acao == "digitar":
                    campos = pagina.query_selector_all(CAMPOS)
                    if campos:
                        campo = rng.choice(campos)
                        texto = rng.choice(TEXTOS)
                        acoes.append(f"digitar {texto[:20]!r}")
                        campo.fill(texto, timeout=1500)
                elif acao == "tecla":
                    tecla = rng.choice(TECLAS)
                    acoes.append(f"tecla {tecla}")
                    pagina.keyboard.press(tecla)
                elif acao == "voltar":
                    acoes.append("voltar")
                    pagina.go_back(timeout=3000)
                else:
                    larg = rng.choice([320, 768, 1280, 1920])
                    acoes.append(f"redimensionar {larg}")
                    pagina.set_viewport_size({"width": larg, "height": 800})
                pagina.wait_for_timeout(120)
                if not (pagina.inner_text("body", timeout=1500) or "").strip():
                    achar("UI-05", "ALTO", "página em branco depois de uma ação", pagina.url)
            except Exception as e:  # clique em elemento que sumiu, navegação interrompida etc.: faz parte do uso hostil
                if "Target closed" in str(e) or "crash" in str(e).lower():
                    achar("UI-06", "CRITICO", "a página travou ou fechou", str(e)[:200])
                    break
        nav.close()
    with open(saida, "w", encoding="utf-8") as f:
        json.dump({"achados": achados, "acoes": len(acoes), "incompleto": False, "modo": "macaco-ui", "semente": SEMENTE}, f, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

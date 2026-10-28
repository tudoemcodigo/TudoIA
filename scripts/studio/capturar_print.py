"""Captura de tela do TudoIA Studio com o cliente somente leitura (tudoia-capturas).

Não faz login de navegador: obtém um access token por client_credentials no Keycloak e envia
`Authorization: Bearer` em todas as requisições do Edge. O Studio aceita esse token só para leitura.

Uso (a partir da raiz do TudoIA):
    .venv\\Scripts\\python.exe -m scripts.studio.capturar_print --rota hardware --saida midia.png

Rotas: hardware, servicos, roteador, imagens. Saída: código 0 se o print foi salvo.
Configuração em .env: TUDOIA_OIDC_ISSUER, TUDOIA_CAPTURAS_CLIENT_ID, TUDOIA_CAPTURAS_CLIENT_SECRET.
Segredos nunca são impressos.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
PAINEL = "http://127.0.0.1:3100"

# Cada rota tem um texto que só aparece quando a tela carregou de verdade (não o login, nem o spinner).
ROTAS = {
    "hardware": ("#hardware", "Monitoramento do Servidor"),
    "servicos": ("#servicos", "Serviços e Infraestrutura Local"),
    "roteador": ("#roteador", "Roteador Inteligente"),
    "imagens": ("#imagens", "Gerador de Imagens de Alta Fidelidade"),
    "modelos": ("#modelos", "Modelos & Motores"),
    "governanca": ("#governanca", "Governança Canônica"),
    "limites": ("#limites", "Limites & Tokens"),
    "telemetria": ("#telemetria", "Telemetria & Logs"),
}


def ler_env(caminho: Path) -> dict[str, str]:
    valores: dict[str, str] = {}
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#") and "=" in linha:
            chave, _, valor = linha.partition("=")
            valores[chave.strip()] = valor.strip()
    return valores


def obter_token(issuer: str, cliente_id: str, segredo: str) -> str:
    corpo = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": cliente_id,
        "client_secret": segredo,
    }).encode("ascii")
    req = urllib.request.Request(f"{issuer}/protocol/openid-connect/token", data=corpo, method="POST")
    with urllib.request.urlopen(req, timeout=10) as resposta:
        dados = json.loads(resposta.read())
    return dados["access_token"]


def capturar(rota: str, saida: Path, largura: int, altura: int, recorte: tuple[int, int, int, int] | None = None) -> None:
    from playwright.sync_api import sync_playwright

    fragmento, texto_esperado = ROTAS[rota]
    env = ler_env(RAIZ / ".env")
    token = obter_token(env["TUDOIA_OIDC_ISSUER"], env["TUDOIA_CAPTURAS_CLIENT_ID"], env["TUDOIA_CAPTURAS_CLIENT_SECRET"])

    saida.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        navegador = pw.chromium.launch(channel="msedge", headless=True)
        try:
            # Com recorte, a captura sai em 2x para o texto da tela continuar nítido na página do carrossel.
            contexto = navegador.new_context(
                viewport={"width": largura, "height": altura},
                device_scale_factor=2 if recorte else 1,
                extra_http_headers={"Authorization": f"Bearer {token}"},
            )
            pagina = contexto.new_page()
            pagina.goto(f"{PAINEL}/app/{fragmento}", wait_until="domcontentloaded")
            pagina.get_by_text(texto_esperado, exact=False).first.wait_for(timeout=20_000)
            pagina.wait_for_load_state("networkidle")
            if recorte:
                x, y, w, h = recorte
                pagina.screenshot(path=str(saida), clip={"x": x, "y": y, "width": w, "height": h})
            else:
                pagina.screenshot(path=str(saida), full_page=True)
        finally:
            navegador.close()


def _recorte(valor: str) -> tuple[int, int, int, int]:
    partes = [int(p) for p in valor.split(",")]
    if len(partes) != 4 or partes[2] <= 0 or partes[3] <= 0:
        raise argparse.ArgumentTypeError("use x,y,largura,altura em pixels CSS (largura e altura > 0)")
    return partes[0], partes[1], partes[2], partes[3]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Captura um print do TudoIA Studio (somente leitura).")
    parser.add_argument("--rota", required=True, choices=sorted(ROTAS))
    parser.add_argument("--saida", required=True, type=Path)
    parser.add_argument("--largura", type=int, default=1440)
    parser.add_argument("--altura", type=int, default=900)
    parser.add_argument("--recorte", type=_recorte, help="x,y,largura,altura: recorta a tela e captura em 2x")
    args = parser.parse_args(argv)
    try:
        capturar(args.rota, args.saida, args.largura, args.altura, args.recorte)
    except Exception as exc:  # noqa: BLE001 — o chamador decide o fallback; a causa vai para o log
        print(f"[captura] falhou: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(f"[captura] print salvo em {args.saida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

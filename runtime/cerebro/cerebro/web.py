import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from urllib.parse import urljoin

import httpx

from .envelope import envelopar
from .vetores import MAX_RESULTADOS

CORTE = "\n[…cortado]"
LIMITE_CORPO = 2 * 1024 * 1024  # bytes: página maior que isso não é lida inteira
MAXIMO_REDIRECIONAMENTOS = 3
PRAZO_TOTAL = 20.0  # segundos para a leitura inteira; o timeout do httpx vale por leitura e não segura gotejamento
MIN_CARACTERES, MAX_CARACTERES = 500, 20000
REDE_NAT64 = ipaddress.ip_network("64:ff9b::/96")

Resolvedor = Callable[[str, int], Awaitable[list[str]]]


async def pesquisar(consulta: str, n: int, searxng_url: str, cliente: httpx.AsyncClient) -> list[dict]:
    if not consulta or not consulta.strip():
        raise ValueError("A consulta está vazia. Diga o que você quer pesquisar na web.")
    r = await cliente.get(
        f"{searxng_url.rstrip('/')}/search",
        params={"q": consulta.strip(), "format": "json", "language": "pt-BR"},
    )
    r.raise_for_status()
    return [
        {"titulo": x.get("title", ""), "url": x.get("url", ""), "trecho": x.get("content", "")}
        for x in r.json().get("results", [])[: min(max(n, 1), MAX_RESULTADOS)]
    ]


async def _resolver_padrao(host: str, porta: int) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, porta, type=socket.SOCK_STREAM)
    return [info[4][0] for info in infos]


def ip_publico(endereco: str) -> bool:
    """Só endereço global (is_global fecha privado, loopback, link-local, CGNAT, 6to4 etc.)."""
    ip = ipaddress.ip_address(endereco)
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        elif ip in REDE_NAT64:
            # o ipaddress considera NAT64 global, mas o gateway entrega no IPv4 embutido, que pode ser interno
            ip = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    # multicast também é "global" para o ipaddress; não é destino de página
    return ip.is_global and not ip.is_multicast


async def _validar_destino(url: str, resolver: Resolvedor) -> tuple[httpx.URL, str]:
    """URL interpretada pelo httpx (o mesmo parser que monta a requisição) e o IP validado onde conectar."""
    try:
        destino = httpx.URL(url)
    except httpx.InvalidURL as e:
        raise ValueError("Endereço inválido.") from e
    if destino.scheme not in ("http", "https"):
        raise ValueError("Só são aceitos endereços http:// ou https://.")
    if not destino.host:
        raise ValueError("Endereço sem host.")
    porta = destino.port or (443 if destino.scheme == "https" else 80)
    try:
        enderecos = await resolver(destino.raw_host.decode("ascii"), porta)
    except OSError as e:
        raise ValueError(f"Não foi possível resolver o endereço ({type(e).__name__}).") from e
    if not enderecos or not all(ip_publico(e) for e in enderecos):
        # Um único endereço interno basta para recusar: o host pode ter registros mistos.
        raise ValueError("Endereço interno ou reservado não é lido pelo Cérebro.")
    return destino, enderecos[0]


async def _ler_limitado(resposta: httpx.Response) -> bytes:
    buffer = bytearray()
    async for pedaco in resposta.aiter_bytes():
        buffer.extend(pedaco)
        if len(buffer) > LIMITE_CORPO:
            raise ValueError("Página maior que 2 MB: não será lida.")
    return bytes(buffer)


async def _baixar(url: str, cliente: httpx.AsyncClient, resolver: Resolvedor) -> tuple[httpx.URL, bytes, str]:
    atual = url
    for _ in range(MAXIMO_REDIRECIONAMENTOS + 1):
        destino, ip = await _validar_destino(atual, resolver)
        # Conecta no IP já validado: o httpx não resolve o nome de novo (fecha DNS rebinding).
        # Host e SNI vão com o nome original, então o certificado é conferido contra o nome.
        # Connection: close impede que um salto para outro nome reaproveite a conexão TLS deste.
        async with cliente.stream(
            "GET", destino.copy_with(host=ip), timeout=15.0, follow_redirects=False,
            headers={"Host": destino.netloc.decode("ascii"), "Connection": "close"},
            extensions={"sni_hostname": destino.raw_host.decode("ascii")},
        ) as r:
            if r.is_redirect and "location" in r.headers:
                atual = urljoin(atual, r.headers["location"])
                continue
            r.raise_for_status()
            return destino, await _ler_limitado(r), r.encoding or "utf-8"
    raise ValueError("Redirecionamentos demais.")


def _envelopar(texto: str, origem: httpx.URL) -> str:
    return envelopar(texto, str(origem.copy_with(userinfo=b"")))


async def ler_pagina(url: str, max_caracteres: int, cliente: httpx.AsyncClient,
                     resolver: Resolvedor = _resolver_padrao) -> str:
    """Lê uma página pública. Cada redirecionamento é validado de novo (SSRF) e o corpo tem teto de tamanho."""
    max_caracteres = min(max(max_caracteres, MIN_CARACTERES), MAX_CARACTERES)
    try:
        async with asyncio.timeout(PRAZO_TOTAL):
            origem, corpo, codificacao = await _baixar(url, cliente, resolver)
    except TimeoutError:
        raise ValueError(f"A página não chegou inteira em {PRAZO_TOTAL:.0f} s: leitura cancelada.") from None

    import trafilatura

    html = corpo.decode(codificacao, errors="replace")
    # extração é CPU pura (até 2 MB de HTML): fora do event loop
    texto = await asyncio.to_thread(trafilatura.extract, html) or html
    if len(texto) > max_caracteres:
        texto = texto[:max_caracteres] + CORTE
    return _envelopar(texto, origem)

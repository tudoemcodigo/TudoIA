"""Conferência do conteúdo de mídia enviada: a extensão sozinha não diz o que o arquivo é."""

LIMITE_UPLOAD_BYTES = 100 * 1024 * 1024


def _riff(dados: bytes, tipo: bytes) -> bool:
    return dados[:4] == b"RIFF" and dados[8:12] == tipo


ASSINATURAS = {
    ".png": lambda d: d.startswith(b"\x89PNG\r\n\x1a\n"),
    ".jpg": lambda d: d.startswith(b"\xff\xd8\xff"),
    ".jpeg": lambda d: d.startswith(b"\xff\xd8\xff"),
    ".gif": lambda d: d[:6] in (b"GIF87a", b"GIF89a"),
    ".bmp": lambda d: d.startswith(b"BM"),
    ".webp": lambda d: _riff(d, b"WEBP"),
    ".mp4": lambda d: d[4:8] == b"ftyp",
    ".mov": lambda d: d[4:8] in (b"ftyp", b"moov", b"mdat", b"wide", b"free"),
    ".webm": lambda d: d.startswith(b"\x1a\x45\xdf\xa3"),
    ".mkv": lambda d: d.startswith(b"\x1a\x45\xdf\xa3"),
    ".avi": lambda d: _riff(d, b"AVI "),
}


def midia_confere(dados: bytes, sufixo: str) -> bool:
    """True se os primeiros bytes batem com o formato da extensão. Extensão desconhecida nunca confere."""
    confere = ASSINATURAS.get(sufixo.lower())
    return bool(confere and confere(dados))

"""Porta em que o painel atende (TUDOIA_PAINEL_PORTA, definida por `tudoia painel --porta`)."""
import os

PORTA_PADRAO = 3100


def porta_do_painel() -> int:
    try:
        return int(os.environ.get("TUDOIA_PAINEL_PORTA", PORTA_PADRAO))
    except ValueError:
        return PORTA_PADRAO
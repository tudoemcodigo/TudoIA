"""
Perfis de destino do TudoIA que a Squad aceita escolher (`--perfil` na CLI, `perfil` na API). Os nomes de modelo são os do
gateway (`config/roteamento.yaml` do TudoIA, seção `perfis`). Só `local-estrito` garante que nada sai da máquina.
"""

PERFIS = {
    "local-estrito": "tudoia-local-estrito",  # nunca sai da máquina e sem fallback para a nuvem (padrão)
    "local": "tudoia-local",                  # local, mas o gateway pode reenviar à nuvem se estourar o contexto
    "hibrido": "tudoia-hibrido",              # local primeiro, nuvem gratuita como apoio
    "nuvem": "tudoia-nuvem",
    "auto": "tudoia-auto",                    # roteador automático: decide por pedido entre local e nuvem; exige consentimento
    "max": "tudoia-max",                      # pago; só por escolha explícita
}

# Modelos que o orquestrador trata como locais sem pedir consentimento de nuvem.
MODELOS_LOCAIS = frozenset({"tudoia-local", "tudoia-local-estrito"})


def modelo_e_local(modelo: str) -> bool:
    return modelo in MODELOS_LOCAIS or modelo.startswith("local/")


def perfil_do_modelo(modelo: str) -> str | None:
    """Nome do perfil (`auto`, `local-estrito`...) de um modelo do gateway, ou None se não for um perfil da Squad."""
    return next((p for p, m in PERFIS.items() if m == modelo), None)

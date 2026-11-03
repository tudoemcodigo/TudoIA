"""
Perfis de destino do TudoIA que a Squad aceita escolher na CLI (`--perfil`). Os nomes de modelo são os do gateway
(`config/roteamento.yaml` do TudoIA, seção `perfis`). Só estes saem da máquina: `hibrido`, `nuvem` e `max`.
"""

PERFIS = {
    "local-estrito": "tudoia-local-estrito",  # nunca sai da máquina e sem fallback para a nuvem (recomendado)
    "local": "tudoia-local",                  # local, mas o gateway pode reenviar à nuvem se estourar o contexto
    "hibrido": "tudoia-hibrido",              # local primeiro, nuvem gratuita como apoio
    "nuvem": "tudoia-nuvem",
    "max": "tudoia-max",                      # pago; só por escolha explícita
}

# Modelos que o orquestrador trata como locais sem pedir consentimento de nuvem.
MODELOS_LOCAIS = frozenset({"tudoia-local", "tudoia-local-estrito"})


def modelo_e_local(modelo: str) -> bool:
    return modelo in MODELOS_LOCAIS or modelo.startswith("local/")

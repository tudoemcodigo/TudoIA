"""Estado da Doutrina TEC para a tela de governança: somente leitura, sem rede e sem gravar nada.

Responde três perguntas: a Doutrina em uso está legível (`DOUTRINA_TEC` aponta para uma pasta com `gerado/manifesto.json`)?
qual commit o TudoIA fixou (`governanca/doutrina.json`)? o Dockerfile e o compose da SquadTI repetem esse commit?
Atualizar o commit é decisão de quem empacota (comandos em `COMANDOS`); a tela só mostra.
"""
import json
from pathlib import Path

try:   # ferramenta de empacotamento; sem ela (instalação sem scripts/) só a checagem dos arquivos derivados some
    from scripts.empacotar import payload as _empacotar
except ImportError:   # pragma: no cover - o produto leva scripts/ (ver INCLUIR em payload.py)
    _empacotar = None

COMANDOS = {
    "atualizar": "python -m scripts.empacotar.payload --sincronizar-pin",
    "derivar": "python -m scripts.empacotar.payload --derivar-pin",
    "empacotar": ".\\scripts\\tudoia.ps1 empacotar",
}


def _manifesto(pasta: Path) -> dict:
    dados = json.loads((pasta / "gerado" / "manifesto.json").read_text(encoding="utf-8"))
    return {"versao": str(dados["versao"]), "hash": str(dados["hash"])}


def estado_doutrina(raiz: Path, env: dict[str, str]) -> dict:
    """{estado, mensagem, em_uso, fixada, derivados_divergentes, comandos}. `estado`: ok | sem_pasta | ilegivel."""
    saida: dict = {"estado": "ok", "mensagem": "", "pasta": None, "em_uso": None, "fixada": None,
                   "derivados_divergentes": [], "aviso_fixacao": None, "comandos": COMANDOS}

    pasta = (env.get("DOUTRINA_TEC") or "").strip()
    if not pasta:
        saida.update(estado="sem_pasta", mensagem="DOUTRINA_TEC não está no .env: a skill, o MCP doutrina-tec e a SquadTI não "
                                                  "trabalham sem a Doutrina (falham fechado).")
    else:
        saida["pasta"] = pasta
        try:
            saida["em_uso"] = _manifesto(Path(pasta))
            saida["mensagem"] = "Doutrina legível."
        except (OSError, ValueError, KeyError, TypeError):
            saida.update(estado="ilegivel", mensagem="DOUTRINA_TEC aponta para uma pasta sem gerado/manifesto.json legível.")

    if _empacotar is None:
        saida["aviso_fixacao"] = "ferramenta de empacotamento indisponível nesta instalação"
        return saida
    try:
        saida["fixada"] = _empacotar.ler_pin(raiz)
        saida["derivados_divergentes"] = _empacotar.sincronizar_pin(raiz)
    except _empacotar.ErroDoutrina as e:
        saida["aviso_fixacao"] = str(e)
    return saida

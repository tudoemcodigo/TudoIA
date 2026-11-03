"""
Carregador da Doutrina TEC para a Squad.

Consome os artefatos gerados pela própria doutrina (gerado/manifesto.json, gerado/<familia>.json e
gerado/<familia>-nucleo.md); nenhum parse de Markdown. Falha fechado: sem doutrina legível, a Squad
não trabalha (um agente sem regras produz código fora do padrão sem avisar).

Cada papel carrega o núcleo e as regras das famílias do perfil dele (`gerado/perfis/<papel>.json`, definido na
Doutrina em ecossistema.json e já dentro do orçamento de tokens); sem perfil o papel não trabalha (falha fechado).
Para forçar as mesmas famílias em todos os papéis, defina DOUTRINA_FAMILIAS (lista separada por vírgula) ou
`doutrina_familias` no estado. Família inexistente ou com nome inválido derruba a tarefa.
"""
import json
import os
import re
from pathlib import Path
from typing import Iterable, Optional

FAMILIAS_PADRAO = ("arquitetura", "ia", "ecossistema")
_RE_FAMILIA = re.compile(r"^[a-z0-9-]{1,40}$")


class DoutrinaIndisponivel(RuntimeError):
    """Doutrina ausente, ilegível ou diferente da registrada na tarefa."""


def raiz_doutrina(state: Optional[dict] = None) -> Path:
    """DOUTRINA_TEC (ambiente) > architecture_source_path do estado. Sem caminho fixo no código."""
    caminho = os.getenv("DOUTRINA_TEC") or (state or {}).get("architecture_source_path")
    if not caminho:
        raise DoutrinaIndisponivel("defina DOUTRINA_TEC (ou architecture_source_path no stack_config)")
    raiz = Path(caminho)
    if not (raiz / "gerado" / "manifesto.json").is_file():
        raise DoutrinaIndisponivel(f"{raiz} não parece uma Doutrina TEC (falta gerado/manifesto.json)")
    return raiz


def familias(state: Optional[dict] = None) -> tuple:
    """Famílias lidas: DOUTRINA_FAMILIAS (ambiente) > doutrina_familias do estado > padrão. Nome validado."""
    bruto = os.getenv("DOUTRINA_FAMILIAS") or (state or {}).get("doutrina_familias")
    if not bruto:
        return FAMILIAS_PADRAO
    itens: Iterable = bruto.split(",") if isinstance(bruto, str) else bruto
    lista = [str(f).strip() for f in itens if str(f).strip()]
    ruins = [f for f in lista if not _RE_FAMILIA.match(f)]
    if not lista or ruins:
        raise DoutrinaIndisponivel(f"família inválida em DOUTRINA_FAMILIAS/doutrina_familias: {ruins or bruto!r}")
    return tuple(dict.fromkeys(lista))


def _json(raiz: Path, nome: str) -> dict:
    try:
        return json.loads((raiz / "gerado" / nome).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise DoutrinaIndisponivel(f"não foi possível ler gerado/{nome}: {e}") from e


def manifesto(state: Optional[dict] = None) -> dict:
    return _json(raiz_doutrina(state), "manifesto.json")


def verificar_versao(state: dict) -> dict:
    """
    Primeira chamada da tarefa: grava versão e hash no estado. Chamadas seguintes: aborta se a doutrina
    mudou no meio da tarefa (a entrega deve seguir UMA versão, rastreável).
    """
    m = manifesto(state)
    atual = {"doutrina_versao": m["versao"], "doutrina_hash": m["hash"]}
    gravado = state.get("doutrina_hash")
    if gravado and gravado != m["hash"]:
        raise DoutrinaIndisponivel(
            f"a Doutrina TEC mudou durante a tarefa ({state.get('doutrina_versao')} -> {m['versao']}); "
            "reinicie a tarefa para que todo o trabalho siga a mesma versão")
    return atual


_RE_PAPEL = re.compile(r"^[a-z0-9-]{1,20}$")
ORCAMENTO_REGRAS_TOKENS = 12000  # regras do papel no prompt (modelo local pequeno): MUST primeiro, depois SHOULD; MAY fora


def _explicito(state: Optional[dict]) -> bool:
    return bool(os.getenv("DOUTRINA_FAMILIAS") or (state or {}).get("doutrina_familias"))


def perfil(papel: str, state: Optional[dict] = None) -> dict:
    """gerado/perfis/<papel>.json: núcleo sugerido e famílias de consulta do papel. Falha fechado se ausente ou corrompido."""
    if not _RE_PAPEL.match(papel or ""):
        raise DoutrinaIndisponivel(f"papel inválido: {papel!r}")
    dados = _json(raiz_doutrina(state), f"perfis/{papel}.json")
    if not isinstance(dados.get("nucleo_sugerido"), list) or not isinstance(dados.get("familias"), list):
        raise DoutrinaIndisponivel(f"perfil do papel '{papel}' malformado")
    return dados


def familias_do_papel(papel: str, state: Optional[dict] = None) -> tuple:
    """Famílias cujo núcleo e regras o papel carrega. DOUTRINA_FAMILIAS/doutrina_familias, se definido, vale para todos
    os papéis; senão vem do perfil da Doutrina (núcleo sugerido pelo papel, já dentro do orçamento de tokens)."""
    if _explicito(state):
        return familias(state)
    excluidas = set((state or {}).get("doutrina_excluir") or ())  # famílias que a stack escolhida não usa (ex.: arquitetura .NET)
    nomes = tuple(dict.fromkeys(str(n) for n in perfil(papel, state)["nucleo_sugerido"] if str(n) not in excluidas))
    if not nomes or not all(_RE_FAMILIA.match(n) for n in nomes):
        raise DoutrinaIndisponivel(f"perfil do papel '{papel}' sem famílias válidas")
    return nomes


def _papeis(papel) -> tuple:
    """Um papel (str) ou vários (sequência), sempre como tupla sem repetição. Vazio é erro: sem papel não há regras."""
    lista = (papel,) if isinstance(papel, str) else tuple(papel or ())
    if not lista:
        raise DoutrinaIndisponivel("nenhum papel informado")
    return tuple(dict.fromkeys(lista))


def nucleo(state: Optional[dict] = None, papel=None) -> str:
    """Núcleo (regras inegociáveis) das famílias lidas, uma após a outra; com `papel` (um ou vários), só as do perfil
    dele(s), sem repetir família."""
    raiz = raiz_doutrina(state)
    partes = []
    if papel:
        nomes = tuple(dict.fromkeys(f for p in _papeis(papel) for f in familias_do_papel(p, state)))
    else:
        nomes = familias(state)
    for fam in nomes:
        arq = raiz / "gerado" / f"{fam}-nucleo.md"
        try:
            partes.append(arq.read_text(encoding="utf-8").strip())
        except OSError as e:
            raise DoutrinaIndisponivel(f"núcleo da família '{fam}' ilegível: {e}") from e
    return "\n\n".join(partes)


def _dados_das_familias(state: Optional[dict], papel: Optional[str] = None) -> list:
    raiz = raiz_doutrina(state)
    nomes = familias_do_papel(papel, state) if papel else familias(state)
    return [_json(raiz, f"{fam}.json") for fam in nomes]


def _tokens(texto: str) -> int:
    return len(texto) // 4  # mesma estimativa da Doutrina (caracteres/4)


def orcamento_de_regras() -> int:
    """DOUTRINA_REGRAS_MAX_TOKENS ajusta o orçamento de regras ao contexto do modelo; inválido volta ao padrão (nunca ilimitado)."""
    try:
        valor = int(os.getenv("DOUTRINA_REGRAS_MAX_TOKENS", ORCAMENTO_REGRAS_TOKENS))
    except (TypeError, ValueError):
        return ORCAMENTO_REGRAS_TOKENS
    return valor if 500 <= valor <= 200_000 else ORCAMENTO_REGRAS_TOKENS


def regras_do_papel(papel: str, state: Optional[dict] = None, incluir_nucleo: bool = False,
                    orcamento_tokens: Optional[int] = None) -> str:
    """
    Regras (só o texto normativo) dos padrões que o papel precisa, nas famílias do perfil dele. Por padrão
    exclui as regras de núcleo, que já vão no contexto fixo: evita pagar tokens duas vezes. O papel pode
    existir em só algumas famílias; só é erro se não existir em nenhuma.

    Cabe no orçamento: `MUST` primeiro (todas as famílias), depois `SHOULD`; `MAY` fica de fora. O que não coube é
    declarado numa linha final com a quantidade, para o agente não presumir que viu tudo (falha visível, não silenciosa).
    """
    orcamento_tokens = orcamento_de_regras() if orcamento_tokens is None else orcamento_tokens
    todos = _dados_das_familias(state, papel)  # sem perfil (e sem DOUTRINA_FAMILIAS) o papel é desconhecido: falha fechado
    conhecidos = sorted({p for d in todos for p in d["por_papel"]})
    if papel not in conhecidos:
        raise DoutrinaIndisponivel(f"papel '{papel}' desconhecido nas famílias lidas (use um de {conhecidos})")
    candidatas = []
    for dados in todos:
        arquivos = dados["por_papel"].get(papel, [])
        for r in dados["regras"]:
            if r["padrao"] not in arquivos or (r["nucleo"] and not incluir_nucleo):
                continue
            ev = f" · prova: {', '.join(r['evidencia'])}" if r["evidencia"] else ""
            candidatas.append((r["nivel"], f"- **{r['id']}** {r['nivel']} — {r['texto']} · verif: {','.join(r['verif'])}{ev}"))
    linhas, gasto, omitidas = [], 0, 0
    for nivel in ("MUST", "SHOULD", "MAY"):
        for n, linha in candidatas:
            if n != nivel:
                continue
            if nivel == "MAY" or gasto + _tokens(linha) > orcamento_tokens:
                omitidas += 1
                continue
            linhas.append(linha)
            gasto += _tokens(linha)
    if omitidas:
        linhas.append(f"- [{omitidas} regra(s) SHOULD/MAY omitida(s) por orçamento de contexto; não presuma que estas são as únicas]")
    return "\n".join(linhas)


def evidencias(state: Optional[dict] = None) -> dict:
    """
    ID da regra -> testes do template que a travam (forma `Classe.Metodo`). O QA roda estes em vez de confiar.
    Provas em outros repositórios (`fonte:caminho#trecho`) não são testes do template e ficam de fora.
    """
    saida = {}
    for dados in _dados_das_familias(state):
        for r in dados["regras"]:
            testes = [e for e in r["evidencia"] if ":" not in e]
            if testes:
                saida[r["id"]] = testes
    return saida


def ids_do_papel(papel: str, state: Optional[dict] = None, prefixo: str = "") -> list:
    """[{'id','nivel'}] das regras do papel (núcleo incluso, MAY incluso, sem orçamento de tokens), só IDs e níveis, na ordem
    MUST, SHOULD, MAY. `prefixo` filtra por família (ex.: 'SEC-'). Serve a relatórios, não ao prompt."""
    todos = _dados_das_familias(state, papel)
    conhecidos = sorted({p for d in todos for p in d["por_papel"]})
    if papel not in conhecidos:
        raise DoutrinaIndisponivel(f"papel '{papel}' desconhecido nas famílias lidas (use um de {conhecidos})")
    achadas = {}
    for dados in todos:
        arquivos = dados["por_papel"].get(papel, [])
        for r in dados["regras"]:
            if r["padrao"] in arquivos and r["id"].startswith(prefixo):
                achadas[r["id"]] = r["nivel"]
    ordem = {"MUST": 0, "SHOULD": 1, "MAY": 2}
    return [{"id": i, "nivel": n} for i, n in sorted(achadas.items(), key=lambda kv: (ordem.get(kv[1], 3), kv[0]))]


def contexto(papel, state: Optional[dict] = None, com_nucleo: bool = True, orcamento_tokens: Optional[int] = None) -> str:
    """Bloco pronto para o prompt de sistema: núcleo (opcional) + regras do papel. `papel` pode ser uma tupla: o núcleo
    sai uma vez só (sem família repetida) e as regras vêm por papel."""
    papeis = _papeis(papel)
    partes = []
    if com_nucleo:
        partes.append("--- NÚCLEO ---\n" + nucleo(state, papeis))
    for p in papeis:
        partes.append(f"--- REGRAS DO PAPEL ({p}) ---\n" + regras_do_papel(p, state, orcamento_tokens=orcamento_tokens))
    return "\n".join(partes)


def ids_existentes(state: Optional[dict] = None) -> frozenset:
    """Todos os IDs de regra que a Doutrina tem (todas as famílias geradas), para conferir o que um modelo cita."""
    raiz = raiz_doutrina(state)
    achados = set()
    for arq in sorted((raiz / "gerado").glob("*.json")):
        if arq.name == "manifesto.json":
            continue
        dados = _json(raiz, arq.name)
        for r in dados.get("regras", []) if isinstance(dados, dict) else []:
            if isinstance(r, dict) and isinstance(r.get("id"), str):
                achados.add(r["id"])
    return frozenset(achados)

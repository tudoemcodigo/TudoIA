"""Regras do roteador tudoia-auto: decide para qual grupo do LiteLLM vai um pedido.

Função pura, só com a biblioteca padrão: é usada pelo hook roteador.py (dentro do container do LiteLLM)
e pelo painel (aba Roteador e testes). As regras vêm de config/roteamento.yaml.
"""
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

LOCAL, NUVEM, CODIGO, LOCAL_AGENTE = "tudoia-local", "tudoia-nuvem", "tudoia-codigo", "tudoia-local-agente"
VISAO, MAXIMO = "tudoia-visao", "tudoia-max"
GRUPOS_COM_VISAO = frozenset({VISAO, MAXIMO})   # destinos que recebem imagem; o resto recebe as imagens trocadas por texto
_MARCADOR = re.compile(r"(?<!\S)#(local|nuvem|max)\b", re.IGNORECASE)
_CODIGO = re.compile(
    r"```|Traceback \(most recent call last\)|^\s*at .+\(.+:\d+\)|^\w*(Error|Exception):|^diff --git|^@@ ",
    re.MULTILINE,
)


@dataclass
class Decisao:
    grupo: str
    pontos: int = 0
    motivos: list[str] = field(default_factory=list)
    marcador: str | None = None


def _norm(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sem_acento.lower()


def validar_regras(regras: dict) -> None:
    """Levanta ValueError se o roteamento.yaml tiver campos ausentes ou de tipo errado (ex.: limiar: 3,5)."""
    if not isinstance(regras, dict):
        raise ValueError("roteamento.yaml: o arquivo deve ser um mapa de campos")
    for campo in ("limiar", "pesos", "ordem"):
        if campo not in regras:
            raise ValueError(f"roteamento.yaml: falta o campo '{campo}'")
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    if not num(regras["limiar"]):
        raise ValueError("roteamento.yaml: 'limiar' deve ser um número (use ponto: 3.5)")
    if not isinstance(regras["pesos"], dict) or not all(num(v) for v in regras["pesos"].values()):
        raise ValueError("roteamento.yaml: 'pesos' deve ter só números")
    if not isinstance(regras.get("limites_texto", {}), dict) or not all(num(v) for v in (regras.get("limites_texto") or {}).values()):
        raise ValueError("roteamento.yaml: 'limites_texto' deve ter só números")
    for campo in ("palavras_dificeis", "palavras_triviais"):
        if campo in regras and not (isinstance(regras[campo], list) and all(isinstance(p, (str, int)) for p in regras[campo])):
            raise ValueError(f"roteamento.yaml: '{campo}' deve ser uma lista entre colchetes: [a, b]")
    ordem = regras["ordem"]
    if not isinstance(ordem, dict) or not all(isinstance(l, list) and all(isinstance(n, str) for n in l) for l in ordem.values()):
        raise ValueError("roteamento.yaml: 'ordem' deve ter, por grupo, uma lista de nomes entre colchetes")


def limites_validos(dados: dict, agora, validade_s: int = 120) -> tuple[set, dict | None]:
    """Esgotados e membros do logs/limites.json, só se o arquivo foi atualizado nos últimos `validade_s` segundos.

    O painel reescreve o arquivo enquanto está aberto; um arquivo velho não pode deixar provedores "esgotados" para sempre.
    """
    from datetime import datetime
    try:
        ts = datetime.fromisoformat(str(dados["ts"]))
        if (agora - ts).total_seconds() > validade_s:
            return set(), None
    except Exception:   # sem ts, ts ilegível ou sem fuso, `dados` que nem é dict: nunca derruba o roteamento
        return set(), None
    # só o que tem o formato esperado: lista de nomes e {grupo: [nomes]}; o resto é ignorado
    esg = dados.get("esgotados")
    esgotados = {n for n in esg if isinstance(n, str)} if isinstance(esg, list) else set()
    mem = dados.get("membros")
    membros = None
    if isinstance(mem, dict):
        membros = {g: [n for n in lista if isinstance(n, str)] for g, lista in mem.items() if isinstance(lista, list)}
    return esgotados, membros


def quarentena_valida(dados, agora) -> set:
    """Nomes de membros em quarentena no logs/quarentena.json cujo `ate` ainda não passou.

    Cada entrada tem validade própria (`ate`); entrada sem `ate` legível, ou arquivo malformado, é ignorada.
    """
    from datetime import datetime
    modelos = dados.get("modelos") if isinstance(dados, dict) else None
    if not isinstance(modelos, dict):
        return set()
    em_quarentena = set()
    for nome, info in modelos.items():
        try:
            if isinstance(nome, str) and datetime.fromisoformat(str(info["ate"])) > agora:
                em_quarentena.add(nome)
        except Exception:   # entrada patológica: ignora só ela
            continue
    return em_quarentena


def quarentena_membros(dados, agora, validade_s: int = 3600) -> dict | None:
    """Membros por grupo gravados no logs/quarentena.json, só se o arquivo foi escrito nos últimos `validade_s` segundos.

    Serve quando o logs/limites.json (que só o painel aberto atualiza) está velho: sem os membros reais, o fallback
    `ordem` do roteamento.yaml inclui provedores sem chave e "todos os membros fora" nunca fecha.
    """
    from datetime import datetime
    try:
        if (agora - datetime.fromisoformat(str(dados["ts"]))).total_seconds() > validade_s:
            return None
        mem = dados.get("membros")
    except Exception:   # sem ts, ts ilegível ou sem fuso, `dados` que nem é dict
        return None
    if not isinstance(mem, dict):
        return None
    return {g: [n for n in lista if isinstance(n, str)] for g, lista in mem.items() if isinstance(lista, list)}


def combinar_limites(limites, quarentena, agora) -> tuple[set, dict | None]:
    """(esgotados, membros) para `decidir`: limites.json válido + quarentena.json válida.

    Os membros do limites.json fresco têm prioridade; sem eles, valem os do quarentena.json. Nunca levanta.
    """
    try:
        esgotados, membros = limites_validos(limites, agora)
    except Exception:
        esgotados, membros = set(), None
    try:
        em_quarentena = quarentena_valida(quarentena, agora)
        if membros is None:
            membros = quarentena_membros(quarentena, agora)
    except Exception:
        em_quarentena = set()
    return esgotados | em_quarentena, membros


def gpu_ocupada_valida(dados, agora) -> bool:
    """True se logs/gpu.json indica que um job/servidor de vídeo está com o GPU lock ativo (expira_em > agora).

    Dentro do container do LiteLLM não dá para consultar o PID do host Windows, então vale o `expira_em` (em UTC).
    Qualquer arquivo ausente, vencido ou malformado devolve False e nunca derruba o roteamento.
    """
    from datetime import datetime
    if not isinstance(dados, dict):
        return False
    try:
        dono = dados.get("dono")
        if not isinstance(dono, str) or not dono.strip():
            return False
        exp = str(dados["expira_em"]).replace("Z", "+00:00")
        return datetime.fromisoformat(exp) > agora
    except Exception:
        return False


def _textos(conteudo) -> list[str]:
    if isinstance(conteudo, str):
        return [conteudo]
    if isinstance(conteudo, list):
        return [b.get("text") or "" for b in conteudo if isinstance(b, dict) and b.get("type") == "text"]
    return []


def _usuario(dados: dict) -> list[dict]:
    return [m for m in dados.get("messages") or [] if isinstance(m, dict) and m.get("role") == "user"]


def texto_usuario(dados: dict) -> str:
    return "\n".join(t for m in _usuario(dados) for t in _textos(m.get("content")))


def ultima_do_usuario(dados: dict) -> str:
    msgs = _usuario(dados)
    return "\n".join(_textos(msgs[-1].get("content"))) if msgs else ""


def _tirar_marcador(dados: dict) -> str | None:
    msgs = _usuario(dados)
    if not msgs:
        return None
    ultima = msgs[-1]
    achado = None
    conteudo = ultima.get("content")
    if isinstance(conteudo, str):
        m = _MARCADOR.search(conteudo)
        if m:
            achado = m.group(1).lower()
            ultima["content"] = _MARCADOR.sub("", conteudo, count=1).strip()
    elif isinstance(conteudo, list):
        for bloco in conteudo:
            if isinstance(bloco, dict) and bloco.get("type") == "text":
                m = _MARCADOR.search(bloco.get("text") or "")
                if m:
                    achado = m.group(1).lower()
                    bloco["text"] = _MARCADOR.sub("", bloco["text"], count=1).strip()
                    break
    return achado


def _bloco_tem_imagem(b: object) -> bool:
    if not isinstance(b, dict):
        return False
    tipo = b.get("type")
    if tipo in ("image", "image_url"):
        return True
    if tipo == "tool_result":
        sub = b.get("content")
        if isinstance(sub, list):
            return any(_bloco_tem_imagem(sb) for sb in sub)
        if isinstance(sub, dict):
            return _bloco_tem_imagem(sub)
    return False


def tem_imagem(dados: dict) -> bool:
    """Só a ÚLTIMA mensagem do usuário decide (incluindo imagens dentro de tool_result):
    imagem em turno antigo não prende a sessão na visão se o turno atual for só texto."""
    for m in reversed(dados.get("messages") or []):
        if not (isinstance(m, dict) and m.get("role") == "user"):
            continue
        conteudo = m.get("content")
        if isinstance(conteudo, list):
            return any(_bloco_tem_imagem(b) for b in conteudo)
        if isinstance(conteudo, dict):
            return _bloco_tem_imagem(conteudo)
        return False
    return False


def tem_qualquer_imagem(dados: dict) -> bool:
    """Detecta se há QUALQUER imagem no histórico completo do payload."""
    for m in dados.get("messages") or []:
        if not isinstance(m, dict):
            continue
        conteudo = m.get("content")
        if isinstance(conteudo, list) and any(_bloco_tem_imagem(b) for b in conteudo):
            return True
        if isinstance(conteudo, dict) and _bloco_tem_imagem(conteudo):
            return True
    return False


def sanitizar_imagens_historico(dados: dict, manter_atual: bool = True) -> None:
    """Substitui imagens por texto para que modelos de código puro (Nemotron) não rejeitem a requisição com erro
    de multimodalidade desabilitada. Só deve rodar quando o destino não tem visão (GRUPOS_COM_VISAO).

    manter_atual=True preserva as imagens da última mensagem do usuário (sem grupo de visão o pedido segue com ela,
    como antes); False troca também essas (sessão de agente com tools: o grupo de código não aceita imagem)."""
    msgs = dados.get("messages") or []
    if not isinstance(msgs, list) or not msgs:
        return
    ultima_user_idx = None
    for i in range(len(msgs) - 1, -1, -1):
        if isinstance(msgs[i], dict) and msgs[i].get("role") == "user":
            ultima_user_idx = i
            break
    for i, m in enumerate(msgs):
        if i == ultima_user_idx and manter_atual:
            continue
        if not isinstance(m, dict):
            continue
        conteudo = m.get("content")
        if isinstance(conteudo, list):
            novos = []
            for b in conteudo:
                if isinstance(b, dict):
                    if b.get("type") in ("image", "image_url"):
                        novos.append({"type": "text", "text": "[Imagem anterior no histórico omitida]"})
                        continue
                    if b.get("type") == "tool_result" and isinstance(b.get("content"), list):
                        sub_novos = []
                        for sb in b["content"]:
                            if isinstance(sb, dict) and sb.get("type") in ("image", "image_url"):
                                sub_novos.append({"type": "text", "text": "[Imagem anterior em ferramenta omitida]"})
                            else:
                                sub_novos.append(sb)
                        b["content"] = sub_novos
                novos.append(b)
            m["content"] = novos


def remover_cache_control(dados: dict) -> None:
    """Remove cache_control de system, mensagens e ferramentas para evitar estouro de cota (429)
    no Gemini Free Tier onde o limite de armazenamento em cache é zero."""
    sistema = dados.get("system")
    if isinstance(sistema, list):   # o Claude Code marca o system com cache_control: era o que ainda escapava
        for b in sistema:
            if isinstance(b, dict):
                b.pop("cache_control", None)
    for m in dados.get("messages") or []:
        if isinstance(m, dict):
            conteudo = m.get("content")
            if isinstance(conteudo, list):
                for b in conteudo:
                    if isinstance(b, dict) and "cache_control" in b:
                        del b["cache_control"]
    for t in dados.get("tools") or []:
        if isinstance(t, dict) and "cache_control" in t:
            del t["cache_control"]


def destinos_com_cache(cfg: dict, fallbacks: dict) -> set[str]:
    """Nomes do config que podem manter cache_control: todos os deployments PAID e sem fallback.

    Com fallback (ex.: tudoia-max → tudoia-nuvem) o router pode mandar o mesmo pedido a um grátis (Gemini Free:
    cota de cache zero, 429), e o hook não roda de novo na troca; então só os pagos pedidos pelo nome mantêm.
    """
    planos: dict[str, set] = {}
    for m in (cfg or {}).get("model_list") or []:
        if isinstance(m, dict) and m.get("model_name"):
            planos.setdefault(m["model_name"], set()).add((m.get("model_info") or {}).get("plano"))
    return {n for n, p in planos.items() if p == {"PAID"} and n not in (fallbacks or {})}


def _tamanho_total(dados: dict) -> int:
    total = sum(len(t) for t in _textos(dados.get("system")))
    for m in dados.get("messages") or []:
        if isinstance(m, dict):
            total += sum(len(t) for t in _textos(m.get("content")))
    return total


def _pontuar(dados: dict, regras: dict) -> tuple[int, list[str]]:
    pesos = regras.get("pesos") or {}
    lim = regras.get("limites_texto") or {}
    ultima = ultima_do_usuario(dados)
    norm = _norm(ultima)
    pontos, motivos = 0, []

    if len(ultima) > lim.get("caracteres", 2000) or _tamanho_total(dados) // 4 > lim.get("tokens_total", 12000):
        pontos += pesos.get("longo", 3)
        motivos.append("longo")
    tem_codigo = bool(_CODIGO.search(ultima))
    if tem_codigo:
        pontos += pesos.get("codigo", 2)
        motivos.append("codigo")
    # fronteira só no início: o termo é prefixo ("revis" casa "revisão"), mas não meio de palavra ("previsão").
    # (?<!\w) e não \b: também vale para termo que comece com símbolo. _norm já tirou os acentos.
    dificeis = sorted({p for p in regras.get("palavras_dificeis") or []
                       if re.search(rf"(?<!\w){re.escape(_norm(str(p)))}", norm)})
    if dificeis:
        pontos += pesos.get("palavras_dificeis", 2) * min(len(dificeis), 2)
        motivos.append("palavras: " + ", ".join(dificeis[:3]))
    if len(_usuario(dados)) > lim.get("turnos", 8):
        pontos += pesos.get("muitos_turnos", 1)
        motivos.append("muitos turnos")
    # "trivial" só desconta quando o pedido é SÓ trivial (sem palavra difícil e sem código)
    if not dificeis and not tem_codigo:
        triviais = [p for p in regras.get("palavras_triviais") or [] if re.search(rf"\b{re.escape(_norm(str(p)))}\b", norm)]
        if triviais:
            pontos += pesos.get("trivial", -3)
            motivos.append("trivial: " + triviais[0])
    return pontos, motivos


def normalizar(v: list[float]) -> list[float]:
    n = math.sqrt(sum(a * a for a in v)) or 1.0
    return [a / n for a in v]


def votar_knn(vetor: list[float], exemplos: list[tuple[list[float], str]], k: int = 7,
              normalizados: bool = False) -> tuple[str | None, int]:
    """Rótulo da maioria entre os k exemplos mais parecidos (cosseno) e a margem: votos do 1º − votos do 2º.

    normalizados=True: vetor e exemplos já têm norma 1 (o hook normaliza uma vez), então basta o produto escalar.
    """
    if not exemplos:
        return None, 0
    # dimensão diferente = vetores de outro modelo de embedding (cache antigo): o zip cortaria em silêncio e o
    # cosseno sairia errado. Sem voto, a decisão fica só com as regras.
    if any(len(v) != len(vetor) for v, _ in exemplos):
        return None, 0
    if not normalizados:
        vetor = normalizar(vetor)
        exemplos = [(normalizar(v), r) for v, r in exemplos]
    sims = [(sum(a * b for a, b in zip(vetor, v, strict=True)), rotulo) for v, rotulo in exemplos]
    sims.sort(key=lambda x: x[0], reverse=True)
    votos = Counter(r for _, r in sims[:k]).most_common()
    return votos[0][0], votos[0][1] - (votos[1][1] if len(votos) > 1 else 0)


def peso_semantico(rotulo: str | None, margem: int, regras: dict) -> tuple[int, str | None]:
    """Só pesa com margem >= 2: voto apertado é ruído e deixa a decisão com a heurística."""
    pesos = regras.get("pesos") or {}
    if margem >= 2 and rotulo == "nuvem":
        return pesos.get("semantico_nuvem", 3), "semântico: nuvem"
    if margem >= 2 and rotulo == "local":
        return pesos.get("semantico_local", -2), "semântico: local"
    return 0, None


def carregar_exemplos(dados: dict) -> list[tuple[str, str]]:
    """(texto, rótulo) de local + nuvem + aprendidos (mesmo formato, em dados["aprendidos"]), sem repetidos."""
    vistos, saida = set(), []
    fontes = [dados or {}, (dados or {}).get("aprendidos") or {}]
    for fonte in fontes:
        for rotulo in ("local", "nuvem"):
            for texto in fonte.get(rotulo) or []:
                if not isinstance(texto, str):
                    continue
                chave = re.sub(r"\W+", " ", _norm(texto)).strip()
                if chave and chave not in vistos:
                    vistos.add(chave)
                    saida.append((texto, rotulo))
    return saida


def precisa_pontuar(dados: dict, grupos_existentes: set[str] | None = None) -> bool:
    """True se `decidir` vai cair no ramo de pontuação. Não altera `dados` (o hook só embute se for pesar)."""
    existentes = grupos_existentes or set()
    achado = _MARCADOR.search(ultima_do_usuario(dados))
    marcador = achado.group(1).lower() if achado else None
    if marcador in ("local", "nuvem") or (marcador == "max" and MAXIMO in existentes):
        return False
    if tem_imagem(dados) and VISAO in existentes:
        return False
    return not dados.get("tools")


def decidir(dados: dict, regras: dict, esgotados=frozenset(), membros: dict | None = None,
            grupos_existentes: set[str] | None = None, vetor=None, exemplos=None, normalizados: bool = False,
            gpu_ocupada: bool = False) -> Decisao:
    """Decide o grupo. Remove #local/#nuvem/#max do texto (altera `dados`).

    membros: membros reais de cada grupo (da config gerada); sem ele, usa regras["ordem"].
    esgotados: nomes de modelo cujo provedor estourou o limite (o painel grava em logs/limites.json).
    grupos_existentes: grupos presentes no config do LiteLLM; None = não sei, e então #max e visão são ignorados.
    vetor, exemplos: embedding do pedido e [(vetor, rótulo)]; o kNN soma peso só no ramo de pontuação.
    gpu_ocupada: True quando logs/gpu.json indica job de vídeo ativo; desvia tudoia-local para tudoia-nuvem (salvo #local).
    """
    marcador = _tirar_marcador(dados)
    existentes = grupos_existentes or set()
    extra: list[str] = []
    d = None
    if marcador == "local":
        return Decisao(LOCAL, motivos=["marcador #local"], marcador="local")
    if marcador == "nuvem":
        d = Decisao(NUVEM, motivos=["marcador #nuvem"], marcador="nuvem")
    elif marcador == "max":
        if MAXIMO in existentes:
            return Decisao(MAXIMO, motivos=["marcador #max"], marcador="max")
        extra.append("#max sem grupo")   # nunca manda para grupo inexistente: segue a regra normal
    if d is None:
        imagem = tem_imagem(dados)
        if imagem and VISAO not in existentes:
            extra.append("imagem sem grupo visao")   # segue as regras normais
        # tools vence imagem: screenshot em tool_result não pode tirar a sessão de agente do grupo de código (os
        # membros da visão podem não aceitar ferramentas). O hook troca a imagem por texto; para ver a imagem com
        # ferramentas, #max (pago, com visão).
        if dados.get("tools"):
            d = Decisao(CODIGO, motivos=["ferramentas"] + (["imagem com ferramentas"] if imagem else []))
        elif imagem and VISAO in existentes:
            d = Decisao(VISAO, motivos=["imagem"])
        else:
            pontos, motivos = _pontuar(dados, regras)
            if vetor and exemplos:
                peso, motivo = peso_semantico(*votar_knn(vetor, exemplos, normalizados=normalizados), regras)
                if motivo:
                    pontos += peso
                    motivos.append(motivo)
            grupo = NUVEM if pontos >= regras.get("limiar", 3) else LOCAL
            d = Decisao(grupo, pontos, motivos)
        d.motivos += extra
        d.marcador = marcador

    if gpu_ocupada and d.grupo == LOCAL:
        lista_nuvem = (membros or regras.get("ordem") or {}).get(NUVEM) or []
        if not (esgotados and lista_nuvem and all(m in esgotados for m in lista_nuvem)):
            d.grupo = NUVEM
            d.motivos.append("gpu ocupada")

    if d.grupo in (NUVEM, CODIGO) and esgotados and not gpu_ocupada:
        lista = (membros or regras.get("ordem") or {}).get(d.grupo) or []
        if lista and all(m in esgotados for m in lista):
            d.grupo = LOCAL if d.grupo == NUVEM else LOCAL_AGENTE
            d.motivos.append("provedores esgotados")
    return d

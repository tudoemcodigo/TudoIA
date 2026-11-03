"""
Driver dos evals: conduz UMA tarefa da SquadTI de ponta a ponta usando só a API HTTP local (stdlib), coleta os arquivos de relatório
e roda os verificadores.

MODO EVAL: o driver aprova sozinho a especificação e o release. Isso é uma aprovação automática de TESTE (nenhum humano revisou) e
fica registrada em cada resultado (`modo_eval`, `aprovacoes_automaticas`). Nunca use este driver para entregar algo de verdade.

Fronteiras: o token vem do ambiente (nunca de argumento) e é removido de tudo que o driver escreve ou levanta como erro; só
loopback; todo pedido HTTP tem prazo; GET é repetido em falha transitória e POST nunca (uma resposta enviada duas vezes seria
outra resposta); a tarefa inteira tem um prazo global.
"""
import http.client
import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote, urlparse

from . import verificadores

RE_CASO = re.compile(r"^[a-z0-9][a-z0-9-]{0,19}$")
HOSTS_LOOPBACK = ("127.0.0.1", "localhost")
MAX_RESPOSTA = 5_000_000
MAX_ARQUIVOS_COLETADOS = 400
MAX_FALHAS_SEGUIDAS = 5
TERMINAIS_RUINS = ("bloqueada", "escalada", "escalada_qa", "escalada_revisao")
COLETA_FIXA = (
    *(verificadores.RELATORIOS + n for n in (*verificadores.PORTOES_COM_APROVADO, *verificadores.PORTOES_DE_EXECUCAO)),
    *(c for candidatos in verificadores.OBRIGATORIOS.values() for c in candidatos),
    "docs/revisao/REVISAO.md",
)
RESPOSTA_DE_REFORCO = ("Não há informação nova além do briefing e das respostas anteriores. Adote o padrão da Doutrina TEC para "
                       "o que faltar, registre a suposição na especificação e prossiga.")


class ErroCaso(Exception):
    """Caso dourado malformado."""


class ErroApi(Exception):
    """Falha ao falar com a API. `status` é 0 quando não houve resposta HTTP. A mensagem nunca traz o token."""

    def __init__(self, status: int, mensagem: str):
        super().__init__(mensagem)
        self.status, self.mensagem = status, mensagem


# ---------------------------------------------------------------- casos
def validar_caso(caso: Any) -> dict:
    if not isinstance(caso, dict):
        raise ErroCaso("o caso deve ser um objeto JSON")
    if not isinstance(caso.get("id"), str) or not RE_CASO.match(caso["id"]):
        raise ErroCaso("id do caso inválido (minúsculas, números e '-', até 20 caracteres)")
    cid = caso["id"]
    briefing = caso.get("briefing")
    if not isinstance(briefing, str) or not briefing.strip() or len(briefing) > 20_000:
        raise ErroCaso(f"{cid}: briefing obrigatório, de até 20000 caracteres")
    respostas = caso.get("respostas_da_entrevista")
    if (not isinstance(respostas, list) or not respostas or not all(isinstance(r, str) and r.strip() for r in respostas)
            or len(resposta_da_entrevista(respostas)) > 20_000):
        raise ErroCaso(f"{cid}: respostas_da_entrevista deve ser lista de textos não vazios que juntos cabem em 20000 caracteres")
    if caso.get("stack") != "python":
        raise ErroCaso(f"{cid}: os casos dourados usam a stack fixa 'python'")
    lim = caso.get("limites")
    if (not isinstance(lim, dict) or any(isinstance(lim.get(k), bool) or not isinstance(lim.get(k), int) or lim[k] <= 0
                                         for k in ("tokens", "tempo_s"))):
        raise ErroCaso(f"{cid}: limites.tokens e limites.tempo_s devem ser inteiros positivos")
    if caso.get("orcamento") is not None and not isinstance(caso["orcamento"], dict):
        raise ErroCaso(f"{cid}: orcamento deve ser um objeto")
    t = caso.get("timeout_s")
    if t is not None and (isinstance(t, bool) or not isinstance(t, (int, float)) or t <= 0):
        raise ErroCaso(f"{cid}: timeout_s deve ser positivo")
    extras = caso.get("verificadores_extra", [])
    if not isinstance(extras, list) or not all(isinstance(e, dict) and e.get("tipo") in verificadores.TIPOS_DO_CASO for e in extras):
        raise ErroCaso(f"{cid}: verificadores_extra com tipo desconhecido (use {sorted(verificadores.TIPOS_DO_CASO)})")
    return caso


def carregar_casos(pasta: Path, ids: Optional[List[str]] = None) -> List[dict]:
    casos = []
    for arq in sorted(Path(pasta).glob("*.json")):
        try:
            casos.append(validar_caso(json.loads(arq.read_text(encoding="utf-8"))))
        except ValueError as e:
            raise ErroCaso(f"{arq.name}: JSON inválido") from e
    repetidos = {c["id"] for c in casos if sum(1 for o in casos if o["id"] == c["id"]) > 1}
    if repetidos:
        raise ErroCaso(f"ids de caso repetidos: {sorted(repetidos)}")
    if ids:
        faltam = sorted(set(ids) - {c["id"] for c in casos})
        if faltam:
            raise ErroCaso(f"caso(s) inexistente(s): {faltam}; disponíveis: {[c['id'] for c in casos]}")
        casos = [c for c in casos if c["id"] in ids]
    if not casos:
        raise ErroCaso(f"nenhum caso em {pasta}")
    return casos


def resposta_da_entrevista(respostas: List[str]) -> str:
    return "Respostas da entrevista (fixas do caso de teste):\n" + "\n".join(f"{i}. {r.strip()}" for i, r in enumerate(respostas, 1))


# ---------------------------------------------------------------- HTTP
class Cliente:
    """Cliente mínimo da API da SquadTI. Uma conexão por pedido (a API fecha após cada resposta), sempre com prazo."""

    def __init__(self, url: str, token: str, timeout_s: float = 30.0, tentativas: int = 3, espera_s: float = 0.5):
        partes = urlparse(url)
        if partes.scheme != "http" or partes.hostname not in HOSTS_LOOPBACK or partes.path not in ("", "/") or partes.port is None:
            raise ErroCaso("URL da API deve ser http://127.0.0.1:<porta> ou http://localhost:<porta> (a API é só de loopback)")
        if not token:
            raise ErroCaso("token ausente (defina TUDOIA_SQUADTI_TOKEN no ambiente)")
        self.host, self.porta = partes.hostname, partes.port
        self._token, self.timeout_s, self.tentativas, self.espera_s = token, timeout_s, max(1, tentativas), espera_s

    def limpar(self, texto: Any) -> str:
        return str(texto).replace(self._token, "***")

    def _uma_vez(self, metodo: str, caminho: str, corpo: Optional[dict]) -> Tuple[int, Any]:
        dados = None if corpo is None else json.dumps(corpo, ensure_ascii=False).encode("utf-8")
        cab = {"Authorization": f"Bearer {self._token}", "Accept": "application/json"}
        if dados is not None:
            cab["Content-Type"] = "application/json"
        conn = http.client.HTTPConnection(self.host, self.porta, timeout=self.timeout_s)
        try:
            conn.request(metodo, caminho, body=dados, headers=cab)
            resp = conn.getresponse()
            bruto = resp.read(MAX_RESPOSTA + 1)
            status = resp.status
        finally:
            conn.close()
        if len(bruto) > MAX_RESPOSTA:
            raise ErroApi(status, "resposta da API grande demais")
        try:
            return status, json.loads(bruto or b"{}")
        except ValueError:
            raise ErroApi(status, f"resposta da API não é JSON (HTTP {status})") from None

    def requisitar(self, metodo: str, caminho: str, corpo: Optional[dict] = None) -> dict:
        """JSON da resposta. GET repete em 5xx e falha de rede; POST não repete. Levanta ErroApi com status e mensagem sem o token."""
        tentativas = self.tentativas if metodo == "GET" else 1
        ultimo: Optional[ErroApi] = None
        for i in range(tentativas):
            if i:
                time.sleep(self.espera_s * (2 ** (i - 1)))
            try:
                status, dado = self._uma_vez(metodo, caminho, corpo)
            except ErroApi as e:
                ultimo = ErroApi(e.status, self.limpar(e.mensagem))
                if e.status < 500:
                    break
                continue
            except (OSError, http.client.HTTPException) as e:  # inclui timeout e conexão recusada
                ultimo = ErroApi(0, f"falha de rede: {type(e).__name__}")
                continue
            if status >= 500:
                ultimo = ErroApi(status, f"a API respondeu HTTP {status}")
                continue
            if status >= 400:
                erro = dado.get("erro") if isinstance(dado, dict) and isinstance(dado.get("erro"), dict) else {}
                raise ErroApi(status, self.limpar(f"HTTP {status} {erro.get('codigo', '')}: {str(erro.get('mensagem', ''))[:300]}").strip())
            if not isinstance(dado, dict):
                raise ErroApi(status, "resposta da API não é um objeto JSON")
            return dado
        raise ultimo or ErroApi(0, "falha desconhecida")


# ---------------------------------------------------------------- coleta
def _gravar(raiz: Path, rel: str, texto: str, token: str) -> bool:
    try:
        destino = verificadores._seguro(raiz, rel)  # '..', caminho absoluto e link que escapa são recusados
    except verificadores.EntradaInvalida:
        return False
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto.replace(token, "***"), encoding="utf-8")
    return True


def coletar_workspace(cliente: Cliente, tarefa: str, detalhe: dict, raiz: Path) -> dict:
    """Copia para `raiz` os arquivos fixos de relatório/documentação e tudo que a API lista em `arquivos`, via /arquivo."""
    raiz.mkdir(parents=True, exist_ok=True)
    listados = [a for a in (detalhe.get("arquivos") or []) if isinstance(a, str)]
    alvo = list(dict.fromkeys([*COLETA_FIXA, *listados]))[:MAX_ARQUIVOS_COLETADOS]
    gravados = recusados = falhas = seguidas = 0
    for rel in alvo:
        if seguidas >= MAX_FALHAS_SEGUIDAS:
            break
        try:
            r = cliente.requisitar("GET", f"/api/tarefas/{quote(tarefa)}/arquivo?caminho={quote(rel, safe='/')}")
        except ErroApi as e:
            if e.status in (404, 415, 422):  # ausente, binário ou caminho recusado pela API: esperado para parte da lista
                seguidas = 0
                continue
            falhas += 1
            seguidas += 1
            continue
        seguidas = 0
        conteudo = r.get("conteudo")
        if not isinstance(conteudo, str):
            continue
        if _gravar(raiz, rel, conteudo, cliente._token):
            gravados += 1
        else:
            recusados += 1
    return {"gravados": gravados, "recusados": recusados, "falhas_de_rede": falhas}


# ---------------------------------------------------------------- tarefa
def id_da_tarefa(rodada: str, caso_id: str, n: int) -> str:
    return f"ev-{rodada}-{caso_id}-{n}"[:64]


def _nos_lentos(auditoria: dict, limite: int = 5) -> List[dict]:
    nos = [n for n in auditoria.get("nos") or [] if isinstance(n, dict) and isinstance(n.get("duracao_s"), (int, float))]
    return [{"no": n.get("no"), "duracao_s": round(float(n["duracao_s"]), 1)}
            for n in sorted(nos, key=lambda n: -float(n["duracao_s"]))[:limite]]


def executar_caso(cliente: Cliente, caso: dict, n: int, rodada: str, destino: Path, *, intervalo_s: float = 2.0,
                  timeout_s: Optional[float] = None, espera_inicial_s: float = 600.0, max_rodadas_entrevista: int = 3) -> dict:
    """Conduz o caso `n` até um desfecho e devolve o resultado (já com os verificadores). Nunca aprova nada além do que o fluxo pede."""
    tarefa = id_da_tarefa(rodada, caso["id"], n)
    prazo_s = float(timeout_s or caso.get("timeout_s") or caso["limites"]["tempo_s"] * 1.5)
    inicio = time.monotonic()
    prazo = inicio + prazo_s
    aprovacoes: List[dict] = []
    contagem = {"responder": 0, "aprovar": 0, "aprovar-release": 0}
    desfecho, motivo, detalhe = "indefinido", "", None

    def acao(nome: str, corpo: Optional[dict] = None) -> None:
        cliente.requisitar("POST", f"/api/tarefas/{quote(tarefa)}/{nome}", corpo)

    try:
        corpo = {"tarefa": tarefa, "briefing": caso["briefing"], "perfil": caso.get("perfil", "auto"), "consentimento_nuvem": True,
                 "stack": caso["stack"]}
        if caso.get("orcamento"):
            corpo["orcamento"] = caso["orcamento"]
        while True:  # 409 = a Squad está ocupada com outra tarefa: espera a vez dentro do prazo
            try:
                cliente.requisitar("POST", "/api/tarefas", corpo)
                break
            except ErroApi as e:
                if e.status != 409 or "ocupado" not in e.mensagem or time.monotonic() > prazo:
                    raise
                time.sleep(intervalo_s)
        visto_ate = time.monotonic() + espera_inicial_s  # a tarefa só existe após o primeiro checkpoint
        while True:
            if time.monotonic() > prazo:
                desfecho, motivo = "timeout", f"prazo de {int(prazo_s)}s esgotado"
                break
            try:
                detalhe = cliente.requisitar("GET", f"/api/tarefas/{quote(tarefa)}")
            except ErroApi as e:
                if e.status == 404 and time.monotonic() < min(visto_ate, prazo):
                    time.sleep(intervalo_s)
                    continue
                raise
            exe = detalhe.get("execucao") if isinstance(detalhe.get("execucao"), dict) else None
            sit = detalhe.get("situacao") if isinstance(detalhe.get("situacao"), dict) else {}
            estado = sit.get("estado")
            if exe and exe.get("estado") == "rodando":
                time.sleep(intervalo_s)
                continue
            if exe and exe.get("estado") == "erro":
                desfecho, motivo = "erro_de_execucao", cliente.limpar(exe.get("erro") or "erro sem detalhe")
                break
            if estado == "concluida":
                desfecho = "concluida"
                break
            if estado in TERMINAIS_RUINS:
                desfecho, motivo = "escalada", cliente.limpar(f"{estado}: {sit.get('mensagem') or ''}")[:500]
                break
            if estado == "aguardando_respostas":
                if contagem["responder"] >= max_rodadas_entrevista:
                    desfecho, motivo = "entrevista_nao_convergiu", f"o analista seguiu perguntando após {contagem['responder']} respostas"
                    break
                texto = resposta_da_entrevista(caso["respostas_da_entrevista"]) if contagem["responder"] == 0 else RESPOSTA_DE_REFORCO
                contagem["responder"] += 1
                acao("responder", {"resposta": texto})
            elif estado in ("aguardando_aprovacao_spec", "aguardando_aprovacao_release"):
                rota = "aprovar" if estado == "aguardando_aprovacao_spec" else "aprovar-release"
                if contagem[rota] >= 2:
                    desfecho, motivo = "aprovacao_em_loop", f"a tarefa voltou a {estado} depois de {contagem[rota]} aprovações"
                    break
                contagem[rota] += 1
                aprovacoes.append({"etapa": estado, "em": time.strftime("%Y-%m-%dT%H:%M:%S"), "automatica_de_teste": True})
                acao(rota)
            else:  # em_fase / inexistente sem execução rodando: ninguém está tocando a tarefa
                desfecho, motivo = "estado_inesperado", cliente.limpar(f"estado {estado!r} sem execução em andamento")
                break
    except ErroApi as e:
        desfecho, motivo = "erro_de_api", e.mensagem
    duracao = round(time.monotonic() - inicio, 1)

    resultado: Dict[str, Any] = {
        "caso": caso["id"], "n": n, "tarefa": tarefa, "rodada": rodada, "modo_eval": True,
        "aprovacoes_automaticas": aprovacoes, "desfecho": desfecho, "motivo": motivo, "duracao_s": duracao,
        "perfil": caso.get("perfil", "auto"), "limites": caso["limites"],
    }
    api: Dict[str, Any] = {"detalhe": detalhe or {}, "duracao_s": duracao}
    if detalhe:
        for chave, rota in (("auditoria", "auditoria"), ("mensagens", "mensagens")):
            try:
                api[chave] = cliente.requisitar("GET", f"/api/tarefas/{quote(tarefa)}/{rota}")
            except ErroApi as e:
                api[chave] = {}
                resultado.setdefault("avisos", []).append(f"{rota} indisponível: {e.mensagem}")
        ws = destino / "workspace"
        resultado["coleta"] = coletar_workspace(cliente, tarefa, detalhe, ws)
        resultado["verificadores"] = verificadores.executar(ws, api, caso)
        resultado["doutrina"] = detalhe.get("doutrina")
        resultado["estado_final"] = (detalhe.get("situacao") or {}).get("estado")
    else:
        resultado["verificadores"] = [{"nome": "execucao", "passou": False, "detalhe": motivo or "a tarefa não chegou a existir"}]
    totais = (api.get("auditoria") or {}).get("totais") or {}
    resultado["tokens"] = totais.get("tokens")
    resultado["tempo_modelo_s"] = totais.get("tempo_s")
    resultado["nos_lentos"] = _nos_lentos(api.get("auditoria") or {})
    resultado["passou"] = desfecho == "concluida" and all(v["passou"] for v in resultado["verificadores"])
    return resultado

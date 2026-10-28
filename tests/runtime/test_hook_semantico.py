"""Hook roteador.py (classificador semântico): importa o módulo com um litellm de mentira, como o container faz."""
import asyncio
import hashlib
import importlib.util
import json
import pathlib
import sys
import time
import types

import pytest

from tudoia_painel import caminhos

LIT = caminhos.raiz() / "runtime/litellm"


def _carregar():
    class CustomLogger:
        pass

    for nome in ("litellm", "litellm.integrations", "litellm.integrations.custom_logger"):
        sys.modules.setdefault(nome, types.ModuleType(nome))
    sys.modules["litellm.integrations.custom_logger"].CustomLogger = CustomLogger
    if str(LIT) not in sys.path:
        sys.path.insert(0, str(LIT))
    spec = importlib.util.spec_from_file_location("roteador_hook_teste", LIT / "roteador.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


H = _carregar()


class _ClienteLento:
    """Faz o papel do httpx.AsyncClient com um Ollama que demora 5 s."""
    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, *a, **k):
        await asyncio.sleep(5)


class _ClienteOk(_ClienteLento):
    async def post(self, url, json=None, **k):
        self.url, self.json = url, json
        return types.SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"embeddings": [[1.0, 0.0]] * len(json["input"])})


@pytest.fixture
def hook(tmp_path, monkeypatch):
    monkeypatch.setattr(H, "DIR_LOGS", str(tmp_path))
    monkeypatch.setattr(H, "ARQ_EVENTOS", str(tmp_path / "eventos.jsonl"))
    monkeypatch.setattr(H, "ARQ_REGRAS", str(caminhos.raiz() / "config/roteamento.yaml"))
    monkeypatch.setattr(H.Roteador, "_ler_config", staticmethod(lambda: {"model_list": [{"model_name": "tudoia-local"}, {"model_name": "tudoia-nuvem"}]}))
    r = H.Roteador()
    r._saude_ok, r._saude_em = True, float("inf")   # Ollama "no ar" sem rede: a checagem real tem testes próprios
    return r


def _ultima_linha(caminho, s=5.0):
    """O Gravador grava em outra thread: espera a linha aparecer."""
    fim = time.time() + s
    while time.time() < fim:
        if caminho.exists() and caminho.read_text(encoding="utf-8").strip():
            return json.loads(caminho.read_text(encoding="utf-8").splitlines()[-1])
        time.sleep(0.02)
    raise AssertionError(f"{caminho.name} não foi gravado")


def test_vetor_timeout_devolve_none_rapido(hook, monkeypatch):
    monkeypatch.setattr(H.httpx, "AsyncClient", _ClienteLento)
    t0 = time.monotonic()
    assert asyncio.run(hook._vetor("oi")) is None
    assert time.monotonic() - t0 < 2


def test_pre_call_com_ollama_lento_completa_com_motivo(hook, monkeypatch):
    monkeypatch.setattr(H.httpx, "AsyncClient", _ClienteLento)
    hook._pronto = [([1.0, 0.0], "nuvem")] * 7   # exemplos já calculados: só o pedido espera o Ollama
    hook._exemplos = lambda: hook._pronto
    dados = {"model": "tudoia-auto", "messages": [{"role": "user", "content": "mostre que raiz de 2 é irracional"}]}
    t0 = time.monotonic()
    r = asyncio.run(hook.async_pre_call_hook({}, None, dados, "completion"))
    assert time.monotonic() - t0 < 2
    assert r["model"] == "tudoia-local"
    linha = _ultima_linha(pathlib.Path(H.DIR_LOGS) / "roteador.jsonl")
    assert "semantico_indisponivel" in linha["motivos"]


def test_vetor_envia_cpu_e_keep_alive(hook, monkeypatch):
    cli = _ClienteOk()
    monkeypatch.setattr(H.httpx, "AsyncClient", lambda *a, **k: cli)
    monkeypatch.setattr(H, "OLLAMA_URL", "http://ollama:11434")
    assert asyncio.run(hook._vetor("oi")) == [1.0, 0.0]
    assert cli.url == "http://ollama:11434/api/embed"
    assert cli.json["model"] == "bge-m3" and cli.json["options"] == {"num_gpu": 0} and cli.json["keep_alive"] == "30m"


def test_semantico_nao_roda_com_marcador_ou_sem_exemplos(hook, monkeypatch):
    chamadas = []

    async def vetor(texto):
        chamadas.append(texto)
        return [1.0, 0.0]

    hook._vetor = vetor
    hook._exemplos = lambda: [([1.0, 0.0], "nuvem")] * 7
    asyncio.run(hook.async_pre_call_hook({}, None, {"model": "tudoia-auto", "messages": [{"role": "user", "content": "#local oi"}]}, "completion"))
    assert chamadas == []
    hook._exemplos = lambda: None
    asyncio.run(hook.async_pre_call_hook({}, None, {"model": "tudoia-auto", "messages": [{"role": "user", "content": "oi"}]}, "completion"))
    assert chamadas == []
    hook._exemplos = lambda: [([1.0, 0.0], "nuvem")] * 7
    r = asyncio.run(hook.async_pre_call_hook({}, None, {"model": "tudoia-auto", "messages": [{"role": "user", "content": "mostre isto"}]}, "completion"))
    assert chamadas == ["mostre isto"] and r["model"] == "tudoia-nuvem"


def test_exemplos_calcula_cache_em_segundo_plano(hook, tmp_path, monkeypatch):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / "exemplos-roteamento.yaml").write_text('local: ["oi"]\nnuvem: ["prova longa"]\n', encoding="utf-8")
    monkeypatch.setattr(H, "ARQ_EXEMPLOS", str(cfg / "exemplos-roteamento.yaml"))
    monkeypatch.setattr(H, "ARQ_APRENDIDOS", str(cfg / "exemplos-aprendidos.yaml"))   # não existe: tudo bem
    monkeypatch.setattr(H, "ARQ_VETORES", str(tmp_path / "exemplos-vetores.json"))
    monkeypatch.setattr(H.httpx, "AsyncClient", _ClienteOk)

    async def cenario():
        assert hook._exemplos() is None          # primeira leitura: ainda calculando, o pedido não espera
        for _ in range(50):
            await asyncio.sleep(0.05)
            if hook._exemplos():
                break
        return hook._exemplos()

    ex = asyncio.run(cenario())
    assert sorted(r for _, r in ex) == ["local", "nuvem"]
    assert (tmp_path / "exemplos-vetores.json").exists()


def test_timeouts_repetidos_agendam_um_so_aquecimento(hook, monkeypatch):
    monkeypatch.setattr(H.httpx, "AsyncClient", _ClienteLento)
    monkeypatch.setattr(H, "LIMITE_EMBED_S", 0.05)
    iniciados = []
    original = hook._aquecer_embed

    async def contado():
        iniciados.append(1)
        await original()

    hook._aquecer_embed = contado

    async def cenario():
        for _ in range(4):
            assert await hook._vetor("oi") is None
        await asyncio.sleep(0.05)

    asyncio.run(cenario())
    assert len(iniciados) == 1


def test_troca_de_arquivo_mantem_exemplos_antigos_ate_o_novo_ficar_pronto(hook, tmp_path, monkeypatch):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    arq = cfg / "exemplos-roteamento.yaml"
    arq.write_text('local: ["oi"]\nnuvem: ["prova"]\n', encoding="utf-8")
    monkeypatch.setattr(H, "ARQ_EXEMPLOS", str(arq))
    monkeypatch.setattr(H, "ARQ_APRENDIDOS", str(cfg / "nao-existe.yaml"))
    monkeypatch.setattr(H, "ARQ_VETORES", str(tmp_path / "v.json"))
    monkeypatch.setattr(H.httpx, "AsyncClient", _ClienteOk)

    async def cenario():
        hook._exemplos()
        for _ in range(50):
            await asyncio.sleep(0.05)
            if hook._exemplos():
                break
        antigo = hook._exemplos()
        assert antigo
        arq.write_text('local: ["oi", "tchau"]\nnuvem: ["prova"]\n', encoding="utf-8")
        import os
        os.utime(arq, (time.time() + 5, time.time() + 5))
        assert hook._exemplos() == antigo      # nova lista ainda sendo calculada: segue com a antiga
        for _ in range(50):
            await asyncio.sleep(0.05)
            if len(hook._exemplos()) == 3:
                break
        return hook._exemplos()

    assert len(asyncio.run(cenario())) == 3


def test_calculo_que_falhou_e_repetido_mesmo_com_lista_antiga(hook, tmp_path, monkeypatch):
    import os
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    arq = cfg / "exemplos-roteamento.yaml"
    arq.write_text('local: ["oi"]\nnuvem: ["prova"]\n', encoding="utf-8")
    monkeypatch.setattr(H, "ARQ_EXEMPLOS", str(arq))
    monkeypatch.setattr(H, "ARQ_APRENDIDOS", str(cfg / "nao-existe.yaml"))
    monkeypatch.setattr(H, "ARQ_VETORES", str(tmp_path / "v.json"))
    monkeypatch.setattr(H.httpx, "AsyncClient", _ClienteOk)

    async def espera(cond):
        for _ in range(60):
            await asyncio.sleep(0.05)
            if cond():
                return

    async def cenario():
        hook._exemplos()
        await espera(lambda: hook._exemplos())
        antigo = hook._exemplos()
        class _Fora(_ClienteLento):
            async def post(self, *a, **k):
                raise OSError("Ollama fora")
        monkeypatch.setattr(H.httpx, "AsyncClient", _Fora)
        arq.write_text('local: ["oi", "tchau"]\nnuvem: ["prova"]\n', encoding="utf-8")
        os.utime(arq, (time.time() + 5, time.time() + 5))
        hook._exemplos()
        await espera(lambda: hook._retomar_em)
        assert hook._retomar_em and hook._exemplos() == antigo   # falhou: segue com a lista antiga
        monkeypatch.setattr(H.httpx, "AsyncClient", _ClienteOk)
        relogio = time.monotonic()
        monkeypatch.setattr(H, "time", types.SimpleNamespace(monotonic=lambda: relogio + 120))   # passou o prazo de nova tentativa
        hook._exemplos()                                                   # reinicia o cálculo
        await espera(lambda: len(hook._exemplos()) == 3)
        return hook._exemplos()

    assert len(asyncio.run(cenario())) == 3


# ── resposta do /v1/messages segurada e refeita quando o provedor trava no meio ─────────────────────────
CFG_CODIGO = {
    "model_list": [
        {"model_name": "tudoia-codigo", "model_info": {"membro": "nim/glm-5.3"}},
        {"model_name": "tudoia-codigo", "model_info": {"membro": "nim/nemotron-3-ultra"}},
        {"model_name": "nim/glm-5.3"}, {"model_name": "nim/nemotron-3-ultra"}, {"model_name": "tudoia-local-agente"},
    ],
    "router_settings": {"fallbacks": [{"tudoia-codigo": ["tudoia-local-agente"]}]},
}


async def _sse(*itens):
    for i in itens:
        yield i


def _rodar_stream(hook, url, stream=True):
    dados = {"model": "tudoia-codigo", "stream": stream, "litellm_call_id": "c1",
             "proxy_server_request": {"url": url}, "metadata": {"a": 1}}
    asyncio.run(hook.async_pre_call_deployment_hook(
        {"litellm_call_id": "c1", "model": "x", "model_info": {"membro": "nim/nemotron-3-ultra"}}, "anthropic_messages"))
    primeiro = _sse(b"event: message_start\n\n", b"event: content_block_delta\n\n", b"event: error\ndata: {}\n\n")

    async def tudo():
        return [x async for x in hook.async_post_call_streaming_iterator_hook(None, primeiro, dados)]
    return asyncio.run(tudo())


def test_messages_travado_no_meio_refaz_em_outro_membro(tmp_path, monkeypatch):
    monkeypatch.setattr(H, "DIR_LOGS", str(tmp_path))
    monkeypatch.setattr(H.Roteador, "_ler_config", staticmethod(lambda: CFG_CODIGO))
    hook = H.Roteador()
    pedidos = []

    async def refazer(request_data, alvo):
        pedidos.append(alvo)
        return _sse(b"event: message_start\n\n", b"event: message_stop\n\n")

    monkeypatch.setattr(H.Roteador, "_refazer", staticmethod(refazer))
    saida = [x for x in _rodar_stream(hook, "http://litellm:4000/v1/messages?beta=true") if b"ping" not in x]
    assert saida == [b"event: message_start\n\n", b"event: message_stop\n\n"]
    assert pedidos == ["nim/glm-5.3"]   # o membro que travou fica de fora


def test_chat_completions_continua_em_streaming_direto(tmp_path, monkeypatch):
    # Open WebUI/n8n veem o texto chegando; só o Claude Code (/v1/messages) espera a resposta inteira
    monkeypatch.setattr(H, "DIR_LOGS", str(tmp_path))
    monkeypatch.setattr(H.Roteador, "_ler_config", staticmethod(lambda: CFG_CODIGO))
    hook = H.Roteador()
    monkeypatch.setattr(H.Roteador, "_refazer", staticmethod(lambda *a: pytest.fail("não devia refazer")))
    assert len(_rodar_stream(hook, "http://litellm:4000/v1/chat/completions")) == 3
    assert len(_rodar_stream(hook, "http://litellm:4000/v1/messages", stream=False)) == 3


# ── M1: limites() nunca derruba o roteamento, nem com JSON patológico ─────────────

@pytest.mark.parametrize("conteudo", ["[" * 200000, '{"ts": "x", "esgotados": 5}', '{"ts": 1}', "\x00", "[]"],
                         ids=["aninhado-demais", "esgotados-int", "ts-numero", "binario", "lista"])
def test_limites_com_json_patologico_nao_quebra(tmp_path, monkeypatch, conteudo):
    monkeypatch.setattr(H, "DIR_LOGS", str(tmp_path))
    (tmp_path / "limites.json").write_text(conteudo, encoding="utf-8")
    (tmp_path / "quarentena.json").write_text(conteudo, encoding="utf-8")
    esgotados, membros = H.Roteador.limites()
    assert esgotados == set() and membros is None


# ── imagens e cache_control conforme o destino final ──────────────────────────────
IMG = {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "AAAA"}}
CACHE = {"type": "ephemeral"}
CFG_GRUPOS = {
    "model_list": [{"model_name": g, "model_info": {"plano": "FREE"}} for g in
                   ("tudoia-local", "tudoia-nuvem", "tudoia-codigo", "tudoia-visao", "tudoia-local-agente")]
    + [{"model_name": "tudoia-max", "model_info": {"plano": "PAID", "membro": "claude-sonnet-5-5"}},
       {"model_name": "claude-sonnet-5-5", "model_info": {"plano": "PAID"}}],
    "router_settings": {"fallbacks": [{"tudoia-max": ["tudoia-nuvem"]}]},
}


@pytest.fixture
def hook_grupos(tmp_path, monkeypatch):
    monkeypatch.setattr(H, "DIR_LOGS", str(tmp_path))
    monkeypatch.setattr(H, "ARQ_EVENTOS", str(tmp_path / "eventos.jsonl"))
    monkeypatch.setattr(H, "ARQ_REGRAS", str(caminhos.raiz() / "config/roteamento.yaml"))
    monkeypatch.setattr(H.Roteador, "_ler_config", staticmethod(lambda: CFG_GRUPOS))
    r = H.Roteador()
    r._saude_ok, r._saude_em = True, float("inf")
    r._exemplos = lambda: None
    return r


def _pre(hook, dados):
    return asyncio.run(hook.async_pre_call_hook({}, None, dados, "anthropic_messages"))


def _historico(modelo, ultima="e agora?", **extra):
    return dict({"model": modelo, "messages": [
        {"role": "user", "content": [IMG, {"type": "text", "text": "veja"}]},
        {"role": "assistant", "content": "vi"},
        {"role": "user", "content": ultima}]}, **extra)


@pytest.mark.parametrize("modelo,texto", [("tudoia-visao", "e agora?"), ("tudoia-max", "e agora?"),
                                          ("tudoia-auto", "#max e agora?")])
def test_destino_com_visao_mantem_imagens_do_historico(hook_grupos, modelo, texto):
    r = _pre(hook_grupos, _historico(modelo, texto))
    assert r["model"] in ("tudoia-visao", "tudoia-max")
    assert r["messages"][0]["content"][0] == IMG   # antes: trocada por texto mesmo com destino de visão


def test_destino_sem_visao_ainda_tira_imagens_do_historico(hook_grupos):
    r = _pre(hook_grupos, _historico("tudoia-auto", "oi"))
    assert r["model"] == "tudoia-local" and r["messages"][0]["content"][0]["type"] == "text"


def test_agente_com_screenshot_em_tool_result_fica_no_codigo_sem_imagem(hook_grupos):
    for modelo in ("tudoia-auto", "tudoia-codigo"):
        dados = {"model": modelo, "tools": [{"name": "screenshot"}], "messages": [
            {"role": "user", "content": "abra a página"},
            {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "screenshot", "input": {}}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": [IMG]}]}]}
        r = _pre(hook_grupos, dados)
        assert r["model"] == "tudoia-codigo", modelo   # antes: tudoia-visao
        assert not H.RR.tem_qualquer_imagem(r)          # o grupo de código não aceita imagem


def test_imagem_sem_tools_pedida_ao_codigo_ainda_vai_para_visao(hook_grupos):
    r = _pre(hook_grupos, {"model": "tudoia-codigo", "messages": [{"role": "user", "content": [IMG]}]})
    assert r["model"] == "tudoia-visao" and r["messages"][0]["content"][0] == IMG


def _com_cache(modelo):
    return {"model": modelo,
            "system": [{"type": "text", "text": "s", "cache_control": dict(CACHE)}],
            "messages": [{"role": "user", "content": [{"type": "text", "text": "oi", "cache_control": dict(CACHE)}]}],
            "tools": [{"name": "ls", "cache_control": dict(CACHE)}]}


def test_cache_control_fica_so_no_pago_sem_fallback(hook_grupos):
    pago = _pre(hook_grupos, _com_cache("claude-sonnet-5-5"))
    assert pago["system"][0]["cache_control"] == CACHE and pago["tools"][0]["cache_control"] == CACHE
    for modelo in ("tudoia-max", "tudoia-nuvem", "tudoia-auto"):   # max cai no nuvem (Gemini Free) no fallback
        r = _pre(hook_grupos, _com_cache(modelo))
        assert "cache_control" not in r["system"][0], modelo   # antes: o system escapava
        assert "cache_control" not in r["messages"][0]["content"][0] and "cache_control" not in r["tools"][0]


def test_sem_config_tira_cache_control_de_todos(hook):
    r = _pre(hook, _com_cache("claude-sonnet-5-5"))
    assert "cache_control" not in r["system"][0]


# ── leituras com cache por mtime e gravações que nunca derrubam o pedido ─────────
def test_limites_e_gpu_so_releem_quando_o_arquivo_muda(tmp_path, monkeypatch):
    import os
    from datetime import datetime, timezone
    monkeypatch.setattr(H, "DIR_LOGS", str(tmp_path))
    agora = datetime.now(timezone.utc).isoformat()
    arq = tmp_path / "limites.json"
    arq.write_text(json.dumps({"ts": agora, "esgotados": ["nim/a"]}), encoding="utf-8")
    (tmp_path / "gpu.json").write_text(json.dumps({"dono": "comfy", "expira_em": "2999-01-01T00:00:00+00:00"}), encoding="utf-8")
    leituras = []
    original = H.json.load
    monkeypatch.setattr(H.json, "load", lambda f, **k: leituras.append(f.name) or original(f, **k))
    for _ in range(5):
        assert H.Roteador.limites()[0] == {"nim/a"} and H.Roteador.gpu_ocupada()
    assert len(leituras) == 2   # limites.json e gpu.json uma vez cada (quarentena.json não existe: nem abre)
    arq.write_text(json.dumps({"ts": agora, "esgotados": ["nim/a", "nim/b"]}), encoding="utf-8")
    futuro = time.time_ns() + 10**9
    os.utime(arq, ns=(futuro, futuro))
    assert H.Roteador.limites()[0] == {"nim/a", "nim/b"} and len(leituras) == 3
    arq.unlink()
    assert H.Roteador.limites() == (set(), None)


def test_ratelimit_com_resposta_estranha_nao_derruba_e_grava_em_segundo_plano(hook, tmp_path):
    lixo = types.SimpleNamespace(_hidden_params="não é dict")   # antes: AttributeError subia para o LiteLLM
    hook._gravar_ratelimit("groq", lixo)
    (tmp_path / "ratelimit.json").write_text('{"nim": {"x": "1"}}', encoding="utf-8")
    ok = types.SimpleNamespace(_hidden_params={"additional_headers": {"llm_provider-x-ratelimit-remaining-requests": "9"}})
    hook._gravar_ratelimit("groq", ok)
    arq = tmp_path / "ratelimit.json"
    fim = time.time() + 5
    while time.time() < fim and "groq" not in arq.read_text(encoding="utf-8"):
        time.sleep(0.02)
    dados = json.loads(arq.read_text(encoding="utf-8"))
    assert dados["nim"] == {"x": "1"} and dados["groq"]["x-ratelimit-remaining-requests"] == "9"


def test_correcao_vai_para_arquivo_proprio(hook, tmp_path):
    _pre(hook, {"model": "tudoia-auto", "messages": [{"role": "user", "content": "#nuvem resuma o livro"}]})
    linha = _ultima_linha(tmp_path / "correcoes.jsonl")
    assert linha["rotulo"] == "nuvem" and linha["caracteres"] == len("resuma o livro")
    assert linha["sha1"] == hashlib.sha1("resuma o livro".encode("utf-8")).hexdigest()
    assert "texto" not in linha and "resuma" not in json.dumps(linha)   # o prompt não vai para o disco


# ── Ollama fora: a decisão automática não manda para o local ────────────────────
class _ClienteSaude(_ClienteLento):
    chamadas = 0
    erro = None

    async def get(self, url, **k):
        type(self).chamadas += 1
        if self.erro:
            raise self.erro
        return types.SimpleNamespace(raise_for_status=lambda: None)


def _hook_com_saude(hook, monkeypatch, erro):
    cls = type("Cli", (_ClienteSaude,), {"chamadas": 0, "erro": erro})
    monkeypatch.setattr(H.httpx, "AsyncClient", cls)
    hook._saude_ok, hook._saude_em = True, float("-inf")
    hook._exemplos = lambda: None
    return cls


def test_ollama_fora_desvia_decisao_automatica(hook, monkeypatch):
    cls = _hook_com_saude(hook, monkeypatch, H.httpx.ConnectError("recusado"))

    async def cenario():
        saida = []
        for _ in range(2):
            dados = {"model": "tudoia-auto", "messages": [{"role": "user", "content": "oi"}]}
            saida.append(await hook.async_pre_call_hook({}, None, dados, "completion"))
        return saida

    r, r2 = asyncio.run(cenario())
    assert r["model"] == r2["model"] == "tudoia-nuvem"
    assert cls.chamadas == 1   # 10 s de cache: o segundo pedido não checa de novo


def test_ollama_fora_nao_desvia_local_explicito(hook, monkeypatch):
    cls = _hook_com_saude(hook, monkeypatch, H.httpx.ConnectError("recusado"))
    r = _pre(hook, {"model": "tudoia-auto", "messages": [{"role": "user", "content": "#local meu segredo"}]})
    assert r["model"] == "tudoia-local" and cls.chamadas == 0   # privacidade: nem pergunta
    assert _pre(hook, {"model": "tudoia-local", "messages": [{"role": "user", "content": "oi"}]})["model"] == "tudoia-local"


def test_ollama_fora_agente_esgotado_volta_para_o_codigo(hook, monkeypatch):
    _hook_com_saude(hook, monkeypatch, H.httpx.ReadTimeout("lento"))
    hook.limites = lambda: ({"nim/c"}, {"tudoia-codigo": ["nim/c"]})
    r = _pre(hook, {"model": "tudoia-auto", "tools": [{"name": "ls"}], "messages": [{"role": "user", "content": "ls"}]})
    assert r["model"] == "tudoia-codigo"


def test_ollama_no_ar_segue_para_o_local(hook, monkeypatch):
    cls = _hook_com_saude(hook, monkeypatch, None)
    assert _pre(hook, {"model": "tudoia-auto", "messages": [{"role": "user", "content": "oi"}]})["model"] == "tudoia-local"
    assert cls.chamadas == 1


def test_checagem_do_ollama_tem_teto_e_um_so_get_por_vez(hook, monkeypatch):
    class _Pendurado(_ClienteSaude):
        chamadas = 0

        async def get(self, url, **k):
            type(self).chamadas += 1
            await asyncio.sleep(5)

    monkeypatch.setattr(H.httpx, "AsyncClient", _Pendurado)
    hook._saude_ok, hook._saude_em = True, float("-inf")

    async def cenario():
        return await asyncio.gather(*(hook._ollama_no_ar() for _ in range(5)))

    t0 = time.monotonic()
    assert asyncio.run(cenario()) == [False] * 5
    assert time.monotonic() - t0 < 1.5 and _Pendurado.chamadas == 1

import asyncio
import importlib.util
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from tudoia_painel import caminhos


def _modulo():
    spec = importlib.util.spec_from_file_location("roteador_eventos", caminhos.raiz() / "runtime/litellm/roteador_eventos.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


E = _modulo()
AGORA = datetime(2026, 10, 19, 22, 0, tzinfo=timezone.utc)


def test_evento_inicio_sem_texto():
    data = {"model": "tudoia-auto", "litellm_call_id": "c1", "messages": [{"role": "user", "content": "SEGREDO do usuário"}],
            "system": "prompt secreto", "stream": True}
    ev = E.evento_inicio(data, grupo="tudoia-nuvem", pontos=4, motivos=["codigo"], origem="claude-cli/2.1", call_type="anthropic_messages")
    texto = json.dumps(ev, ensure_ascii=False)
    assert "SEGREDO" not in texto and "secreto" not in texto
    assert ev["tipo"] == "inicio" and ev["id"] == "c1" and ev["grupo"] == "tudoia-nuvem" and ev["stream"] is True
    assert ev["modelo_pedido"] == "tudoia-auto" and ev["origem"] == "claude-cli/2.1"


def test_evento_generico_descarta_campos_desconhecidos():
    ev = E.evento("fim", "c1", tokens_saida=10, messages=["x"], conteudo="y")
    assert "messages" not in ev and "conteudo" not in ev and ev["tokens_saida"] == 10 and "ts" in ev


def test_progresso_limita_a_2_por_segundo():
    p = E.Progresso()
    t0 = AGORA
    emitidos = [p.registrar("c1", 5, t0 + timedelta(milliseconds=100 * i)) for i in range(10)]   # 1 s de chunks
    assert sum(1 for e in emitidos if e) == 2
    assert p.tokens("c1") == 50


def test_contar_tokens_chunk_formatos():
    obj = SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="abcdefgh"))])
    assert E.contar_tokens_chunk(obj) == 2
    assert E.contar_tokens_chunk({"choices": [{"delta": {"content": "abcd"}}]}) == 1
    assert E.contar_tokens_chunk({"type": "content_block_delta", "delta": {"text": "abcdefghijkl"}}) == 3
    assert E.contar_tokens_chunk(SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="a"))])) == 1
    assert E.contar_tokens_chunk(object()) == 0
    assert E.contar_tokens_chunk(None) == 0
    assert E.contar_tokens_chunk(b"data: {}") == 0


def test_repassar_entrega_todos_os_chunks_mesmo_se_a_contagem_explodir():
    async def gerador():
        for i in range(5):
            yield i

    def explode(chunk):
        raise RuntimeError("bug na contagem")

    async def coletar():
        return [c async for c in E.repassar(gerador(), explode)]

    assert asyncio.run(coletar()) == [0, 1, 2, 3, 4]


def test_cortar_arquivo_remove_mais_de_24h(tmp_path):
    p = tmp_path / "eventos.jsonl"
    velho = {"ts": (AGORA - timedelta(hours=25)).isoformat(), "tipo": "fim"}
    novo = {"ts": (AGORA - timedelta(hours=1)).isoformat(), "tipo": "fim"}
    p.write_text(json.dumps(velho) + "\n" + json.dumps(novo) + "\nlinha-quebrada\n", encoding="utf-8")
    E.cortar_arquivo(p, AGORA)
    linhas = p.read_text(encoding="utf-8").splitlines()
    assert len(linhas) == 1 and json.loads(linhas[0])["ts"] == novo["ts"]


def test_cortar_arquivo_respeita_tamanho(tmp_path):
    p = tmp_path / "eventos.jsonl"
    linha = json.dumps({"ts": AGORA.isoformat(), "tipo": "progresso", "x": "y" * 200})
    p.write_text((linha + "\n") * 2000, encoding="utf-8")   # ~450 KB
    E.cortar_arquivo(p, AGORA, max_mb=0.1)
    assert p.stat().st_size <= 0.1 * 1024 * 1024
    assert p.read_text(encoding="utf-8").splitlines()[-1] == linha


def test_repassar_avisa_quando_o_cliente_desiste():
    async def gerador():
        for i in range(100):
            yield i

    fim = []

    async def consumir_parte():
        g = E.repassar(gerador(), lambda c: None, ao_terminar=fim.append)
        async for c in g:
            if c == 3:
                break
        await g.aclose()

    async def consumir_tudo():
        async for _ in E.repassar(gerador(), lambda c: None, ao_terminar=fim.append):
            pass

    asyncio.run(consumir_parte())
    asyncio.run(consumir_tudo())
    assert fim == [False, True]


def test_resumir_erro_sem_texto_do_provedor():
    class BadRequest(Exception):
        status_code = 400

    msg = E.resumir_erro(BadRequest("o texto 'meu CPF é 123' é inválido"))
    assert msg == "BadRequest (HTTP 400)" and "CPF" not in msg
    assert E.resumir_erro(None) == "falha"
    assert E.resumir_erro(TimeoutError("x")) == "TimeoutError"


def test_gravador_em_thread_e_corte_por_tamanho(tmp_path):
    import time
    p = tmp_path / "eventos.jsonl"
    g = E.Gravador(str(p), max_mb=0.01, checar_s=0.05)
    for i in range(400):
        g.put(E.evento("progresso", f"id{i}", tokens_saida=i))
    deadline = time.time() + 5
    while time.time() < deadline and (not p.exists() or g.fila.qsize()):
        time.sleep(0.05)
    time.sleep(0.3)
    g.parar()
    assert p.exists() and p.stat().st_size <= 0.01 * 1024 * 1024 + 300


def test_gravador_nao_bloqueia_com_fila_cheia(tmp_path):
    g = E.Gravador(str(tmp_path / "e.jsonl"), tamanho_fila=2, iniciar=False)
    for i in range(10):
        g.put({"ts": "x", "tipo": "progresso", "id": str(i)})   # não levanta nem trava
    assert g.fila.qsize() == 2


def test_contar_tokens_em_chunk_sse_anthropic_bytes():
    # no /v1/messages (Claude Code) o iterador recebe o SSE já serializado
    chunk = (b'event: content_block_delta\n'
             b'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"abcdefghijkl"}}\n\n'
             b'event: content_block_delta\n'
             b'data: {"type":"content_block_delta","index":0,"delta":{"type":"thinking_delta","thinking":"abcd"}}\n\n')
    assert E.contar_tokens_chunk(chunk) == 4
    assert E.contar_tokens_chunk(chunk.decode()) == 4
    assert E.contar_tokens_chunk(b'event: ping\ndata: {"type":"ping"}\n\n') == 0
    assert E.contar_tokens_chunk(b"data: [DONE]\n\n") == 0


def _esperar(cond, s=5.0):
    import time
    fim = time.time() + s
    while time.time() < fim and not cond():
        time.sleep(0.02)
    return cond()


def test_gravador_outros_arquivos_giram_para_ponto_1(tmp_path):
    import json
    eventos, outro = tmp_path / "eventos.jsonl", tmp_path / "correcoes.jsonl"
    outro.write_text("velho\n" * 400, encoding="utf-8")            # ~2,4 KB: acima do limite do teste
    (tmp_path / "correcoes.jsonl.1").write_text("mais velho\n", encoding="utf-8")
    g = E.Gravador(str(eventos), max_outros_mb=0.001)
    g.put({"ts": "x", "texto": "novo"}, str(outro))
    assert _esperar(lambda: g.fila.qsize() == 0)
    g.parar()   # termina o lote em andamento; ler antes disso trava o rename no Windows
    assert [json.loads(l)["texto"] for l in outro.read_text(encoding="utf-8").splitlines()] == ["novo"]
    assert (tmp_path / "correcoes.jsonl.1").read_text(encoding="utf-8") == "velho\n" * 400   # sobrescreve o .1
    assert not eventos.exists() or "novo" not in eventos.read_text(encoding="utf-8")


def test_gravador_substitui_json_inteiro_e_sobrevive_a_valor_estranho(tmp_path):
    import json
    rl, ev = tmp_path / "ratelimit.json", tmp_path / "eventos.jsonl"
    g = E.Gravador(str(ev))
    g.put({"ts": "x", "custo_usd": object()})                     # antes matava a thread (TypeError no json.dumps)
    g.put({"groq": {"a": "1"}}, str(rl), substituir=True)
    g.put({"groq": {"a": "2"}}, str(rl), substituir=True)
    g.put({"ts": "y", "tipo": "depois"})
    assert _esperar(lambda: g.fila.qsize() == 0)
    g.parar()
    assert "depois" in ev.read_text(encoding="utf-8")   # a thread continuou viva
    assert json.loads(rl.read_text(encoding="utf-8")) == {"groq": {"a": "2"}}
    assert not (tmp_path / "ratelimit.json.tmp").exists()

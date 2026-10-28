import asyncio
import importlib.util

from tudoia_painel import caminhos


def _modulo():
    spec = importlib.util.spec_from_file_location("roteador_resiliente", caminhos.raiz() / "runtime/litellm/roteador_resiliente.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


R = _modulo()
INICIO = b'event: message_start\ndata: {"type":"message_start"}\n\n'
TEXTO = b'event: content_block_delta\ndata: {"type":"content_block_delta"}\n\n'
FIM = b'event: message_stop\ndata: {"type":"message_stop"}\n\n'
OUTRO = TEXTO.replace(b'"content_block_delta"}', b'"content_block_delta", "x": "outro"}')   # SSE válido: termina em linha vazia
ERRO = b'event: error\ndata: {"type":"error","error":{"type":"api_error","message":"Timeout on reading data"}}\n\n'


async def _gerar(*itens, atraso=0.0, explode=None):
    for i in itens:
        if atraso:
            await asyncio.sleep(atraso)
        yield i
    if explode:
        raise explode


def _coletar(gen):
    async def tudo():
        return [x async for x in gen]
    return asyncio.run(tudo())


def _sem_ping(saida):
    return [x for x in saida if x != R.PING]


def test_stream_completo_e_entregue_igual():
    refeitos = []
    saida = _coletar(R.entregar(_gerar(INICIO, TEXTO, FIM), lambda alvo: refeitos.append(alvo), ["b"]))
    assert _sem_ping(saida) == [INICIO, TEXTO, FIM]
    assert refeitos == []


def test_evento_de_erro_no_meio_refaz_no_proximo_e_nada_do_primeiro_vaza():
    # o caso do "Server error mid-response": o provedor manda conteúdo e depois o adaptador emite event: error
    refeitos = []

    async def refazer(alvo):
        refeitos.append(alvo)
        return _gerar(INICIO, OUTRO, FIM)

    saida = _coletar(R.entregar(_gerar(INICIO, TEXTO, ERRO), refazer, ["nim/glm-5.3", "tudoia-local-agente"]))
    assert _sem_ping(saida) == [INICIO, OUTRO, FIM]
    assert refeitos == ["nim/glm-5.3"]


def test_excecao_no_meio_tambem_refaz():
    async def refazer(alvo):
        return _gerar(INICIO, FIM)

    saida = _coletar(R.entregar(_gerar(INICIO, TEXTO, explode=RuntimeError("socket")), refazer, ["b"]))
    assert _sem_ping(saida) == [INICIO, FIM]


def test_stream_sem_message_stop_conta_como_falha():
    async def refazer(alvo):
        return _gerar(INICIO, FIM)

    saida = _coletar(R.entregar(_gerar(INICIO, TEXTO), refazer, ["b"]))
    assert _sem_ping(saida) == [INICIO, FIM]


def test_todos_falham_entrega_a_ultima_resposta_com_o_erro():
    async def refazer(alvo):
        if alvo == "b":
            raise RuntimeError("router sem membro")
        return _gerar(INICIO, b"c", ERRO)

    saida = _coletar(R.entregar(_gerar(INICIO, TEXTO, ERRO), refazer, ["b", "c"]))
    assert _sem_ping(saida) == [INICIO, b"c", ERRO]   # o cliente ainda vê um erro claro, não um stream pendurado


def test_sem_plano_entrega_o_que_veio():
    saida = _coletar(R.entregar(_gerar(INICIO, TEXTO, ERRO), lambda a: None, []))
    assert _sem_ping(saida) == [INICIO, TEXTO, ERRO]


def test_falha_sem_nenhum_byte_vira_erro_anthropic():
    async def refazer(alvo):
        raise RuntimeError("x")

    saida = _coletar(R.entregar(_gerar(explode=RuntimeError("caiu")), refazer, ["b"]))
    assert len(_sem_ping(saida)) == 1 and b"event: error" in saida[-1]


def test_ping_enquanto_segura_a_resposta():
    # o Claude Code não pode ficar sem bytes enquanto o provedor gera: ping é ignorado pelo SDK
    saida = _coletar(R.entregar(_gerar(INICIO, TEXTO, FIM, atraso=0.12), lambda a: None, [], ping_s=0.05))
    assert saida[0] == R.PING
    assert _sem_ping(saida) == [INICIO, TEXTO, FIM]


def test_aceita_str_e_chunks_com_varios_eventos():
    junto = (INICIO + TEXTO).decode()
    saida = _coletar(R.entregar(_gerar(junto, FIM.decode()), lambda a: None, []))
    assert _sem_ping(saida) == [junto, FIM.decode()]


def test_plano_outros_membros_depois_fallbacks():
    cfg = {
        "model_list": [
            {"model_name": "tudoia-codigo", "model_info": {"membro": "nim/glm-5.3"}},
            {"model_name": "tudoia-codigo", "model_info": {"membro": "nim/nemotron-3-ultra"}},
            {"model_name": "nim/glm-5.3", "model_info": {}},
            {"model_name": "nim/nemotron-3-ultra", "model_info": {}},
            {"model_name": "tudoia-local-agente", "model_info": {"membro": "local/tudoia-agente"}},
            {"model_name": "tudoia-nuvem", "model_info": {"membro": "groq/gpt-oss-120b"}},
        ],
        "router_settings": {"fallbacks": [{"tudoia-codigo": ["tudoia-local-agente"]}, {"nim/glm-5.3": ["tudoia-nuvem"]}]},
    }
    mapa = R.mapa_de_grupos(cfg)
    assert R.plano(mapa, "tudoia-codigo", "nim/nemotron-3-ultra") == ["nim/glm-5.3", "tudoia-local-agente"]
    assert R.plano(mapa, "tudoia-codigo", None) == ["nim/glm-5.3", "nim/nemotron-3-ultra", "tudoia-local-agente"][:R.MAX_TENTATIVAS]
    assert R.plano(mapa, "nim/glm-5.3", "nim/glm-5.3") == ["tudoia-nuvem"]
    assert R.plano(mapa, "desconhecido", None) == []
    # membro sem deployment próprio pelo nome não entra (o router não saberia o que é)
    cfg["model_list"] = [m for m in cfg["model_list"] if m["model_name"] != "nim/glm-5.3"]
    assert R.plano(R.mapa_de_grupos(cfg), "tudoia-codigo", "nim/nemotron-3-ultra") == ["tudoia-local-agente"]


class _Deployment:   # o proxy grava data["deployment"] = Deployment(...) (pydantic) depois da 1ª resposta
    pass


def test_pedido_refeito_leva_so_campos_do_cliente():
    # sem isso o objeto Deployment ia para o provedor: Ollama "not JSON serializable", NIM HTTP 400
    original = {
        "model": "tudoia-codigo", "messages": [{"role": "user", "content": "oi"}], "system": "s",
        "max_tokens": 100, "stream": True, "tools": [{"name": "t"}], "thinking": {"type": "enabled"},
        "deployment": _Deployment(), "model_info": {"membro": "nim/glm-5.3"}, "api_base": "https://nim",
        "litellm_logging_obj": object(), "litellm_call_id": "velho", "proxy_server_request": {"url": "x"},
        "metadata": {"user_id": "u", "deployment": "nvidia/x", "model_info": {}, "api_base": "https://nim",
                     "deployment_model_name": "tudoia-codigo"},
    }
    dados = R.pedido_para_refazer(original, "tudoia-local-agente", "novo")
    assert dados["model"] == "tudoia-local-agente" and dados["litellm_call_id"] == "novo"
    assert set(dados) == {"model", "messages", "system", "max_tokens", "stream", "tools", "thinking",
                          "metadata", "litellm_call_id", "disable_fallbacks"}
    assert dados["metadata"] == {"user_id": "u"}            # o que o router carimbou da tentativa anterior sai
    assert original["metadata"]["api_base"] == "https://nim"  # e o pedido original fica intacto
    dados["messages"].append("x")
    assert len(original["messages"]) == 1


def _parada(motivo, saida):
    return ('event: message_delta\ndata: {"type": "message_delta", "delta": {"stop_reason": "%s"}, '
            '"usage": {"output_tokens": %d}}\n\n' % (motivo, saida)).encode()


def test_cortada_por_max_tokens_refaz_em_outro_modelo():
    # 21/10/2026: o tudoia-chat local (num_ctx 32k) recebeu 32,7k tokens, encheu a janela e parou com 30 tokens de
    # saída e stop_reason max_tokens; o Claude Code mostrou "response exceeded the 32000 output token maximum"
    refeitos = []

    async def refazer(alvo):
        refeitos.append(alvo)
        return _gerar(INICIO, b"inteira", _parada("end_turn", 900), FIM)

    saida = _coletar(R.entregar(_gerar(INICIO, TEXTO, _parada("max_tokens", 30), FIM), refazer, ["b"], max_saida=32000))
    assert _sem_ping(saida) == [INICIO, b"inteira", _parada("end_turn", 900), FIM]
    assert refeitos == ["b"]


def test_modelo_que_gasta_o_orcamento_grande_inteiro_tambem_refaz():
    # 32k tokens num pedido de agente é modelo em laço; outro modelo costuma terminar
    async def refazer(alvo):
        return _gerar(INICIO, _parada("end_turn", 10), FIM)

    saida = _coletar(R.entregar(_gerar(INICIO, _parada("max_tokens", 32000), FIM), refazer, ["b"], max_saida=32000))
    assert _sem_ping(saida) == [INICIO, _parada("end_turn", 10), FIM]


def test_orcamento_pequeno_usado_por_inteiro_e_resposta_valida():
    # o Claude Code faz chamadas curtas (título, resumo) com max_tokens baixo: bater no limite ali é normal
    refeitos = []
    original = [INICIO, _parada("max_tokens", 512), FIM]
    saida = _coletar(R.entregar(_gerar(*original), lambda a: refeitos.append(a), ["b"], max_saida=512))
    assert _sem_ping(saida) == original and refeitos == []


def test_tentativa_que_nem_comeca_nao_gasta_a_vez():
    # membro em cooldown falha na hora (RouterRateLimitError): não pode tirar a vez do próximo da fila
    tentados = []

    async def refazer(alvo):
        tentados.append(alvo)
        if alvo in ("b", "c"):
            raise RuntimeError("em cooldown")
        return _gerar(INICIO, b"ok", FIM)

    plano = ["b", "c", "d"]
    saida = _coletar(R.entregar(_gerar(INICIO, ERRO), refazer, plano))
    assert _sem_ping(saida) == [INICIO, b"ok", FIM] and tentados == ["b", "c", "d"]


def test_plano_vai_ate_a_reserva_e_o_local():
    cfg = {
        "model_list": [
            {"model_name": "tudoia-codigo", "model_info": {"membro": "nim/glm-5.3"}},
            {"model_name": "tudoia-codigo", "model_info": {"membro": "nim/nemotron-3-ultra"}},
            {"model_name": "nim/glm-5.3", "model_info": {}},
            {"model_name": "nim/nemotron-3-ultra", "model_info": {}},
            {"model_name": "tudoia-codigo-reserva", "model_info": {"membro": "or/nemotron-3-ultra"}},
            {"model_name": "tudoia-local-agente", "model_info": {"membro": "local/tudoia-agente"}},
        ],
        "router_settings": {"fallbacks": [{"tudoia-codigo": ["tudoia-codigo-reserva", "tudoia-local-agente"]}]},
    }
    assert R.plano(R.mapa_de_grupos(cfg), "tudoia-codigo", "nim/glm-5.3") == [
        "nim/nemotron-3-ultra", "tudoia-codigo-reserva", "tudoia-local-agente"]


def test_pedido_refeito_desliga_os_fallbacks_do_router():
    # sem isso, refazer em nim/nemotron-3-ultra (em cooldown) caía no fallback dele, tudoia-nuvem → Groq → tudoia-chat
    # local, modelos de chat que não aguentam o tamanho do pedido do Claude Code; quem escolhe o próximo é o plano
    dados = R.pedido_para_refazer({"model": "x", "messages": []}, "nim/nemotron-3-ultra", "id")
    assert dados["disable_fallbacks"] is True


def _delta(texto, campo="text"):
    import json
    return ('event: content_block_delta\ndata: {"type": "content_block_delta", "index": 0, "delta": '
            '{"type": "%s_delta", "%s": %s}}\n\n' % (campo, campo, json.dumps(texto))).encode()


def test_detector_pega_texto_se_repetindo():
    d = R.DetectorDeLaco()
    frase = "Vou analisar o arquivo novamente para confirmar. "
    assert not any(d.alimentar(_delta(frase)) for _ in range(20))     # ~1000 caracteres: ainda cedo para julgar
    assert any(d.alimentar(_delta(frase)) for _ in range(100))


def test_detector_pega_laco_no_pensamento_e_no_json_da_ferramenta():
    for campo in ("thinking", "partial_json"):
        d = R.DetectorDeLaco()
        assert any(d.alimentar(_delta('{"a": 1}, ', campo)) for _ in range(800))


def test_detector_nao_acusa_texto_normal_nem_codigo_com_linhas_parecidas():
    d = R.DetectorDeLaco()
    linhas = [f"| {i:4d} | item_{i * 7 % 13} | valor {i * i} |\n" for i in range(600)]   # tabela: parecida, nunca igual
    assert not any(d.alimentar(_delta(l)) for l in linhas)


def test_laco_corta_o_stream_e_refaz_em_outro_modelo():
    async def em_laco():
        yield INICIO
        while True:   # o provedor nunca para sozinho: só o corte salva
            yield _delta("de novo e de novo ")
            await asyncio.sleep(0)

    refeitos = []

    async def refazer(alvo):
        refeitos.append(alvo)
        return _gerar(INICIO, b"certo", FIM)

    saida = _coletar(R.entregar(em_laco(), refazer, ["b"]))
    assert _sem_ping(saida) == [INICIO, b"certo", FIM] and refeitos == ["b"]


def test_texto_do_modelo_com_event_error_nao_e_falha():
    # pedir "servidor SSE" faz o modelo escrever "event: error"; o texto vem escapado dentro de data: {...}
    codigo = _delta('res.write("event: error\ndata: {}\n\n")\nif "message_stop" in linha:\n')
    refeitos = []
    saida = _coletar(R.entregar(_gerar(INICIO, codigo, FIM), lambda a: refeitos.append(a), ["b"]))
    assert _sem_ping(saida) == [INICIO, codigo, FIM] and refeitos == []


def test_message_stop_so_no_texto_nao_conta_como_fim():
    # o contrário: o modelo cita "event: message_stop" e o stream é cortado antes do fim de verdade
    citado = _delta("o servidor manda\nevent: message_stop\nno final")

    async def refazer(alvo):
        return _gerar(INICIO, FIM)

    saida = _coletar(R.entregar(_gerar(INICIO, citado), refazer, ["b"]))
    assert _sem_ping(saida) == [INICIO, FIM]


def test_evento_partido_entre_chunks_e_crlf_ainda_e_reconhecido():
    assert R._completa([INICIO, b"event: message_st", b"op\r\ndata: {}\r\n\r\n"])
    assert not R._completa([INICIO, FIM, b"event:error\ndata: {}\n\n"])   # sem espaço depois do ':' também vale (SSE)


def _periodico_forca_bruta(fim):
    # algoritmo antigo, para comparar
    return any(fim[p:] == fim[:-p] for p in range(1, R.DetectorDeLaco.PERIODO_MAX + 1))


def _checar(texto):
    d = R.DetectorDeLaco()
    d._texto, d._desde_checagem = texto[:-1], R.DetectorDeLaco.CHECAR_A_CADA
    return d.alimentar(_delta(texto[-1]))


def test_detector_rapido_da_o_mesmo_resultado_que_o_antigo():
    import random
    rnd = random.Random(7)
    J = R.DetectorDeLaco.JANELA
    casos = []
    for p in (1, 2, 37, 749, 750, 751, 1499):   # 750 é o limite; 751 em diante não é laço para o detector
        base = "".join(rnd.choice("abc") for _ in range(p))
        casos.append((base * (J // p + 2))[:J])
    quase = list(casos[3])
    quase[10] = "z"   # periódico menos 1 caractere lá no começo: não pode acusar
    casos.append("".join(quase))
    casos += ["".join(rnd.choice("ab") for _ in range(J)) for _ in range(30)]   # alfabeto pequeno: muitos candidatos
    for texto in casos:
        assert _checar(texto) == _periodico_forca_bruta(texto[-J:]), len(texto)
    assert _checar(casos[4]) and not _checar(casos[5]) and not _checar(casos[7])


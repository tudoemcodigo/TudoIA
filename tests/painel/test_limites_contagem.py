"""Uma chamada aparece no /spend/logs do LiteLLM e no eventos.jsonl do hook: tem de contar uma vez só."""
import json
from datetime import datetime, timedelta, timezone

from tudoia_painel import limites


def _cenario(tmp_path, monkeypatch, logs_litellm, eventos):
    (tmp_path / ".env").write_text("LITELLM_MASTER_KEY=sk-teste\n", encoding="utf-8")
    pasta_logs = tmp_path / "dados" / "logs"
    pasta_logs.mkdir(parents=True)
    (pasta_logs / "eventos.jsonl").write_text("".join(json.dumps(e) + "\n" for e in eventos), encoding="utf-8")
    monkeypatch.setattr(limites, "ler_logs_litellm", lambda k, horas: logs_litellm)
    return limites.obter_metricas_limites(tmp_path, periodo_horas=24)


def _agora(delta_min=0):
    return (datetime.now(timezone.utc) - timedelta(minutes=delta_min)).isoformat()


def test_chamada_nas_duas_fontes_conta_uma_vez(tmp_path, monkeypatch):
    log = {"request_id": "chatcmpl-1", "litellm_call_id": "uuid-1", "model": "ollama_chat/qwen3.5:latest",
           "custom_llm_provider": "ollama_chat", "startTime": _agora(5), "status": "success",
           "prompt_tokens": 22, "completion_tokens": 100, "total_tokens": 122}
    evento = {"ts": _agora(5), "tipo": "fim", "id": "uuid-1", "modelo": "qwen3.5:latest", "provedor": "local",
              "tokens_entrada": 22, "tokens_saida": 100, "ok": True}

    res = _cenario(tmp_path, monkeypatch, [log], [evento])

    assert res["resumo"]["total_tokens"] == 122
    assert [m["modelo"] for m in res["ranking_modelos"]] == ["ollama_chat/qwen3.5:latest"]


def test_evento_sem_par_no_litellm_continua_contando(tmp_path, monkeypatch):
    # LiteLLM fora do ar (lista vazia): o eventos.jsonl é a única fonte e não pode ser descartado.
    evento = {"ts": _agora(2), "tipo": "fim", "id": "uuid-2", "modelo": "qwen3.8:latest", "provedor": "local",
              "tokens_entrada": 17, "tokens_saida": 19, "ok": True}

    res = _cenario(tmp_path, monkeypatch, [], [evento])

    assert res["resumo"]["total_tokens"] == 36


def test_log_sem_litellm_call_id_usa_request_id(tmp_path, monkeypatch):
    logs = [{"request_id": f"chatcmpl-{i}", "model": "ollama_chat/x", "startTime": _agora(1), "status": "success",
             "prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2} for i in range(3)]

    res = _cenario(tmp_path, monkeypatch, logs, [])

    assert res["resumo"]["total_tokens"] == 6

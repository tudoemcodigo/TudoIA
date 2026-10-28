import json

import pytest

from tudoia_instalador.motor import (ErroInstalacao, Estado, Etapa, Motor, ReinicioNecessario)

from .duplos import ExecutorFalso


def _motor(ctx, etapas, tmp_path):
    ctx.executor = ExecutorFalso(ctx.log, ctx.redator)
    return Motor(ctx, etapas, arquivo_log=tmp_path / "estado" / "instalador.log")


def _etapa(id_, ordem, falha=None, aplica=True):
    def executar(c):
        ordem.append(id_)
        if falha:
            raise falha
    return Etapa(id_, f"Etapa {id_}", executar, lambda o: aplica)


def test_roda_na_ordem_e_marca_concluida(ctx, tmp_path):
    ordem = []
    m = _motor(ctx, [_etapa("a", ordem), _etapa("b", ordem), _etapa("c", ordem)], tmp_path)
    assert m.rodar() is True and ordem == ["a", "b", "c"]
    assert [e["estado"] for e in m.instantaneo()["etapas"]] == ["ok", "ok", "ok"]


def test_etapa_que_nao_se_aplica_e_pulada(ctx, tmp_path):
    ordem = []
    m = _motor(ctx, [_etapa("a", ordem), _etapa("b", ordem, aplica=False)], tmp_path)
    assert m.rodar() is True and ordem == ["a"]
    assert m.instantaneo()["etapas"][1]["estado"] == "pulada"


def test_para_na_primeira_falha_e_nao_roda_as_proximas(ctx, tmp_path):
    ordem = []
    m = _motor(ctx, [_etapa("a", ordem), _etapa("b", ordem, falha=ErroInstalacao("Docker sumiu")), _etapa("c", ordem)], tmp_path)
    assert m.rodar() is False and ordem == ["a", "b"]
    s = m.instantaneo()
    assert s["falhou"] and s["erro"] == "Docker sumiu" and [e["estado"] for e in s["etapas"]] == ["ok", "falhou", "pendente"]


def test_retomar_pula_o_que_ja_concluiu(ctx, tmp_path):
    ordem = []
    falha = ErroInstalacao("rede caiu")
    etapas = [_etapa("a", ordem), _etapa("b", ordem, falha=falha), _etapa("c", ordem)]
    m = _motor(ctx, etapas, tmp_path)
    m.rodar()
    etapas[1] = _etapa("b", ordem)            # o problema foi corrigido
    m2 = _motor(ctx, etapas, tmp_path)         # outra execução: lê o estado.json
    assert m2.rodar() is True and ordem == ["a", "b", "b", "c"]


def test_reinicio_pausa_e_fica_registrado_no_estado(ctx, tmp_path):
    ordem = []
    m = _motor(ctx, [_etapa("a", ordem), _etapa("b", ordem, falha=ReinicioNecessario("reinicie o Windows")), _etapa("c", ordem)], tmp_path)
    assert m.rodar() is False and ordem == ["a", "b"]
    s = m.instantaneo()
    assert s["reinicio"] and not s["falhou"]
    assert json.loads((tmp_path / "estado" / "estado.json").read_text())["reinicio"] is True


def test_erro_inesperado_nao_vaza_o_texto_da_excecao(ctx, tmp_path):
    ctx.redator.adicionar("senha-super-secreta")
    m = _motor(ctx, [_etapa("a", [], falha=RuntimeError("falhou com senha-super-secreta"))], tmp_path)
    m.rodar()
    s = m.instantaneo()
    assert "senha-super-secreta" not in s["erro"] and "RuntimeError" in s["erro"]
    assert "senha-super-secreta" not in "\n".join(s["linhas"])


def test_log_mascara_segredos_na_memoria_e_no_arquivo(ctx, tmp_path):
    ctx.redator.adicionar("gsk_segredo_de_teste")
    m = _motor(ctx, [Etapa("a", "A", lambda c: c.log("chave gsk_segredo_de_teste no comando"))], tmp_path)
    m.rodar()
    assert "gsk_segredo_de_teste" not in "\n".join(m.instantaneo()["linhas"])
    assert "gsk_segredo_de_teste" not in (tmp_path / "estado" / "instalador.log").read_text(encoding="utf-8")


def test_estado_em_disco_nao_guarda_segredo(ctx, tmp_path):
    ctx.o.chaves_provedores = {"GROQ_API_KEY": "gsk_valor_secreto_1234"}
    ctx.o.keycloak_existente_senha = "senha-do-keycloak"
    m = _motor(ctx, [_etapa("a", [])], tmp_path)
    m.rodar()
    bruto = (tmp_path / "estado" / "estado.json").read_text(encoding="utf-8")
    assert "gsk_valor_secreto_1234" not in bruto and "senha-do-keycloak" not in bruto and "GROQ_API_KEY" in bruto


def test_instantaneo_entrega_so_as_linhas_novas(ctx, tmp_path):
    m = _motor(ctx, [Etapa("a", "A", lambda c: [c.log("um"), c.log("dois")])], tmp_path)
    m.rodar()
    primeiro = m.instantaneo(0)
    assert primeiro["linhas"][-3:] == ["um", "dois", "== Instalação concluída"]
    assert m.instantaneo(primeiro["proximo"])["linhas"] == []


def test_estado_corrompido_e_ignorado(tmp_path):
    (tmp_path / "estado.json").write_text("{isso nao e json", encoding="utf-8")
    assert Estado(tmp_path).dados["etapas"] == {}


def test_esperar_ate_respeita_o_limite(ctx):
    tempo = {"t": 0.0}
    ctx.agora = lambda: tempo["t"]
    ctx.esperar = lambda s: tempo.__setitem__("t", tempo["t"] + s)
    assert ctx.esperar_ate(lambda: False, 10, "algo", intervalo=3) is False
    assert any("tempo esgotado" in x for x in ctx.logs)
    assert ctx.esperar_ate(lambda: True, 10, "algo") is True


@pytest.mark.parametrize("cmd_falha", [True, False])
def test_erro_de_comando_mostra_o_fim_da_saida(ctx, tmp_path, falha_de_comando, cmd_falha):
    m = _motor(ctx, [_etapa("a", [], falha=falha_de_comando("docker compose falhou") if cmd_falha else None)], tmp_path)
    m.rodar()
    texto = "\n".join(m.instantaneo()["linhas"])
    assert ("saida do comando" in texto) == cmd_falha


def test_saida_do_console_cp1252_nao_derruba_a_instalacao(monkeypatch):
    """Regressão da instalação real: o mklink devolveu texto com acento, virou U+FFFD e o print em cp1252 estourou."""
    import io
    import sys

    from tudoia_instalador.__main__ import _configurar_saida

    bruto = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(bruto, encoding="cp1252", errors="strict"))
    _configurar_saida()
    print("Jun\ufffd\ufffdo criada → ok")
    sys.stdout.flush()
    assert "ok".encode() in bruto.getvalue()


def test_nova_execucao_depois_de_uma_instalacao_completa_roda_tudo_de_novo(ctx, tmp_path):
    ordem = []
    etapas = [_etapa("a", ordem), _etapa("b", ordem)]
    assert _motor(ctx, etapas, tmp_path).rodar() is True
    assert _motor(ctx, etapas, tmp_path).rodar() is True       # reinstalação com outras opções: não pode pular tudo
    assert ordem == ["a", "b", "a", "b"]


def test_retomada_depois_de_falha_continua_pulando_o_que_ja_concluiu(ctx, tmp_path):
    ordem = []
    _motor(ctx, [_etapa("a", ordem), _etapa("b", ordem, falha=ErroInstalacao("x"))], tmp_path).rodar()
    _motor(ctx, [_etapa("a", ordem), _etapa("b", ordem)], tmp_path).rodar()
    assert ordem == ["a", "b", "b"]

"""Estado da Doutrina TEC na tela de governança: só leitura, nunca derruba a tela e nunca devolve o .env."""
import json
from pathlib import Path

import pytest

from tudoia_painel.doutrina_servico import COMANDOS, estado_doutrina

SHA = "a" * 40
OUTRO = "b" * 40
DOCKERFILE = "FROM x\nARG DOUTRINA_SHA={}\n"
COMPOSE = "services:\n  squadti:\n    build:\n      args:\n        DOUTRINA_SHA: ${{SQUADTI_DOUTRINA_SHA:-{}}}\n"


def _raiz(tmp_path: Path, pin: str = SHA, dockerfile: str = SHA, compose: str = SHA) -> Path:
    raiz = tmp_path / "raiz"
    (raiz / "governanca").mkdir(parents=True)
    (raiz / "governanca" / "doutrina.json").write_text(json.dumps({"repositorio": "o/r", "sha": pin}), encoding="utf-8")
    (raiz / "runtime" / "squadti").mkdir(parents=True)
    (raiz / "runtime" / "squadti" / "Dockerfile").write_text(DOCKERFILE.format(dockerfile), encoding="utf-8")
    (raiz / "runtime" / "docker-compose.yml").write_text(COMPOSE.format(compose), encoding="utf-8")
    return raiz


def _doutrina(tmp_path: Path, manifesto: object = None) -> Path:
    pasta = tmp_path / "doutrina"
    (pasta / "gerado").mkdir(parents=True)
    dados = {"versao": "0.0.1", "hash": "ae24131f6f9f6016", "arquivos": []} if manifesto is None else manifesto
    (pasta / "gerado" / "manifesto.json").write_text(dados if isinstance(dados, str) else json.dumps(dados), encoding="utf-8")
    return pasta


def test_tudo_em_dia(tmp_path):
    e = estado_doutrina(_raiz(tmp_path), {"DOUTRINA_TEC": str(_doutrina(tmp_path))})
    assert e["estado"] == "ok" and e["em_uso"] == {"versao": "0.0.1", "hash": "ae24131f6f9f6016"}
    assert e["fixada"] == {"repositorio": "o/r", "sha": SHA} and e["derivados_divergentes"] == [] and e["aviso_fixacao"] is None
    assert e["comandos"] == COMANDOS and "--sincronizar-pin" in COMANDOS["atualizar"]


@pytest.mark.parametrize("env", [{}, {"DOUTRINA_TEC": ""}, {"DOUTRINA_TEC": "   "}])
def test_sem_variavel_a_doutrina_e_apontada_como_ausente(tmp_path, env):
    e = estado_doutrina(_raiz(tmp_path), env)
    assert e["estado"] == "sem_pasta" and e["em_uso"] is None and "falham fechado" in e["mensagem"]
    assert e["fixada"]["sha"] == SHA                      # o pin continua visível


@pytest.mark.parametrize("manifesto", ["{nao e json", [], {"versao": "1"}, {"hash": "x"}, "null"])
def test_manifesto_corrompido_ou_incompleto_e_ilegivel_sem_derrubar_a_tela(tmp_path, manifesto):
    e = estado_doutrina(_raiz(tmp_path), {"DOUTRINA_TEC": str(_doutrina(tmp_path, manifesto))})
    assert e["estado"] == "ilegivel" and e["em_uso"] is None


def test_pasta_inexistente_e_ilegivel(tmp_path):
    e = estado_doutrina(_raiz(tmp_path), {"DOUTRINA_TEC": str(tmp_path / "nao-existe")})
    assert e["estado"] == "ilegivel"


def test_dockerfile_e_compose_defasados_aparecem_na_lista(tmp_path):
    e = estado_doutrina(_raiz(tmp_path, dockerfile=OUTRO), {"DOUTRINA_TEC": str(_doutrina(tmp_path))})
    assert e["derivados_divergentes"] == ["runtime/squadti/Dockerfile"]
    e = estado_doutrina(_raiz(tmp_path / "2", compose=OUTRO), {"DOUTRINA_TEC": str(_doutrina(tmp_path / "2"))})
    assert e["derivados_divergentes"] == ["runtime/docker-compose.yml"]


@pytest.mark.parametrize("pin", ["main", "abc", ""])
def test_pin_invalido_vira_aviso_e_nao_excecao(tmp_path, pin):
    e = estado_doutrina(_raiz(tmp_path, pin=pin), {"DOUTRINA_TEC": str(_doutrina(tmp_path))})
    assert e["fixada"] is None and e["aviso_fixacao"] and e["estado"] == "ok"


def test_instalacao_sem_arquivos_da_squadti_vira_aviso(tmp_path):
    raiz = tmp_path / "raiz"
    (raiz / "governanca").mkdir(parents=True)
    (raiz / "governanca" / "doutrina.json").write_text(json.dumps({"repositorio": "o/r", "sha": SHA}), encoding="utf-8")
    e = estado_doutrina(raiz, {})
    assert e["aviso_fixacao"] and e["estado"] == "sem_pasta"


def test_e_somente_leitura_e_nao_vaza_o_resto_do_env(tmp_path):
    raiz = _raiz(tmp_path, dockerfile=OUTRO)
    antes = {p: p.read_bytes() for p in raiz.rglob("*") if p.is_file()}
    e = estado_doutrina(raiz, {"DOUTRINA_TEC": str(_doutrina(tmp_path)), "OPENAI_API_KEY": "sk-super-secreto-1234567890"})
    assert {p: p.read_bytes() for p in raiz.rglob("*") if p.is_file()} == antes
    assert "sk-super-secreto" not in json.dumps(e)

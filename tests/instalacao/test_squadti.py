"""SquadTI no instalador: opcional (fora do padrão), vira perfil do compose, token só com o perfil e etapa da chave."""
from tudoia_instalador import etapas, opcoes, sistema
from tudoia_painel import cli


def test_squadti_e_opcional_e_vira_perfil_do_compose():
    assert "squadti" in opcoes.COMPONENTES and "squadti" not in opcoes.PADRAO_COMPONENTES
    assert "squadti" in opcoes.PERFIS_COMPOSE
    sem = opcoes.Opcoes()
    assert "squadti" not in sem.perfis
    com = opcoes.Opcoes(componentes=[*opcoes.PADRAO_COMPONENTES, "squadti"], admin_email="admin@exemplo.com")
    assert "squadti" in com.perfis and opcoes.validar(com) == []


def test_porta_e_espaco_da_squad_entram_na_conferencia():
    assert sistema.PORTAS["squadti"] == 8790
    assert sistema.portas_necessarias(["squadti"])["squadti"] == 8790
    assert "squadti" not in sistema.portas_necessarias(["cerebro"])
    assert sistema.espaco_necessario_gb(["squadti"]) > sistema.espaco_necessario_gb([])


def test_etapa_da_chave_so_roda_com_a_squad_e_depois_da_stack():
    todas = etapas.montar_etapas()
    ids = [e.id for e in todas]
    assert ids.index("squadti") > ids.index("stack")
    etapa = next(e for e in todas if e.id == "squadti")
    assert etapa.aplica(opcoes.Opcoes(componentes=["squadti"])) and not etapa.aplica(opcoes.Opcoes())


def test_token_da_squad_so_e_gerado_com_o_perfil(tmp_path):
    (tmp_path / ".env").write_text("COMPOSE_PROFILES=cerebro\n", encoding="utf-8")
    assert "TUDOIA_SQUADTI_TOKEN" not in cli.preencher_segredos(tmp_path)
    (tmp_path / ".env").write_text("COMPOSE_PROFILES=cerebro,squadti\n", encoding="utf-8")
    assert "TUDOIA_SQUADTI_TOKEN" in cli.preencher_segredos(tmp_path)
    token = [l for l in (tmp_path / ".env").read_text(encoding="utf-8").splitlines() if l.startswith("TUDOIA_SQUADTI_TOKEN=")][0]
    assert len(token.split("=", 1)[1]) >= 32            # a API da Squad recusa token curto
    assert "TUDOIA_SQUADTI_TOKEN" not in cli.preencher_segredos(tmp_path)   # nunca troca um valor existente

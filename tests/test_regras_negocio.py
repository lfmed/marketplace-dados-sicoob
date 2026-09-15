"""Regras de negócio (RN) + MODELO ativo-cêntrico polimórfico (oficial do cliente).
Sem disparar concessão real. id_ativo_aisn = PK da combinação de origem; escopo UC
resolvido via tabela_aisn. Schemas parametrizados ({GOV}/{ACC})."""
import pytest

from app import db
from app import constants as C
from app.config import config
from app.schemas import GOV, ACC
from app.services import request_service, approval_service, catalog_service
from app.services.ativo_scope import objetos_do_ativo
from app.services.request_service import RegraNegocioError
from tests.conftest import limpar_solicitacao

# IDs = PK da combinação de origem (ICA / TABELA / SCA / DCA).
ICA_ATIVO = "ica_ib_nav_gold"                        # tipo 1 (owner u_ana) -> schema mkt_ib_nav_gold
TAB_ATIVO = "tab_ica_ib_nav_gold_dim_cooperado"      # tipo 2 (owner u_ana) -> tabela dim_cooperado
SUB_ATIVO = "sca_ib_gold"                            # tipo 3 (owner u_ana) -> N schemas
DOM_ATIVO = "dca_canais_gold"                        # tipo 4 (owner u_ana) -> N schemas
CARLOS_ATIVO = "ica_cad_360_gold"                    # tipo 1 (owner u_carlos)


# ---------------- Modelo: ativo é o driver + resolução polimórfica ----------------
def test_id_ativo_e_pk_da_origem(conectado):
    a = db.query_one(f"SELECT * FROM {ACC}.ativo_aisn WHERE id_ativo_aisn=%s", (ICA_ATIVO,))
    assert a and str(a["cod_tipo_ativo"]) == C.AT_ICA
    ica = db.query_one(f"SELECT * FROM {GOV}.iniciativa_camada_ambiente "
                       f"WHERE id_iniciativa_camada_ambiente=%s", (ICA_ATIVO,))
    assert ica is not None
    # sem colunas denormalizadas; grupo embutido em nome_grupo_ativo
    assert "nome_dominio" not in a and "nome_schema" not in a and "id_referencia" not in a
    assert a["nome_grupo_ativo"]


def test_scope_ica_schema(conectado):
    a = db.query_one(f"SELECT * FROM {ACC}.ativo_aisn WHERE id_ativo_aisn=%s", (ICA_ATIVO,))
    objs = objetos_do_ativo(a)
    assert objs and all(o["tipo"] == "SCHEMA" for o in objs)
    assert any(o["schema"] == "mkt_ib_nav_gold" and o["catalogo"] == config.UC_CATALOG for o in objs)


def test_scope_tabela_uma_tabela(conectado):
    a = db.query_one(f"SELECT * FROM {ACC}.ativo_aisn WHERE id_ativo_aisn=%s", (TAB_ATIVO,))
    objs = objetos_do_ativo(a)
    assert len(objs) == 1 and objs[0]["tipo"] == "TABLE"
    assert objs[0]["schema"] == "mkt_ib_nav_gold" and objs[0]["tabela"] == "dim_cooperado"


def test_scope_subdominio_expande(conectado):
    a = db.query_one(f"SELECT * FROM {ACC}.ativo_aisn WHERE id_ativo_aisn=%s", (SUB_ATIVO,))
    objs = objetos_do_ativo(a)
    assert len(objs) >= 1 and all(o["tipo"] == "SCHEMA" for o in objs)


def test_scope_dominio_expande(conectado):
    a = db.query_one(f"SELECT * FROM {ACC}.ativo_aisn WHERE id_ativo_aisn=%s", (DOM_ATIVO,))
    objs = objetos_do_ativo(a)
    assert len(objs) > 1 and all(o["tipo"] == "SCHEMA" for o in objs)


def test_rn005_catalogo_driver_ativo_com_breadcrumb(conectado):
    ativos = catalog_service.listar_ativos()
    assert len(ativos) > 0
    assert all(a["owners"] for a in ativos)
    ica = next(a for a in ativos if a["id_ativo_aisn"] == ICA_ATIVO)
    assert ica["nome_dominio"] == "Canais e Experiência"
    assert ica["tipo_label"] == C.TIPO_ATIVO_LABEL[C.AT_ICA]
    assert ica["nome_grupo_ativo"]  # rótulo de agrupamento de ativos (não é o grupo de acesso)


def test_catalogo_filtra_por_dominio_derivado(conectado):
    do_dom = catalog_service.listar_ativos(id_dominio="dom_canais")
    assert do_dom and all(a["nome_dominio"] == "Canais e Experiência" for a in do_dom)


# ---------------- Regras de negócio ----------------
def test_rn007_grupo_somente_membro(conectado, usuario):
    with pytest.raises(RegraNegocioError, match="membro"):
        request_service.criar_solicitacao(
            usuario("u_ana"), C.B_GRUPO, ICA_ATIVO,
            id_grupo="grp_risco_credito", justificativa="x")


def test_grupo_gestor_autoriza_dono_grupo_aprova(conectado, usuario):
    """Pedido em nome de grupo exploratório: 1ª etapa = GESTOR imediato do solicitante
    (u_mariana); 2ª etapa = DONO DO GRUPO (u_daniela), não o dono do ativo (u_ana)."""
    id1 = request_service.criar_solicitacao(
        usuario("u_leandro"), C.B_GRUPO, ICA_ATIVO,
        id_grupo="grp_risco_credito", justificativa="grupo")
    try:
        s = request_service.detalhe(id1)
        # 1ª etapa: autorizador previsto é o GESTOR do solicitante (não o dono do grupo)
        assert s["id_usuario_autorizador_previsto"] == "u_mariana"
        # o dono do grupo (u_daniela) NÃO faz a 1ª etapa (não é gestor do solicitante)
        with pytest.raises(RegraNegocioError, match="RN-013"):
            approval_service.decidir_autorizacao(id1, "u_daniela", aprovar=True)
        approval_service.decidir_autorizacao(id1, "u_mariana", aprovar=True)     # gestor autoriza
        # 2ª etapa: o dono do ATIVO (u_ana) NÃO aprova pedido de grupo
        with pytest.raises(RegraNegocioError, match="proprietário do grupo"):
            approval_service.decidir_aprovacao_owner(id1, "u_ana", aprovar=True)
        # o dono do GRUPO (u_daniela) aprova
        approval_service.decidir_aprovacao_owner(id1, "u_daniela", aprovar=True)
        s = request_service.detalhe(id1)
        assert s["cod_status_solicitacao"] == C.S_APROVADA_OWNER
        assert s["dono_grupo"] and s["dono_grupo"]["id_usuario_aisn"] == "u_daniela"
    finally:
        limpar_solicitacao(id1)


def test_ativo_inexistente(conectado, usuario):
    with pytest.raises(RegraNegocioError, match="Ativo"):
        request_service.criar_solicitacao(usuario("u_leandro"), C.B_NOMINAL, "nao_existe",
                                          justificativa="x")


def test_rn010_duplicidade(conectado, usuario):
    id1 = request_service.criar_solicitacao(usuario("u_leandro"), C.B_NOMINAL, ICA_ATIVO,
                                            justificativa="1a")
    try:
        with pytest.raises(RegraNegocioError, match="RN-010"):
            request_service.criar_solicitacao(usuario("u_leandro"), C.B_NOMINAL, ICA_ATIVO,
                                              justificativa="2a")
    finally:
        limpar_solicitacao(id1)


def test_rn014_solicitante_nao_autoriza(conectado, usuario):
    id1 = request_service.criar_solicitacao(usuario("u_leandro"), C.B_NOMINAL, TAB_ATIVO,
                                            justificativa="x")
    try:
        with pytest.raises(RegraNegocioError, match="RN-014"):
            approval_service.decidir_autorizacao(id1, "u_leandro", aprovar=True)
    finally:
        limpar_solicitacao(id1)


def test_rn017_owner_nao_aprova_proprio(conectado, usuario):
    id1 = request_service.criar_solicitacao(usuario("u_carlos"), C.B_NOMINAL, CARLOS_ATIVO,
                                            justificativa="x")
    try:
        approval_service.decidir_autorizacao(id1, "u_mariana", aprovar=True)  # gestor autoriza
        with pytest.raises(RegraNegocioError, match="RN-017"):
            approval_service.decidir_aprovacao_owner(id1, "u_carlos", aprovar=True)
    finally:
        limpar_solicitacao(id1)


def test_rf014_tipo_acesso_privilegios(conectado):
    from app.services import grant_executor
    objs = [{"tipo": "SCHEMA", "catalogo": "cat", "schema": "sch", "tabela": None}]
    cmds_rw = grant_executor.montar_comandos(C.OP_CONCESSAO, "x@y.com", objs,
                                             grant_executor._privilegios("LEITURA_ESCRITA"))
    cmds_r = grant_executor.montar_comandos(C.OP_CONCESSAO, "x@y.com", objs,
                                            grant_executor._privilegios("LEITURA"))
    assert any("MODIFY" in c for c in cmds_rw)
    assert not any("MODIFY" in c for c in cmds_r)


def test_grant_por_nivel(conectado):
    from app.services import grant_executor
    cmds_tab = grant_executor.montar_comandos(
        C.OP_CONCESSAO, "mkt_at_x",
        [{"tipo": "TABLE", "catalogo": "cat", "schema": "sch", "tabela": "tb"}], ["SELECT"])
    assert any("ON TABLE cat.sch.tb" in c for c in cmds_tab)
    cmds_sch = grant_executor.montar_comandos(
        C.OP_CONCESSAO, "mkt_at_x",
        [{"tipo": "SCHEMA", "catalogo": "cat", "schema": "sch", "tabela": None}], ["SELECT"])
    assert any("ON SCHEMA cat.sch" in c for c in cmds_sch)


def test_rf024_superior_pode_autorizar(conectado, usuario):
    id1 = request_service.criar_solicitacao(usuario("u_leandro"), C.B_NOMINAL, ICA_ATIVO,
                                            justificativa="rf024")
    try:
        assert "u_roberto" in request_service.superiores("u_leandro")
        approval_service.decidir_autorizacao(id1, "u_roberto", aprovar=True)
        s = request_service.detalhe(id1)
        assert s["cod_status_solicitacao"] == C.S_AUTORIZADA
    finally:
        limpar_solicitacao(id1)


def test_cancelamento(conectado, usuario):
    id1 = request_service.criar_solicitacao(usuario("u_leandro"), C.B_NOMINAL, TAB_ATIVO,
                                            justificativa="x")
    try:
        request_service.cancelar(id1, "u_leandro")
        s = request_service.detalhe(id1)
        assert s["cod_status_solicitacao"] == C.S_CANCELADA
        with pytest.raises(RegraNegocioError):
            request_service.cancelar(id1, "u_leandro")
    finally:
        limpar_solicitacao(id1)

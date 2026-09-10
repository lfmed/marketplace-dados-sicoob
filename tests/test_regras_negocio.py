"""Testes das regras de negócio (RN) e do MODELO ativo-cêntrico polimórfico.
Sem disparar concessão real. Validam que o ativo é o driver e que catálogo/schema/
tabela/domínio são NAVEGADOS nas relações (id_ativo_aisn = PK da origem)."""
import pytest

from app import db
from app import constants as C
from app.config import config
from app.services import request_service, approval_service, catalog_service
from app.services.ativo_scope import objetos_do_ativo
from app.services.request_service import RegraNegocioError
from tests.conftest import limpar_solicitacao

# IDs = PK da entidade de origem (sem prefixo). Owners herdados da iniciativa.
ICA_ATIVO = "ica_ib_nav_gold"                        # tipo 1 (owner u_ana) -> schema mkt_ib_nav_gold
TAB_ATIVO = "tab_ica_ib_nav_gold_dim_cooperado"      # tipo 2 (owner u_ana) -> tabela dim_cooperado
SUB_ATIVO = "sub_ib"                                 # tipo 3 (owner u_ana) -> N schemas
DOM_ATIVO = "dom_canais"                             # tipo 4 (owner u_ana) -> N schemas
CARLOS_ATIVO = "ica_cad_360_gold"                    # tipo 1 (owner u_carlos)


# ---------------- Modelo: ativo é o driver + resolução polimórfica ----------------
def test_id_ativo_e_pk_da_origem(conectado):
    """RN-modelo: id_ativo_aisn É a PK da entidade de origem (ICA), sem coluna denormalizada."""
    a = db.query_one("SELECT * FROM governanca.ativo_aisn WHERE id_ativo_aisn=%s", (ICA_ATIVO,))
    assert a and str(a["cod_tipo_ativo"]) == C.AT_ICA
    # o mesmo id existe em iniciativa_camada_ambiente (relação por igualdade de PK)
    ica = db.query_one("SELECT * FROM governanca.iniciativa_camada_ambiente "
                       "WHERE id_iniciativa_camada_ambiente=%s", (ICA_ATIVO,))
    assert ica is not None
    # e NÃO há mais colunas denormalizadas no ativo
    assert "nome_dominio" not in a and "id_referencia" not in a and "nome_schema" not in a


def test_scope_ica_um_schema(conectado):
    a = db.query_one("SELECT * FROM governanca.ativo_aisn WHERE id_ativo_aisn=%s", (ICA_ATIVO,))
    objs = objetos_do_ativo(a)
    assert len(objs) == 1 and objs[0]["tipo"] == "SCHEMA"
    assert objs[0]["catalogo"] == config.UC_CATALOG and objs[0]["schema"] == "mkt_ib_nav_gold"


def test_scope_tabela_uma_tabela(conectado):
    a = db.query_one("SELECT * FROM governanca.ativo_aisn WHERE id_ativo_aisn=%s", (TAB_ATIVO,))
    objs = objetos_do_ativo(a)
    assert len(objs) == 1 and objs[0]["tipo"] == "TABLE"
    assert objs[0]["schema"] == "mkt_ib_nav_gold" and objs[0]["tabela"] == "dim_cooperado"


def test_scope_dominio_expande(conectado):
    a = db.query_one("SELECT * FROM governanca.ativo_aisn WHERE id_ativo_aisn=%s", (DOM_ATIVO,))
    objs = objetos_do_ativo(a)
    assert len(objs) > 1 and all(o["tipo"] == "SCHEMA" for o in objs)


def test_rn005_catalogo_driver_ativo_com_breadcrumb(conectado):
    """O catálogo lista ATIVOS (driver), todos com owner (RN-005), com breadcrumb e
    rótulo de nível DERIVADOS das relações (não de colunas copiadas)."""
    ativos = catalog_service.listar_ativos()
    assert len(ativos) > 0
    assert all(a["owners"] for a in ativos)
    # o ativo de ICA tem breadcrumb de domínio derivado e rótulo de nível
    ica = next(a for a in ativos if a["id_ativo_aisn"] == ICA_ATIVO)
    assert ica["nome_dominio"] == "Canais e Experiência"
    assert ica["tipo_label"] == C.TIPO_ATIVO_LABEL[C.AT_ICA]


def test_catalogo_filtra_por_dominio_derivado(conectado):
    """Filtro por domínio funciona sobre o domínio DERIVADO polimorficamente."""
    do_dom = catalog_service.listar_ativos(id_dominio="dom_canais")
    assert do_dom and all(a["nome_dominio"] == "Canais e Experiência" for a in do_dom)


# ---------------- Regras de negócio ----------------
def test_rn007_grupo_somente_membro(conectado, usuario):
    with pytest.raises(RegraNegocioError, match="membro"):
        request_service.criar_solicitacao(
            usuario("u_ana"), C.B_GRUPO, ICA_ATIVO,
            id_grupo="grp_risco_credito", justificativa="x")


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
    # LEITURA_ESCRITA gera MODIFY; LEITURA não. (nível SCHEMA)
    from app.services import grant_executor
    objs = [{"tipo": "SCHEMA", "catalogo": "cat", "schema": "sch", "tabela": None}]
    cmds_rw = grant_executor.montar_comandos(C.OP_CONCESSAO, "x@y.com", objs,
                                             grant_executor._privilegios("LEITURA_ESCRITA"))
    cmds_r = grant_executor.montar_comandos(C.OP_CONCESSAO, "x@y.com", objs,
                                            grant_executor._privilegios("LEITURA"))
    assert any("MODIFY" in c for c in cmds_rw)
    assert not any("MODIFY" in c for c in cmds_r)


def test_grant_por_nivel(conectado):
    # TABELA -> GRANT ON TABLE; SCHEMA -> GRANT ON SCHEMA (provisionamento do grupo do ativo)
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

"""Testes das regras de negócio (RN) no modelo ATIVO-cêntrico — sem disparar GRANT."""
import pytest

from app import constants as C
from app.services import request_service, approval_service
from app.services.request_service import RegraNegocioError
from tests.conftest import limpar_solicitacao

INI_ATIVO = "at_ini_ib_nav"                         # ativo de iniciativa (owner u_ana)
TAB_ATIVO = "at_tab_ica_ib_nav_gold_dim_cooperado"  # ativo de tabela (owner u_ana)


def test_rn005_catalogo_so_com_owner(conectado):
    from app.services import catalog_service
    ativos = catalog_service.listar_ativos()
    assert len(ativos) > 0
    assert all(a["owners"] for a in ativos)  # todo ativo listado tem owner


def test_rn007_grupo_somente_membro(conectado, usuario):
    # u_ana NÃO é membro de grupo exploratório -> solicitar p/ grupo deve falhar
    with pytest.raises(RegraNegocioError, match="membro"):
        request_service.criar_solicitacao(
            usuario("u_ana"), C.B_GRUPO, INI_ATIVO,
            id_grupo="grp_risco_credito", justificativa="x")


def test_ativo_inexistente(conectado, usuario):
    with pytest.raises(RegraNegocioError, match="Ativo"):
        request_service.criar_solicitacao(usuario("u_leandro"), C.B_NOMINAL, "at_nao_existe",
                                          justificativa="x")


def test_rn010_duplicidade(conectado, usuario):
    id1 = request_service.criar_solicitacao(usuario("u_leandro"), C.B_NOMINAL, INI_ATIVO,
                                            justificativa="1a")
    try:
        with pytest.raises(RegraNegocioError, match="RN-010"):
            request_service.criar_solicitacao(usuario("u_leandro"), C.B_NOMINAL, INI_ATIVO,
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
    # u_carlos é owner do ativo da iniciativa ini_cad_360; cria nominal p/ si mesmo
    id1 = request_service.criar_solicitacao(usuario("u_carlos"), C.B_NOMINAL, "at_ini_cad_360",
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
    # TABELA -> GRANT ON TABLE; SCHEMA -> GRANT ON SCHEMA (RN-003 superada pelo ativo)
    from app.services import grant_executor
    cmds_tab = grant_executor.montar_comandos(
        C.OP_CONCESSAO, "x@y.com",
        [{"tipo": "TABLE", "catalogo": "cat", "schema": "sch", "tabela": "tb"}], ["SELECT"])
    assert any("ON TABLE cat.sch.tb" in c for c in cmds_tab)
    cmds_sch = grant_executor.montar_comandos(
        C.OP_CONCESSAO, "x@y.com",
        [{"tipo": "SCHEMA", "catalogo": "cat", "schema": "sch", "tabela": None}], ["SELECT"])
    assert any("ON SCHEMA cat.sch" in c for c in cmds_sch)


def test_rf024_superior_pode_autorizar(conectado, usuario):
    id1 = request_service.criar_solicitacao(usuario("u_leandro"), C.B_NOMINAL, INI_ATIVO,
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

"""Testes das regras de negócio (RN) — não disparam GRANT (validação antes da efetivação)."""
import pytest

from app import constants as C
from app.services import request_service, approval_service
from app.services.request_service import RegraNegocioError
from tests.conftest import limpar_solicitacao

INI = "ini_ib_nav"           # owner u_ana
AMB = "amb_prod"
ICAS = ["ica_ib_nav_silver", "ica_ib_nav_gold"]


def test_rn005_catalogo_so_com_owner(conectado):
    from app.services import catalog_service
    inis = catalog_service.listar_iniciativas()
    assert len(inis) > 0
    # toda iniciativa listada tem owner preenchido
    assert all(i["owners"] for i in inis)


def test_rn007_grupo_somente_membro(conectado, usuario):
    # u_ana NÃO é membro de nenhum grupo -> solicitar p/ grupo deve falhar
    with pytest.raises(RegraNegocioError, match="membro"):
        request_service.criar_solicitacao(
            usuario("u_ana"), C.B_GRUPO, INI, AMB, ICAS,
            id_grupo="grp_risco_credito", justificativa="x")


def test_rn004_exige_camada(conectado, usuario):
    with pytest.raises(RegraNegocioError, match="camada"):
        request_service.criar_solicitacao(usuario("u_leandro"), C.B_NOMINAL, INI, AMB, [], justificativa="x")


def test_rn010_duplicidade(conectado, usuario):
    id1 = request_service.criar_solicitacao(usuario("u_leandro"), C.B_NOMINAL, INI, AMB,
                                            ["ica_ib_nav_silver"], justificativa="1a")
    try:
        with pytest.raises(RegraNegocioError, match="RN-010"):
            request_service.criar_solicitacao(usuario("u_leandro"), C.B_NOMINAL, INI, AMB,
                                              ["ica_ib_nav_silver"], justificativa="2a")
    finally:
        limpar_solicitacao(id1)


def test_rn014_solicitante_nao_autoriza(conectado, usuario):
    id1 = request_service.criar_solicitacao(usuario("u_leandro"), C.B_NOMINAL, INI, AMB,
                                            ["ica_ib_nav_gold"], justificativa="x")
    try:
        # u_leandro tentando autorizar a própria solicitação
        with pytest.raises(RegraNegocioError, match="RN-014"):
            approval_service.decidir_autorizacao(id1, "u_leandro", aprovar=True)
    finally:
        limpar_solicitacao(id1)


def test_rn017_owner_nao_aprova_proprio(conectado, usuario):
    # u_carlos é owner de ini_cad_360; cria solicitação nominal p/ si mesmo lá
    id1 = request_service.criar_solicitacao(usuario("u_carlos"), C.B_NOMINAL, "ini_cad_360", AMB,
                                            ["ica_cad_360_gold"], justificativa="x")
    try:
        approval_service.decidir_autorizacao(id1, "u_mariana", aprovar=True)  # gestor autoriza
        with pytest.raises(RegraNegocioError, match="RN-017"):
            approval_service.decidir_aprovacao_owner(id1, "u_carlos", aprovar=True)
    finally:
        limpar_solicitacao(id1)


def test_rf014_tipo_acesso_privilegios(conectado):
    # LEITURA_ESCRITA deve gerar MODIFY; LEITURA não.
    from app.services import grant_executor
    schemas = [{"nome_catalogo": "cat", "nome_schema": "sch"}]
    cmds_rw = grant_executor.montar_comandos(C.OP_CONCESSAO, "x@y.com", schemas,
                                             grant_executor._privilegios("LEITURA_ESCRITA"))
    cmds_r = grant_executor.montar_comandos(C.OP_CONCESSAO, "x@y.com", schemas,
                                            grant_executor._privilegios("LEITURA"))
    assert any("MODIFY" in c for c in cmds_rw)
    assert not any("MODIFY" in c for c in cmds_r)


def test_rf024_superior_pode_autorizar(conectado, usuario):
    # u_leandro -> gestor u_mariana -> superior u_roberto. Roberto (superior) pode autorizar.
    id1 = request_service.criar_solicitacao(usuario("u_leandro"), C.B_NOMINAL, INI, AMB,
                                            ["ica_ib_nav_silver"], justificativa="rf024")
    try:
        assert "u_roberto" in request_service.superiores("u_leandro")
        approval_service.decidir_autorizacao(id1, "u_roberto", aprovar=True)
        s = request_service.detalhe(id1)
        assert s["cod_status_solicitacao"] == C.S_AUTORIZADA
    finally:
        limpar_solicitacao(id1)


def test_cancelamento(conectado, usuario):
    id1 = request_service.criar_solicitacao(usuario("u_leandro"), C.B_NOMINAL, INI, AMB,
                                            ["ica_ib_nav_silver"], justificativa="x")
    try:
        request_service.cancelar(id1, "u_leandro")
        s = request_service.detalhe(id1)
        assert s["cod_status_solicitacao"] == C.S_CANCELADA
        # cancelar de novo falha
        with pytest.raises(RegraNegocioError):
            request_service.cancelar(id1, "u_leandro")
    finally:
        limpar_solicitacao(id1)

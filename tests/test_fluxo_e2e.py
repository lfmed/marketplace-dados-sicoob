"""Teste ponta a ponta com GRANT/REVOKE REAIS no Unity Catalog.
Lento (usa o SQL warehouse). solicitar -> autorizar -> aprovar -> efetivar ->
verificar grant -> revogar -> verificar."""
import pytest

from app import db, constants as C
from app.config import config
from app.services import request_service, approval_service, access_service, audit_service
from scripts.uc_sql import run_sql
from tests.conftest import limpar_solicitacao

INI = "ini_ib_nav"
AMB = "amb_prod"
ICAS = ["ica_ib_nav_silver", "ica_ib_nav_gold"]
EMAIL = "leandro.medeiros@databricks.com"
SCHEMA = "mkt_ib_nav_gold"


def _grant_presente(schema, principal):
    cat = config.UC_CATALOG
    _s, rows = run_sql(f"SHOW GRANTS ON SCHEMA {cat}.{schema}", warehouse_id=config.WAREHOUSE_ID)
    return any(principal in (r[0] or "") and "SELECT" in (r[1] or "") for r in rows)


def test_fluxo_nominal_grant_real(conectado, usuario):
    id_sol = request_service.criar_solicitacao(usuario("u_leandro"), C.B_NOMINAL, INI, AMB, ICAS,
                                              justificativa="e2e pytest")
    try:
        approval_service.decidir_autorizacao(id_sol, "u_mariana", aprovar=True)
        approval_service.decidir_aprovacao_owner(id_sol, "u_ana", aprovar=True)

        ac = db.query_one("SELECT * FROM gestao_acesso.acesso WHERE id_solicitacao_acesso=%s", (id_sol,))
        assert ac["cod_status_acesso"] == C.A_AGUARDANDO_EFETIVACAO

        access_service.processar_execucoes_pendentes()
        ac = db.query_one("SELECT * FROM gestao_acesso.acesso WHERE id_acesso=%s", (ac["id_acesso"],))
        assert ac["cod_status_acesso"] == C.A_EFETIVADO, ac["cod_status_acesso"]
        assert _grant_presente(SCHEMA, EMAIL), "GRANT não encontrado no UC"

        # revogação pelo owner
        access_service.solicitar_revogacao(ac["id_acesso"], "u_ana", justificativa="fim e2e")
        access_service.processar_execucoes_pendentes()
        ac = db.query_one("SELECT * FROM gestao_acesso.acesso WHERE id_acesso=%s", (ac["id_acesso"],))
        assert ac["cod_status_acesso"] == C.A_REVOGADO
        assert not _grant_presente(SCHEMA, EMAIL), "GRANT ainda presente após revogação"

        # RF-081..088: o histórico da solicitação deve trazer os eventos do ciclo de vida
        # do acesso (efetivação e revogação) com data — não só os da solicitação.
        eventos = {e["cod_evento"]: e for e in audit_service.eventos_da_solicitacao(id_sol)}
        assert C.EV_EFETIVADO in eventos, "evento de efetivação ausente no histórico"
        assert C.EV_REVOGADO in eventos, "evento de revogação ausente no histórico"
        assert eventos[C.EV_REVOGADO]["datahora_evento"] is not None, "data da revogação ausente"
    finally:
        # limpa grants residuais e dados
        cat = config.UC_CATALOG
        for sch in ("mkt_ib_nav_gold", "mkt_ib_nav_silver"):
            try:
                run_sql(f"REVOKE SELECT, USE SCHEMA ON SCHEMA {cat}.{sch} FROM `{EMAIL}`",
                        warehouse_id=config.WAREHOUSE_ID)
            except Exception:
                pass
        limpar_solicitacao(id_sol)

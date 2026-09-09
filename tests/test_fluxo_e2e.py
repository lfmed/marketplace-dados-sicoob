"""Teste ponta a ponta ATIVO-cêntrico com GRANT/REVOKE REAIS no Unity Catalog.
Cobre concessão por NÍVEL: ativo de TABELA (GRANT ON TABLE) e de INICIATIVA (ON SCHEMA).
Lento (usa o SQL warehouse)."""
import time
import pytest

from app import db, constants as C
from app.config import config
from app.services import request_service, approval_service, access_service, audit_service
from scripts.uc_sql import run_sql
from tests.conftest import limpar_solicitacao

EMAIL = "leandro.medeiros@databricks.com"
TAB_ATIVO = "at_tab_ica_ib_nav_gold_dim_cooperado"
INI_ATIVO = "at_ini_ib_nav"


def _grant_presente(obj_sql, principal):
    _s, rows = run_sql(f"SHOW GRANTS ON {obj_sql}", warehouse_id=config.WAREHOUSE_ID)
    return any(principal in (r[0] or "") and "SELECT" in (r[1] or "") for r in rows)


def _aguarda_status(id_acesso, alvo, tentativas=12):
    """Processa execuções e aguarda o acesso atingir o status alvo (tolera worker do app)."""
    for _ in range(tentativas):
        access_service.processar_execucoes_pendentes()
        ac = db.query_one("SELECT * FROM gestao_acesso.acesso WHERE id_acesso=%s", (id_acesso,))
        if ac["cod_status_acesso"] == alvo:
            return ac
        time.sleep(3)
    return db.query_one("SELECT * FROM gestao_acesso.acesso WHERE id_acesso=%s", (id_acesso,))


def _fluxo(usuario, id_ativo, obj_sql):
    id_sol = request_service.criar_solicitacao(usuario("u_leandro"), C.B_NOMINAL, id_ativo,
                                              justificativa="e2e pytest")
    try:
        approval_service.decidir_autorizacao(id_sol, "u_mariana", aprovar=True)
        approval_service.decidir_aprovacao_owner(id_sol, "u_ana", aprovar=True)
        ac = db.query_one("SELECT * FROM gestao_acesso.acesso WHERE id_solicitacao_acesso=%s", (id_sol,))
        ac = _aguarda_status(ac["id_acesso"], C.A_EFETIVADO)
        assert ac["cod_status_acesso"] == C.A_EFETIVADO, ac["cod_status_acesso"]
        assert _grant_presente(obj_sql, EMAIL), "GRANT não encontrado no UC"

        access_service.solicitar_revogacao(ac["id_acesso"], "u_ana", justificativa="fim e2e")
        ac = _aguarda_status(ac["id_acesso"], C.A_REVOGADO)
        assert ac["cod_status_acesso"] == C.A_REVOGADO

        # RF-081..088: histórico traz efetivação e revogação com data
        eventos = {e["cod_evento"]: e for e in audit_service.eventos_da_solicitacao(id_sol)}
        assert C.EV_EFETIVADO in eventos and C.EV_REVOGADO in eventos
        assert eventos[C.EV_REVOGADO]["datahora_evento"] is not None
        return id_sol
    finally:
        limpar_solicitacao(id_sol)


def test_fluxo_ativo_tabela_grant_real(conectado, usuario):
    """Ativo de TABELA → GRANT/REVOKE ON TABLE reais."""
    run_sql("SELECT 1", warehouse_id=config.WAREHOUSE_ID)  # aquece o warehouse
    cat = config.UC_CATALOG
    try:
        _fluxo(usuario, TAB_ATIVO, f"TABLE {cat}.mkt_ib_nav_gold.dim_cooperado")
    finally:
        try:
            run_sql(f"REVOKE SELECT ON TABLE {cat}.mkt_ib_nav_gold.dim_cooperado FROM `{EMAIL}`",
                    warehouse_id=config.WAREHOUSE_ID)
        except Exception:
            pass


def test_fluxo_ativo_iniciativa_grant_real(conectado, usuario):
    """Ativo de INICIATIVA → GRANT/REVOKE ON SCHEMA reais (expande p/ schemas)."""
    run_sql("SELECT 1", warehouse_id=config.WAREHOUSE_ID)
    cat = config.UC_CATALOG
    try:
        _fluxo(usuario, INI_ATIVO, f"SCHEMA {cat}.mkt_ib_nav_gold")
    finally:
        for sch in ("mkt_ib_nav_gold", "mkt_ib_nav_silver"):
            try:
                run_sql(f"REVOKE SELECT, USE SCHEMA ON SCHEMA {cat}.{sch} FROM `{EMAIL}`",
                        warehouse_id=config.WAREHOUSE_ID)
            except Exception:
                pass

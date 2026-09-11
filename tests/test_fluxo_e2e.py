"""Ponta a ponta do modelo ATIVO-cêntrico (oficial) com CONCESSÃO POR ASSOCIAÇÃO A GRUPO.
O acesso inclui o beneficiário no GRUPO DO ATIVO (real via SCIM) e revoga removendo-o.
Cobre ativo de ICA (schema) e de TABELA. Lento (warehouse + SCIM). Requer perfil com
permissão de gerenciar grupos. Schemas parametrizados ({APP}/{ACC})."""
import time
import pytest

from app import db, constants as C
from app.config import config
from app.db import get_client
from app.schemas import ACC, APP
from app.services import request_service, approval_service, access_service, audit_service
from scripts.uc_sql import run_sql
from tests.conftest import limpar_solicitacao

EMAIL = "leandro.medeiros@databricks.com"
ICA_ATIVO = "ica_ib_nav_gold"                    # owner u_ana -> schema mkt_ib_nav_gold
TAB_ATIVO = "tab_ica_ib_nav_gold_dim_cooperado"  # owner u_ana -> tabela dim_cooperado


def _grupo_do_ativo(id_ativo):
    row = db.query_one(
        f"SELECT nome_grupo_ativo AS nome_grupo FROM {ACC}.ativo_aisn WHERE id_ativo_aisn=%s",
        (id_ativo,))
    return row["nome_grupo"] if row else None


def _uid(w, email):
    us = list(w.users.list(filter=f'userName eq "{email}"'))
    return us[0].id if us else None


def _e_membro(nome_grupo, email):
    w = get_client()
    gs = list(w.groups.list(filter=f'displayName eq "{nome_grupo}"'))
    if not gs:
        return None
    uid = _uid(w, email)
    if not uid:
        return None
    g = w.groups.get(gs[0].id)
    return any(m.value == uid for m in (g.members or []))


def _grupo_tem_select(obj_sql, nome_grupo):
    try:
        _s, rows = run_sql(f"SHOW GRANTS ON {obj_sql}", warehouse_id=config.WAREHOUSE_ID)
        return any(nome_grupo in (r[0] or "") and "SELECT" in (r[1] or "") for r in rows)
    except Exception:
        return False


def _limpar_membership(nome_grupo, email):
    try:
        from databricks.sdk.service import iam
        w = get_client()
        gs = list(w.groups.list(filter=f'displayName eq "{nome_grupo}"'))
        uid = _uid(w, email)
        if gs and uid:
            w.groups.patch(gs[0].id,
                           operations=[iam.Patch(op=iam.PatchOp.REMOVE, path=f'members[value eq "{uid}"]')],
                           schemas=[iam.PatchSchema.URN_IETF_PARAMS_SCIM_API_MESSAGES_2_0_PATCH_OP])
    except Exception:
        pass


def _aguarda_status(id_acesso, alvo, tentativas=12):
    for _ in range(tentativas):
        access_service.processar_execucoes_pendentes()
        ac = db.query_one(f"SELECT * FROM {APP}.acesso WHERE id_acesso=%s", (id_acesso,))
        if ac["cod_status_acesso"] == alvo:
            return ac
        time.sleep(3)
    return db.query_one(f"SELECT * FROM {APP}.acesso WHERE id_acesso=%s", (id_acesso,))


def _fluxo_associacao(usuario, id_ativo, obj_sql):
    nome_grupo = _grupo_do_ativo(id_ativo)
    assert nome_grupo, "ativo sem grupo definido"
    _limpar_membership(nome_grupo, EMAIL)

    id_sol = request_service.criar_solicitacao(usuario("u_leandro"), C.B_NOMINAL, id_ativo,
                                              justificativa="e2e pytest")
    try:
        approval_service.decidir_autorizacao(id_sol, "u_mariana", aprovar=True)   # gestor
        approval_service.decidir_aprovacao_owner(id_sol, "u_ana", aprovar=True)    # owner do ativo
        ac = db.query_one(f"SELECT * FROM {APP}.acesso WHERE id_solicitacao_acesso=%s", (id_sol,))
        ac = _aguarda_status(ac["id_acesso"], C.A_EFETIVADO)
        assert ac["cod_status_acesso"] == C.A_EFETIVADO, ac["cod_status_acesso"]

        assert _e_membro(nome_grupo, EMAIL) is True, f"{EMAIL} não foi associado ao {nome_grupo}"
        tem = _grupo_tem_select(obj_sql, nome_grupo)
        print(f"[info] grupo {nome_grupo} tem SELECT em {obj_sql}: {tem} "
              f"(soft — depende de account groups no UC)")

        access_service.solicitar_revogacao(ac["id_acesso"], "u_ana", justificativa="fim e2e")
        ac = _aguarda_status(ac["id_acesso"], C.A_REVOGADO)
        assert ac["cod_status_acesso"] == C.A_REVOGADO
        assert _e_membro(nome_grupo, EMAIL) is False, f"{EMAIL} não foi removido do {nome_grupo}"

        eventos = {e["cod_evento"]: e for e in audit_service.eventos_da_solicitacao(id_sol)}
        assert C.EV_EFETIVADO in eventos and C.EV_REVOGADO in eventos
        assert eventos[C.EV_REVOGADO]["datahora_evento"] is not None
        return id_sol
    finally:
        _limpar_membership(nome_grupo, EMAIL)
        limpar_solicitacao(id_sol)


def test_fluxo_ativo_ica_associacao(conectado, usuario):
    run_sql("SELECT 1", warehouse_id=config.WAREHOUSE_ID)
    cat = config.UC_CATALOG
    _fluxo_associacao(usuario, ICA_ATIVO, f"SCHEMA {cat}.mkt_ib_nav_gold")


def test_fluxo_ativo_tabela_associacao(conectado, usuario):
    run_sql("SELECT 1", warehouse_id=config.WAREHOUSE_ID)
    cat = config.UC_CATALOG
    _fluxo_associacao(usuario, TAB_ATIVO, f"TABLE {cat}.mkt_ib_nav_gold.dim_cooperado")

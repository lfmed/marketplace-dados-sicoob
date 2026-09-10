"""Teste ponta a ponta do modelo ATIVO-cêntrico com CONCESSÃO POR ASSOCIAÇÃO A GRUPO.
O acesso é concedido incluindo o beneficiário no GRUPO DO ATIVO (real, via SCIM) e
revogado removendo-o. Cobre ativo de ICA (1 schema) e de TABELA (1 tabela).
Lento (usa o SQL warehouse + SCIM). Requer perfil com permissão de gerenciar grupos."""
import time
import pytest

from app import db, constants as C
from app.config import config
from app.db import get_client
from app.services import request_service, approval_service, access_service, audit_service
from scripts.uc_sql import run_sql
from tests.conftest import limpar_solicitacao

EMAIL = "leandro.medeiros@databricks.com"
ICA_ATIVO = "ica_ib_nav_gold"                    # owner u_ana -> schema mkt_ib_nav_gold
TAB_ATIVO = "tab_ica_ib_nav_gold_dim_cooperado"  # owner u_ana -> tabela dim_cooperado


def _grupo_do_ativo(id_ativo):
    row = db.query_one(
        """SELECT g.nome_grupo FROM governanca.ativo_aisn a
             JOIN governanca.grupo_acesso g ON g.id_grupo_acesso=a.id_grupo_acesso
            WHERE a.id_ativo_aisn=%s""", (id_ativo,))
    return row["nome_grupo"] if row else None


def _uid(w, email):
    us = list(w.users.list(filter=f'userName eq "{email}"'))
    return us[0].id if us else None


def _e_membro(nome_grupo, email):
    """True/False se `email` é membro do grupo; None se grupo/usuário não resolvido."""
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
    """Best-effort: remove o usuário do grupo do ativo (idempotente)."""
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
    """Processa execuções e aguarda o acesso atingir o status alvo (tolera worker do app)."""
    for _ in range(tentativas):
        access_service.processar_execucoes_pendentes()
        ac = db.query_one("SELECT * FROM gestao_acesso.acesso WHERE id_acesso=%s", (id_acesso,))
        if ac["cod_status_acesso"] == alvo:
            return ac
        time.sleep(3)
    return db.query_one("SELECT * FROM gestao_acesso.acesso WHERE id_acesso=%s", (id_acesso,))


def _fluxo_associacao(usuario, id_ativo, obj_sql):
    nome_grupo = _grupo_do_ativo(id_ativo)
    assert nome_grupo, "ativo sem grupo definido"
    if _e_membro(nome_grupo, EMAIL) is None:
        # grupo ainda não existe (será criado na concessão) — ok; garante estado limpo
        _limpar_membership(nome_grupo, EMAIL)

    id_sol = request_service.criar_solicitacao(usuario("u_leandro"), C.B_NOMINAL, id_ativo,
                                              justificativa="e2e pytest")
    try:
        approval_service.decidir_autorizacao(id_sol, "u_mariana", aprovar=True)   # gestor
        approval_service.decidir_aprovacao_owner(id_sol, "u_ana", aprovar=True)    # owner do ativo
        ac = db.query_one("SELECT * FROM gestao_acesso.acesso WHERE id_solicitacao_acesso=%s", (id_sol,))
        ac = _aguarda_status(ac["id_acesso"], C.A_EFETIVADO)
        assert ac["cod_status_acesso"] == C.A_EFETIVADO, ac["cod_status_acesso"]

        # CORE do modelo: o beneficiário foi incluído no GRUPO DO ATIVO (associação real)
        assert _e_membro(nome_grupo, EMAIL) is True, f"{EMAIL} não foi associado ao {nome_grupo}"
        # Provisionamento do grupo nos objetos (best-effort; depende de account groups — D-009)
        tem = _grupo_tem_select(obj_sql, nome_grupo)
        print(f"[info] grupo {nome_grupo} tem SELECT em {obj_sql}: {tem} "
              f"(soft — depende de account groups no UC)")

        # Revogação -> remove a associação
        access_service.solicitar_revogacao(ac["id_acesso"], "u_ana", justificativa="fim e2e")
        ac = _aguarda_status(ac["id_acesso"], C.A_REVOGADO)
        assert ac["cod_status_acesso"] == C.A_REVOGADO
        assert _e_membro(nome_grupo, EMAIL) is False, f"{EMAIL} não foi removido do {nome_grupo}"

        # RF-081..088: histórico traz efetivação e revogação com data
        eventos = {e["cod_evento"]: e for e in audit_service.eventos_da_solicitacao(id_sol)}
        assert C.EV_EFETIVADO in eventos and C.EV_REVOGADO in eventos
        assert eventos[C.EV_REVOGADO]["datahora_evento"] is not None
        return id_sol
    finally:
        _limpar_membership(nome_grupo, EMAIL)
        limpar_solicitacao(id_sol)


def test_fluxo_ativo_ica_associacao(conectado, usuario):
    """Ativo de ICA (1 schema) → associação/desassociação real no grupo do ativo."""
    run_sql("SELECT 1", warehouse_id=config.WAREHOUSE_ID)  # aquece o warehouse
    cat = config.UC_CATALOG
    _fluxo_associacao(usuario, ICA_ATIVO, f"SCHEMA {cat}.mkt_ib_nav_gold")


def test_fluxo_ativo_tabela_associacao(conectado, usuario):
    """Ativo de TABELA (1 tabela) → associação/desassociação real no grupo do ativo."""
    run_sql("SELECT 1", warehouse_id=config.WAREHOUSE_ID)
    cat = config.UC_CATALOG
    _fluxo_associacao(usuario, TAB_ATIVO, f"TABLE {cat}.mkt_ib_nav_gold.dim_cooperado")

#!/usr/bin/env python3
"""Valida que o WORKER DO APP PUBLICADO (rodando como o service principal, agora admin)
consegue EFETIVAR a concessão por associação a grupo — SEM processar nada localmente.
Cria a solicitação, aprova (gestor+owner) e apenas AGUARDA o worker publicado processar.
Uso: APP_DISABLE_WORKER=true python -m scripts.verify_deployed_worker
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("APP_DISABLE_WORKER", "true")  # NÃO processa localmente

from app import db, constants as C  # noqa: E402
from app.db import get_client  # noqa: E402
from app.services import request_service, approval_service, access_service  # noqa: E402
from tests.conftest import limpar_solicitacao  # noqa: E402

EMAIL = "leandro.medeiros@databricks.com"
ICA_ATIVO = "ica_ib_nav_gold"


def _grupo(id_ativo):
    from app.schemas import ACC
    r = db.query_one(f"SELECT nome_grupo_ativo AS nome_grupo FROM {ACC}.ativo_aisn WHERE id_ativo_aisn=%s",
                     (id_ativo,))
    return r["nome_grupo"] if r else None


def _e_membro(nome_grupo, email):
    w = get_client()
    gs = list(w.groups.list(filter=f'displayName eq "{nome_grupo}"'))
    if not gs:
        return None
    us = list(w.users.list(filter=f'userName eq "{email}"'))
    if not us:
        return None
    g = w.groups.get(gs[0].id)
    return any(m.value == us[0].id for m in (g.members or []))


def _espera(id_acesso, alvo, seg=120):
    """Aguarda SEM processar localmente — quem processa é o worker publicado (SP)."""
    fim = time.time() + seg
    while time.time() < fim:
        ac = db.query_one("SELECT cod_status_acesso FROM marketplace_app.acesso WHERE id_acesso=%s", (id_acesso,))
        if ac and ac["cod_status_acesso"] == alvo:
            return True
        time.sleep(5)
    return False


def main():
    nome_grupo = _grupo(ICA_ATIVO)
    u = lambda uid: db.query_one("SELECT * FROM governanca.usuario_aisn WHERE id_usuario_aisn=%s", (uid,))  # noqa: E731 (schema default)
    id_sol = request_service.criar_solicitacao(u("u_leandro"), C.B_NOMINAL, ICA_ATIVO, justificativa="verify SP worker")
    try:
        approval_service.decidir_autorizacao(id_sol, "u_mariana", aprovar=True)
        approval_service.decidir_aprovacao_owner(id_sol, "u_ana", aprovar=True)
        ac = db.query_one("SELECT * FROM marketplace_app.acesso WHERE id_solicitacao_acesso=%s", (id_sol,))
        print(f"acesso {ac['id_acesso']} criado; aguardando WORKER PUBLICADO efetivar...")
        ok = _espera(ac["id_acesso"], C.A_EFETIVADO)
        print("EFETIVADO pelo worker publicado:", ok)
        print("membro do grupo do ativo:", _e_membro(nome_grupo, EMAIL))
        # mostra o comando registrado pela execução (quem/como efetivou)
        ex = db.query_one("""SELECT cod_status_execucao, desc_comando, desc_erro FROM marketplace_app.execucao_tecnica
                              WHERE id_acesso=%s ORDER BY datahora_inicio DESC LIMIT 1""", (ac["id_acesso"],))
        print("execucao:", ex["cod_status_execucao"], "| erro:", ex["desc_erro"])
        print("comando:", (ex["desc_comando"] or "")[:300])

        access_service.solicitar_revogacao(ac["id_acesso"], "u_ana", justificativa="fim verify")
        ok_r = _espera(ac["id_acesso"], C.A_REVOGADO)
        print("REVOGADO pelo worker publicado:", ok_r)
        print("membro após revogação:", _e_membro(nome_grupo, EMAIL))
    finally:
        # garante limpeza da associação e da solicitação
        try:
            from databricks.sdk.service import iam
            w = get_client()
            gs = list(w.groups.list(filter=f'displayName eq "{nome_grupo}"'))
            us = list(w.users.list(filter=f'userName eq "{EMAIL}"'))
            if gs and us:
                w.groups.patch(gs[0].id,
                               operations=[iam.Patch(op=iam.PatchOp.REMOVE, path=f'members[value eq "{us[0].id}"]')],
                               schemas=[iam.PatchSchema.URN_IETF_PARAMS_SCIM_API_MESSAGES_2_0_PATCH_OP])
        except Exception:
            pass
        limpar_solicitacao(id_sol)
        print("limpeza ok.")


if __name__ == "__main__":
    main()

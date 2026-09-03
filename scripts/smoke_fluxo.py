#!/usr/bin/env python3
"""Smoke test do fluxo completo com GRANT REAL no Unity Catalog.
solicitar -> autorizar (gestor) -> aprovar (owner) -> efetivar -> verificar grant ->
revogar -> verificar. Limpa os dados criados ao final.
Uso: DATABRICKS_CONFIG_PROFILE=DEFAULT python3 scripts/smoke_fluxo.py
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import db
from app import constants as C
from app.services import request_service, approval_service, access_service
from scripts.uc_sql import run_sql

SOLIC = "u_leandro"           # solicitante (e-mail real -> grant verificável)
GESTOR = "u_mariana"
OWNER = "u_ana"               # owner de ini_ib_nav
INI = "ini_ib_nav"
AMB = "amb_prod"
ICAS = ["ica_ib_nav_silver", "ica_ib_nav_gold"]
EMAIL = "leandro.medeiros@databricks.com"
SCHEMA_GOLD = "mkt_ib_nav_gold"


def grants_contem(schema, principal):
    cat = db.query_one("SELECT nome_catalogo FROM governanca.iniciativa_camada_ambiente WHERE nome_schema=%s", (schema,))["nome_catalogo"]
    _s, rows = run_sql(f"SHOW GRANTS ON SCHEMA {cat}.{schema}")
    return any(principal in (r[0] or "") and "SELECT" in (r[1] or "") for r in rows)


def cleanup(id_sol):
    ac = db.query_one("SELECT id_acesso FROM gestao_acesso.acesso WHERE id_solicitacao_acesso=%s", (id_sol,))
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            if ac:
                aid = ac["id_acesso"]
                cur.execute("DELETE FROM gestao_acesso.execucao_tecnica WHERE id_acesso=%s", (aid,))
                cur.execute("DELETE FROM gestao_acesso.revogacao_acesso WHERE id_acesso=%s", (aid,))
                cur.execute("DELETE FROM gestao_acesso.acesso_camada WHERE id_acesso=%s", (aid,))
                cur.execute("DELETE FROM gestao_acesso.evento_ciclo_vida WHERE id_acesso=%s", (aid,))
                cur.execute("DELETE FROM gestao_acesso.acesso WHERE id_acesso=%s", (aid,))
            cur.execute("DELETE FROM gestao_acesso.evento_ciclo_vida WHERE id_solicitacao_acesso=%s", (id_sol,))
            cur.execute("DELETE FROM gestao_acesso.autorizacao_hierarquica WHERE id_solicitacao_acesso=%s", (id_sol,))
            cur.execute("DELETE FROM gestao_acesso.aprovacao_owner WHERE id_solicitacao_acesso=%s", (id_sol,))
            cur.execute("DELETE FROM gestao_acesso.solicitacao_camada WHERE id_solicitacao_acesso=%s", (id_sol,))
            cur.execute("DELETE FROM gestao_acesso.solicitacao_acesso WHERE id_solicitacao_acesso=%s", (id_sol,))


def main():
    ok = True
    # limpa grant residual e qualquer solicitação anterior deste beneficiário/iniciativa
    solicitante = db.query_one("SELECT * FROM governanca.usuario_aisn WHERE id_usuario_aisn=%s", (SOLIC,))
    print("1) Criar solicitação (nominal, 2 camadas)")
    id_sol = request_service.criar_solicitacao(solicitante, C.B_NOMINAL, INI, AMB, ICAS,
                                               justificativa="smoke test")
    print("   id:", id_sol)

    print("2) Autorização do gestor")
    approval_service.decidir_autorizacao(id_sol, GESTOR, aprovar=True)

    print("3) Aprovação do owner (cria acesso)")
    approval_service.decidir_aprovacao_owner(id_sol, OWNER, aprovar=True)
    ac = db.query_one("SELECT * FROM gestao_acesso.acesso WHERE id_solicitacao_acesso=%s", (id_sol,))
    assert ac["cod_status_acesso"] == C.A_AGUARDANDO_EFETIVACAO, ac["cod_status_acesso"]
    print("   acesso:", ac["id_acesso"], ac["cod_status_acesso"])

    print("4) Worker efetiva (GRANT real)")
    n = access_service.processar_execucoes_pendentes()
    ac = db.query_one("SELECT * FROM gestao_acesso.acesso WHERE id_acesso=%s", (ac["id_acesso"],))
    print("   processadas:", n, "| status:", ac["cod_status_acesso"])
    if ac["cod_status_acesso"] != C.A_EFETIVADO:
        ex = db.query_one("SELECT desc_erro FROM gestao_acesso.execucao_tecnica WHERE id_acesso=%s ORDER BY datahora_inicio DESC LIMIT 1", (ac["id_acesso"],))
        print("   ERRO:", ex)
        ok = False

    print("5) Verifica GRANT real no UC")
    tem = grants_contem(SCHEMA_GOLD, EMAIL)
    print("   grant presente:", tem); ok = ok and tem

    print("6) Owner solicita revogação")
    access_service.solicitar_revogacao(ac["id_acesso"], OWNER, justificativa="fim do smoke")
    n = access_service.processar_execucoes_pendentes()
    ac = db.query_one("SELECT * FROM gestao_acesso.acesso WHERE id_acesso=%s", (ac["id_acesso"],))
    print("   processadas:", n, "| status:", ac["cod_status_acesso"])
    ok = ok and ac["cod_status_acesso"] == C.A_REVOGADO

    print("7) Verifica revogação")
    tem = grants_contem(SCHEMA_GOLD, EMAIL)
    print("   grant ainda presente:", tem); ok = ok and not tem

    print("8) Cleanup")
    cleanup(id_sol)
    print("\nRESULTADO:", "✅ OK" if ok else "❌ FALHOU")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Concede ao service principal do App as permissões UC de PROVISIONAMENTO: USE CATALOG +
MANAGE nos schemas de dados (mkt_*), para o app fazer GRANT do grupo do ativo nesses objetos.

Necessário APENAS quando PROVISION_GROUP_GRANT=true (dev/demo). Em PRODUÇÃO a concessão é
só-membership (o Motor já concede o GRANT do grupo), então o SP do app NÃO precisa de MANAGE —
precisa de: gerente dos account groups (associação de membros), role no Lakebase, CAN_USE no
warehouse e SELECT nas tabelas Delta de origem (ver docs/DEPLOY.md §4).

Uso: DATABRICKS_CONFIG_PROFILE=DEFAULT python3 scripts/grant_app_sp.py <sp_client_id>
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import config
from app import db
from app.schemas import GOV
from scripts.uc_sql import run_sql


def main(sp):
    cat = config.UC_CATALOG
    # MANAGE no catálogo permite ao SP conceder USE CATALOG (provisionamento do grupo, dev).
    print(f"GRANT USE CATALOG, MANAGE ON CATALOG {cat} TO {sp}")
    run_sql(f"GRANT USE CATALOG, MANAGE ON CATALOG {cat} TO `{sp}`", warehouse_id=config.WAREHOUSE_ID)
    # Os schemas de dados alvo vêm de tabela_aisn (única com o alvo UC no modelo oficial).
    schemas = [r["nome_schema"] for r in db.query(
        f"SELECT DISTINCT nome_schema FROM {GOV}.tabela_aisn "
        "WHERE nome_schema IS NOT NULL ORDER BY nome_schema")]
    for s in schemas:
        run_sql(f"GRANT USE SCHEMA, MANAGE ON SCHEMA {cat}.{s} TO `{sp}`",
                warehouse_id=config.WAREHOUSE_ID)
    print(f"MANAGE concedido em {len(schemas)} schemas de dados ao SP {sp} "
          f"(provisionamento; em produção use só-membership).")


if __name__ == "__main__":
    main(sys.argv[1])

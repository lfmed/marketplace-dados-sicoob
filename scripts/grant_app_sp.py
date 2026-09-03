#!/usr/bin/env python3
"""Concede ao service principal do App as permissões UC necessárias para efetivar acessos:
USE CATALOG no catálogo + MANAGE nos schemas das unidades (mkt_*), permitindo que o app
faça GRANT/REVOKE de SELECT/MODIFY aos beneficiários.
Uso: DATABRICKS_CONFIG_PROFILE=DEFAULT python3 scripts/grant_app_sp.py <sp_client_id>
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import config
from app import db
from scripts.uc_sql import run_sql


def main(sp):
    cat = config.UC_CATALOG
    # MANAGE no catálogo permite ao SP conceder USE CATALOG aos beneficiários (RF-067..069).
    print(f"GRANT USE CATALOG, MANAGE ON CATALOG {cat} TO {sp}")
    run_sql(f"GRANT USE CATALOG, MANAGE ON CATALOG {cat} TO `{sp}`", warehouse_id=config.WAREHOUSE_ID)
    schemas = [r["nome_schema"] for r in db.query(
        "SELECT DISTINCT nome_schema FROM governanca.iniciativa_camada_ambiente "
        "WHERE nome_schema IS NOT NULL ORDER BY nome_schema")]
    for s in schemas:
        run_sql(f"GRANT USE SCHEMA, MANAGE ON SCHEMA {cat}.{s} TO `{sp}`",
                warehouse_id=config.WAREHOUSE_ID)
    print(f"MANAGE concedido em {len(schemas)} schemas mkt_* ao SP {sp}")


if __name__ == "__main__":
    main(sys.argv[1])

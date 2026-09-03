#!/usr/bin/env python3
"""SYNCED TABLES NATIVAS (Delta -> Lakebase) — modo produção/cliente (D-010/D-011).

Registra o banco Lakebase como catálogo UC e cria uma synced table por tabela de
governança (fonte Delta), materializando o schema `governanca` (somente-leitura) no
Lakebase. Parametrizado por app/config.py e idempotente.

Pré-requisito: o executor precisa de CREATE CATALOG no metastore (em dev o usuário não
tem — ver D-011; por isso o protótipo usa db/sync/sync_governanca.py).

Uso: DATABRICKS_CONFIG_PROFILE=DEFAULT python3 -m db.native_sync_setup
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import config  # noqa: E402
from app.db import get_client  # noqa: E402
from scripts.uc_sql import run_sql  # noqa: E402
from db.seed.gov_schema import GOV_TABLES, GOV_SCHEMA_UC  # noqa: E402

LAKEBASE_UC_CATALOG = os.getenv("LAKEBASE_UC_CATALOG", "lakebase_marketplace")
CKPT_SCHEMA = os.getenv("SYNC_CKPT_SCHEMA", "marketplace_sync_ckpt")
SCHED = os.getenv("SYNC_SCHEDULING_POLICY", "SNAPSHOT")  # SNAPSHOT|TRIGGERED|CONTINUOUS


def _api(method, path, body=None):
    return get_client().api_client.do(method, path, body=body)


def branch_resource():
    # endpoint -> .../branches/<b>/endpoints/<e>; branch = tudo antes de /endpoints
    ep = config.LAKEBASE_ENDPOINT
    return ep.split("/endpoints/")[0]


def register_catalog():
    try:
        _api("GET", f"/api/2.0/postgres/catalogs/{LAKEBASE_UC_CATALOG}")
        print(f"  catálogo UC '{LAKEBASE_UC_CATALOG}' já existe")
        return
    except Exception:
        pass
    body = {"name": LAKEBASE_UC_CATALOG,
            "spec": {"postgres_database": config.LAKEBASE_DBNAME,
                     "create_database_if_missing": False,
                     "branch": branch_resource()}}
    _api("POST", f"/api/2.0/postgres/catalogs?catalog_id={LAKEBASE_UC_CATALOG}", body)
    print(f"  catálogo UC '{LAKEBASE_UC_CATALOG}' registrado -> Lakebase")


def create_synced_tables():
    cat = config.UC_CATALOG
    # schema de checkpoints do pipeline (catálogo standard)
    run_sql(f"CREATE SCHEMA IF NOT EXISTS {cat}.{CKPT_SCHEMA}")
    for tabela, cols, pk in GOV_TABLES:
        src = f"{cat}.{GOV_SCHEMA_UC}.{tabela}"
        dst = f"{LAKEBASE_UC_CATALOG}.governanca.{tabela}"
        try:
            _api("GET", f"/api/2.0/postgres/synced_tables/{dst}")
            print(f"  synced table {dst} já existe")
            continue
        except Exception:
            pass
        body = {"name": f"synced_tables/{dst}",
                "spec": {"source_table_full_name": src,
                         "primary_key_columns": pk,
                         "scheduling_policy": SCHED,
                         "create_database_objects_if_missing": True,
                         "new_pipeline_spec": {"storage_catalog": cat,
                                               "storage_schema": CKPT_SCHEMA}}}
        _api("POST", f"/api/2.0/postgres/synced_tables?synced_table_id={dst}", body)
        print(f"  synced table criada: {dst}  (policy={SCHED})")


def main():
    print("== Registrando banco Lakebase no UC ==")
    register_catalog()
    print("== Criando synced tables (governanca) ==")
    create_synced_tables()
    print("Synced tables nativas configuradas.")


if __name__ == "__main__":
    main()

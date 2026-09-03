#!/usr/bin/env python3
"""SYNC CONTROLADO Delta->Lakebase (modo DEV/protótipo — D-011).
Lê as tabelas Delta de governança (fonte da verdade no UC) e faz UPSERT por PK no schema
`governanca` do Lakebase. É o stand-in do synced-table nativo enquanto o dev não tem
CREATE CATALOG. No cliente, use db/native_sync_setup.py (synced tables nativas).
Uso: DATABRICKS_CONFIG_PROFILE=DEFAULT python3 -m db.sync.sync_governanca
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.config import config  # noqa: E402
from app.db import get_conn  # noqa: E402
from scripts.uc_sql import run_sql  # noqa: E402
from db.seed.gov_schema import GOV_TABLES, GOV_SCHEMA_UC, coerce_from_delta  # noqa: E402


def upsert(cur, tabela, cols, pk, valores):
    ph = ",".join(["%s"] * len(cols))
    non_pk = [c for c in cols if c not in pk]
    if non_pk:
        sets = ",".join(f"{c}=EXCLUDED.{c}" for c in non_pk)
        sql = (f'INSERT INTO governanca.{tabela} ({",".join(cols)}) VALUES ({ph}) '
               f'ON CONFLICT ({",".join(pk)}) DO UPDATE SET {sets}')
    else:
        sql = (f'INSERT INTO governanca.{tabela} ({",".join(cols)}) VALUES ({ph}) '
               f'ON CONFLICT ({",".join(pk)}) DO NOTHING')
    cur.execute(sql, valores)


def sync():
    cat = config.UC_CATALOG
    total = 0
    with get_conn(autocommit=False) as conn:
        with conn.cursor() as cur:
            for tabela, cols, pk in GOV_TABLES:
                fq = f"{cat}.{GOV_SCHEMA_UC}.{tabela}"
                _state, rows = run_sql(f"SELECT {', '.join(cols)} FROM {fq}",
                                       warehouse_id=config.WAREHOUSE_ID)
                for r in rows:
                    valores = [coerce_from_delta(cols[i], r[i]) for i in range(len(cols))]
                    upsert(cur, tabela, cols, pk, valores)
                if rows:
                    total += len(rows)
                    print(f"  {tabela}: {len(rows)} linhas sincronizadas")
        conn.commit()
    print(f"Sync Delta->Lakebase concluído ({total} linhas).")


if __name__ == "__main__":
    sync()

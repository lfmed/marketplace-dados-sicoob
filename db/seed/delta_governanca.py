#!/usr/bin/env python3
"""Cria as tabelas Delta de governança no Unity Catalog (fonte da verdade do .drawio)
e carrega o seed sintético. Depois, essas tabelas são sincronizadas para o Lakebase
via synced tables nativas (D-010). CDF habilitado p/ permitir modo TRIGGERED.
Uso: DATABRICKS_CONFIG_PROFILE=DEFAULT python3 -m db.seed.delta_governanca
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.config import config  # noqa: E402
from scripts.uc_sql import run_sql  # noqa: E402
from db.seed.gov_schema import GOV_TABLES, GOV_SCHEMA_UC, delta_type  # noqa: E402
from db.seed.rows import build_rows  # noqa: E402
from db.seed.seed_uc_targets import build_icas  # noqa: E402


def _lit(v):
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "true" if v else "false"
    s = str(v).replace("'", "''")
    return f"'{s}'"


def create_delta_tables():
    cat = config.UC_CATALOG
    run_sql(f"CREATE SCHEMA IF NOT EXISTS {cat}.{GOV_SCHEMA_UC} "
            f"COMMENT 'Fonte da verdade (Delta) do modelo de governança - Marketplace Sicoob'")
    for tabela, cols, pk in GOV_TABLES:
        coldefs = []
        for c in cols:
            t = delta_type(c)
            nn = " NOT NULL" if c in pk else ""
            coldefs.append(f"{c} {t}{nn}")
        # CREATE OR REPLACE p/ acompanhar evolução de schema no seed (dev; recria vazio).
        ddl = (f"CREATE OR REPLACE TABLE {cat}.{GOV_SCHEMA_UC}.{tabela} "
               f"({', '.join(coldefs)}) "
               f"TBLPROPERTIES (delta.enableChangeDataFeed = true)")
        run_sql(ddl)
    print(f"  {len(GOV_TABLES)} tabelas Delta criadas em {cat}.{GOV_SCHEMA_UC}")


def load_delta():
    cat = config.UC_CATALOG
    icas = build_icas()
    rows = build_rows(icas)
    for tabela, cols, pk in GOV_TABLES:
        data_rows = rows.get(tabela, [])
        fq = f"{cat}.{GOV_SCHEMA_UC}.{tabela}"
        run_sql(f"TRUNCATE TABLE {fq}")
        if not data_rows:
            continue
        values = []
        for r in data_rows:
            values.append("(" + ", ".join(_lit(r.get(c)) for c in cols) + ")")
        # insere em lotes de 200 linhas
        for i in range(0, len(values), 200):
            chunk = values[i:i + 200]
            run_sql(f"INSERT INTO {fq} ({', '.join(cols)}) VALUES " + ", ".join(chunk))
        print(f"    {tabela}: {len(data_rows)} linhas")


def main():
    print("== Criando tabelas Delta de governança ==")
    create_delta_tables()
    print("== Carregando seed sintético no Delta ==")
    load_delta()
    print("Delta de governança pronto.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Cria as tabelas Delta do Motor (governanca + gestao_acesso) no Unity Catalog e carrega
o seed sintético. Em produção o cliente já tem essas tabelas (plataforma.*); aqui é dev.
Uso: DATABRICKS_CONFIG_PROFILE=DEFAULT python3 -m db.seed.delta_governanca
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.config import config  # noqa: E402
from scripts.uc_sql import run_sql  # noqa: E402
from db.seed.gov_schema import GOV_TABLES, DELTA_SCHEMAS, delta_type  # noqa: E402
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
    cat = config.GOV_CATALOG
    for sch in DELTA_SCHEMAS:
        run_sql(f"CREATE SCHEMA IF NOT EXISTS {cat}.{sch} "
                f"COMMENT 'Motor (Delta) - Marketplace Sicoob'")
    for schema, tabela, cols, pk in GOV_TABLES:
        coldefs = [f"{c} {delta_type(c)}{' NOT NULL' if c in pk else ''}" for c in cols]
        ddl = (f"CREATE OR REPLACE TABLE {cat}.{schema}.{tabela} "
               f"({', '.join(coldefs)}) "
               f"TBLPROPERTIES (delta.enableChangeDataFeed = true)")
        run_sql(ddl)
    print(f"  {len(GOV_TABLES)} tabelas Delta criadas em {cat}.[{', '.join(DELTA_SCHEMAS)}]")


def load_delta():
    cat = config.GOV_CATALOG
    icas = build_icas()
    rows = build_rows(icas)
    for schema, tabela, cols, pk in GOV_TABLES:
        data_rows = rows.get(tabela, [])
        fq = f"{cat}.{schema}.{tabela}"
        run_sql(f"TRUNCATE TABLE {fq}")
        if not data_rows:
            continue
        values = ["(" + ", ".join(_lit(r.get(c)) for c in cols) + ")" for r in data_rows]
        for i in range(0, len(values), 200):
            run_sql(f"INSERT INTO {fq} ({', '.join(cols)}) VALUES " + ", ".join(values[i:i + 200]))
        print(f"    {schema}.{tabela}: {len(data_rows)} linhas")


def main():
    print("== Criando tabelas Delta do Motor (governanca + gestao_acesso) ==")
    create_delta_tables()
    print("== Carregando seed sintético no Delta ==")
    load_delta()
    print("Delta do Motor pronto.")


if __name__ == "__main__":
    main()

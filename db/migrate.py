#!/usr/bin/env python3
"""Aplica os DDLs (schemas governanca + gestao_acesso) no Lakebase.
Uso: DATABRICKS_CONFIG_PROFILE=DEFAULT python3 -m db.migrate
Idempotente (CREATE ... IF NOT EXISTS)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import run_script, query  # noqa: E402

DDL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ddl")
# governanca é criada por SYNCED TABLES (Delta->Lakebase, D-010); migrate cria só gestao_acesso.
FILES = ["02_gestao_acesso.sql"]


def main():
    for f in FILES:
        path = os.path.join(DDL_DIR, f)
        print(f"==> aplicando {f}")
        with open(path, encoding="utf-8") as fh:
            run_script(fh.read())
        print(f"    OK {f}")
    # verificação
    rows = query(
        """
        SELECT table_schema, count(*) AS n
        FROM information_schema.tables
        WHERE table_schema IN ('governanca','gestao_acesso')
        GROUP BY table_schema ORDER BY table_schema
        """
    )
    print("Tabelas por schema:")
    for r in rows:
        print("  ", r["table_schema"], "=", r["n"])


if __name__ == "__main__":
    main()

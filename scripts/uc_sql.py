#!/usr/bin/env python3
"""Executa SQL no Unity Catalog via Statement Execution API (SDK).
Uso: python3 uc_sql.py "SELECT current_user()"  [warehouse_id]
Reutilizado para criar objetos UC de exemplo e executar GRANT/REVOKE.
"""
import os
import sys
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

DEFAULT_WAREHOUSE = os.environ.get("DATABRICKS_WAREHOUSE_ID", "b8e52268d9828bdd")  # parametrizável por env
PROFILE = os.environ.get("DATABRICKS_CONFIG_PROFILE", "DEFAULT")


def get_client():
    # No Databricks (notebook/Apps) não há perfil de CLI: cai para a auth do ambiente.
    try:
        return WorkspaceClient(profile=PROFILE)
    except Exception:
        return WorkspaceClient()


def run_sql(sql: str, warehouse_id: str = DEFAULT_WAREHOUSE, catalog=None, schema=None):
    w = get_client()
    resp = w.statement_execution.execute_statement(
        warehouse_id=warehouse_id,
        statement=sql,
        catalog=catalog,
        schema=schema,
        wait_timeout="50s",
    )
    # poll if still running
    stmt_id = resp.statement_id
    import time
    while resp.status and resp.status.state in (StatementState.PENDING, StatementState.RUNNING):
        time.sleep(1)
        resp = w.statement_execution.get_statement(stmt_id)
    state = resp.status.state if resp.status else None
    if state == StatementState.FAILED:
        err = resp.status.error
        raise RuntimeError(f"SQL FAILED: {err.message if err else 'unknown'}")
    rows = []
    if resp.result and resp.result.data_array:
        rows = resp.result.data_array
    return state, rows


if __name__ == "__main__":
    sql = sys.argv[1]
    wh = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_WAREHOUSE
    state, rows = run_sql(sql, wh)
    print("STATE:", state)
    for r in rows:
        print("  ", r)

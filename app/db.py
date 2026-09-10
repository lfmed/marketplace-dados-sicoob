"""Camada de acesso ao Lakebase (Postgres) do App.

Padrão de conexão que funciona tanto localmente (perfil CLI) quanto no Databricks Apps
(service principal via Config()). Token OAuth é curto (1h) — cacheamos e renovamos.
Ver docs/DECISIONS.md (infra) e skill databricks-lakebase-autoscale.
"""
import os
import socket
import subprocess
import threading
import time
import contextlib

import psycopg
from psycopg.rows import dict_row
from databricks.sdk import WorkspaceClient

from app.config import config

_lock = threading.Lock()
_client = None
_token = {"value": None, "exp": 0.0}
_host_cache = {"host": None, "addr": None}
_TOKEN_TTL = 45 * 60  # renova antes de 1h


def get_client() -> WorkspaceClient:
    global _client
    if _client is None:
        # No Apps, Config() detecta o SP; localmente usa o perfil.
        try:
            _client = WorkspaceClient(profile=config.DATABRICKS_PROFILE)
        except Exception:
            _client = WorkspaceClient()
    return _client


_account_client = None


def get_account_client():
    """AccountClient para gerenciar GRUPOS DE CONTA (produção). Reusa a auth do SP/perfil."""
    global _account_client
    if _account_client is None:
        from databricks.sdk import AccountClient
        try:
            _account_client = AccountClient(host=config.DATABRICKS_ACCOUNT_HOST,
                                            account_id=config.DATABRICKS_ACCOUNT_ID,
                                            profile=config.DATABRICKS_PROFILE)
        except Exception:
            _account_client = AccountClient(host=config.DATABRICKS_ACCOUNT_HOST,
                                            account_id=config.DATABRICKS_ACCOUNT_ID)
    return _account_client


def get_groups_client():
    """Cliente SCIM para gerenciar grupos (associação de membros), conforme GROUPS_SCOPE:
    'account' -> AccountClient (grupos de conta, produção); 'workspace' -> WorkspaceClient
    (grupos workspace-local, dev). Ambos expõem a MESMA interface .groups/.users/
    .service_principals, então o membership_executor é agnóstico ao escopo."""
    if config.GROUPS_SCOPE == "account":
        return get_account_client()
    return get_client()


def _resolve(host: str) -> str:
    if _host_cache["addr"] and _host_cache["host"] == host:
        return _host_cache["addr"]
    addr = None
    try:
        out = subprocess.run(["dig", "+short", host], capture_output=True, text=True, timeout=10)
        ips = [l for l in out.stdout.split() if l and l[0].isdigit()]
        if ips:
            addr = ips[-1]
    except Exception:
        pass
    if not addr:
        addr = socket.gethostbyname(host)
    _host_cache.update(host=host, addr=addr)
    return addr


def _get_host() -> str:
    if _host_cache["host"]:
        return _host_cache["host"]
    ep = get_client().postgres.get_endpoint(name=config.LAKEBASE_ENDPOINT)
    return ep.status.hosts.host


def _get_token() -> str:
    now = time.time()
    with _lock:
        if _token["value"] and now < _token["exp"]:
            return _token["value"]
        cred = get_client().postgres.generate_database_credential(endpoint=config.LAKEBASE_ENDPOINT)
        _token["value"] = cred.token
        _token["exp"] = now + _TOKEN_TTL
        return cred.token


_user_cache = {"name": None}


def _get_user():
    if not _user_cache["name"]:
        _user_cache["name"] = get_client().current_user.me().user_name
    return _user_cache["name"]


def connect(autocommit: bool = True, tentativas: int = 3) -> psycopg.Connection:
    """Conecta ao Lakebase com retry (autoscaling pode acordar de scale-to-zero)."""
    host = _get_host()
    ultimo_erro = None
    for i in range(tentativas):
        try:
            return psycopg.connect(
                host=host,
                hostaddr=_resolve(host),
                dbname=config.LAKEBASE_DBNAME,
                user=_get_user(),
                password=_get_token(),
                sslmode="require",
                autocommit=autocommit,
                row_factory=dict_row,
                connect_timeout=20,
            )
        except (psycopg.OperationalError, psycopg.errors.ConnectionTimeout) as e:
            ultimo_erro = e
            time.sleep(1.5 * (i + 1))
    raise ultimo_erro


@contextlib.contextmanager
def get_conn(autocommit: bool = True):
    conn = connect(autocommit=autocommit)
    try:
        yield conn
    finally:
        conn.close()


def query(sql: str, params=None):
    """SELECT -> lista de dicts."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.fetchall()


def query_one(sql: str, params=None):
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params=None):
    """INSERT/UPDATE/DELETE -> rowcount."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.rowcount


def run_script(sql_script: str):
    """Executa um script DDL multi-statement."""
    with get_conn(autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(sql_script)


def run_uc_sql(sql: str, warehouse_id: str = None):
    """Executa SQL no Unity Catalog via Statement Execution API (usa o SP no app,
    ou o perfil CLI localmente). Retorna (state, rows)."""
    import time as _t
    from databricks.sdk.service.sql import StatementState
    wh = warehouse_id or config.WAREHOUSE_ID
    w = get_client()
    resp = w.statement_execution.execute_statement(warehouse_id=wh, statement=sql, wait_timeout="50s")
    sid = resp.statement_id
    while resp.status and resp.status.state in (StatementState.PENDING, StatementState.RUNNING):
        _t.sleep(1)
        resp = w.statement_execution.get_statement(sid)
    state = resp.status.state if resp.status else None
    if state == StatementState.FAILED:
        err = resp.status.error
        raise RuntimeError(f"UC SQL FAILED: {err.message if err else 'unknown'}")
    rows = resp.result.data_array if (resp.result and resp.result.data_array) else []
    return state, rows

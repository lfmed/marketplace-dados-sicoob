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


def connect(autocommit: bool = True) -> psycopg.Connection:
    host = _get_host()
    user = get_client().current_user.me().user_name
    conn = psycopg.connect(
        host=host,
        hostaddr=_resolve(host),
        dbname=config.LAKEBASE_DBNAME,
        user=user,
        password=_get_token(),
        sslmode="require",
        autocommit=autocommit,
        row_factory=dict_row,
    )
    return conn


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

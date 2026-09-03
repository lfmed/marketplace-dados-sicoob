#!/usr/bin/env python3
"""Helper de conexão ao Lakebase Autoscaling (dev).
Gera token OAuth (1h), resolve DNS (contorno macOS) e conecta via psycopg3.
Reutilizado por migrations/seed. Em produção o App usará este mesmo padrão com refresh.
"""
import os
import socket
import subprocess
import psycopg
from databricks.sdk import WorkspaceClient

PROFILE = os.environ.get("DATABRICKS_CONFIG_PROFILE", "DEFAULT")
ENDPOINT = os.environ.get(
    "LAKEBASE_ENDPOINT",
    "projects/marketplace-dados/branches/production/endpoints/primary",
)
DBNAME = os.environ.get("LAKEBASE_DBNAME", "databricks_postgres")


def get_client():
    return WorkspaceClient(profile=PROFILE)


def resolve_host(host: str) -> str:
    """Contorno de DNS no macOS: usa dig; cai para socket se falhar."""
    try:
        out = subprocess.run(["dig", "+short", host], capture_output=True, text=True, timeout=10)
        ips = [l for l in out.stdout.split() if l and l[0].isdigit()]
        if ips:
            return ips[-1]
    except Exception:
        pass
    return socket.gethostbyname(host)


def connect(autocommit: bool = True):
    w = get_client()
    ep = w.postgres.get_endpoint(name=ENDPOINT)
    host = ep.status.hosts.host
    cred = w.postgres.generate_database_credential(endpoint=ENDPOINT)
    user = w.current_user.me().user_name
    hostaddr = resolve_host(host)
    conn = psycopg.connect(
        host=host,
        hostaddr=hostaddr,
        dbname=DBNAME,
        user=user,
        password=cred.token,
        sslmode="require",
        autocommit=autocommit,
    )
    return conn


if __name__ == "__main__":
    with connect() as c:
        with c.cursor() as cur:
            cur.execute("SELECT version(), current_database(), current_user")
            print(cur.fetchone())

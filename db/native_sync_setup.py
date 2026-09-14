#!/usr/bin/env python3
"""SYNCED TABLES NATIVAS (Delta -> Lakebase) — modo produção/cliente (D-010/D-011).

Registra o banco Lakebase como catálogo UC e cria uma synced table por tabela do Motor
(fonte Delta em GOV_CATALOG), materializando os schemas `governanca` e `gestao_acesso`
(somente-leitura) no Lakebase. Parametrizado por app/config.py e idempotente.

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
from db.seed.gov_schema import GOV_TABLES, DELTA_SCHEMAS  # noqa: E402

LAKEBASE_UC_CATALOG = os.getenv("LAKEBASE_UC_CATALOG", "lakebase_marketplace")
CKPT_SCHEMA = os.getenv("SYNC_CKPT_SCHEMA", "marketplace_sync_ckpt")
SCHED = os.getenv("SYNC_SCHEDULING_POLICY", "SNAPSHOT")  # SNAPSHOT|TRIGGERED|CONTINUOUS


def _api(method, path, body=None):
    return get_client().api_client.do(method, path, body=body)


def branch_resource():
    # endpoint -> .../branches/<b>/endpoints/<e>; branch = tudo antes de /endpoints.
    # Guard: se o endpoint vier vazio/malformado, o servidor devolveria um erro críptico
    # (" is not a valid endpoint id"). Falha aqui com mensagem acionável.
    ep = config.LAKEBASE_ENDPOINT or ""
    if "/endpoints/" not in ep:
        raise ValueError(
            f"LAKEBASE_ENDPOINT inválido ou vazio: {ep!r}. Defina no formato "
            "projects/<projeto>/branches/<branch>/endpoints/<endpoint> "
            "(cell de config do notebook, ou env LAKEBASE_ENDPOINT no app.yaml)."
        )
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
    # Origem Delta do Motor: catálogo parametrizável (cliente = plataforma) + os schemas
    # governanca/gestao_acesso. Destino: mesmos schemas no catálogo UC do Lakebase.
    cat = config.GOV_CATALOG
    # schema de checkpoints do pipeline
    run_sql(f"CREATE SCHEMA IF NOT EXISTS {cat}.{CKPT_SCHEMA}")
    for schema, tabela, cols, pk in GOV_TABLES:
        src = f"{cat}.{schema}.{tabela}"
        dst = f"{LAKEBASE_UC_CATALOG}.{schema}.{tabela}"
        try:
            _api("GET", f"/api/2.0/postgres/synced_tables/{dst}")
            print(f"  synced table {dst} já existe")
            continue
        except Exception:
            pass
        # 'branch' é obrigatório no spec da synced table: é o que liga a synced table ao
        # endpoint do Lakebase. Sem ele o servidor devolve " is not a valid endpoint id".
        # 'postgres_database' é explícito (validado ponta a ponta): funciona no catálogo
        # registrado (mesmo valor que o catálogo aponta) e também no catálogo padrão.
        body = {"name": f"synced_tables/{dst}",
                "spec": {"source_table_full_name": src,
                         "primary_key_columns": pk,
                         "scheduling_policy": SCHED,
                         "branch": branch_resource(),
                         "postgres_database": config.LAKEBASE_DBNAME,
                         "create_database_objects_if_missing": True,
                         "new_pipeline_spec": {"storage_catalog": cat,
                                               "storage_schema": CKPT_SCHEMA}}}
        _api("POST", f"/api/2.0/postgres/synced_tables?synced_table_id={dst}", body)
        print(f"  synced table criada: {dst}  (policy={SCHED})")


def main():
    print("== Config resolvida ==")
    print(f"  LAKEBASE_ENDPOINT   = {config.LAKEBASE_ENDPOINT!r}")
    print(f"  LAKEBASE_DBNAME     = {config.LAKEBASE_DBNAME!r}")
    print(f"  LAKEBASE_UC_CATALOG = {LAKEBASE_UC_CATALOG!r}")
    print(f"  GOV_CATALOG (Delta) = {config.GOV_CATALOG!r}")
    print(f"  WAREHOUSE_ID        = {config.WAREHOUSE_ID!r}")
    print(f"  scheduling_policy   = {SCHED!r}")
    print("== Registrando banco Lakebase no UC ==")
    register_catalog()
    print(f"== Criando synced tables ({', '.join(DELTA_SCHEMAS)}) ==")
    create_synced_tables()
    print("Synced tables nativas configuradas.")


if __name__ == "__main__":
    main()

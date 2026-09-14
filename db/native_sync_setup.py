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
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import config  # noqa: E402
from app.db import get_client  # noqa: E402
from scripts.uc_sql import run_sql  # noqa: E402
from db.seed.gov_schema import GOV_TABLES, DELTA_SCHEMAS  # noqa: E402

LAKEBASE_UC_CATALOG = os.getenv("LAKEBASE_UC_CATALOG", "lakebase_marketplace")
CKPT_SCHEMA = os.getenv("SYNC_CKPT_SCHEMA", "marketplace_sync_ckpt")
SCHED = os.getenv("SYNC_SCHEDULING_POLICY", "SNAPSHOT")  # SNAPSHOT|TRIGGERED|CONTINUOUS
VALID_POLICIES = {"SNAPSHOT", "TRIGGERED", "CONTINUOUS"}


def _validar_overrides(pk_overrides, policy_overrides):
    """Falha cedo com mensagem clara: policy fora do enum; avisa chave de override que não
    bate com nenhuma tabela do modelo (senão o override é ignorado em silêncio)."""
    nomes = {t[1] for t in GOV_TABLES}
    for rotulo, d in (("pk_overrides", pk_overrides), ("policy_overrides", policy_overrides)):
        for k in d:
            if k not in nomes:
                print(f"  ⚠ {rotulo}: tabela '{k}' não existe no modelo — override IGNORADO")
    invalidas = {p for p in list(policy_overrides.values()) + [SCHED] if p not in VALID_POLICIES}
    if invalidas:
        raise ValueError(
            f"scheduling_policy inválida: {sorted(invalidas)}. Use um de {sorted(VALID_POLICIES)} "
            "(TRIGGERED/CONTINUOUS exigem CDF na origem).")


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


def _delete_synced_table(dst):
    """Remove a synced table e espera sumir (recreate). DELETE basta — não é preciso
    dropar a tabela Postgres (validado: recriar com PK diferente funciona)."""
    _api("DELETE", f"/api/2.0/postgres/synced_tables/{dst}")
    for _ in range(15):  # eventual: aguarda o GET voltar 404
        try:
            _api("GET", f"/api/2.0/postgres/synced_tables/{dst}")
            time.sleep(2)
        except Exception:
            return
    print(f"  ⚠ {dst} ainda aparece após o delete; seguindo mesmo assim")


def create_synced_tables(pk_overrides=None, recreate=False, policy_overrides=None):
    # Origem Delta do Motor: catálogo parametrizável (cliente = plataforma) + os schemas
    # governanca/gestao_acesso. Destino: mesmos schemas no catálogo UC do Lakebase.
    # pk_overrides: dict {nome_tabela -> [colunas de PK]} para o cliente ajustar a chave
    # primária de cada tabela sem editar o modelo; ausente/vazio => usa o padrão do modelo.
    # policy_overrides: dict {nome_tabela -> 'SNAPSHOT'|'TRIGGERED'|'CONTINUOUS'} p/ definir a
    # política de sync por tabela; ausente => usa a global SYNC_SCHEDULING_POLICY (SCHED).
    # TRIGGERED/CONTINUOUS exigem Change Data Feed (CDF) na tabela Delta de origem.
    # recreate: se True, dropa e recria synced tables que já existem (p/ aplicar nova PK/policy);
    # se False (padrão), pula as que já existem.
    pk_overrides = pk_overrides or {}
    policy_overrides = policy_overrides or {}
    _validar_overrides(pk_overrides, policy_overrides)
    cat = config.GOV_CATALOG
    # schema de checkpoints do pipeline
    run_sql(f"CREATE SCHEMA IF NOT EXISTS {cat}.{CKPT_SCHEMA}")
    for schema, tabela, cols, pk in GOV_TABLES:
        pk_use = pk_overrides.get(tabela, pk)
        sched_use = policy_overrides.get(tabela, SCHED)
        src = f"{cat}.{schema}.{tabela}"
        dst = f"{LAKEBASE_UC_CATALOG}.{schema}.{tabela}"
        exists = True
        try:
            _api("GET", f"/api/2.0/postgres/synced_tables/{dst}")
        except Exception:
            exists = False
        if exists:
            if not recreate:
                print(f"  synced table {dst} já existe (use recreate=True p/ recriar)")
                continue
            _delete_synced_table(dst)
            print(f"  synced table {dst} removida (recreate)")
        # 'branch' é obrigatório no spec da synced table: é o que liga a synced table ao
        # endpoint do Lakebase. Sem ele o servidor devolve " is not a valid endpoint id".
        # 'postgres_database' é explícito (validado ponta a ponta): funciona no catálogo
        # registrado (mesmo valor que o catálogo aponta) e também no catálogo padrão.
        body = {"name": f"synced_tables/{dst}",
                "spec": {"source_table_full_name": src,
                         "primary_key_columns": pk_use,
                         "scheduling_policy": sched_use,
                         "branch": branch_resource(),
                         "postgres_database": config.LAKEBASE_DBNAME,
                         "create_database_objects_if_missing": True,
                         "new_pipeline_spec": {"storage_catalog": cat,
                                               "storage_schema": CKPT_SCHEMA}}}
        _api("POST", f"/api/2.0/postgres/synced_tables?synced_table_id={dst}", body)
        print(f"  synced table criada: {dst}  (policy={sched_use}, pk={pk_use})")


def main(pk_overrides=None, recreate=False, policy_overrides=None):
    print("== Config resolvida ==")
    print(f"  LAKEBASE_ENDPOINT   = {config.LAKEBASE_ENDPOINT!r}")
    print(f"  LAKEBASE_DBNAME     = {config.LAKEBASE_DBNAME!r}")
    print(f"  LAKEBASE_UC_CATALOG = {LAKEBASE_UC_CATALOG!r}")
    print(f"  GOV_CATALOG (Delta) = {config.GOV_CATALOG!r}")
    print(f"  WAREHOUSE_ID        = {config.WAREHOUSE_ID!r}")
    print(f"  scheduling_policy   = {SCHED!r} (global)")
    if policy_overrides:
        print(f"  policy overrides    = {policy_overrides}")
    print("== Registrando banco Lakebase no UC ==")
    register_catalog()
    print(f"== Criando synced tables ({', '.join(DELTA_SCHEMAS)}) — recreate={recreate} ==")
    create_synced_tables(pk_overrides, recreate=recreate, policy_overrides=policy_overrides)
    print("Synced tables nativas configuradas.")


if __name__ == "__main__":
    main()

# Databricks notebook source
# MAGIC %md
# MAGIC # Registrar synced tables (Delta → Lakebase) — SEM CLI
# MAGIC
# MAGIC Popula os mirrors **`governanca`** e **`gestao_acesso`** no Lakebase (Postgres) a
# MAGIC partir do Delta do Motor (`plataforma.*`), criando **synced tables nativas**
# MAGIC (reverse ETL gerenciado). É o equivalente ao que o `databricks bundle`/CLI faria —
# MAGIC mas roda **aqui, dentro do workspace** (server-side), então o firewall que bloqueia a
# MAGIC CLI local **não** atrapalha.
# MAGIC
# MAGIC Este notebook está no **repositório já clonado** no Databricks; basta abrir e rodar as
# MAGIC células em ordem. Ele chama `db.native_sync_setup` (fonte única).
# MAGIC
# MAGIC ### Pré-requisitos (do executor deste notebook)
# MAGIC - **`CREATE CATALOG`** no metastore (registra o Lakebase como catálogo UC) e permissão
# MAGIC   de criar **synced tables**.
# MAGIC - **`CREATE SCHEMA`** no catálogo Delta (`plataforma`) — para o schema de checkpoints do pipeline.
# MAGIC - **`CAN_USE`** no SQL Warehouse e **`SELECT`** nas tabelas Delta de origem.
# MAGIC - Um **projeto/endpoint Lakebase** já existente.
# MAGIC
# MAGIC > Só precisa rodar **uma vez** (é idempotente — reexecutar pula o que já existe). A
# MAGIC > atualização dos dados fica por conta da própria synced table (política de scheduling).

# COMMAND ----------

# MAGIC %pip install "psycopg[binary]>=3.1" "databricks-sdk>=0.81.0"

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Configuração — **EDITE os valores do cliente**
# MAGIC Estes são os mesmos parâmetros do `app.yaml`. Ajuste para a workspace do cliente.

# COMMAND ----------

import os

# --- Catálogo Delta do Motor (origem) e schemas ---
os.environ["GOV_CATALOG"]        = "plataforma"        # catálogo Delta com governanca + gestao_acesso
os.environ["SCHEMA_GOVERNANCA"]  = "governanca"
os.environ["SCHEMA_GESTAO"]      = "gestao_acesso"
os.environ["SCHEMA_APP"]         = "marketplace_app"

# --- Lakebase (destino) ---
os.environ["LAKEBASE_ENDPOINT"]  = "projects/marketplace-dados/branches/production/endpoints/primary"
os.environ["LAKEBASE_DBNAME"]    = "databricks_postgres"
# Catálogo UC que aponta para o database Lakebase (criado por este notebook se não existir):
os.environ["LAKEBASE_UC_CATALOG"] = "lakebase_marketplace"

# --- Warehouse para ler o Delta ---
os.environ["DATABRICKS_WAREHOUSE_ID"] = "<warehouse_id_do_cliente>"

# Política de sync das synced tables: SNAPSHOT (uma carga), TRIGGERED (sob demanda) ou
# CONTINUOUS (streaming). Governança muda pouco -> SNAPSHOT/TRIGGERED costuma bastar.
os.environ["SYNC_SCHEDULING_POLICY"] = "TRIGGERED"

# Este notebook só PROVISIONA; não sobe app/worker no processo do notebook.
os.environ["AUTO_BOOTSTRAP_APP_SCHEMA"] = "false"
os.environ["APP_DISABLE_WORKER"] = "true"

# O repo (Git folder) já entra no sys.path automaticamente. Se `import db` falhar, ajuste:
# import sys; sys.path.insert(0, "/Workspace/Repos/<voce>/marketplace-dados-sicoob")

print("Config aplicada. Catálogo Delta:", os.environ["GOV_CATALOG"],
      "| Lakebase UC:", os.environ["LAKEBASE_UC_CATALOG"])

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Registrar o catálogo Lakebase + criar as synced tables
# MAGIC Cria uma synced table por tabela do Motor (governanca + gestao_acesso). Idempotente.

# COMMAND ----------

from db.native_sync_setup import main as registrar_synced_tables

registrar_synced_tables()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Verificar (mesmo diagnóstico que o app faz no boot)
# MAGIC Confirma que os mirrors ficaram visíveis no Lakebase e conta as linhas das tabelas-chave.

# COMMAND ----------

from app.bootstrap import verify_mirrors

ok = verify_mirrors()
print("\nMirrors OK ✓" if ok else "\nAlgo faltou — veja os ✗ acima")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. (Opcional) Atualização recorrente
# MAGIC Se usar `SNAPSHOT`/`TRIGGERED`, agende este notebook como um **Job** (Databricks
# MAGIC Workflows) na cadência desejada, ou troque `SYNC_SCHEDULING_POLICY=CONTINUOUS` para
# MAGIC sync contínuo. Reexecutar é seguro (idempotente).

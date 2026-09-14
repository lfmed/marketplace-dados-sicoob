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

# MAGIC %md
# MAGIC Instala as libs do app (mesmas do `requirements.txt`). **Flask é obrigatório**: importar
# MAGIC `db.native_sync_setup` puxa `from app.config …`, e importar o pacote `app` executa
# MAGIC `app/__init__.py` (que carrega o Flask). O runtime do notebook não traz Flask (só o de Apps).

# COMMAND ----------

# MAGIC %pip install "Flask>=3.0" "psycopg[binary]>=3.1" "databricks-sdk>=0.81.0" "python-dotenv>=1.0"

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

# Política de sync GLOBAL (padrão de TODAS as tabelas — ajuste por tabela na seção 2b):
#   SNAPSHOT   = cópia periódica completa; NÃO exige Change Data Feed (CDF) na origem.
#   TRIGGERED  = atualização incremental sob demanda; EXIGE CDF na tabela Delta de origem.
#   CONTINUOUS = streaming contínuo; EXIGE CDF na origem.
os.environ["SYNC_SCHEDULING_POLICY"] = "TRIGGERED"

# Recriar synced tables que JÁ existem? True dropa+recria (para aplicar nova PK ou policy);
# False (padrão) pula as que já existem. A PK só é aplicada na CRIAÇÃO da synced table.
RECREATE = False

# Este notebook só PROVISIONA; não sobe app/worker no processo do notebook.
os.environ["AUTO_BOOTSTRAP_APP_SCHEMA"] = "false"
os.environ["APP_DISABLE_WORKER"] = "true"

# O repo (Git folder) já entra no sys.path automaticamente. Se `import db` falhar, ajuste:
# import sys; sys.path.insert(0, "/Workspace/Repos/<voce>/marketplace-dados-sicoob")

print("Config aplicada. Catálogo Delta:", os.environ["GOV_CATALOG"],
      "| Lakebase UC:", os.environ["LAKEBASE_UC_CATALOG"])

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Chaves primárias por tabela — **EDITE se precisar**
# MAGIC A synced table usa a PK para o *upsert*. Os valores abaixo são o **padrão do modelo
# MAGIC oficial** (`db/seed/gov_schema.py`); ajuste a lista de colunas de qualquer tabela cuja
# MAGIC PK seja diferente no seu ambiente. A chave do dicionário é o **nome da tabela**
# MAGIC (tabela não listada aqui cai no padrão do modelo).

# COMMAND ----------

PRIMARY_KEYS = {
    # --- governanca (taxonomia) ---
    "dominio_informacao":          ["id_dominio_informacao"],
    "subdominio_informacao":       ["id_subdominio_informacao"],
    "iniciativa_aisn":             ["id_iniciativa_aisn"],
    "camada_aisn":                 ["id_camada_aisn"],
    "ambiente_aisn":               ["id_ambiente_aisn"],
    "iniciativa_camada_ambiente":  ["id_iniciativa_camada_ambiente"],
    "subdominio_camada_ambiente":  ["id_subdominio_camada_ambiente"],
    "dominio_camada_ambiente":     ["id_dominio_camada_ambiente"],
    "tabela_aisn":                 ["id_tabela_aisn"],
    "usuario_aisn":                ["id_usuario_aisn"],
    "dominio_proprietario":        ["id_dominio_informacao", "id_usuario_aisn"],
    "subdominio_proprietario":     ["id_subdominio_informacao", "id_usuario_aisn"],
    "iniciativa_proprietario":     ["id_iniciativa_aisn", "id_usuario_aisn"],
    # --- gestao_acesso (referência de acesso) ---
    "hierarquia_usuario":          ["id_usuario_aisn", "id_gestor_aisn"],
    "grupo_acesso":                ["id_grupo_acesso"],
    "grupo_acesso_membro":         ["id_grupo_acesso", "id_entidade"],
    "ativo_aisn":                  ["id_ativo_aisn"],
    "ativo_proprietario":          ["id_ativo_aisn", "id_usuario_aisn"],
}
print(f"{len(PRIMARY_KEYS)} tabelas com PK definida")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2b. Política de sync POR TABELA — **opcional**
# MAGIC Deixe **vazio** para todas usarem a política global (`SYNC_SCHEDULING_POLICY`).
# MAGIC Preencha só as exceções. Valores: **`SNAPSHOT`** (sem CDF) · **`TRIGGERED`**/**`CONTINUOUS`**
# MAGIC (exigem **CDF** habilitado na tabela Delta de origem: `delta.enableChangeDataFeed=true`).
# MAGIC
# MAGIC ⚠️ Mudar a política (ou a PK) de uma tabela **já criada** só tem efeito com
# MAGIC **`RECREATE = True`** (seção 1) — senão a synced table existente é pulada.

# COMMAND ----------

SYNC_POLICY = {
    # "usuario_aisn": "SNAPSHOT",     # ex.: muda pouco -> carga completa (sem CDF)
    # "ativo_aisn":   "TRIGGERED",    # ex.: muda mais  -> incremental (exige CDF)
}
print(f"{len(SYNC_POLICY)} tabela(s) com política específica; demais usam "
      f"{os.environ['SYNC_SCHEDULING_POLICY']}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Registrar o catálogo Lakebase + criar as synced tables
# MAGIC Cria uma synced table por tabela do Motor (governanca + gestao_acesso). Idempotente.
# MAGIC Usa as PKs definidas acima (`pk_overrides`).

# COMMAND ----------

from db.native_sync_setup import main as registrar_synced_tables

registrar_synced_tables(pk_overrides=PRIMARY_KEYS, recreate=RECREATE, policy_overrides=SYNC_POLICY)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Verificar (mesmo diagnóstico que o app faz no boot)
# MAGIC Confirma que os mirrors ficaram visíveis no Lakebase e conta as linhas das tabelas-chave.

# COMMAND ----------

from app.bootstrap import verify_mirrors

ok = verify_mirrors()
print("\nMirrors OK ✓" if ok else "\nAlgo faltou — veja os ✗ acima")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. (Opcional) Atualização recorrente
# MAGIC **Reexecutar este notebook NÃO atualiza os dados** — ele é idempotente e **pula** as
# MAGIC synced tables já existentes (só cria as que faltam, ou recria se `RECREATE=True`).
# MAGIC O refresh dos dados é da **própria synced table / pipeline**, conforme a política:
# MAGIC - **`CONTINUOUS`**: atualiza sozinha (streaming).
# MAGIC - **`TRIGGERED`**: dispare o refresh da pipeline (UI da synced table / API) ou agende
# MAGIC   **a pipeline** (não este notebook) na cadência desejada.
# MAGIC - **`SNAPSHOT`**: recarga completa a cada disparo da pipeline.

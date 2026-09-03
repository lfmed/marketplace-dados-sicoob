# Deploy — Marketplace de Dados Sicoob

Guia para provisionar o banco e publicar o app em **qualquer workspace** (dev ou cliente).
Todo o código de banco é reproduzível e parametrizado (ver `app/config.py`).

## 1. Pré-requisitos
- Databricks CLI autenticado na workspace-alvo (`databricks auth login`).
- Python 3.11+, `pip install -r requirements.txt`.
- SQL Warehouse (serverless) ativo.
- Projeto Lakebase (autoscaling). Criar, se necessário:
  ```
  databricks postgres create-project marketplace-dados \
    --json '{"spec":{"display_name":"Marketplace Dados Sicoob","pg_version":"17"}}'
  ```
- Privilégios:
  - Para **synced tables nativas** (`--mode native`): `CREATE CATALOG` no metastore.
  - Para conceder/revogar acessos: o executor (usuário/SP do app) precisa de
    `USE CATALOG` + `MANAGE`/owner nos schemas alvo (ou ser admin).

## 2. Configuração (parâmetros de ambiente)
Defina via env ou `app.yaml` (nenhum valor é hardcoded fora de `app/config.py`):

| Variável | Descrição | Ex. (dev) |
|---|---|---|
| `UC_CATALOG` | catálogo UC onde ficam os schemas (o app só cria schemas) | `stable_classic_pg4xe1_catalog` |
| `DATABRICKS_WAREHOUSE_ID` | warehouse p/ DDL/GRANT/REVOKE | `b8e52268d9828bdd` |
| `LAKEBASE_ENDPOINT` | endpoint do Lakebase | `projects/marketplace-dados/branches/production/endpoints/primary` |
| `LAKEBASE_DBNAME` | database Postgres | `databricks_postgres` |
| `GRANT_EXECUTE_REAL` | executar GRANT/REVOKE reais | `true` |
| `APP_ENABLE_PROXY` | seletor "atuar como" (demo) | `true` (prod: `false`) |

## 3. Provisionar o banco (reproduzível)
Um único entrypoint recria tudo (idempotente):

```bash
# CLIENTE (produção) — synced tables NATIVAS (exige CREATE CATALOG):
python -m db.setup --mode native

# DEV/protótipo — sync controlado Delta->Lakebase (sem CREATE CATALOG):
python -m db.setup --mode dev
```

O que cada passo faz:
1. Cria schemas Lakebase: `gestao_acesso` (sempre) e, em `dev`, `governanca`.
2. Cria as **tabelas Delta de governança** (`{UC_CATALOG}.marketplace_governanca`) + seed.
3. Cria **alvos reais de GRANT no UC** (grupos + 1 schema por iniciativa+camada).
4. Popula `governanca` no Lakebase: `native` = synced tables; `dev` = sync controlado.

> **Dados reais no cliente:** o seed é sintético (demo). Para produção, aponte as synced
> tables (`db/native_sync_setup.py`) para as tabelas Delta reais mantidas pelo **Motor de
> Governança** do cliente, em vez do schema sintético `marketplace_governanca`.

## 4. Permissões do app (service principal)
Ao rodar no Databricks Apps, o app roda como um service principal (SP). Conceda (script
pronto: `python scripts/grant_app_sp.py <sp_client_id>`):
```sql
-- MANAGE no CATÁLOGO é necessário para o SP conceder USE CATALOG aos beneficiários:
GRANT USE CATALOG, MANAGE ON CATALOG <UC_CATALOG> TO `<app-sp-client-id>`;
GRANT USE SCHEMA, MANAGE ON SCHEMA <UC_CATALOG>.<cada schema mkt_*> TO `<app-sp-client-id>`;
```
- **Warehouse:** `databricks warehouses set-permissions <wh> --json '{"access_control_list":[{"service_principal_name":"<sp-client-id>","permission_level":"CAN_USE"}]}'`.
- **Lakebase:** crie um role Postgres para o SP e conceda privilégios:
  ```
  databricks postgres create-role projects/<proj>/branches/production --role-id app-marketplace \
    --json '{"spec":{"identity_type":"SERVICE_PRINCIPAL","auth_method":"LAKEBASE_OAUTH_V1","postgres_role":"<sp-client-id>"}}'
  ```
  Depois (como owner do projeto), no Postgres:
  ```sql
  GRANT CONNECT ON DATABASE databricks_postgres TO "<sp-client-id>";
  GRANT USAGE ON SCHEMA governanca TO "<sp-client-id>";
  GRANT SELECT ON ALL TABLES IN SCHEMA governanca TO "<sp-client-id>";
  GRANT USAGE ON SCHEMA gestao_acesso TO "<sp-client-id>";
  GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA gestao_acesso TO "<sp-client-id>";
  ALTER DEFAULT PRIVILEGES IN SCHEMA gestao_acesso GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "<sp-client-id>";
  ```

## 5. Publicar o app (Databricks Apps)
```bash
databricks apps create marketplace-dados
databricks sync --watch . /Workspace/Users/<voce>/marketplace-dados   # ou databricks bundle
databricks apps deploy marketplace-dados \
  --source-code-path /Workspace/Users/<voce>/marketplace-dados
```
- Comando de runtime: `gunicorn -c gunicorn.conf.py app:app` (ver `app.yaml`).
- Porta: bind em `DATABRICKS_APP_PORT` (nunca 8080).
- `FLASK_SECRET_KEY`: configure como secret/resource da app.

## 6. Verificação pós-deploy
- `GET /health` → `{"status":"ok"}`.
- Catálogo carrega iniciativas; fluxo solicitar→autorizar→aprovar→efetivar concede acesso
  real (verificar em Catalog Explorer / `SHOW GRANTS ON SCHEMA ...`).
- Rodar `pytest tests/` (integração) apontando para a workspace.

## Observação sobre grants de grupo
Grants a grupos exigem **grupos de conta** no Unity Catalog (ver `docs/DECISIONS.md` D-009).
Em dev, os grupos criados via SCIM são workspace-local e o grant de grupo resulta em
`ERRO_EFETIVACAO` (tratado/reprocessável). No cliente, use grupos de conta reais.

# Marketplace de Dados — Sicoob

App de **catálogo e gestão de acesso a dados** (Databricks App · Flask + Jinja2 · Lakebase).
O catálogo gira em torno do **ativo** (`ativo_aisn`) — a unidade liberável em **qualquer
nível** (domínio, subdomínio, iniciativa/schema ou tabela). O usuário pede acesso a um ativo
(para si ou para seu grupo exploratório); a aprovação é em duas etapas — **gestor imediato**
→ **owner do ativo** — e a efetivação é por **associação ao grupo do ativo** (o grupo detém
o privilégio no Unity Catalog).

Cobre o MVP dos requisitos (RN-001..042 / RF-001..092) de `Requisitos - App Acesso.pdf`.

## Arquitetura
```
Usuário ─▶ App Flask (Databricks Apps)
             ├─ lê  governanca   (catálogo = ativos)  ── SYNC ◀── Delta (UC) = fonte da verdade (Motor)
             ├─ lê/grava gestao_acesso (ciclo de vida) — nativo no Lakebase
             ├─ associa o beneficiário ao GRUPO DO ATIVO (SCIM: account groups em prod)
             └─ provisiona o GRANT do grupo nos objetos UC (por nível: schema/tabela)
```
- **governanca** (16 tabelas): modelo do Motor, mantido em Delta no UC e **sincronizado** para
  o Lakebase (synced tables nativas em produção; sync controlado no protótipo — ver
  `docs/DECISIONS.md` D-010/D-011). O app **só lê**. Inclui `ativo_aisn` (driver do catálogo,
  **polimórfico**: `id_ativo_aisn` = PK da entidade de origem, `cod_tipo_ativo` numérico).
- **gestao_acesso**: solicitação → autorização hierárquica → aprovação owner → acesso →
  execução técnica → revogação + trilha de auditoria. Nativo no Lakebase (leitura/escrita).
- **Concessão = associação a grupo** (não GRANT por usuário): o beneficiário é incluído no
  grupo do ativo, que detém o privilégio no UC. Ver `docs/ARQUITETURA-APP.md`.
- Nomenclatura: snake_case + prefixos (`docs/DECISIONS.md` D-001).

> **Rotas e fontes de dados:** `docs/ARQUITETURA-APP.md` documenta cada rota, o serviço que
> ela chama e de onde busca/grava os dados.

## Estrutura
```
app/            Flask (factory, config, db, identity, worker)
  services/     catálogo, solicitação, aprovação, acesso, ativo_scope, membership/grant executor, auditoria
  routes/       blueprints (catálogo, solicitações, aprovações, acessos, auditoria)
  templates/    Jinja2 (tema Sicoob) · static/style.css
db/
  ddl/          01_governanca.sql, 02_gestao_acesso.sql
  seed/         dataset sintético + build Delta + alvos UC
  sync/         sync controlado Delta→Lakebase (dev)
  native_sync_setup.py   synced tables NATIVAS (cliente)
  setup.py      entrypoint único: python -m db.setup --mode dev|native
tests/          pytest (regras de negócio + e2e com grant real)
docs/           DECISIONS, DEPLOY, guia de implantação (HTML), modelo de dados
scripts/        helpers (uc_sql, lb_conn, smoke_fluxo)
```

## Rodar localmente
```bash
pip install -r requirements.txt
export DATABRICKS_CONFIG_PROFILE=DEFAULT
python -m db.setup --mode dev        # provisiona banco + seed (idempotente)
python run.py                        # http://localhost:8000
```
No protótipo, use o seletor **"Atuar como (proxy)"** para navegar como solicitante,
gestor (ex.: Mariana Alves) e owner (ex.: Ana Paula Ribeiro).

## Testes
```bash
export DATABRICKS_CONFIG_PROFILE=DEFAULT APP_DISABLE_WORKER=true
python -m pytest tests/              # 15 regras/modelo (rápido) + 2 e2e (associação real ao grupo, lento)
```
> Para o e2e determinístico, pare o app publicado antes (`databricks apps stop marketplace-dados`)
> e reinicie depois — senão o worker publicado (SP) pode disputar as execuções pendentes.

## Deploy (workspace do cliente)

Guia visual completo: **`guia-implementacao.html`** (na raiz; cópia em `docs/`).
Runbook detalhado: **`docs/DEPLOY.md`**. O código do banco é parametrizado — nada é fixo
fora de `app/config.py`. Passo a passo:

### 0. Infraestrutura (o cliente provisiona)
- Workspace Databricks com **Unity Catalog**; **SQL Warehouse serverless** ativo.
- **Projeto Lakebase** (autoscaling, PG 17).
- **Catálogo UC + schemas reais** dos dados (alvos do grant) — já existentes.
- **Service Principal** do app; **SSO**; **account groups** (se usar grant por grupo).
- **Base de governança** (domínios, iniciativas, camadas, owners, hierarquia) em Delta,
  mantida pelo Motor de Governança do cliente.

### 1. Obter o código
```bash
git clone https://github.com/lfmed/marketplace-dados-sicoob.git
cd marketplace-dados-sicoob
pip install -r requirements.txt
```
Ou via **Git folders** do Databricks (Workspace → Repos → Add repo, ou
`databricks repos create <url> gitHub --path /Workspace/Users/<voce>/marketplace-dados`).

### 2. Autenticar o CLI + criar o Lakebase
```bash
databricks auth login --host https://<workspace>.cloud.databricks.com
databricks postgres create-project marketplace-dados \
  --json '{"spec":{"display_name":"Marketplace Dados Sicoob","pg_version":"17"}}'
```

### 3. Configurar (`app.yaml` / env)
```
UC_CATALOG            catálogo UC existente onde ficam os schemas de dados
DATABRICKS_WAREHOUSE_ID   warehouse p/ DDL e GRANT/REVOKE
LAKEBASE_ENDPOINT     projects/marketplace-dados/branches/production/endpoints/primary
LAKEBASE_UC_CATALOG   catálogo que registra o Lakebase no UC (ex.: lakebase_marketplace)
GRANT_EXECUTE_REAL    true
APP_ENABLE_PROXY      false   # produção: identidade só por SSO (X-Forwarded-Email)
GROUPS_SCOPE          account # produção: grupos de conta (dev sem conta: workspace)
DATABRICKS_ACCOUNT_ID <account-id>   # exigido quando GROUPS_SCOPE=account
```

### 4. Provisionar o banco
```bash
# Produção: synced tables nativas, sem seed sintético (requer CREATE CATALOG no metastore)
python -m db.setup --mode native --no-seed
# Dev/demo: sync controlado + seed sintético
python -m db.setup --mode dev
```
Cria `gestao_acesso` no Lakebase e o espelho `governanca` (synced tables do Delta real).
Seed opcional: `--seed` / `--no-seed`. As tabelas também podem ser criadas manualmente
(`psql -f db/ddl/02_gestao_acesso.sql`) e a governança populada pelo seu próprio ETL.

### 5. Permissões do service principal
```bash
python scripts/grant_app_sp.py <sp_client_id>
```
Concede `USE CATALOG` + `MANAGE` no catálogo/schemas, `CAN_USE` no warehouse e um role no
Lakebase. Comandos explícitos em `docs/DEPLOY.md` §4.

**Concessão por grupo:** como a efetivação inclui o beneficiário no **grupo do ativo**, o SP
do app precisa poder **gerenciar a associação desses grupos**. Em produção (grupos de conta,
`GROUPS_SCOPE=account`), torne o SP **gerente dos grupos de conta** (ou admin de conta). Em
dev (grupos workspace-local), o SP precisa poder gerenciar grupos do workspace (ex.: estar em
`admins`). Ver `docs/DEPLOY.md` §2.

### 6. Publicar no Databricks Apps
```bash
databricks apps create marketplace-dados
databricks sync . /Workspace/Users/<voce>/marketplace-dados   # pule se usou Git folders
databricks apps deploy marketplace-dados \
  --source-code-path /Workspace/Users/<voce>/marketplace-dados
```
Runtime `gunicorn -c gunicorn.conf.py app:app` (`app.yaml`); bind em `DATABRICKS_APP_PORT`
(nunca 8080); `FLASK_SECRET_KEY` como *secret*.

### 7. Verificar
```bash
curl -s https://<app-url>/health          # -> {"status":"ok"}
python -m pytest tests/                    # regras + e2e com grant real
# conferir no UC:  SHOW GRANTS ON SCHEMA <UC_CATALOG>.<schema_real>
```

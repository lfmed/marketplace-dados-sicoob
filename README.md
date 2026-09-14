# Marketplace de Dados — Sicoob

App de **catálogo e gestão de acesso a dados** (Databricks App · Flask + Jinja2 · Lakebase).
O catálogo gira em torno do **ativo** (`ativo_aisn`) — a unidade liberável em **qualquer
nível** (domínio, subdomínio, iniciativa/ICA ou tabela). O usuário pede acesso a um ativo
(para si ou para um grupo do qual é membro); a aprovação é em duas etapas — **gestor
imediato** → **owner do ativo** — e a efetivação é por **associação ao grupo do ativo** (o
grupo detém o privilégio no Unity Catalog).

Cobre o MVP dos requisitos (RN-001..042 / RF-001..092) de `Requisitos - App Acesso.pdf`.

## Arquitetura — 3 schemas (modelo oficial do cliente)
```
Usuário ─▶ App Flask (Databricks Apps)
             ├─ lê  governanca     (taxonomia + ativos-origem)   ─┐ Delta do Motor
             ├─ lê  gestao_acesso  (referência: ativos, grupos)  ─┘ (plataforma), sync → Lakebase
             ├─ lê/grava marketplace_app (workflow do app)  — nativo no Lakebase
             └─ associa o beneficiário ao GRUPO DO ATIVO (SCIM: account groups em prod)
```
Catálogo Delta **`plataforma`** (parametrizável via `GOV_CATALOG`); nomes de schema também
parametrizáveis (`SCHEMA_*`). Distribuição:

- **`governanca`** (Motor de Governança, **somente leitura**): taxonomia — domínio,
  subdomínio, iniciativa, camada, ambiente; as combinações **`iniciativa_camada_ambiente`,
  `subdominio_camada_ambiente`, `dominio_camada_ambiente`**; **`tabela_aisn`** (única com o
  alvo UC catálogo/schema/tabela); `usuario_aisn`; e os proprietários de domínio/subdomínio/
  iniciativa.
- **`gestao_acesso`** (Motor de Acesso, **somente leitura**): `hierarquia_usuario`,
  `grupo_acesso`, `grupo_acesso_membro`, **`ativo_aisn`** (o driver do catálogo) e
  `ativo_proprietario`. O ativo é **polimórfico** — `id_ativo_aisn` = PK da combinação de
  origem, discriminada por `cod_tipo_ativo` (1=ICA, 2=TABELA, 3=SUBDOMINIO, 4=DOMINIO) — e
  já traz o **grupo embutido** (`nome_grupo_ativo`).
- **`marketplace_app`** (workflow do App, **leitura/escrita**): solicitação → autorização
  hierárquica → aprovação owner → acesso → execução técnica → revogação + trilha de auditoria.

Sincronização Delta→Lakebase: synced tables nativas em produção; sync controlado no protótipo
(ver `docs/DECISIONS.md` D-010/D-011). O **escopo UC** de qualquer ativo é resolvido **sempre
via `tabela_aisn`** (a ICA não tem schema próprio). **Concessão = associação a grupo** (não
GRANT por usuário): o beneficiário entra no grupo do ativo, que já detém o privilégio no UC
(concedido pelo Motor em produção). Nomenclatura: snake_case + prefixos (D-001).

> **Rotas e fontes de dados:** `docs/ARQUITETURA-APP.md` (e `docs/arquitetura-app.html`)
> documentam cada rota, o serviço que ela chama e de onde busca/grava os dados.

## Estrutura
```
app/            Flask (factory, config, db, identity, worker, schemas)
  services/     catálogo, solicitação, aprovação, acesso, ativo_scope, membership/grant executor, auditoria
  routes/       blueprints (catálogo, solicitações, aprovações, acessos, auditoria)
  templates/    Jinja2 (tema Sicoob) · static/style.css
db/
  ddl/          01_governanca.sql · 02_gestao_acesso.sql · 03_app.sql (workflow)
  seed/         dataset sintético + build Delta + alvos UC (dev)
  sync/         sync controlado Delta→Lakebase (dev)
  native_sync_setup.py   synced tables NATIVAS (cliente)
  setup.py      entrypoint único: python -m db.setup --mode dev|native
tests/          pytest (regras/modelo + e2e com associação real ao grupo)
docs/           DECISIONS, DEPLOY, ARQUITETURA-APP, guia de implantação (HTML)
scripts/        helpers (uc_sql, lb_conn, grant_app_sp, verify_deployed_worker)
```

## Rodar localmente (dev)
```bash
pip install -r requirements.txt
export DATABRICKS_CONFIG_PROFILE=DEFAULT
python -m db.setup --mode dev        # provisiona banco + seed sintético (idempotente)
python run.py                        # http://localhost:8000
```
No protótipo, use o seletor **"Atuar como (proxy)"** para navegar como solicitante,
gestor (ex.: Mariana Alves) e owner (ex.: Ana Paula Ribeiro).

## Testes
```bash
export DATABRICKS_CONFIG_PROFILE=DEFAULT APP_DISABLE_WORKER=true
python -m pytest tests/              # 16 regras/modelo (rápido) + 2 e2e (associação real ao grupo, lento)
```
> Para o e2e determinístico, pare o app publicado antes (`databricks apps stop marketplace-dados`)
> e reinicie depois — senão o worker publicado (SP) pode disputar as execuções pendentes.

---

# Deploy no cliente (as tabelas de governança já existem)

Guia visual: **`guia-implementacao.html`** (raiz; cópia em `docs/`). Runbook: **`docs/DEPLOY.md`**.
No cliente, `governanca` e `gestao_acesso` (com **ativos, grupos e proprietários**) **já são
mantidos pelo Motor** em Delta (`plataforma.*`) — o app **não os cria nem semeia**. O app só
cria o próprio schema de workflow (`marketplace_app`) e consome o resto.

> **⚡ Sem a CLI `databricks` (firewall)?** Não precisa dela. Com o repo **já clonado** no
> Databricks (Git folders), crie/publique o app pela **UI de Apps** apontando para a pasta
> do repo (passo 6). Na subida, a **própria app cria o `marketplace_app`** no Lakebase (pelo
> SP, server-side) e **loga cada ponto provisionado/verificado** em *App ▸ Logs*
> (`AUTO_BOOTSTRAP_APP_SCHEMA=true`, default). Os comandos de CLI (passos 2, 4 e 6) viram
> alternativas. Detalhes: `docs/DEPLOY.md` §⚡.

### 0. O que o cliente provisiona (o resto já existe)
- **Projeto Lakebase** (autoscaling, PG 17) para o app.
- **SQL Warehouse serverless** ativo (para registrar as synced tables / DDL).
- **Service Principal** do app; **SSO** na workspace.
- **`plataforma.governanca` + `plataforma.gestao_acesso`** já criados e populados pelo Motor
  (taxonomia, `tabela_aisn`, `ativo_aisn` com `nome_grupo_ativo`, `grupo_acesso`, owners…).
- **Account groups** dos ativos já existentes (os `nome_grupo_ativo`), com o **GRANT já
  concedido** nos objetos pelo Motor/governança.

### 1. Obter o código
```bash
git clone https://github.com/lfmed/marketplace-dados-sicoob.git
cd marketplace-dados-sicoob && pip install -r requirements.txt
```
Ou via **Git folders** do Databricks (Workspace → Repos → Add repo).

### 2. Autenticar + criar o Lakebase
```bash
databricks auth login --host https://<workspace>.cloud.databricks.com
databricks postgres create-project marketplace-dados \
  --json '{"spec":{"display_name":"Marketplace Dados Sicoob","pg_version":"17"}}'
```

### 3. Configurar (`app.yaml` / env) — catálogo e schema parametrizáveis
```
GOV_CATALOG           plataforma        # catálogo Delta do Motor (governanca + gestao_acesso)
SCHEMA_GOVERNANCA     governanca
SCHEMA_GESTAO         gestao_acesso
SCHEMA_APP            marketplace_app   # schema do workflow do app (criado pelo app)
LAKEBASE_ENDPOINT     projects/marketplace-dados/branches/production/endpoints/primary
DATABRICKS_WAREHOUSE_ID  <warehouse-id>
GROUPS_SCOPE          account           # grupos de conta (principais do UC)
DATABRICKS_ACCOUNT_ID <account-id>
PROVISION_GROUP_GRANT false             # o Motor já concede o grant do grupo; app só faz membership
GRANT_EXECUTE_REAL    true
APP_ENABLE_PROXY      false             # identidade só por SSO (X-Forwarded-Email)
```

### 4. Provisionar o banco (sem seed — governança já existe)

**Sem CLI:** o `marketplace_app` é criado pela app na subida (§⚡). As *synced tables* dos
mirrors (governanca/gestao_acesso) são registradas **sem CLI** rodando o notebook
**`notebooks/registrar_synced_tables.py`** no workspace (server-side — chama
`db.native_sync_setup`; exige `CREATE CATALOG` no metastore). Alternativas p/ o
`marketplace_app`: `from app.bootstrap import run; run()` num notebook, ou colar
`db/ddl/marketplace_app.sql` no editor SQL do Lakebase.

**Com CLI** (cria o `marketplace_app` **e** registra as synced tables num passo só):
```bash
python -m db.setup --mode native --no-seed
```
Cria o schema **`marketplace_app`** (workflow do app) no Lakebase e registra as **synced
tables nativas** de `plataforma.governanca` e `plataforma.gestao_acesso` (mirror somente
leitura). **Não** cria nem semeia a governança (já existe, mantida pelo Motor).

### 5. Permissões do service principal (concessão = membership)
- **Gerente dos account groups dos ativos** — para incluir/remover membros (é a concessão).
  Em produção o SP **não** precisa de `MANAGE` nos schemas de dados: o Motor já concedeu o
  grant do grupo (`PROVISION_GROUP_GRANT=false`).
- **Role no Lakebase** (OAuth) para conectar no Postgres.
- **`CAN_USE`** no warehouse.
- **`SELECT`** nas tabelas Delta `plataforma.governanca.*` e `plataforma.gestao_acesso.*`
  (para as synced tables lerem a origem).

Comandos explícitos em `docs/DEPLOY.md` §4.

### 6. Publicar no Databricks Apps

**Sem CLI (recomendado no cliente):** *Compute ▸ Apps ▸ Create app*, aponte o **source code
path** para a pasta do repo em *Repos*, configure as env vars (passo 3) e faça **Deploy**
pela UI. Na subida a app provisiona o `marketplace_app` e loga tudo (§⚡).

**Com CLI:**
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
```
No app: **solicitar → autorizar (gestor) → aprovar (owner do ativo) → efetivar**. Confirme que
o beneficiário **virou membro** do account group do ativo e que o grupo **detém o `SELECT`**
no objeto:
```sql
SHOW GRANTS ON SCHEMA <catalogo>.<schema_real>;   -- o grupo do ativo aparece com SELECT
```

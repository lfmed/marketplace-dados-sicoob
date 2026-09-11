# Deploy — Marketplace de Dados Sicoob

Guia para provisionar o banco e publicar o app em **qualquer workspace** (dev ou cliente).
Todo o código de banco é reproduzível e parametrizado (ver `app/config.py`).

## ⚡ Deploy SEM a CLI databricks (recomendado no cliente — repo já clonado)

Quando o cliente **não consegue usar a CLI `databricks`** (ex.: firewall bloqueia o
`databricks` local), **não precisa dela**. Como o **repositório já está clonado no
Databricks** (Repos/Git folder) e o app roda **dentro** da workspace, todo o
provisionamento acontece server-side. Passos, tudo pela **UI**:

1. **Repo clonado** em *Workspace ▸ Repos* (Git folder) — já feito.
2. **Criar o App** em *Compute ▸ Apps ▸ Create app*, apontando o **source code path** para
   a pasta do repo clonado. Configure as env vars do cliente (ver §2 e `app.yaml`:
   `GOV_CATALOG=plataforma`, `SCHEMA_*`, `GROUPS_SCOPE=account`, `PROVISION_GROUP_GRANT=false`,
   `DATABRICKS_ACCOUNT_ID`). Comando de runtime já vem no `app.yaml`.
3. **Deploy pela UI.** Na subida, a **própria app provisiona o schema de workflow**
   (`marketplace_app`) direto no Lakebase (pelo service principal, sem CLI) e **loga em
   detalhe** cada ponto — veja em *App ▸ Logs* (ou `databricks apps logs`, se disponível):
   ```
   [bootstrap ...] » PROVISIONAMENTO NA SUBIDA DO APP — Marketplace de Dados
   [bootstrap ...] ✓ conexão OK — usuário=<sp> database=databricks_postgres
   [bootstrap ...] » [2/3] provisionando schema de workflow 'marketplace_app' …
   [bootstrap ...]   tabela marketplace_app.solicitacao_acesso — ＋ CRIADA
   [bootstrap ...] ✓ schema 'marketplace_app' pronto: 7 tabelas
   [bootstrap ...] » [3/3] verificando schemas espelho do Motor (só-leitura) …
   [bootstrap ...] ✓   gestao_acesso.ativo_aisn: 74 linhas
   [bootstrap ...] ✓ PROVISIONAMENTO OK — app pronto para atender.
   ```
   Isso é controlado por `AUTO_BOOTSTRAP_APP_SCHEMA` (default `true`). É idempotente e
   serializado entre workers (advisory lock) — pode reiniciar à vontade.

> **O que a app cria vs. o que já tem que existir:** a app só cria o **seu** schema de
> workflow (`marketplace_app`). Os schemas de **leitura** `governanca` e `gestao_acesso`
> são **synced tables do Motor** do cliente — devem existir **antes** (o log `[3/3]` acima
> confirma que a app as enxerga; se aparecer `✗ ... VAZIO/ausente`, o time do Motor precisa
> registrá-las — ver §3).

**Alternativas sem CLI** para criar o `marketplace_app` (caso prefira não usar o boot):
- **Notebook no repo clonado** (server-side): abra um notebook na pasta do repo e rode
  ```python
  %pip install -r requirements.txt
  import os
  os.environ["AUTO_BOOTSTRAP_APP_SCHEMA"] = "false"
  os.environ["APP_DISABLE_WORKER"] = "true"
  from app.bootstrap import run
  run()
  ```
- **Editor SQL do Lakebase**: cole o arquivo pronto `db/ddl/marketplace_app.sql`
  (gerado por `scripts/gen_app_sql.py` a partir do `03_app.sql`) e execute.

O restante deste guia detalha os recursos de infra (§0), parâmetros (§2) e a rota **com**
CLI (§3, §5) para quem a tiver.

## 0. O que o CLIENTE provisiona (checklist de infra)

O código (app Flask + banco) é entregue pronto, idempotente e parametrizado. Do lado do
cliente é preciso ter os recursos abaixo **antes** de publicar:

| # | Recurso | Para quê | Quem cria |
|---|---|---|---|
| 1 | **Workspace Databricks** com **Unity Catalog** habilitado | base de tudo | cliente |
| 2 | **SQL Warehouse serverless** (ativo) | executa o DDL e os `GRANT/REVOKE` reais | cliente |
| 3 | **Projeto Lakebase** (autoscaling, PG 17) | banco transacional do app: ciclo de vida do acesso (`gestao_acesso`) + espelho da governança (`governanca`) | cliente (ou nós, com acesso) |
| 4 | **Catálogo UC de destino** já existente + os **schemas reais** que guardam os dados por iniciativa/camada | são os **alvos** do grant (o app concede `SELECT`/`MODIFY` neles) | cliente — os dados já existem |
| 5 | **Service Principal do app** com `USE CATALOG`+`MANAGE` no catálogo, `MANAGE` nos schemas alvo, `CAN_USE` no warehouse e um role no Lakebase | o app **efetiva o acesso** agindo como esse SP | cliente concede (script pronto — §4) |
| 6 | **Base de governança** (domínios, subdomínios, **iniciativas**, camadas, ambientes, **owners**, usuários, **hierarquia** gestor/superior, grupos) em **tabelas Delta**, mantida pelo **Motor de Governança** do cliente | é o que o app cataloga e usa p/ validar elegibilidade e rotear as aprovações | cliente (Motor de Governança) |
| 7 | **Grupos de conta** (account groups) no UC — se for usar acesso por grupo exploratório | grant a grupo exige account group (D-009) | cliente |
| 8 | **SSO** na workspace | identidade do usuário logado no app (via header `X-Forwarded-Email`) | cliente |

> **Dev vs. Produção — a diferença central:** em **dev** nós geramos dados **sintéticos**
> (governança fake + schemas UC `mkt_*` fake) só para testar o grant real ponta a ponta.
> Em **produção NÃO se semeia nada**: a base de governança vem do **Motor de Governança**
> do cliente (item 6) e os alvos de grant são os **schemas reais** do cliente (item 4). O
> app é o mesmo; muda a **origem dos dados** (parametrizada) e o modo de sync (§3, `native`).

**Fluxo de dados em produção:** Motor de Governança (Delta) → *synced tables* → Lakebase
`governanca` (leitura) · o app grava o ciclo de vida em Lakebase `gestao_acesso` · e
**efetiva o acesso no Unity Catalog** (grant no schema real) via o SP do app.

## 1. Pré-requisitos
- Databricks CLI autenticado na workspace-alvo (`databricks auth login`) — **opcional**:
  se o cliente não puder usar a CLI (firewall), use a rota **sem CLI** acima (⚡).
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
| `AUTO_BOOTSTRAP_APP_SCHEMA` | app cria o schema `marketplace_app` no boot (deploy sem CLI) | `true` |
| `APP_ENABLE_PROXY` | seletor "atuar como" (demo) | `true` (prod: `false`) |
| `GROUPS_SCOPE` | escopo dos grupos: `account` (produção) ou `workspace` (dev) | `workspace` (prod: `account`) |
| `DATABRICKS_ACCOUNT_ID` | id da conta (só quando `GROUPS_SCOPE=account`) | — |
| `DATABRICKS_ACCOUNT_HOST` | host do console de conta | `https://accounts.cloud.databricks.com` |

> **Concessão por associação a grupo (importante).** O acesso é concedido incluindo o
> beneficiário no **grupo do ativo** (`ativo_aisn.id_grupo_acesso`), que detém o `GRANT` no
> UC. Em **produção** esses grupos são **grupos de CONTA** (`GROUPS_SCOPE=account`): são
> principais válidos no UC e o app os gerencia via AccountClient — o **service principal do
> app precisa de direito de _gerente de grupo_ desses grupos de conta** (ou ser admin de
> conta), além de `DATABRICKS_ACCOUNT_ID`. Em **dev sem acesso à conta** (`GROUPS_SCOPE=
> workspace`) usam-se grupos workspace-local: a associação funciona (o SP precisa poder
> gerenciar grupos do workspace — ex.: estar no grupo `admins`), mas o `GRANT` do grupo nos
> objetos **não propaga** (grupo workspace-local não é principal do UC — limitação D-009).

## 3. Provisionar o banco (reproduzível)

> **Sem CLI?** O schema de workflow (`marketplace_app`) é criado **automaticamente na
> subida do app** (§⚡ acima, `AUTO_BOOTSTRAP_APP_SCHEMA=true`) — esta seção é para quem
> tem CLI ou quer rodar o provisionamento completo (incl. synced tables) explicitamente.

Um único entrypoint recria tudo (idempotente):

```bash
# CLIENTE (produção) — synced tables NATIVAS, SEM seed sintético (exige CREATE CATALOG):
python -m db.setup --mode native --no-seed

# DEV/protótipo — sync controlado Delta->Lakebase + seed sintético (sem CREATE CATALOG):
python -m db.setup --mode dev
```

> **Seed opcional** (`--seed` / `--no-seed`): liga por padrão em `--mode dev` e desliga em
> `--mode native`. O seed cria a governança **sintética** + schemas UC `mkt_*` de teste;
> em produção use `--no-seed` para o app consumir a governança e os schemas **reais**.

O que cada passo faz:
1. Cria schemas Lakebase: `gestao_acesso` (sempre) e, em `dev`, `governanca`.
2. **[dev]** Cria as tabelas Delta de governança sintéticas (`{UC_CATALOG}.marketplace_governanca`) + seed.
   **[prod]** Pulado — a governança vem do Motor de Governança do cliente.
3. **[dev]** Cria alvos de GRANT sintéticos no UC (grupos + 1 schema `mkt_*` por iniciativa+camada).
   **[prod]** Pulado — os alvos são os **schemas reais** do cliente já existentes.
4. Popula `governanca` no Lakebase: `native` (prod) = synced tables a partir do Delta do
   Motor; `dev` = sync controlado a partir do schema sintético.

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

**Sem CLI (repo já clonado) — recomendado no cliente:** *Compute ▸ Apps ▸ Create app*,
aponte o **source code path** para a pasta do repo em *Repos*, configure as env vars (§2)
e faça **Deploy** pela UI. Na subida a app provisiona o `marketplace_app` e loga tudo (§⚡).

**Com CLI:**
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

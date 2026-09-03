# Decisões de Arquitetura — Marketplace de Dados Sicoob

Registro das decisões-chave. Cada uma tem id `D-NNN`, data e origem.

## D-001 — Nomenclatura: snake_case (do .drawio) — 2026-09-03
Diante do conflito entre o Guia PDF (PascalCase) e o modelo .drawio (snake_case),
**seguimos snake_case** com prefixos semânticos (`id_`,`nome_`,`desc_`,`cod_`,`bol_`,
`datahora_`,`tipo_`) e sufixo `_aisn`. Motivo: modelo concreto entregue + nativo do
Postgres/Lakebase (evita identificadores aspados) + respeita o espírito do guia.
*(Confirmado pelo usuário.)*

## D-002 — Schema `gestao_acesso` projetado por nós — 2026-09-03
O .drawio traz só governança. **Projetamos** o schema `gestao_acesso` (ciclo de vida:
solicitação, autorização hierárquica, aprovação do owner, acesso, execução técnica,
revogação, eventos) no mesmo estilo do modelo, com **checkpoint de validação com o
usuário antes de implementar**. *(Confirmado pelo usuário.)*

## D-003 — Efetivação com GRANTs REAIS no Unity Catalog — 2026-09-03
A efetivação técnica (RN-030) executa **GRANT/REVOKE reais no Unity Catalog** desta
workspace de dev. Para viabilizar, **criamos objetos UC reais** (catálogos/schemas/
tabelas de exemplo representando as iniciativas Sicoob, camadas Bronze/Silver/Gold) que
servem de alvo dos grants. Executor idempotente (RN-041), com estados
Aprovado→Efetivado/Erro. *(Confirmado pelo usuário — "executar grants reais no uc, você
deve criar exemplos de iniciativas para poder simular".)*

## D-004 — Seed sintético estilo Sicoob + objetos UC reais — 2026-09-03
Populamos o schema `governanca` com **dados sintéticos realistas** no estilo do
screenshot (domínios: Canais e Experiência, Cliente e Relacionamento, etc.; iniciativas,
owners, hierarquia, grupos exploratórios). As entradas de `tabela_aisn` **apontam para os
objetos UC reais** criados na D-003, para o teste de grant ser real ponta a ponta.
*(Confirmado pelo usuário.)*

## D-005 — Identidade: SSO em prod + "Atuar como (proxy)" para demo — 2026-09-03
*(Default assumido, não perguntado.)* Em produção, a identidade vem do SSO do Databricks
Apps (header `X-Forwarded-Email`). No protótipo, mantemos o seletor **"Atuar como
(proxy)"** do screenshot para demonstrar os papéis (solicitante/gestor/owner) sem precisar
de múltiplos logins. Configurável/desligável para o deploy no cliente. *(Sinalizar ao
usuário; reverter se discordar.)*

## D-006 — Workspace de desenvolvimento — 2026-09-03
Dev na workspace `fevm-stable-classic-pg4xe1.cloud.databricks.com` (perfil CLI DEFAULT,
válido). App deve ser **parametrizável** para deploy futuro na workspace do cliente (sem
hardcode de host/catálogo/warehouse).

## D-007 — Catálogo é parâmetro de config; app só cria schemas — 2026-09-03
Neste ambiente **não é possível criar catálogos UC** (metastore com Default Storage exige
a UI). Portanto: o **nome do catálogo é um parâmetro de configuração** (`UC_CATALOG`,
dev = `stable_classic_pg4xe1_catalog`) e o App/seed **só criam e concedem em SCHEMAS**
dentro dele. *(Confirmado pelo usuário: "o catálogo pode ser especificado como um arquivo
de configuração, nesse meu ambiente não posso criar catálogos, só schemas".)*

## D-008 — Grant no nível de SCHEMA (= iniciativa+camada+ambiente) — 2026-09-03
Cada **unidade funcional de acesso** (`iniciativa_camada_ambiente`) mapeia para **um
schema UC**. Como não há acesso granular por tabela (RN-003), a concessão é
`GRANT USE CATALOG` + `USE SCHEMA` + `SELECT ON SCHEMA` (cascateia para todas as tabelas),
e a revogação o inverso. Validado no ambiente (schema/tabela/grant/revoke OK).

## D-009 — Grant de grupo exige grupo de CONTA no UC — 2026-09-03
Validado no ambiente: `GRANT ... TO <email real>` funciona (nominal verificável). Já
`GRANT ... TO <grupo>` exige um **principal de conta**; grupos criados via SCIM de
workspace são workspace-local e **não resolvem** (`PRINCIPAL_DOES_NOT_EXIST`); só
`account users` resolve. Não há `AccountClient` aqui para criar grupos de conta.
**Decisão:** o executor faz o grant **fiel ao modelo** (`TO <nome_grupo>`); na workspace
de dev, sem grupo de conta correspondente, isso resulta em **ERRO_EFETIVACAO** com
mensagem clara (demonstra RN-031/RF-061/RF-079 e o reprocessamento). Na workspace do
cliente, onde os grupos exploratórios serão grupos de conta reais, o caminho fica verde
sem mudança de código. O caminho **nominal** cobre a demonstração de grant real verde.

## D-010 — Governança em Delta (UC) sincronizada p/ Lakebase; gestão nativa no Lakebase — 2026-09-03
Arquitetura de dados (confirmada pelo usuário: "o modelo do drawio fica em tabelas Unity
Catalog no lakehouse, e são sincronizadas com o lakebase; as tabelas adicionais ficam no
lakebase"):
- **governanca (modelo .drawio)** → fonte da verdade em **tabelas Delta no UC**
  (`{catalog}.marketplace_governanca`), **sincronizada** para o schema `governanca` do
  Lakebase (o App lê a cópia no Lakebase).
- **gestao_acesso (ciclo de vida)** → nativo no **Lakebase**.

**Mecanismo de sync (ESCOLHIDO pelo usuário: synced tables NATIVAS agora):**
confirmado (docs + CLI) que Lakebase Autoscaling suporta synced tables de Delta via
`databricks postgres create-catalog` (registra o DB no UC) + `create-synced-table`
(+ `create-cdf-config` p/ TRIGGERED/CONTINUOUS). Neste SDK Python 0.99.0 esses métodos
**não existem** → usamos **CLI/REST**. Consequências:
- governanca no Lakebase = **synced tables somente-leitura/gerenciadas** (SNAPSHOT no
  protótipo; TRIGGERED com CDF possível). Criadas pelo sync, não por DDL manual.
- As **FKs `gestao_acesso → governanca` foram removidas** (viram referências lógicas
  validadas na aplicação), pois o lado governanca é gerenciado externamente/somente-leitura.
- gestao_acesso permanece nativo/gravável no Lakebase.
- App inalterado: continua lendo o schema `governanca` do Lakebase.
(O Glean estava indisponível — token OAuth expirado; capacidade confirmada via docs
oficiais e presença dos comandos no CLI.)

## D-011 — Synced tables nativas bloqueadas em dev por permissão; dev usa sync controlado — 2026-09-03
Descobri (empiricamente) o body correto das APIs beta:
- **Registrar DB no UC:** `POST /api/2.0/postgres/catalogs?catalog_id=<cat>` com corpo
  **não-embrulhado** `{"name":"<cat>","spec":{"postgres_database":"databricks_postgres",
  "branch":"projects/marketplace-dados/branches/production"}}`.
- **Synced table:** `POST /api/2.0/postgres/synced_tables?synced_table_id=<cat>.<schema>.<tab>`
  com `{"name":"synced_tables/<...>","spec":{"source_table_full_name":"<uc.delta>",
  "primary_key_columns":[...],"scheduling_policy":"SNAPSHOT","create_database_objects_if_missing":true,
  "new_pipeline_spec":{"storage_catalog":"<cat>","storage_schema":"marketplace_sync_ckpt"}}}`.

**Bloqueio em dev:** o registro do catálogo falha com *"User does not have CREATE CATALOG
on Metastore"* — leandro é admin de workspace, não de metastore. Não é contornável por mim.

**Resolução (mantém tudo pronto p/ o cliente):**
- Código **nativo pronto e parametrizado**: `db/native_sync_setup.py` (roda no cliente, que
  terá CREATE CATALOG). Idempotente.
- **Dev/protótipo:** `db/sync/sync_governanca.py` faz o sync controlado Delta→Lakebase
  (upsert por PK) para o app funcionar agora. A DDL de `gestao_acesso` **não tem FK dura**
  para governanca, então serve tanto para governanca=synced-readonly (cliente) quanto
  governanca=tabela-controlada (dev).
- Entrypoint único `db/setup.py --mode dev|native` recria TUDO em qualquer workspace
  (atende "deixe sempre o código do banco pronto p/ o cliente").
- **Para destravar nativo em dev:** um admin de metastore concede
  `GRANT CREATE CATALOG ON METASTORE TO \`leandro.medeiros@databricks.com\`` e roda
  `python -m db.setup --mode native`.

## D-012 — Deploy no Databricks Apps + permissões do SP — 2026-09-03
App publicado: `marketplace-dados` → https://marketplace-dados-7474646973581105.aws.databricksapps.com
(SP client id `0507aae8-d95f-474f-a35c-e7798ccb17ee`). Testado ponta a ponta NO APP
publicado: solicitar → autorizar (gestor) → aprovar (owner) → **GRANT real executado pelo
SP** (leandro obteve SELECT em `mkt_ib_trx_gold`), com trilha de auditoria completa.
**Lição:** para o SP conceder `USE CATALOG` aos beneficiários ele precisa de **MANAGE no
CATÁLOGO** (não basta MANAGE nos schemas) — o erro inicial `ERRO_EFETIVACAO` foi
corretamente capturado nas tabelas de log e resolvido com `GRANT MANAGE ON CATALOG` +
reprocessamento (RF-079/080). Permissões do SP codificadas em `scripts/grant_app_sp.py`
e documentadas em `docs/DEPLOY.md`. Lakebase: role Postgres do SP via `create-role` +
grants nos schemas.

## Infra provisionada (dev) — 2026-09-03
- **Lakebase (autoscaling):** project `projects/marketplace-dados`, branch `production`,
  endpoint `.../endpoints/primary` (host `ep-lucky-dawn-d2x5bhqt.database.us-east-1.cloud.databricks.com`),
  PG 17, db `databricks_postgres`. Conexão OAuth via SDK (`scripts/lb_conn.py`).
- **SQL Warehouse (para GRANTs/DDL UC):** `b8e52268d9828bdd` (Serverless Starter, RUNNING).
- **Catálogo UC (config):** `stable_classic_pg4xe1_catalog`.
- **Helper SQL UC:** `scripts/uc_sql.py`.

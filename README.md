# Marketplace de Dados — Sicoob

App de **catálogo e gestão de acesso a dados** (Databricks App · Flask + Jinja2 · Lakebase).
Usuários navegam um catálogo por **domínio → subdomínio → iniciativa** e solicitam acesso
(nominal ou por grupo exploratório). Aprovação em duas etapas — **gestor imediato** →
**owner da iniciativa** — e o app **efetiva o acesso via GRANT real no Unity Catalog**.

Cobre o MVP dos requisitos (RN-001..042 / RF-001..092) de `Requisitos - App Acesso.pdf`.

## Arquitetura
```
Usuário ─▶ App Flask (Databricks Apps)
             ├─ lê  governanca   (catálogo)  ── SYNC ◀── Delta (UC) = fonte da verdade (modelo .drawio)
             ├─ lê/grava gestao_acesso (ciclo de vida) — nativo no Lakebase
             └─ efetiva GRANT/REVOKE reais no Unity Catalog (nível de schema = iniciativa+camada)
```
- **governanca** (16 tabelas do `.drawio`): mantida em Delta no UC e **sincronizada** para o
  Lakebase (synced tables nativas em produção; sync controlado no protótipo — ver
  `docs/DECISIONS.md` D-010/D-011).
- **gestao_acesso** (9 tabelas): solicitação → autorização hierárquica → aprovação owner →
  acesso → execução técnica → revogação + trilha de auditoria. Nativo no Lakebase.
- Nomenclatura: snake_case + prefixos (`docs/DECISIONS.md` D-001).

## Estrutura
```
app/            Flask (factory, config, db, identity, worker)
  services/     catálogo, solicitação, aprovação, acesso, executor de grant, auditoria
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
python -m pytest tests/              # 7 regras (rápido) + 1 e2e com grant real (lento)
```

## Deploy
Ver **`docs/DEPLOY.md`** (provisionamento reproduzível + publicação no Databricks Apps +
permissões do service principal). O código do banco é parametrizado para recriação na
workspace do cliente.

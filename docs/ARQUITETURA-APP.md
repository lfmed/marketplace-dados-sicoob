# Arquitetura do App — Rotas e Fontes de Dados

Doc técnica do **Marketplace de Dados** (Flask + Jinja2 no Databricks Apps). Explica
**quais rotas existem**, **o que cada uma faz** e **de onde busca/grava os dados**.
Complementa `README.md` (visão geral), `DEPLOY.md` (deploy) e `DECISIONS.md` (decisões).

Modelo oficial do cliente: catálogo Delta **`plataforma`** e **3 schemas** no Lakebase,
todos **parametrizáveis** via `app/schemas.py` (← config: `GOV_CATALOG`, `SCHEMA_*`).

---

## 1. Camadas

```
Navegador
   │  (HTTP, SSO X-Forwarded-Email; em dev, proxy "atuar como")
   ▼
Flask (app/) ── blueprints (app/routes/*) ── camada fina: lê o form, resolve o usuário,
   │                                          chama um serviço e renderiza um template.
   ▼
Serviços (app/services/*) ── regras de negócio + SQL. É AQUI que os dados são lidos/gravados.
   │
   ├─▶ Lakebase (Postgres)         via app/db.py  (psycopg, OAuth 1h)
   │      ├─ {GOV} governanca       → LEITURA (mirror do Motor de Governança)
   │      ├─ {ACC} gestao_acesso    → LEITURA (mirror do Motor de Acesso: ativos, grupos, owners)
   │      └─ {APP} marketplace_app  → LEITURA/ESCRITA (workflow do App)
   ├─▶ Grupos SCIM                 via app/db.get_groups_client()  (account em prod / workspace em dev)
   │      └─ associar/desassociar o beneficiário no grupo do ativo (a CONCESSÃO)
   └─▶ Unity Catalog               via app/db.run_uc_sql (SQL Warehouse) — só quando
          PROVISION_GROUP_GRANT (dev). Em produção o Motor já concede o grant do grupo.
```

### Diagrama de fluxo (concessão de acesso)

```mermaid
flowchart TD
    U[Usuário] -->|/catalogo| CAT[catalog_service]
    CAT -->|lê ativo_aisn + tabela_aisn| GOVACC[(governanca + gestao_acesso<br/>mirrors do Motor)]
    U -->|/solicitar| REQ[request_service]
    REQ -->|grava solicitação + evento| APPW[(marketplace_app<br/>workflow, Lakebase)]
    U -->|/aprovacoes gestor + owner| APR[approval_service]
    APR -->|cria acesso + execução PENDENTE| APPW
    W[worker de background] -->|lê execuções PENDENTES| APPW
    W --> MEM[membership_executor]
    MEM -->|associa beneficiário ao grupo do ativo| SCIM[(Grupos SCIM<br/>account/workspace)]
    MEM -.->|só em dev: provisiona GRANT do grupo| UC[(Unity Catalog<br/>via SQL Warehouse)]
    MEM -->|atualiza status + evento| APPW
```

---

## 2. Fontes de dados (onde o app busca)

| Fonte | Como o app acessa | Papel | Leitura/Escrita |
|---|---|---|---|
| **`{GOV}` governanca** | `app/db.py` (Postgres) | **Taxonomia do Motor de Governança**: domínio, subdomínio, iniciativa, camada, ambiente; combinações `iniciativa/subdominio/dominio_camada_ambiente`; **`tabela_aisn`** (único com o alvo UC); `usuario_aisn`; proprietários dom/sub/ini. Mirror do Delta via synced tables (prod) / sync controlado (dev). | **Somente leitura** |
| **`{ACC}` gestao_acesso** | `app/db.py` (Postgres) | **Referência do Motor de Acesso**: `hierarquia_usuario`, `grupo_acesso`, `grupo_acesso_membro`, **`ativo_aisn`** (driver do catálogo, com `nome_grupo_ativo`) e `ativo_proprietario`. Mirror do Delta. | **Somente leitura** |
| **`{APP}` marketplace_app** | `app/db.py` (Postgres) | **Workflow do App**: solicitação → autorização → aprovação → acesso → execução técnica → revogação → eventos. Nativo no Lakebase. | **Leitura e escrita** |
| **Grupos (SCIM)** | `app/db.get_groups_client()` → AccountClient (prod) ou WorkspaceClient (dev) | **A concessão em si**: incluir/remover o beneficiário (usuário ou grupo do usuário) no **grupo do ativo**. | Leitura/escrita SCIM |
| **Unity Catalog** | `app/db.run_uc_sql` (SQL Warehouse) | **Só em dev** (`PROVISION_GROUP_GRANT=true`): garante o `GRANT` do grupo do ativo nos objetos resolvidos via `tabela_aisn`. Em produção o Motor já concedeu. | Escrita (DCL), dev |

> **`governanca` e `gestao_acesso` são mirrors** (somente leitura) do Motor do cliente
> (Delta em `plataforma.*` → synced tables). Só **`marketplace_app`** é transacional/do app.
> Ver `DECISIONS.md` D-010/D-011/D-015.

---

## 3. Identidade do usuário (`app/identity.py`)

`usuario_atual()` resolve o usuário corrente por ordem de precedência:
1. **Proxy** (dev/demo): `session["proxy_user_id"]` — seletor "Atuar como" (D-005).
2. **SSO** (produção): header `X-Forwarded-Email` do Databricks Apps → `usuario_por_email`.
3. **Fallback dev**: `DEV_FALLBACK_EMAIL`.

O e-mail é casado em `{GOV}.usuario_aisn` (`desc_email`). Se autenticado mas não mapeado,
retorna um stub só com e-mail (sem `id_usuario_aisn`). Os **papéis** (`gestor`, `owner`) e os
grupos do usuário são injetados em todos os templates por um `context_processor` em
`app/__init__.py` (gestor = existe em `{ACC}.hierarquia_usuario` como gestor; owner = existe
em `{ACC}.ativo_proprietario`).

---

## 4. Rotas (o que cada uma faz e de onde busca os dados)

Legenda de fontes: **G** = `{GOV}` governanca (leitura), **A** = `{ACC}` gestao_acesso
(referência, leitura), **APP** = `{APP}` marketplace_app (workflow), **SCIM** = grupos,
**UC** = Unity Catalog (só dev).

### `main` (`app/routes/main.py`)
| Método | Rota | Faz | Fontes |
|---|---|---|---|
| GET | `/` | redireciona p/ `/catalogo` | — |
| GET | `/health` | healthcheck `{"status":"ok"}` | — |
| POST | `/proxy` | troca o usuário atuante (dev) | sessão |

### `catalog` (`app/routes/catalog.py`) — serviço `catalog_service`
| Método | Rota | Faz | Fontes |
|---|---|---|---|
| GET | `/catalogo` | lista **ativos** (driver = `ativo_aisn`, com `nome_grupo_ativo` embutido), filtros por nível/domínio/subdomínio/busca; breadcrumb derivado polimorficamente | **A**: `ativo_aisn`, `ativo_proprietario`; **G**: `*_camada_ambiente`/`iniciativa`/`subdominio`/`dominio` + `usuario_aisn` |
| GET | `/ativo/<id_ativo>` | detalhe do ativo: owners, grupo, **escopo UC resolvido via `tabela_aisn`** (`ativo_scope`) e formulário de solicitação | **A**: ativo + owners + `grupo_acesso_membro`; **G**: `tabela_aisn` + taxonomia |

### `requests` (`app/routes/requests.py`) — serviço `request_service`
| Método | Rota | Faz | Fontes |
|---|---|---|---|
| POST | `/solicitar` | cria solicitação p/ um ativo (nominal ou grupo); valida RN-005/007/010/013/014 | lê **A**: `ativo_aisn`, `ativo_proprietario`, `grupo_acesso_membro`, `hierarquia_usuario`; **G**: `usuario_aisn`; grava **APP**: `solicitacao_acesso` + `evento_ciclo_vida` |
| GET | `/minhas-solicitacoes` | solicitações do usuário + status do acesso | **APP**: `solicitacao_acesso`, `acesso`; **A/G**: joins do ativo |
| GET | `/solicitacao/<id>` | detalhe + escopo UC + histórico + etapa pendente | **APP**: `solicitacao_acesso`, `acesso`, `evento_ciclo_vida`; **A**: ativo + `ativo_proprietario` |
| POST | `/solicitacao/<id>/cancelar` | cancela (RN-011) | grava **APP**: `solicitacao_acesso`, `evento_ciclo_vida` |

### `approvals` (`app/routes/approvals.py`) — serviço `approval_service`
| Método | Rota | Faz | Fontes |
|---|---|---|---|
| GET | `/aprovacoes` | fila do gestor (hierarquia) + fila do owner (do ativo) | **APP**: `solicitacao_acesso`; **A**: `hierarquia_usuario`, `ativo_proprietario`, ativo |
| POST | `/aprovacoes/<id>/gestor` | autoriza/reprova (RN-013/014) | grava **APP**: `autorizacao_hierarquica`, `solicitacao_acesso`, `evento` |
| POST | `/aprovacoes/<id>/owner` | aprova/reprova (RN-006/017); se aprova, **cria o acesso** | lê **A**: `ativo_proprietario`; grava **APP**: `aprovacao_owner`, `solicitacao_acesso`, `acesso`, `execucao_tecnica` (PENDENTE), `evento` |

### `accesses` (`app/routes/accesses.py`) — serviço `access_service`
| Método | Rota | Faz | Fontes |
|---|---|---|---|
| GET | `/meus-acessos` | acessos do usuário (nominal + por grupo) + acesso padrão de owner (RN-016/025) | **APP**: `acesso`; **A**: ativo + `grupo_acesso_membro` + `ativo_proprietario` |
| GET | `/acessos-owner` | acessos concedidos no escopo do owner | **APP**: `acesso`; **A**: ativo + `ativo_proprietario` + `grupo_acesso`; **G**: `usuario_aisn` |
| POST | `/acesso/<id>/revogar` | solicita revogação (RN-026) | lê **A**: `ativo_proprietario`; grava **APP**: `revogacao_acesso`, `execucao_tecnica` (PENDENTE), `evento` |
| POST | `/acesso/<id>/reprocessar` | reenfileira execução (RF-079/080) | grava **APP**: `execucao_tecnica` (PENDENTE) |

### `audit` (`app/routes/audit.py`) — serviço `audit_service`
| Método | Rota | Faz | Fontes |
|---|---|---|---|
| GET | `/auditoria` | trilha restrita ao escopo do owner (RF-088) | **APP**: `solicitacao_acesso` + `acesso`; **A**: ativo + `ativo_proprietario` + `grupo_acesso`; **G**: `usuario_aisn` |
| GET | `/resumo-dominio` | agregados por domínio (nº ativos, acessos, solicitações) — domínio derivado polimorficamente | **G**: `dominio_informacao`; **A**: `ativo_aisn`; **APP**: `acesso`, `solicitacao_acesso` |

---

## 5. O ativo como driver (resolução polimórfica)

O catálogo gira em torno de **`{ACC}.ativo_aisn`**. Sem colunas denormalizadas de UC:
**`id_ativo_aisn` É a PK da combinação de origem** e **`cod_tipo_ativo`** (código numérico)
diz onde resolver. O alvo concreto no Unity Catalog vive **só em `tabela_aisn`**, então o
escopo é sempre alcançado através dela:

| `cod_tipo_ativo` | Origem (`id_ativo_aisn` = PK dela) | Escopo UC (via `tabela_aisn`) |
|---|---|---|
| `1` = ICA | `iniciativa_camada_ambiente` | schemas DISTINTOS das tabelas da ICA (`ON SCHEMA`) |
| `2` = TABELA | `tabela_aisn` | 1 tabela (`ON TABLE`) |
| `3` = SUBDOMINIO | `subdominio_camada_ambiente` | N schemas (join camada+ambiente → tabelas) |
| `4` = DOMINIO | `dominio_camada_ambiente` | N schemas (join camada+ambiente → tabelas) |

`app/services/ativo_scope.py` centraliza isto:
- `objetos_do_ativo(ativo)` → objetos UC concretos (SCHEMA/TABLE) resolvidos via `tabela_aisn`;
- `ativo_join(alias)` / `ativo_cols(alias)` → um `LEFT JOIN` polimórfico reutilizado por
  todos os serviços que reconstrói o breadcrumb (`nome_dominio`, `nome_subdominio`) e o
  `tipo_label` **com os mesmos aliases** — por isso os templates não precisaram mudar;
- `dominio_id_expr()` / `subdominio_id_expr()` → expressões para filtrar em `WHERE`.

O **owner** do ativo vem de `{ACC}.ativo_proprietario`; o **grupo do ativo** está embutido em
`{ACC}.ativo_aisn.nome_grupo_ativo` (com FK para `grupo_acesso`).

---

## 6. Concessão por associação a grupo (efetivação)

Aprovado pelo owner, o acesso não é um `GRANT` por usuário — é uma **associação a grupo**:

1. `approval_service.decidir_aprovacao_owner` cria `acesso` (AGUARDANDO) + `execucao_tecnica`
   PENDENTE (em `{APP}`).
2. O **worker** (`app/worker.py`, poll ~15s, advisory lock p/ múltiplos gunicorn) chama
   `access_service.processar_execucoes_pendentes`, que delega a
   `membership_executor.executar`:
   - resolve o **grupo do ativo** (`ativo_aisn.nome_grupo_ativo`);
   - **CONCESSÃO** → inclui no grupo o beneficiário (**nominal**→usuário; **grupo**→grupo do
     usuário, aninhado) via SCIM. Se `PROVISION_GROUP_GRANT` (dev), também garante o `GRANT`
     do grupo nos objetos resolvidos via `tabela_aisn`; em **produção isso é `false`** — o
     Motor já concedeu o grant, o app **só faz membership**;
   - **REVOGAÇÃO** → remove o membro do grupo.
3. Atualiza `acesso.cod_status_acesso` (EFETIVADO/REVOGADO/ERRO), `execucao_tecnica` e grava
   `evento_ciclo_vida`.

**Escopo dos grupos (`config.GROUPS_SCOPE`)** — `db.get_groups_client()` decide o cliente SCIM:
- **`account`** (produção): grupos de **conta** (principais válidos no UC → o `GRANT` do
  grupo propaga). Exige `DATABRICKS_ACCOUNT_ID` e o **SP do app como gerente** desses grupos.
- **`workspace`** (dev sem conta): grupos workspace-local; a associação é real e verificável,
  mas o `GRANT` do grupo **não propaga** no UC (`PRINCIPAL_DOES_NOT_EXIST` — limitação D-009).
  Em dev, o SP precisa poder gerenciar grupos do workspace (ex.: estar em `admins`).

---

## 7. Resumo por serviço

| Serviço | Arquivo | Responsabilidade | Grava em |
|---|---|---|---|
| `catalog_service` | `services/catalog_service.py` | vitrine de ativos + detalhe + escopo | — (só lê) |
| `request_service` | `services/request_service.py` | criar/listar/cancelar solicitação, regras, hierarquia/grupos | `{APP}` marketplace_app |
| `approval_service` | `services/approval_service.py` | filas + decisões (gestor/owner) | `{APP}` marketplace_app |
| `access_service` | `services/access_service.py` | acessos, revogação, **worker de efetivação** | `{APP}` marketplace_app |
| `membership_executor` | `services/membership_executor.py` | **concessão = associação ao grupo** (SCIM); provisiona GRANT só em dev | SCIM (+ UC em dev) |
| `grant_executor` | `services/grant_executor.py` | monta/executa GRANT/REVOKE do grupo nos objetos (dev/provisionamento) | UC |
| `ativo_scope` | `services/ativo_scope.py` | resolução polimórfica ativo → objetos UC (via `tabela_aisn`) + JOIN de detalhes | — |
| `audit_service` | `services/audit_service.py` | trilha de eventos + resumo por domínio | `{APP}` marketplace_app (eventos) |

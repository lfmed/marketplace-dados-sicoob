# Prompt Registry — Marketplace de Dados Sicoob

Registro de rastreabilidade das instruções (prompts), decisões e marcos do projeto.
Mantido a cada interação relevante. Sessão inicial: `f4cddb36` — 2026-09-03.

---

## PR-001 — Prompt inicial (2026-09-03)

**Instrução do usuário (verbatim, resumida):**
> Sicoob precisa de um aplicativo para funcionar como marketplace de dados, onde os
> usuários acessam o app, veem um catálogo de dados organizado por domínio, subdomínio
> e iniciativa e podem solicitar acesso para si mesmo ou para seu grupo; o gestor
> imediato aprova e depois o dono do dado também aprova.
> - App em Databricks Apps com Flask, HTML e Jinja2
> - Base de dados: Lakebase autoscaling
> - Modelo de dados segue: `Modelo - Motores Governança e Acesso.drawio.html`
> - Nomenclatura segue: `Guia - Padrão de nomenclatura.pdf`
> - Requisitos em: `Requisitos - App Acesso.pdf`
> - Exemplo de tela: `Screenshot 2026-09-03 at 15.16.24.png`
> - Fazer o prompt registry, controlar marcos em memória, ser eficiente, garantir
>   qualidade via testes.
> - Entender, tirar dúvidas, montar plano com etapas.
> - Futuro deploy será na workspace do cliente.

**Complemento (mid-turn):**
> O app precisa ser criado na workspace `https://fevm-stable-classic-pg4xe1.cloud.databricks.com/?o=7474646973581105`

**Ações tomadas:**
- Lidos e interpretados os 4 artefatos (requisitos, nomenclatura, modelo .drawio, screenshot).
- Extraído o modelo ER de governança (16 tabelas) → `docs/01-modelo-dados.md`.
- Verificado acesso à workspace-alvo (perfil DEFAULT válido, usuário Leandro Medeiros).
- Criados marcos em memória (ver `MEMORY.md`).
- Levantadas dúvidas de escopo e proposto plano em etapas.

**Decisões-chave registradas:** ver `docs/DECISIONS.md`.

---

## PR-002 — Respostas às dúvidas de escopo (2026-09-03)

Usuário respondeu às 4 perguntas de kickoff:
1. **gestao_acesso** → "Eu projeto o schema gestao_acesso" (com validação antes de implementar) → D-002.
2. **Efetivação** → "executar grants reais no uc, você deve criar exemplos de iniciativas para poder simular" → D-003.
3. **Dados catálogo** → "seed sintético estilo sicoob, mas use isso para criar schemas e tabelas nessa workspace para poder testar de forma real o grant de acessos" → D-003 + D-004.
4. **Nomenclatura** → "snake_case do .drawio" → D-001.

Decisões consolidadas em `docs/DECISIONS.md` (D-001..D-006). Plano em etapas apresentado.

## PR-003 — Início da execução / Etapa 1 (2026-09-03)

Usuário: "pode começar". Complemento: "o catálogo pode ser especificado como um arquivo
de configuração, nesse meu ambiente não posso criar catálogos, só schemas".

Ações: carregado skill Lakebase; descoberta do ambiente (admin, warehouse serverless
RUNNING, SDK 0.99.0/psycopg3); validado SQL UC + fluxo schema/tabela/GRANT/REVOKE;
**Lakebase project `marketplace-dados` criado e conectável**. Decisões D-007, D-008 e
bloco "Infra provisionada" adicionados em `docs/DECISIONS.md`.

## PR-004 — Sync de Delta + verificação Glean (2026-09-03)

Usuário: "o modelo do drawio fica em tabelas Unity Catalog no lakehouse, e são
sincronizadas com o lakebase, as tabelas adicionais ficam no lakebase" e depois "procure
no glean o lakebase autoscaling aceita sync de delta". Glean estava indisponível (token
OAuth expirado) → confirmado via docs oficiais + CLI que Autoscaling suporta synced
tables. Usuário escolheu **synced tables nativas agora** → D-010/D-011.

## PR-005 — Banco sempre pronto p/ cliente (2026-09-03)

Usuário: "deixe sempre preparado o código do banco de dados, pois quando mudar pra
workspace do cliente, ele vai precisar criar lá também." → Entrypoint único
`db/setup.py --mode dev|native` + `db/native_sync_setup.py` + DDLs + `docs/DEPLOY.md`,
tudo parametrizado e idempotente.

## PR-006 — App completo entregue (2026-09-03)

Backend + UI Flask/Jinja2 (tema Sicoob) construídos e validados:
- 8/8 testes passando (`tests/`): 7 regras de negócio + 1 e2e com GRANT/REVOKE reais.
- Smoke UI: 10 rotas 200 OK.
- Verificação visual: `docs/screenshot_catalogo.png` e `screenshot_iniciativa.png` batem
  com a tela de referência.
Falta (opcional, sob confirmação): deploy no Databricks Apps da workspace de dev.

<!-- Novos prompts/instruções relevantes são anexados abaixo com id incremental PR-NNN. -->

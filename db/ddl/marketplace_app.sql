-- =====================================================================
-- Marketplace de Dados — schema de WORKFLOW do app (marketplace_app)
-- GERADO por scripts/gen_app_sql.py a partir de db/ddl/03_app.sql (NÃO editar à mão).
--
-- Rota SEM CLI: cole este arquivo no editor SQL do Lakebase (Postgres) e execute como o
-- role/owner do database. Idempotente (CREATE ... IF NOT EXISTS) — pode rodar de novo.
-- Alternativa recomendada: a própria app cria este schema no boot (AUTO_BOOTSTRAP_APP_SCHEMA=true).
-- Os schemas de leitura governanca/gestao_acesso são synced tables do Motor e NÃO são criados aqui.
-- =====================================================================

-- =====================================================================
-- Schema marketplace_app (marketplace_app) — WORKFLOW do próprio App (projetado por nós, D-002).
-- Nativo/gravável no Lakebase, SEMPRE aplicado (dev e cliente). Ancorado no ATIVO
-- (id_ativo_aisn -> gestao_acesso.ativo_aisn, lógico). Referências a governanca/gestao_acesso são LÓGICAS
-- (sem FK dura: são schemas synced/somente-leitura, D-010). Nome PARAMETRIZÁVEL
-- (marketplace_app via config.SCHEMA_APP).
-- =====================================================================
CREATE SCHEMA IF NOT EXISTS marketplace_app;

-- ---------- Solicitação (RF-011..021) ----------
CREATE TABLE IF NOT EXISTS marketplace_app.solicitacao_acesso (
    id_solicitacao_acesso        VARCHAR(255) PRIMARY KEY,
    id_usuario_solicitante       VARCHAR(255) NOT NULL,   -- -> governanca.usuario_aisn (lógico)
    cod_tipo_beneficiario        VARCHAR(20)  NOT NULL,   -- NOMINAL | GRUPO
    id_usuario_beneficiario      VARCHAR(255),            -- -> governanca.usuario_aisn (lógico)
    id_grupo_acesso              VARCHAR(255),            -- -> gestao_acesso.grupo_acesso (lógico)
    id_ativo_aisn                VARCHAR(255) NOT NULL,   -- -> gestao_acesso.ativo_aisn (lógico)
    cod_tipo_acesso              VARCHAR(30)  NOT NULL DEFAULT 'LEITURA',
    desc_justificativa           VARCHAR(2000),
    cod_status_solicitacao       VARCHAR(40)  NOT NULL DEFAULT 'PENDENTE_AUTORIZACAO',
    id_usuario_autorizador_previsto VARCHAR(255),
    datahora_criacao             TIMESTAMP DEFAULT now(),
    datahora_atualizacao         TIMESTAMP DEFAULT now(),
    CONSTRAINT ck_solicitacao_tipo_benef CHECK (cod_tipo_beneficiario IN ('NOMINAL','GRUPO')),
    CONSTRAINT ck_solicitacao_status CHECK (cod_status_solicitacao IN (
        'PENDENTE_AUTORIZACAO','AUTORIZADA','REPROVADA_GESTOR',
        'APROVADA_OWNER','REPROVADA_OWNER','CANCELADA')),
    CONSTRAINT ck_solicitacao_benef CHECK (
        (cod_tipo_beneficiario = 'NOMINAL' AND id_usuario_beneficiario IS NOT NULL AND id_grupo_acesso IS NULL) OR
        (cod_tipo_beneficiario = 'GRUPO'   AND id_grupo_acesso IS NOT NULL))
);

-- ---------- Autorização hierárquica (gestor) — RF-026..033 ----------
CREATE TABLE IF NOT EXISTS marketplace_app.autorizacao_hierarquica (
    id_autorizacao_hierarquica   VARCHAR(255) PRIMARY KEY,
    id_solicitacao_acesso        VARCHAR(255) NOT NULL REFERENCES marketplace_app.solicitacao_acesso(id_solicitacao_acesso),
    id_usuario_autorizador       VARCHAR(255) NOT NULL,
    cod_resultado                VARCHAR(20)  NOT NULL,
    desc_justificativa           VARCHAR(2000),
    datahora_decisao             TIMESTAMP DEFAULT now(),
    CONSTRAINT ck_autoriz_resultado CHECK (cod_resultado IN ('APROVADA','REPROVADA'))
);

-- ---------- Aprovação do owner do ativo — RF-034..039 ----------
CREATE TABLE IF NOT EXISTS marketplace_app.aprovacao_owner (
    id_aprovacao_owner           VARCHAR(255) PRIMARY KEY,
    id_solicitacao_acesso        VARCHAR(255) NOT NULL REFERENCES marketplace_app.solicitacao_acesso(id_solicitacao_acesso),
    id_usuario_owner             VARCHAR(255) NOT NULL,
    cod_resultado                VARCHAR(20)  NOT NULL,
    desc_justificativa           VARCHAR(2000),
    datahora_decisao             TIMESTAMP DEFAULT now(),
    CONSTRAINT ck_aprov_resultado CHECK (cod_resultado IN ('APROVADA','REPROVADA'))
);

-- ---------- Acesso concedido — RF-051..055 ----------
CREATE TABLE IF NOT EXISTS marketplace_app.acesso (
    id_acesso                    VARCHAR(255) PRIMARY KEY,
    id_solicitacao_acesso        VARCHAR(255) NOT NULL REFERENCES marketplace_app.solicitacao_acesso(id_solicitacao_acesso),
    cod_tipo_beneficiario        VARCHAR(20)  NOT NULL,
    id_usuario_beneficiario      VARCHAR(255),
    id_grupo_acesso              VARCHAR(255),
    id_ativo_aisn                VARCHAR(255) NOT NULL,   -- -> gestao_acesso.ativo_aisn (lógico)
    cod_tipo_acesso              VARCHAR(30)  NOT NULL,
    cod_status_acesso            VARCHAR(40)  NOT NULL DEFAULT 'APROVADO_AGUARDANDO_EFETIVACAO',
    datahora_aprovacao           TIMESTAMP DEFAULT now(),
    datahora_efetivacao          TIMESTAMP,
    datahora_revogacao           TIMESTAMP,
    CONSTRAINT ck_acesso_status CHECK (cod_status_acesso IN (
        'APROVADO_AGUARDANDO_EFETIVACAO','EFETIVADO','ERRO_EFETIVACAO','REVOGADO'))
);

-- ---------- Execução técnica (associação a grupo, idempotente RN-041) — RF-062..080 ----------
CREATE TABLE IF NOT EXISTS marketplace_app.execucao_tecnica (
    id_execucao_tecnica          VARCHAR(255) PRIMARY KEY,
    id_acesso                    VARCHAR(255) NOT NULL REFERENCES marketplace_app.acesso(id_acesso),
    cod_tipo_operacao            VARCHAR(20)  NOT NULL,
    cod_status_execucao          VARCHAR(20)  NOT NULL DEFAULT 'PENDENTE',
    desc_comando                 VARCHAR(4000),
    desc_erro                    VARCHAR(4000),
    num_tentativa                INTEGER DEFAULT 1,
    datahora_inicio              TIMESTAMP DEFAULT now(),
    datahora_fim                 TIMESTAMP,
    CONSTRAINT ck_exec_operacao CHECK (cod_tipo_operacao IN ('CONCESSAO','REVOGACAO')),
    CONSTRAINT ck_exec_status CHECK (cod_status_execucao IN ('PENDENTE','EFETIVADA','ERRO'))
);

-- ---------- Revogação solicitada pelo owner — RF-042/043, RF-072..075 ----------
CREATE TABLE IF NOT EXISTS marketplace_app.revogacao_acesso (
    id_revogacao_acesso          VARCHAR(255) PRIMARY KEY,
    id_acesso                    VARCHAR(255) NOT NULL REFERENCES marketplace_app.acesso(id_acesso),
    id_usuario_solicitante       VARCHAR(255) NOT NULL,
    desc_justificativa           VARCHAR(2000),
    cod_status_revogacao         VARCHAR(30)  NOT NULL DEFAULT 'SOLICITADA',
    datahora_solicitacao         TIMESTAMP DEFAULT now(),
    datahora_conclusao           TIMESTAMP,
    CONSTRAINT ck_revog_status CHECK (cod_status_revogacao IN ('SOLICITADA','EFETIVADA','ERRO'))
);

-- ---------- Auditoria / histórico (RN-027) — RF-056, RF-081..088 ----------
CREATE TABLE IF NOT EXISTS marketplace_app.evento_ciclo_vida (
    id_evento_ciclo_vida         VARCHAR(255) PRIMARY KEY,
    id_solicitacao_acesso        VARCHAR(255) REFERENCES marketplace_app.solicitacao_acesso(id_solicitacao_acesso),
    id_acesso                    VARCHAR(255) REFERENCES marketplace_app.acesso(id_acesso),
    cod_evento                   VARCHAR(60)  NOT NULL,
    desc_detalhe                 VARCHAR(2000),
    id_usuario_evento            VARCHAR(255),
    datahora_evento              TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_solicitacao_ativo ON marketplace_app.solicitacao_acesso(id_ativo_aisn);
CREATE INDEX IF NOT EXISTS idx_solicitacao_solicitante ON marketplace_app.solicitacao_acesso(id_usuario_solicitante);
CREATE INDEX IF NOT EXISTS idx_solicitacao_status ON marketplace_app.solicitacao_acesso(cod_status_solicitacao);
CREATE INDEX IF NOT EXISTS idx_solicitacao_autorizador ON marketplace_app.solicitacao_acesso(id_usuario_autorizador_previsto);
CREATE INDEX IF NOT EXISTS idx_acesso_ativo ON marketplace_app.acesso(id_ativo_aisn);
CREATE INDEX IF NOT EXISTS idx_acesso_beneficiario ON marketplace_app.acesso(id_usuario_beneficiario);
CREATE INDEX IF NOT EXISTS idx_acesso_grupo ON marketplace_app.acesso(id_grupo_acesso);
CREATE INDEX IF NOT EXISTS idx_acesso_status ON marketplace_app.acesso(cod_status_acesso);
CREATE INDEX IF NOT EXISTS idx_execucao_acesso ON marketplace_app.execucao_tecnica(id_acesso);
CREATE INDEX IF NOT EXISTS idx_evento_solicitacao ON marketplace_app.evento_ciclo_vida(id_solicitacao_acesso);
CREATE INDEX IF NOT EXISTS idx_evento_acesso ON marketplace_app.evento_ciclo_vida(id_acesso);

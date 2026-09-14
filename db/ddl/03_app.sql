-- =====================================================================
-- Schema {APP} (marketplace_app) — WORKFLOW do próprio App (projetado por nós, D-002).
-- Nativo/gravável no Lakebase, SEMPRE aplicado (dev e cliente). Ancorado no ATIVO
-- (id_ativo_aisn -> {ACC}.ativo_aisn, lógico). Referências a {GOV}/{ACC} são LÓGICAS
-- (sem FK dura: são schemas synced/somente-leitura, D-010). Nome PARAMETRIZÁVEL
-- ({APP} via config.SCHEMA_APP).
-- =====================================================================
CREATE SCHEMA IF NOT EXISTS {APP};

-- ---------- Solicitação (RF-011..021) ----------
CREATE TABLE IF NOT EXISTS {APP}.solicitacao_acesso (
    id_solicitacao_acesso        VARCHAR(255) PRIMARY KEY,
    id_usuario_solicitante       VARCHAR(255) NOT NULL,   -- -> {GOV}.usuario_aisn (lógico)
    cod_tipo_beneficiario        VARCHAR(20)  NOT NULL,   -- NOMINAL | GRUPO
    id_usuario_beneficiario      VARCHAR(255),            -- -> {GOV}.usuario_aisn (lógico)
    id_grupo_acesso              VARCHAR(255),            -- -> {ACC}.grupo_acesso (lógico)
    id_ativo_aisn                VARCHAR(255) NOT NULL,   -- -> {ACC}.ativo_aisn (lógico)
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
        (cod_tipo_beneficiario = 'GRUPO'   AND id_grupo_acesso IS NOT NULL AND id_usuario_beneficiario IS NULL))
);

-- ---------- Autorização hierárquica (gestor) — RF-026..033 ----------
CREATE TABLE IF NOT EXISTS {APP}.autorizacao_hierarquica (
    id_autorizacao_hierarquica   VARCHAR(255) PRIMARY KEY,
    id_solicitacao_acesso        VARCHAR(255) NOT NULL REFERENCES {APP}.solicitacao_acesso(id_solicitacao_acesso),
    id_usuario_autorizador       VARCHAR(255) NOT NULL,
    cod_resultado                VARCHAR(20)  NOT NULL,
    desc_justificativa           VARCHAR(2000),
    datahora_decisao             TIMESTAMP DEFAULT now(),
    CONSTRAINT ck_autoriz_resultado CHECK (cod_resultado IN ('APROVADA','REPROVADA'))
);

-- ---------- Aprovação do owner do ativo — RF-034..039 ----------
CREATE TABLE IF NOT EXISTS {APP}.aprovacao_owner (
    id_aprovacao_owner           VARCHAR(255) PRIMARY KEY,
    id_solicitacao_acesso        VARCHAR(255) NOT NULL REFERENCES {APP}.solicitacao_acesso(id_solicitacao_acesso),
    id_usuario_owner             VARCHAR(255) NOT NULL,
    cod_resultado                VARCHAR(20)  NOT NULL,
    desc_justificativa           VARCHAR(2000),
    datahora_decisao             TIMESTAMP DEFAULT now(),
    CONSTRAINT ck_aprov_resultado CHECK (cod_resultado IN ('APROVADA','REPROVADA'))
);

-- ---------- Acesso concedido — RF-051..055 ----------
CREATE TABLE IF NOT EXISTS {APP}.acesso (
    id_acesso                    VARCHAR(255) PRIMARY KEY,
    id_solicitacao_acesso        VARCHAR(255) NOT NULL REFERENCES {APP}.solicitacao_acesso(id_solicitacao_acesso),
    cod_tipo_beneficiario        VARCHAR(20)  NOT NULL,
    id_usuario_beneficiario      VARCHAR(255),
    id_grupo_acesso              VARCHAR(255),
    id_ativo_aisn                VARCHAR(255) NOT NULL,   -- -> {ACC}.ativo_aisn (lógico)
    cod_tipo_acesso              VARCHAR(30)  NOT NULL,
    cod_status_acesso            VARCHAR(40)  NOT NULL DEFAULT 'APROVADO_AGUARDANDO_EFETIVACAO',
    datahora_aprovacao           TIMESTAMP DEFAULT now(),
    datahora_efetivacao          TIMESTAMP,
    datahora_revogacao           TIMESTAMP,
    CONSTRAINT ck_acesso_status CHECK (cod_status_acesso IN (
        'APROVADO_AGUARDANDO_EFETIVACAO','EFETIVADO','ERRO_EFETIVACAO','REVOGADO','CANCELADO'))
);

-- ---------- Execução técnica (associação a grupo, idempotente RN-041) — RF-062..080 ----------
CREATE TABLE IF NOT EXISTS {APP}.execucao_tecnica (
    id_execucao_tecnica          VARCHAR(255) PRIMARY KEY,
    id_acesso                    VARCHAR(255) NOT NULL REFERENCES {APP}.acesso(id_acesso),
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
CREATE TABLE IF NOT EXISTS {APP}.revogacao_acesso (
    id_revogacao_acesso          VARCHAR(255) PRIMARY KEY,
    id_acesso                    VARCHAR(255) NOT NULL REFERENCES {APP}.acesso(id_acesso),
    id_usuario_solicitante       VARCHAR(255) NOT NULL,
    desc_justificativa           VARCHAR(2000),
    cod_status_revogacao         VARCHAR(30)  NOT NULL DEFAULT 'SOLICITADA',
    datahora_solicitacao         TIMESTAMP DEFAULT now(),
    datahora_conclusao           TIMESTAMP,
    CONSTRAINT ck_revog_status CHECK (cod_status_revogacao IN ('SOLICITADA','EFETIVADA','ERRO'))
);

-- ---------- Auditoria / histórico (RN-027) — RF-056, RF-081..088 ----------
CREATE TABLE IF NOT EXISTS {APP}.evento_ciclo_vida (
    id_evento_ciclo_vida         VARCHAR(255) PRIMARY KEY,
    id_solicitacao_acesso        VARCHAR(255) REFERENCES {APP}.solicitacao_acesso(id_solicitacao_acesso),
    id_acesso                    VARCHAR(255) REFERENCES {APP}.acesso(id_acesso),
    cod_evento                   VARCHAR(60)  NOT NULL,
    desc_detalhe                 VARCHAR(2000),
    id_usuario_evento            VARCHAR(255),
    datahora_evento              TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_solicitacao_ativo ON {APP}.solicitacao_acesso(id_ativo_aisn);
CREATE INDEX IF NOT EXISTS idx_solicitacao_solicitante ON {APP}.solicitacao_acesso(id_usuario_solicitante);
CREATE INDEX IF NOT EXISTS idx_solicitacao_status ON {APP}.solicitacao_acesso(cod_status_solicitacao);
CREATE INDEX IF NOT EXISTS idx_solicitacao_autorizador ON {APP}.solicitacao_acesso(id_usuario_autorizador_previsto);
CREATE INDEX IF NOT EXISTS idx_acesso_ativo ON {APP}.acesso(id_ativo_aisn);
CREATE INDEX IF NOT EXISTS idx_acesso_beneficiario ON {APP}.acesso(id_usuario_beneficiario);
CREATE INDEX IF NOT EXISTS idx_acesso_grupo ON {APP}.acesso(id_grupo_acesso);
CREATE INDEX IF NOT EXISTS idx_acesso_status ON {APP}.acesso(cod_status_acesso);
CREATE INDEX IF NOT EXISTS idx_execucao_acesso ON {APP}.execucao_tecnica(id_acesso);
CREATE INDEX IF NOT EXISTS idx_evento_solicitacao ON {APP}.evento_ciclo_vida(id_solicitacao_acesso);
CREATE INDEX IF NOT EXISTS idx_evento_acesso ON {APP}.evento_ciclo_vida(id_acesso);

-- Migrações idempotentes (aplicadas no boot; CREATE TABLE IF NOT EXISTS não altera tabela já existente).
-- Adiciona o estado CANCELADO ao acesso (solicitante cancela após erro de efetivação).
ALTER TABLE {APP}.acesso DROP CONSTRAINT IF EXISTS ck_acesso_status;
ALTER TABLE {APP}.acesso ADD CONSTRAINT ck_acesso_status CHECK (cod_status_acesso IN (
    'APROVADO_AGUARDANDO_EFETIVACAO','EFETIVADO','ERRO_EFETIVACAO','REVOGADO','CANCELADO'));

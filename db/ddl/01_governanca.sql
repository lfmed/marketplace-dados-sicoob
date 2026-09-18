-- =====================================================================
-- Schema {GOV} (governanca) — Motor de Gestão de Governança (modelo oficial do cliente).
-- Taxonomia + combinações camada/ambiente por nível + tabelas + usuários + proprietários.
-- No cliente é Delta em plataforma.governanca, sincronizado p/ o Lakebase (somente leitura).
-- Em dev é mirror controlado. Nomes de schema PARAMETRIZÁVEIS ({GOV} via config.SCHEMA_GOVERNANCA).
-- =====================================================================
CREATE SCHEMA IF NOT EXISTS {GOV};

-- ---------- Taxonomia ----------
CREATE TABLE IF NOT EXISTS {GOV}.dominio_informacao (
    id_dominio_informacao      VARCHAR(255) PRIMARY KEY,
    nome_dominio               VARCHAR(255) NOT NULL,
    tag_dominio                VARCHAR(255),            -- padrão de tag p/ objetos do domínio
    sigla_dominio              VARCHAR(255),            -- sigla usada nos padrões de grupo
    desc_dominio               VARCHAR(1000),
    datahora_inicio_validade   TIMESTAMP DEFAULT now(),
    datahora_fim_validade      TIMESTAMP,
    bol_atual                  BOOLEAN DEFAULT true,
    bol_excluido               BOOLEAN DEFAULT false
);

CREATE TABLE IF NOT EXISTS {GOV}.subdominio_informacao (
    id_subdominio_informacao   VARCHAR(255) PRIMARY KEY,
    id_dominio_informacao      VARCHAR(255) NOT NULL REFERENCES {GOV}.dominio_informacao(id_dominio_informacao),
    nome_subdominio            VARCHAR(255) NOT NULL,
    tag_subdominio             VARCHAR(255),
    sigla_subdominio           VARCHAR(255),
    desc_subdominio            VARCHAR(1000),
    datahora_inicio_validade   TIMESTAMP DEFAULT now(),
    datahora_fim_validade      TIMESTAMP,
    bol_atual                  BOOLEAN DEFAULT true,
    bol_excluido               BOOLEAN DEFAULT false
);

CREATE TABLE IF NOT EXISTS {GOV}.iniciativa_aisn (
    id_iniciativa_aisn         VARCHAR(255) PRIMARY KEY,
    id_subdominio_informacao   VARCHAR(255) NOT NULL REFERENCES {GOV}.subdominio_informacao(id_subdominio_informacao),
    sigla_iniciativa           VARCHAR(255),            -- sigla (valor antigo de nome_iniciativa)
    nome_iniciativa            VARCHAR(255) NOT NULL,
    desc_iniciativa            VARCHAR(1000),
    cod_status_iniciativa      VARCHAR(50),
    datahora_inicio_validade   TIMESTAMP DEFAULT now(),
    datahora_fim_validade      TIMESTAMP,
    bol_atual                  BOOLEAN DEFAULT true,
    bol_excluido               BOOLEAN DEFAULT false
);
-- Migração idempotente (mirror dev): CREATE TABLE IF NOT EXISTS não altera tabela já
-- existente. Adiciona sigla_iniciativa se a tabela foi criada antes da coluna existir.
ALTER TABLE {GOV}.iniciativa_aisn ADD COLUMN IF NOT EXISTS sigla_iniciativa VARCHAR(255);

CREATE TABLE IF NOT EXISTS {GOV}.camada_aisn (
    id_camada_aisn             VARCHAR(255) PRIMARY KEY,
    nome_camada                VARCHAR(255) NOT NULL,   -- Bronze / Silver / Gold
    desc_camada                VARCHAR(1000),
    datahora_inicio_validade   TIMESTAMP DEFAULT now(),
    datahora_fim_validade      TIMESTAMP,
    bol_atual                  BOOLEAN DEFAULT true,
    bol_excluido               BOOLEAN DEFAULT false
);

CREATE TABLE IF NOT EXISTS {GOV}.ambiente_aisn (
    id_ambiente_aisn           VARCHAR(255) PRIMARY KEY,
    nome_ambiente              VARCHAR(255) NOT NULL,   -- Produção / etc.
    desc_ambiente              VARCHAR(1000),
    datahora_inicio_validade   TIMESTAMP DEFAULT now(),
    datahora_fim_validade      TIMESTAMP,
    bol_atual                  BOOLEAN DEFAULT true,
    bol_excluido               BOOLEAN DEFAULT false
);

-- Combinação iniciativa+camada+ambiente (unidade funcional; NÃO carrega catálogo/schema —
-- o alvo UC vive só em tabela_aisn). Nome/desc próprios (oficial do cliente).
CREATE TABLE IF NOT EXISTS {GOV}.iniciativa_camada_ambiente (
    id_iniciativa_camada_ambiente VARCHAR(255) PRIMARY KEY,
    id_iniciativa_aisn         VARCHAR(255) NOT NULL REFERENCES {GOV}.iniciativa_aisn(id_iniciativa_aisn),
    id_camada_aisn             VARCHAR(255) NOT NULL REFERENCES {GOV}.camada_aisn(id_camada_aisn),
    id_ambiente_aisn           VARCHAR(255) NOT NULL REFERENCES {GOV}.ambiente_aisn(id_ambiente_aisn),
    nome_iniciativa_camada_ambiente VARCHAR(255),
    desc_iniciativa_camada_ambiente VARCHAR(1000),
    bol_elegivel_acesso        BOOLEAN DEFAULT true,
    datahora_inicio_validade   TIMESTAMP DEFAULT now(),
    datahora_fim_validade      TIMESTAMP,
    bol_atual                  BOOLEAN DEFAULT true,
    bol_excluido               BOOLEAN DEFAULT false,
    UNIQUE (id_iniciativa_aisn, id_camada_aisn, id_ambiente_aisn)
);

CREATE TABLE IF NOT EXISTS {GOV}.subdominio_camada_ambiente (
    id_subdominio_camada_ambiente VARCHAR(255) PRIMARY KEY,
    id_subdominio_informacao   VARCHAR(255) NOT NULL REFERENCES {GOV}.subdominio_informacao(id_subdominio_informacao),
    id_camada_aisn             VARCHAR(255) NOT NULL REFERENCES {GOV}.camada_aisn(id_camada_aisn),
    id_ambiente_aisn           VARCHAR(255) NOT NULL REFERENCES {GOV}.ambiente_aisn(id_ambiente_aisn),
    nome_subdominio_camada_ambiente VARCHAR(255),
    desc_subdominio_camada_ambiente VARCHAR(1000),
    bol_elegivel_acesso        BOOLEAN DEFAULT true,
    datahora_inicio_validade   TIMESTAMP DEFAULT now(),
    datahora_fim_validade      TIMESTAMP,
    bol_atual                  BOOLEAN DEFAULT true,
    bol_excluido               BOOLEAN DEFAULT false,
    UNIQUE (id_subdominio_informacao, id_camada_aisn, id_ambiente_aisn)
);

CREATE TABLE IF NOT EXISTS {GOV}.dominio_camada_ambiente (
    id_dominio_camada_ambiente VARCHAR(255) PRIMARY KEY,
    id_dominio_informacao      VARCHAR(255) NOT NULL REFERENCES {GOV}.dominio_informacao(id_dominio_informacao),
    id_camada_aisn             VARCHAR(255) NOT NULL REFERENCES {GOV}.camada_aisn(id_camada_aisn),
    id_ambiente_aisn           VARCHAR(255) NOT NULL REFERENCES {GOV}.ambiente_aisn(id_ambiente_aisn),
    nome_dominio_camada_ambiente VARCHAR(255),
    desc_dominio_camada_ambiente VARCHAR(1000),
    bol_elegivel_acesso        BOOLEAN DEFAULT true,
    datahora_inicio_validade   TIMESTAMP DEFAULT now(),
    datahora_fim_validade      TIMESTAMP,
    bol_atual                  BOOLEAN DEFAULT true,
    bol_excluido               BOOLEAN DEFAULT false,
    UNIQUE (id_dominio_informacao, id_camada_aisn, id_ambiente_aisn)
);

-- Única tabela com o alvo concreto no Unity Catalog (catálogo.schema.tabela).
CREATE TABLE IF NOT EXISTS {GOV}.tabela_aisn (
    id_tabela_aisn             VARCHAR(255) PRIMARY KEY,
    id_iniciativa_camada_ambiente VARCHAR(255) NOT NULL REFERENCES {GOV}.iniciativa_camada_ambiente(id_iniciativa_camada_ambiente),
    nome_catalogo              VARCHAR(255) NOT NULL,
    nome_schema                VARCHAR(255) NOT NULL,
    nome_tabela                VARCHAR(255) NOT NULL,
    desc_tabela                VARCHAR(1000),
    cod_status_tabela          VARCHAR(50),
    bol_elegivel_acesso        BOOLEAN DEFAULT true,
    datahora_inicio_validade   TIMESTAMP DEFAULT now(),
    datahora_fim_validade      TIMESTAMP,
    bol_atual                  BOOLEAN DEFAULT true,
    bol_excluido               BOOLEAN DEFAULT false
);

CREATE TABLE IF NOT EXISTS {GOV}.usuario_aisn (
    id_usuario_aisn            VARCHAR(255) PRIMARY KEY,
    nome_usuario               VARCHAR(255),
    nome_completo              VARCHAR(255),
    desc_nome                  VARCHAR(1000),
    desc_email                 VARCHAR(500),   -- principal UC alvo do GRANT nominal
    desc_sobrenome             VARCHAR(255),
    cod_conta_databricks       VARCHAR(255),
    datahora_inicio_validade   TIMESTAMP DEFAULT now(),
    datahora_fim_validade      TIMESTAMP,
    bol_ativo                  BOOLEAN DEFAULT true,
    bol_atual                  BOOLEAN DEFAULT true,
    bol_excluido               BOOLEAN DEFAULT false
);

-- ---------- Proprietários (domínio / subdomínio / iniciativa) ----------
CREATE TABLE IF NOT EXISTS {GOV}.dominio_proprietario (
    id_dominio_informacao      VARCHAR(255) NOT NULL REFERENCES {GOV}.dominio_informacao(id_dominio_informacao),
    id_usuario_aisn            VARCHAR(255) NOT NULL REFERENCES {GOV}.usuario_aisn(id_usuario_aisn),
    cod_tipo_proprietario      VARCHAR(50),
    bol_principal              BOOLEAN DEFAULT false,
    datahora_inicio_validade   TIMESTAMP DEFAULT now(),
    datahora_fim_validade      TIMESTAMP,
    bol_atual                  BOOLEAN DEFAULT true,
    bol_excluido               BOOLEAN DEFAULT false,
    PRIMARY KEY (id_dominio_informacao, id_usuario_aisn)
);

CREATE TABLE IF NOT EXISTS {GOV}.subdominio_proprietario (
    id_subdominio_informacao   VARCHAR(255) NOT NULL REFERENCES {GOV}.subdominio_informacao(id_subdominio_informacao),
    id_usuario_aisn            VARCHAR(255) NOT NULL REFERENCES {GOV}.usuario_aisn(id_usuario_aisn),
    cod_tipo_proprietario      VARCHAR(50),
    bol_principal              BOOLEAN DEFAULT false,
    datahora_inicio_validade   TIMESTAMP DEFAULT now(),
    datahora_fim_validade      TIMESTAMP,
    bol_atual                  BOOLEAN DEFAULT true,
    bol_excluido               BOOLEAN DEFAULT false,
    PRIMARY KEY (id_subdominio_informacao, id_usuario_aisn)
);

CREATE TABLE IF NOT EXISTS {GOV}.iniciativa_proprietario (
    id_iniciativa_aisn         VARCHAR(255) NOT NULL REFERENCES {GOV}.iniciativa_aisn(id_iniciativa_aisn),
    id_usuario_aisn            VARCHAR(255) NOT NULL REFERENCES {GOV}.usuario_aisn(id_usuario_aisn),
    cod_tipo_proprietario      VARCHAR(50),
    bol_principal              BOOLEAN DEFAULT false,
    datahora_inicio_validade   TIMESTAMP DEFAULT now(),
    datahora_fim_validade      TIMESTAMP,
    bol_atual                  BOOLEAN DEFAULT true,
    bol_excluido               BOOLEAN DEFAULT false,
    PRIMARY KEY (id_iniciativa_aisn, id_usuario_aisn)
);

CREATE INDEX IF NOT EXISTS idx_subdominio_dominio ON {GOV}.subdominio_informacao(id_dominio_informacao);
CREATE INDEX IF NOT EXISTS idx_iniciativa_subdominio ON {GOV}.iniciativa_aisn(id_subdominio_informacao);
CREATE INDEX IF NOT EXISTS idx_ica_iniciativa ON {GOV}.iniciativa_camada_ambiente(id_iniciativa_aisn);
CREATE INDEX IF NOT EXISTS idx_sca_subdominio ON {GOV}.subdominio_camada_ambiente(id_subdominio_informacao);
CREATE INDEX IF NOT EXISTS idx_dca_dominio ON {GOV}.dominio_camada_ambiente(id_dominio_informacao);
CREATE INDEX IF NOT EXISTS idx_tabela_ica ON {GOV}.tabela_aisn(id_iniciativa_camada_ambiente);
CREATE INDEX IF NOT EXISTS idx_iniciativa_owner_ini ON {GOV}.iniciativa_proprietario(id_iniciativa_aisn);

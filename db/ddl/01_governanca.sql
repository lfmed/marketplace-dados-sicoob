-- =====================================================================
-- Schema: governanca  (catálogo — modelo do .drawio "Motores Governança e Acesso")
-- Nomenclatura snake_case + prefixos (D-001). SCD2 em todas as entidades.
-- No protótipo é populado por seed sintético (Motor de Governança ainda não existe).
-- =====================================================================
CREATE SCHEMA IF NOT EXISTS governanca;
SET search_path TO governanca;

-- ---------- Taxonomia ----------
CREATE TABLE IF NOT EXISTS dominio_informacao (
    id_dominio_informacao      VARCHAR(255) PRIMARY KEY,
    nome_dominio               VARCHAR(255) NOT NULL,
    desc_dominio               VARCHAR(1000),
    datahora_inicio_validade   TIMESTAMP DEFAULT now(),
    datahora_fim_validade      TIMESTAMP,
    bol_atual                  BOOLEAN DEFAULT true,
    bol_excluido               BOOLEAN DEFAULT false
);

CREATE TABLE IF NOT EXISTS subdominio_informacao (
    id_subdominio_informacao   VARCHAR(255) PRIMARY KEY,
    id_dominio_informacao      VARCHAR(255) NOT NULL REFERENCES dominio_informacao(id_dominio_informacao),
    nome_subdominio            VARCHAR(255) NOT NULL,
    desc_subdominio            VARCHAR(1000),
    datahora_inicio_validade   TIMESTAMP DEFAULT now(),
    datahora_fim_validade      TIMESTAMP,
    bol_atual                  BOOLEAN DEFAULT true,
    bol_excluido               BOOLEAN DEFAULT false
);

CREATE TABLE IF NOT EXISTS iniciativa_aisn (
    id_iniciativa_aisn         VARCHAR(255) PRIMARY KEY,
    id_subdominio_informacao   VARCHAR(255) NOT NULL REFERENCES subdominio_informacao(id_subdominio_informacao),
    nome_iniciativa            VARCHAR(255) NOT NULL,
    desc_iniciativa            VARCHAR(1000),
    cod_status_iniciativa      VARCHAR(50),
    datahora_inicio_validade   TIMESTAMP DEFAULT now(),
    datahora_fim_validade      TIMESTAMP,
    bol_atual                  BOOLEAN DEFAULT true,
    bol_excluido               BOOLEAN DEFAULT false
);

CREATE TABLE IF NOT EXISTS camada_aisn (
    id_camada_aisn             VARCHAR(255) PRIMARY KEY,
    nome_camada                VARCHAR(255) NOT NULL,   -- Bronze / Silver / Gold
    desc_camada                VARCHAR(1000),
    datahora_inicio_validade   TIMESTAMP DEFAULT now(),
    datahora_fim_validade      TIMESTAMP,
    bol_atual                  BOOLEAN DEFAULT true,
    bol_excluido               BOOLEAN DEFAULT false
);

CREATE TABLE IF NOT EXISTS ambiente_aisn (
    id_ambiente_aisn           VARCHAR(255) PRIMARY KEY,
    nome_ambiente              VARCHAR(255) NOT NULL,   -- Produção / etc.
    desc_ambiente              VARCHAR(1000),
    datahora_inicio_validade   TIMESTAMP DEFAULT now(),
    datahora_fim_validade      TIMESTAMP,
    bol_atual                  BOOLEAN DEFAULT true,
    bol_excluido               BOOLEAN DEFAULT false
);

-- Unidade funcional de gestão de acesso (RN-001) -> mapeia para 1 schema UC (D-008)
CREATE TABLE IF NOT EXISTS iniciativa_camada_ambiente (
    id_iniciativa_camada_ambiente VARCHAR(255) PRIMARY KEY,
    id_iniciativa_aisn         VARCHAR(255) NOT NULL REFERENCES iniciativa_aisn(id_iniciativa_aisn),
    id_camada_aisn             VARCHAR(255) NOT NULL REFERENCES camada_aisn(id_camada_aisn),
    id_ambiente_aisn           VARCHAR(255) NOT NULL REFERENCES ambiente_aisn(id_ambiente_aisn),
    nome_catalogo              VARCHAR(255),            -- catálogo UC (parâmetro de config)
    nome_schema                VARCHAR(255),            -- schema UC alvo dos GRANTs
    bol_elegivel_acesso        BOOLEAN DEFAULT true,
    datahora_inicio_validade   TIMESTAMP DEFAULT now(),
    datahora_fim_validade      TIMESTAMP,
    bol_atual                  BOOLEAN DEFAULT true,
    bol_excluido               BOOLEAN DEFAULT false,
    UNIQUE (id_iniciativa_aisn, id_camada_aisn, id_ambiente_aisn)
);

CREATE TABLE IF NOT EXISTS tabela_aisn (
    id_tabela_aisn             VARCHAR(255) PRIMARY KEY,
    id_iniciativa_camada_ambiente VARCHAR(255) NOT NULL REFERENCES iniciativa_camada_ambiente(id_iniciativa_camada_ambiente),
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

-- ---------- Usuários / hierarquia / grupos ----------
CREATE TABLE IF NOT EXISTS usuario_aisn (
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

CREATE TABLE IF NOT EXISTS hierarquia_usuario (
    id_usuario_aisn            VARCHAR(255) NOT NULL REFERENCES usuario_aisn(id_usuario_aisn),
    id_gestor_aisn             VARCHAR(255) NOT NULL REFERENCES usuario_aisn(id_usuario_aisn),
    datahora_inicio_validade   TIMESTAMP DEFAULT now(),
    datahora_fim_validade      TIMESTAMP,
    bol_atual                  BOOLEAN DEFAULT true,
    bol_excluido               BOOLEAN DEFAULT false,
    PRIMARY KEY (id_usuario_aisn, id_gestor_aisn)
);

CREATE TABLE IF NOT EXISTS grupo_acesso (
    id_grupo_acesso            VARCHAR(255) PRIMARY KEY,
    id_externo_grupo           VARCHAR(255),
    cod_conta_databricks       VARCHAR(255),
    nome_grupo                 VARCHAR(255) NOT NULL,   -- nome do grupo UC alvo do GRANT de grupo
    tipo_grupo                 VARCHAR(255) NOT NULL,   -- ex.: EXPLORATORIO
    datahora_inicio_validade   TIMESTAMP DEFAULT now(),
    datahora_fim_validade      TIMESTAMP,
    bol_atual                  BOOLEAN DEFAULT true,
    bol_excluido               BOOLEAN DEFAULT false
);

CREATE TABLE IF NOT EXISTS grupo_acesso_membro (
    id_grupo_acesso            VARCHAR(255) NOT NULL REFERENCES grupo_acesso(id_grupo_acesso),
    id_entidade                VARCHAR(255) NOT NULL,   -- id do usuário membro
    tipo_entidade              VARCHAR(100),            -- USUARIO / GRUPO
    nome_entidade              VARCHAR(255),
    cod_conta_databricks       VARCHAR(255),
    datahora_inicio_validade   TIMESTAMP DEFAULT now(),
    datahora_fim_validade      TIMESTAMP,
    bol_atual                  BOOLEAN DEFAULT true,
    bol_excluido               BOOLEAN DEFAULT false,
    PRIMARY KEY (id_grupo_acesso, id_entidade)
);

-- Ativo = unidade liberável do marketplace (RN-001), registro de PUBLICAÇÃO sobre uma
-- entidade de governança. Relação POLIMÓRFICA: id_ativo_aisn É a PK da entidade de origem
-- e cod_tipo_ativo (código numérico) diz em qual tabela resolver:
--   '1'=ICA (iniciativa_camada_ambiente) | '2'=TABELA (tabela_aisn)
--   '3'=SUBDOMINIO (subdominio_informacao) | '4'=DOMINIO (dominio_informacao)
-- Catálogo/schema/tabela/domínio/subdomínio são ALCANÇADOS navegando as relações do
-- modelo — nunca copiados aqui (por isso não há FK física única). O grupo do ativo
-- (id_grupo_acesso) detém o privilégio no UC e é nele que o solicitante é incluído.
-- Owner em ativo_proprietario. Em produção isto vem do Motor de Governança.
CREATE TABLE IF NOT EXISTS ativo_aisn (
    id_ativo_aisn              VARCHAR(255) PRIMARY KEY,  -- = PK da entidade de origem
    id_grupo_acesso            VARCHAR(255) REFERENCES grupo_acesso(id_grupo_acesso),
    cod_tipo_ativo             VARCHAR(50),          -- 1=ICA | 2=TABELA | 3=SUBDOMINIO | 4=DOMINIO
    nome_ativo                 VARCHAR(255) NOT NULL,
    desc_ativo                 VARCHAR(1000),
    bol_elegivel_acesso        BOOLEAN DEFAULT true,
    datahora_inicio_validade   TIMESTAMP DEFAULT now(),
    datahora_fim_validade      TIMESTAMP,
    bol_atual                  BOOLEAN DEFAULT true,
    bol_excluido               BOOLEAN DEFAULT false
);
-- Migração (dev): remove colunas denormalizadas de versões anteriores. O breadcrumb e o
-- alvo UC passam a ser navegados nas relações (ativo_scope), nunca copiados aqui.
ALTER TABLE ativo_aisn DROP COLUMN IF EXISTS id_referencia;
ALTER TABLE ativo_aisn DROP COLUMN IF EXISTS nome_dominio;
ALTER TABLE ativo_aisn DROP COLUMN IF EXISTS nome_subdominio;
ALTER TABLE ativo_aisn DROP COLUMN IF EXISTS nome_catalogo;
ALTER TABLE ativo_aisn DROP COLUMN IF EXISTS nome_schema;
ALTER TABLE ativo_aisn DROP COLUMN IF EXISTS nome_tabela;

-- ---------- Owners (proprietários) ----------
CREATE TABLE IF NOT EXISTS dominio_proprietario (
    id_usuario_aisn            VARCHAR(255) NOT NULL REFERENCES usuario_aisn(id_usuario_aisn),
    id_dominio_informacao      VARCHAR(255) NOT NULL REFERENCES dominio_informacao(id_dominio_informacao),
    cod_tipo_proprietario      VARCHAR(50),
    bol_principal              BOOLEAN DEFAULT false,
    datahora_inicio_validade   TIMESTAMP DEFAULT now(),
    datahora_fim_validade      TIMESTAMP,
    bol_atual                  BOOLEAN DEFAULT true,
    bol_excluido               BOOLEAN DEFAULT false,
    PRIMARY KEY (id_usuario_aisn, id_dominio_informacao)
);

CREATE TABLE IF NOT EXISTS subdominio_proprietario (
    id_usuario_aisn            VARCHAR(255) NOT NULL REFERENCES usuario_aisn(id_usuario_aisn),
    id_subdominio_informacao   VARCHAR(255) NOT NULL REFERENCES subdominio_informacao(id_subdominio_informacao),
    cod_tipo_proprietario      VARCHAR(50),
    bol_principal              BOOLEAN DEFAULT false,
    datahora_inicio_validade   TIMESTAMP DEFAULT now(),
    datahora_fim_validade      TIMESTAMP,
    bol_atual                  BOOLEAN DEFAULT true,
    bol_excluido               BOOLEAN DEFAULT false,
    PRIMARY KEY (id_usuario_aisn, id_subdominio_informacao)
);

-- Owner que aprova a solicitação (RN-006)
CREATE TABLE IF NOT EXISTS iniciativa_proprietario (
    id_usuario_aisn            VARCHAR(255) NOT NULL REFERENCES usuario_aisn(id_usuario_aisn),
    id_iniciativa_aisn         VARCHAR(255) NOT NULL REFERENCES iniciativa_aisn(id_iniciativa_aisn),
    cod_tipo_proprietario      VARCHAR(50),
    bol_principal              BOOLEAN DEFAULT false,
    datahora_inicio_validade   TIMESTAMP DEFAULT now(),
    datahora_fim_validade      TIMESTAMP,
    bol_atual                  BOOLEAN DEFAULT true,
    bol_excluido               BOOLEAN DEFAULT false,
    PRIMARY KEY (id_usuario_aisn, id_iniciativa_aisn)
);

CREATE TABLE IF NOT EXISTS ativo_proprietario (
    id_usuario_aisn            VARCHAR(255) NOT NULL REFERENCES usuario_aisn(id_usuario_aisn),
    id_ativo_aisn              VARCHAR(255) NOT NULL REFERENCES ativo_aisn(id_ativo_aisn),
    cod_tipo_proprietario      VARCHAR(50),
    bol_principal              BOOLEAN DEFAULT false,
    datahora_inicio_validade   TIMESTAMP DEFAULT now(),
    datahora_fim_validade      TIMESTAMP,
    bol_atual                  BOOLEAN DEFAULT true,
    bol_excluido               BOOLEAN DEFAULT false,
    PRIMARY KEY (id_usuario_aisn, id_ativo_aisn)
);

-- Índices de apoio às consultas do catálogo
CREATE INDEX IF NOT EXISTS idx_subdominio_dominio ON subdominio_informacao(id_dominio_informacao);
CREATE INDEX IF NOT EXISTS idx_iniciativa_subdominio ON iniciativa_aisn(id_subdominio_informacao);
CREATE INDEX IF NOT EXISTS idx_ica_iniciativa ON iniciativa_camada_ambiente(id_iniciativa_aisn);
CREATE INDEX IF NOT EXISTS idx_tabela_ica ON tabela_aisn(id_iniciativa_camada_ambiente);
CREATE INDEX IF NOT EXISTS idx_iniciativa_owner_ini ON iniciativa_proprietario(id_iniciativa_aisn);
CREATE INDEX IF NOT EXISTS idx_hierarquia_gestor ON hierarquia_usuario(id_gestor_aisn);

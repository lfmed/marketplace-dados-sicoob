-- =====================================================================
-- Schema {ACC} (gestao_acesso) — Motor de Gestão de Acesso (modelo oficial do cliente).
-- REFERÊNCIA de acesso: hierarquia, grupos, ativos e proprietários dos ativos.
-- No cliente é Delta em plataforma.gestao_acesso, sincronizado p/ o Lakebase (leitura).
-- O WORKFLOW do App (solicitação/aprovação/acesso/execução...) fica em {APP} (03_app.sql).
-- Nomes de schema PARAMETRIZÁVEIS ({ACC} via config.SCHEMA_GESTAO).
-- =====================================================================
CREATE SCHEMA IF NOT EXISTS {ACC};

CREATE TABLE IF NOT EXISTS {ACC}.hierarquia_usuario (
    id_usuario_aisn            VARCHAR(255) NOT NULL,   -- -> {GOV}.usuario_aisn (lógico)
    id_gestor_aisn             VARCHAR(255) NOT NULL,   -- -> {GOV}.usuario_aisn (lógico)
    datahora_inicio_validade   TIMESTAMP DEFAULT now(),
    datahora_fim_validade      TIMESTAMP,
    bol_atual                  BOOLEAN DEFAULT true,
    bol_excluido               BOOLEAN DEFAULT false,
    PRIMARY KEY (id_usuario_aisn, id_gestor_aisn)
);

CREATE TABLE IF NOT EXISTS {ACC}.grupo_acesso (
    id_grupo_acesso            VARCHAR(255) PRIMARY KEY,
    id_externo_grupo           VARCHAR(255),
    cod_conta_databricks       VARCHAR(255),
    nome_grupo                 VARCHAR(255) NOT NULL,   -- nome do grupo UC alvo da associação
    tipo_grupo                 VARCHAR(100),            -- 'exploratorio' = pedível em nome do grupo
    datahora_inicio_validade   TIMESTAMP DEFAULT now(),
    datahora_fim_validade      TIMESTAMP,
    bol_atual                  BOOLEAN DEFAULT true,
    bol_excluido               BOOLEAN DEFAULT false
);

CREATE TABLE IF NOT EXISTS {ACC}.grupo_acesso_membro (
    id_grupo_acesso            VARCHAR(255) NOT NULL REFERENCES {ACC}.grupo_acesso(id_grupo_acesso),
    cod_conta_databricks       VARCHAR(255),
    tipo_entidade              VARCHAR(100),            -- USUARIO / GRUPO
    id_entidade                VARCHAR(255) NOT NULL,   -- id do usuário/grupo membro
    nome_entidade              VARCHAR(255),
    datahora_inicio_validade   TIMESTAMP DEFAULT now(),
    datahora_fim_validade      TIMESTAMP,
    bol_atual                  BOOLEAN DEFAULT true,
    bol_excluido               BOOLEAN DEFAULT false,
    PRIMARY KEY (id_grupo_acesso, id_entidade)
);

-- Ativo = unidade liberável (processado pelo Motor a partir de domínio/subdomínio/
-- iniciativa). Relação POLIMÓRFICA: id_ativo_aisn É a PK da combinação de origem e
-- cod_tipo_ativo diz onde resolver ('1'=ICA, '2'=TABELA, '3'=SUBDOMINIO, '4'=DOMINIO).
-- O grupo do ativo (id_grupo_acesso/nome_grupo_ativo) detém o privilégio no UC; a
-- concessão inclui o beneficiário nesse grupo. Sem colunas de catálogo/schema (o alvo
-- UC é navegado via {GOV}.tabela_aisn — ver app/services/ativo_scope.py).
CREATE TABLE IF NOT EXISTS {ACC}.ativo_aisn (
    id_ativo_aisn              VARCHAR(255) PRIMARY KEY,  -- = PK da combinação de origem
    id_grupo_acesso            VARCHAR(255) NOT NULL REFERENCES {ACC}.grupo_acesso(id_grupo_acesso),
    nome_grupo_ativo           VARCHAR(255) NOT NULL,     -- nome do grupo do ativo (alvo da associação)
    desc_grupo_ativo           VARCHAR(1000),
    cod_tipo_ativo             VARCHAR(50),               -- 1=ICA | 2=TABELA | 3=SUBDOMINIO | 4=DOMINIO
    nome_ativo                 VARCHAR(255) NOT NULL,
    desc_ativo                 VARCHAR(1000),
    bol_elegivel_acesso        BOOLEAN DEFAULT true,
    datahora_inicio_validade   TIMESTAMP DEFAULT now(),
    datahora_fim_validade      TIMESTAMP,
    bol_atual                  BOOLEAN DEFAULT true,
    bol_excluido               BOOLEAN DEFAULT false
);

CREATE TABLE IF NOT EXISTS {ACC}.ativo_proprietario (
    id_ativo_aisn              VARCHAR(255) NOT NULL REFERENCES {ACC}.ativo_aisn(id_ativo_aisn),
    id_usuario_aisn            VARCHAR(255) NOT NULL,   -- -> {GOV}.usuario_aisn (lógico)
    cod_tipo_proprietario      VARCHAR(50),
    bol_principal              BOOLEAN DEFAULT false,
    datahora_inicio_validade   TIMESTAMP DEFAULT now(),
    datahora_fim_validade      TIMESTAMP,
    bol_atual                  BOOLEAN DEFAULT true,
    bol_excluido               BOOLEAN DEFAULT false,
    PRIMARY KEY (id_ativo_aisn, id_usuario_aisn)
);

-- Proprietário do GRUPO de acesso (grupos exploratórios). O proprietário do grupo faz a
-- APROVAÇÃO HIERÁRQUICA dos acessos pedidos em nome do grupo (análogo ao gestor no acesso
-- nominal). Alimentada pelo Motor de Gestão de Acesso.
CREATE TABLE IF NOT EXISTS {ACC}.grupo_acesso_proprietario (
    id_grupo_acesso            VARCHAR(255) NOT NULL REFERENCES {ACC}.grupo_acesso(id_grupo_acesso),
    id_usuario_aisn            VARCHAR(255) NOT NULL,   -- -> {GOV}.usuario_aisn (lógico)
    cod_tipo_proprietario      VARCHAR(50),
    bol_principal              BOOLEAN DEFAULT false,
    datahora_inicio_validade   TIMESTAMP DEFAULT now(),
    datahora_fim_validade      TIMESTAMP,
    bol_atual                  BOOLEAN DEFAULT true,
    bol_excluido               BOOLEAN DEFAULT false,
    PRIMARY KEY (id_grupo_acesso, id_usuario_aisn)
);

CREATE INDEX IF NOT EXISTS idx_hierarquia_gestor ON {ACC}.hierarquia_usuario(id_gestor_aisn);
CREATE INDEX IF NOT EXISTS idx_grupo_membro_entidade ON {ACC}.grupo_acesso_membro(id_entidade);
CREATE INDEX IF NOT EXISTS idx_ativo_grupo ON {ACC}.ativo_aisn(id_grupo_acesso);
CREATE INDEX IF NOT EXISTS idx_ativo_prop_usuario ON {ACC}.ativo_proprietario(id_usuario_aisn);
CREATE INDEX IF NOT EXISTS idx_grupo_prop_usuario ON {ACC}.grupo_acesso_proprietario(id_usuario_aisn);
CREATE INDEX IF NOT EXISTS idx_grupo_prop_grupo ON {ACC}.grupo_acesso_proprietario(id_grupo_acesso);

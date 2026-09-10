"""Constantes de domínio — estados do ciclo de vida e eventos (RN/RF)."""

# Status da solicitação
S_PENDENTE_AUTORIZACAO = "PENDENTE_AUTORIZACAO"
S_AUTORIZADA = "AUTORIZADA"
S_REPROVADA_GESTOR = "REPROVADA_GESTOR"
S_APROVADA_OWNER = "APROVADA_OWNER"
S_REPROVADA_OWNER = "REPROVADA_OWNER"
S_CANCELADA = "CANCELADA"

STATUS_SOLICITACAO_ABERTOS = {S_PENDENTE_AUTORIZACAO, S_AUTORIZADA}
STATUS_SOLICITACAO_CANCELAVEL = {S_PENDENTE_AUTORIZACAO, S_AUTORIZADA}

STATUS_SOLICITACAO_LABEL = {
    S_PENDENTE_AUTORIZACAO: "Pendente de autorização do gestor",
    S_AUTORIZADA: "Aguardando aprovação do owner",
    S_REPROVADA_GESTOR: "Reprovada pelo gestor",
    S_APROVADA_OWNER: "Aprovada pelo owner",
    S_REPROVADA_OWNER: "Reprovada pelo owner",
    S_CANCELADA: "Cancelada",
}

# Status do acesso (distinto da aprovação — RN-018/029)
A_AGUARDANDO_EFETIVACAO = "APROVADO_AGUARDANDO_EFETIVACAO"
A_EFETIVADO = "EFETIVADO"
A_ERRO_EFETIVACAO = "ERRO_EFETIVACAO"
A_REVOGADO = "REVOGADO"

STATUS_ACESSO_LABEL = {
    A_AGUARDANDO_EFETIVACAO: "Aprovado · aguardando efetivação",
    A_EFETIVADO: "Efetivado",
    A_ERRO_EFETIVACAO: "Erro na efetivação",
    A_REVOGADO: "Revogado",
}

# Resultado de decisão
R_APROVADA = "APROVADA"
R_REPROVADA = "REPROVADA"

# Execução técnica
OP_CONCESSAO = "CONCESSAO"
OP_REVOGACAO = "REVOGACAO"
E_PENDENTE = "PENDENTE"
E_EFETIVADA = "EFETIVADA"
E_ERRO = "ERRO"

# Tipo de beneficiário
B_NOMINAL = "NOMINAL"
B_GRUPO = "GRUPO"

# Tipos de ATIVO (código numérico do Motor) -> tabela de origem que o resolve.
# O id_ativo_aisn É a PK da entidade de origem (relação polimórfica, sem FK física).
AT_ICA = "1"         # iniciativa_camada_ambiente  -> 1 schema  (GRANT ON SCHEMA)
AT_TABELA = "2"      # tabela_aisn                 -> 1 tabela  (GRANT ON TABLE)
AT_SUBDOMINIO = "3"  # subdominio_informacao       -> N schemas (expande)
AT_DOMINIO = "4"     # dominio_informacao          -> N schemas (expande)

TIPO_ATIVO_LABEL = {
    AT_ICA: "Iniciativa",
    AT_TABELA: "Tabela",
    AT_SUBDOMINIO: "Subdomínio",
    AT_DOMINIO: "Domínio",
}
# Ordem de exibição no catálogo (do mais amplo ao mais específico)
TIPOS_ATIVO = [AT_DOMINIO, AT_SUBDOMINIO, AT_ICA, AT_TABELA]

# Tipos de acesso (RF-014) -> privilégios UC concedidos no schema
TIPOS_ACESSO = {
    "LEITURA": ["SELECT"],
    "LEITURA_ESCRITA": ["SELECT", "MODIFY"],
}
TIPO_ACESSO_LABEL = {
    "LEITURA": "Leitura (SELECT)",
    "LEITURA_ESCRITA": "Leitura e escrita (SELECT + MODIFY)",
}

# Eventos de auditoria
EV_SOLICITACAO_CRIADA = "SOLICITACAO_CRIADA"
EV_AUTORIZADA = "AUTORIZACAO_HIERARQUICA_APROVADA"
EV_REPROVADA_GESTOR = "AUTORIZACAO_HIERARQUICA_REPROVADA"
EV_APROVADA_OWNER = "APROVACAO_OWNER_APROVADA"
EV_REPROVADA_OWNER = "APROVACAO_OWNER_REPROVADA"
EV_CANCELADA = "SOLICITACAO_CANCELADA"
EV_ACESSO_CRIADO = "ACESSO_CRIADO"
EV_EFETIVADO = "ACESSO_EFETIVADO"
EV_ERRO_EFETIVACAO = "ERRO_EFETIVACAO"
EV_REVOGACAO_SOLICITADA = "REVOGACAO_SOLICITADA"
EV_REVOGADO = "ACESSO_REVOGADO"

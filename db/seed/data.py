"""Dataset sintético estilo Sicoob (D-004).
IDs são slugs determinísticos para o seed ser idempotente e os nomes de schema UC
serem estáveis. desc_email do beneficiário real (leandro) permite GRANT real verificável.
"""

# Personas. O e-mail REAL (leandro) é usado para demonstrar GRANT nominal verificável.
# Os demais são sintéticos (para demonstrar as filas de aprovação via proxy).
REAL_EMAIL = "leandro.medeiros@databricks.com"

USUARIOS = [
    # id, nome_completo, email, papel (para navegação/proxy)
    ("u_leandro",  "Leandro Medeiros", REAL_EMAIL,                        "solicitante_real"),
    ("u_bruno",    "Bruno Carvalho",   "bruno.carvalho@sicoob.com.br",    "solicitante"),
    ("u_mariana",  "Mariana Alves",    "mariana.alves@sicoob.com.br",     "gestor"),
    ("u_ana",      "Ana Paula Ribeiro","ana.ribeiro@sicoob.com.br",       "owner"),
    ("u_carlos",   "Carlos Eduardo Souza","carlos.souza@sicoob.com.br",   "owner"),
    ("u_daniela",  "Daniela Prado",    "daniela.prado@sicoob.com.br",     "owner"),
    ("u_eduardo",  "Eduardo Nunes",    "eduardo.nunes@sicoob.com.br",     "owner"),
]

# Hierarquia (usuario -> gestor imediato). RN-013/033.
HIERARQUIA = [
    ("u_leandro", "u_mariana"),
    ("u_bruno",   "u_mariana"),
    ("u_ana",     "u_mariana"),
    ("u_carlos",  "u_mariana"),
]

# Ambientes
AMBIENTES = [
    ("amb_prod", "Produção", "Ambiente produtivo"),
]

# Camadas (Bronze/Silver/Gold) — RN-002 independentes
CAMADAS = [
    ("cam_bronze", "Bronze", "Dados brutos"),
    ("cam_silver", "Silver", "Dados tratados"),
    ("cam_gold",   "Gold",   "Dados curados para consumo"),
]

# Domínios
DOMINIOS = [
    ("dom_canais",   "Canais e Experiência",     "Jornadas e canais digitais do cooperado"),
    ("dom_cliente",  "Cliente e Relacionamento", "Cadastro, perfil e relacionamento"),
    ("dom_credito",  "Crédito e Risco",          "Concessão, score e risco de crédito"),
    ("dom_pgto",     "Pagamentos e Transações",  "Pix, cartões e transações"),
]

# Subdomínios (id, dominio, nome)
SUBDOMINIOS = [
    ("sub_ib",       "dom_canais",  "Internet Banking"),
    ("sub_mobile",   "dom_canais",  "Mobile"),
    ("sub_apis",     "dom_canais",  "Parceiros e APIs"),
    ("sub_cadastro", "dom_cliente", "Identificação e Cadastro"),
    ("sub_perfil",   "dom_cliente", "Perfil e Segmentação"),
    ("sub_priv",     "dom_cliente", "Consentimentos e Privacidade"),
    ("sub_score",    "dom_credito", "Score e Modelos"),
    ("sub_proposta", "dom_credito", "Propostas e Contratos"),
    ("sub_pix",      "dom_pgto",    "Pix e Instantâneos"),
    ("sub_cartao",   "dom_pgto",    "Cartões"),
]

# Iniciativas (id, subdominio, nome, desc, owner_id, [camadas])
INICIATIVAS = [
    ("ini_ib_nav",   "sub_ib",       "IB · Navegação e Sessões",   "Sessões, jornadas e eventos de navegação no IB web.", "u_ana",     ["cam_silver", "cam_gold"]),
    ("ini_ib_trx",   "sub_ib",       "IB · Transações Web",        "Transações financeiras efetuadas no Internet Banking web.", "u_ana", ["cam_silver", "cam_gold"]),
    ("ini_mob_eng",  "sub_mobile",   "Mobile · Engajamento",       "Dispositivos, sessões e adoção de funcionalidades no app mobile.", "u_ana", ["cam_gold"]),
    ("ini_api_tel",  "sub_apis",     "APIs · Telemetria de Consumo","Volume, latência e status das chamadas às APIs por parceiro.", "u_ana", ["cam_bronze", "cam_silver"]),
    ("ini_api_parc", "sub_apis",     "APIs · Cadastro de Parceiros","Parceiros integrados, escopos contratados e situação contratual.", "u_ana", ["cam_gold"]),
    ("ini_cad_360",  "sub_cadastro", "Cadastro · Cooperado 360",   "Cadastro mestre do cooperado: dados pessoais e situação cadastral.", "u_carlos", ["cam_silver", "cam_gold"]),
    ("ini_cad_doc",  "sub_cadastro", "Cadastro · Documentos",      "Documentos de identificação vinculados ao cooperado.", "u_carlos", ["cam_silver"]),
    ("ini_perf_seg", "sub_perfil",   "Perfil · Segmentos e Score", "Segmentos comportamentais e score de relacionamento do cooperado.", "u_carlos", ["cam_gold"]),
    ("ini_priv_lgpd","sub_priv",     "Privacidade · Consentimentos LGPD","Consentimentos, finalidades de uso e histórico de revogações (LGPD).", "u_carlos", ["cam_gold"]),
    ("ini_cred_score","sub_score",   "Risco · Score de Crédito",   "Score de crédito e variáveis de risco por cooperado.", "u_daniela", ["cam_silver", "cam_gold"]),
    ("ini_cred_prop","sub_proposta", "Crédito · Propostas e Contratos","Propostas, contratos e situação de crédito.", "u_daniela", ["cam_gold"]),
    ("ini_pix_trx",  "sub_pix",      "Pix · Transações Instantâneas","Transações Pix, chaves e limites por cooperado.", "u_eduardo", ["cam_silver", "cam_gold"]),
    ("ini_card_fat", "sub_cartao",   "Cartões · Faturas e Limites","Faturas, limites e uso de cartões.", "u_eduardo", ["cam_gold"]),
]

# Grupos exploratórios (id, nome_grupo_UC, tipo, membros[ids usuario])
# nome_grupo é o nome REAL do grupo UC (criado no seed) alvo do GRANT de grupo.
GRUPOS = [
    ("grp_risco_credito", "mkt_risco_credito", "EXPLORATORIO", ["u_leandro", "u_bruno"]),
    ("grp_dados_canais",  "mkt_dados_canais",  "EXPLORATORIO", ["u_leandro", "u_bruno"]),
    ("grp_compliance_pld","mkt_compliance_pld","EXPLORATORIO", ["u_bruno"]),
]

# Tabelas de exemplo por camada (nome lógico -> colunas). Reaproveitadas em cada ICA.
TABELAS_EXEMPLO = {
    "cam_bronze": [("evento_bruto", "id_evento BIGINT, datahora_evento TIMESTAMP, desc_payload STRING")],
    "cam_silver": [("fato_movimento", "id_movimento BIGINT, num_cooperativa INT, valor_movimento DECIMAL(18,2), datahora_carga TIMESTAMP")],
    "cam_gold":   [("indicador_consolidado", "id_indicador BIGINT, nome_indicador STRING, valor_indicador DECIMAL(18,4), ano_mes INT"),
                   ("dim_cooperado", "id_cooperado BIGINT, nome_cooperado STRING, sigla_uf STRING")],
}

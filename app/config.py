"""Configuração central do Marketplace de Dados.

TODOS os valores específicos de ambiente ficam aqui, lidos de variáveis de ambiente,
com defaults de desenvolvimento. Para deploy na workspace do cliente, basta ajustar as
env vars (via app.yaml `env`/`valueFrom`) — nenhum valor de infraestrutura é hardcoded
no restante do código. Ver docs/DECISIONS.md (D-006, D-007).
"""
import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # dotenv é opcional (não existe no runtime do Apps)
    pass


def _b(v: str, default: bool) -> bool:
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "y", "sim")


class Config:
    # --- Perfil CLI (dev local; no Apps a auth vem do service principal) ---
    DATABRICKS_PROFILE = os.getenv("DATABRICKS_CONFIG_PROFILE", "DEFAULT")

    # --- Unity Catalog: catálogo é PARÂMETRO; o app só cria/concede em schemas ---
    UC_CATALOG = os.getenv("UC_CATALOG", "stable_classic_pg4xe1_catalog")
    # Prefixo dos schemas de exemplo (unidade funcional = iniciativa+camada+ambiente)
    UC_SCHEMA_PREFIX = os.getenv("UC_SCHEMA_PREFIX", "mkt")
    # Catálogo Delta onde o Motor mantém governanca + gestao_acesso (cliente: "plataforma").
    # Dev: usa o próprio UC_CATALOG (não é possível criar o catálogo do cliente aqui).
    GOV_CATALOG = os.getenv("GOV_CATALOG", os.getenv("UC_CATALOG", "stable_classic_pg4xe1_catalog"))

    # --- SQL Warehouse usado para executar DDL/GRANT/REVOKE no UC ---
    WAREHOUSE_ID = os.getenv("DATABRICKS_WAREHOUSE_ID", "b8e52268d9828bdd")

    # --- Escopo dos grupos (concessão por associação) ---
    # 'account' = grupos de CONTA (produção/cliente): gerenciados via AccountClient e são
    #             principais válidos p/ GRANT no UC. Exige DATABRICKS_ACCOUNT_ID + SP com
    #             direito de gerente de grupo (ou admin de conta).
    # 'workspace' = grupos workspace-local (dev sem acesso à conta). Default.
    GROUPS_SCOPE = os.getenv("GROUPS_SCOPE", "workspace").strip().lower()
    DATABRICKS_ACCOUNT_ID = os.getenv("DATABRICKS_ACCOUNT_ID", "")
    DATABRICKS_ACCOUNT_HOST = os.getenv("DATABRICKS_ACCOUNT_HOST", "https://accounts.cloud.databricks.com")

    # --- Lakebase (Postgres) — base operacional do App ---
    LAKEBASE_ENDPOINT = os.getenv(
        "LAKEBASE_ENDPOINT",
        "projects/marketplace-dados/branches/production/endpoints/primary",
    )
    LAKEBASE_DBNAME = os.getenv("LAKEBASE_DBNAME", "databricks_postgres")
    # Nomes de schema PARAMETRIZÁVEIS (dev = seu catálogo fixo; cliente = plataforma).
    # governanca: taxonomia (Motor de Governança). gestao_acesso: referência de acesso do
    # Motor (hierarquia, grupos, ativos, proprietários). marketplace_app: workflow do App.
    SCHEMA_GOVERNANCA = os.getenv("SCHEMA_GOVERNANCA", "governanca")
    SCHEMA_GESTAO = os.getenv("SCHEMA_GESTAO", "gestao_acesso")
    SCHEMA_APP = os.getenv("SCHEMA_APP", "marketplace_app")

    # Valor de grupo_acesso.tipo_grupo que marca um grupo EXPLORATÓRIO (para o qual o usuário
    # pode solicitar acesso). Comparação case-insensitive. Cliente: 'exploratorio'.
    GRUPO_TIPO_EXPLORATORIO = os.getenv("GRUPO_TIPO_EXPLORATORIO", "exploratorio")

    # --- Identidade / demo ---
    # Em prod: identidade via SSO (header X-Forwarded-Email). Em dev: proxy "atuar como".
    ENABLE_PROXY = _b(os.getenv("APP_ENABLE_PROXY"), True)
    # E-mail usado quando não há header de SSO (dev local)
    DEV_FALLBACK_EMAIL = os.getenv("DEV_FALLBACK_EMAIL", "leandro.medeiros@databricks.com")

    # --- Efetivação técnica ---
    # true = executa GRANT/REVOKE reais no UC (D-003); false = simula (registra só o log)
    GRANT_EXECUTE_REAL = _b(os.getenv("GRANT_EXECUTE_REAL"), True)
    # Provisionamento do GRANT do grupo do ativo nos objetos. Em PRODUÇÃO o grupo já vem
    # concedido pelo Motor/governança -> false (o app só gerencia membership). Em dev
    # (sem Motor) -> true para a demo ter efeito. Default true (dev); cliente define false.
    PROVISION_GROUP_GRANT = _b(os.getenv("PROVISION_GROUP_GRANT"), True)
    # SLA de efetivação (RN-030): 30 minutos
    EFETIVACAO_SLA_MIN = int(os.getenv("EFETIVACAO_SLA_MIN", "30"))

    # --- Provisionamento na subida (deploy sem CLI) ---
    # true = ao subir, a app cria o schema de workflow ({APP} marketplace_app) direto no
    # Lakebase (server-side, pelo SP) e loga em detalhe o que provisiona/verifica. Assim o
    # deploy não depende da CLI databricks (útil quando o cliente tem firewall). Idempotente.
    AUTO_BOOTSTRAP = _b(os.getenv("AUTO_BOOTSTRAP_APP_SCHEMA"), True)

    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-marketplace-sicoob-troque-em-prod")

    @classmethod
    def as_dict(cls):
        return {k: getattr(cls, k) for k in dir(cls) if k.isupper()}


config = Config()

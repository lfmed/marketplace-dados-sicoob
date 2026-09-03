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

    # --- SQL Warehouse usado para executar DDL/GRANT/REVOKE no UC ---
    WAREHOUSE_ID = os.getenv("DATABRICKS_WAREHOUSE_ID", "b8e52268d9828bdd")

    # --- Lakebase (Postgres) — base operacional do App ---
    LAKEBASE_ENDPOINT = os.getenv(
        "LAKEBASE_ENDPOINT",
        "projects/marketplace-dados/branches/production/endpoints/primary",
    )
    LAKEBASE_DBNAME = os.getenv("LAKEBASE_DBNAME", "databricks_postgres")
    SCHEMA_GOVERNANCA = os.getenv("SCHEMA_GOVERNANCA", "governanca")
    SCHEMA_GESTAO = os.getenv("SCHEMA_GESTAO", "gestao_acesso")

    # --- Identidade / demo ---
    # Em prod: identidade via SSO (header X-Forwarded-Email). Em dev: proxy "atuar como".
    ENABLE_PROXY = _b(os.getenv("APP_ENABLE_PROXY"), True)
    # E-mail usado quando não há header de SSO (dev local)
    DEV_FALLBACK_EMAIL = os.getenv("DEV_FALLBACK_EMAIL", "leandro.medeiros@databricks.com")

    # --- Efetivação técnica ---
    # true = executa GRANT/REVOKE reais no UC (D-003); false = simula (registra só o log)
    GRANT_EXECUTE_REAL = _b(os.getenv("GRANT_EXECUTE_REAL"), True)
    # SLA de efetivação (RN-030): 30 minutos
    EFETIVACAO_SLA_MIN = int(os.getenv("EFETIVACAO_SLA_MIN", "30"))

    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-marketplace-sicoob-troque-em-prod")

    @classmethod
    def as_dict(cls):
        return {k: getattr(cls, k) for k in dir(cls) if k.isupper()}


config = Config()

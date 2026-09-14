"""Nomes de schema do Lakebase, PARAMETRIZÁVEIS via config (não hardcode).

O mesmo código roda no dev (catálogo/schemas do leandro) e no cliente (catálogo
`plataforma`), bastando ajustar as env vars. Distribuição das tabelas conforme o
modelo oficial do cliente:

- GOV (governanca): taxonomia do Motor de Governança — dominio/subdominio/iniciativa/
  camada/ambiente, as combinações *_camada_ambiente, tabela_aisn, usuario_aisn e os
  proprietários de domínio/subdomínio/iniciativa.
- ACC (gestao_acesso): referência do Motor de Acesso — hierarquia_usuario, grupo_acesso,
  grupo_acesso_membro, ativo_aisn, ativo_proprietario. (Somente leitura para o app.)
- APP (marketplace_app): workflow do próprio App — solicitacao_acesso,
  autorizacao_hierarquica, aprovacao_owner, acesso, execucao_tecnica, revogacao_acesso,
  evento_ciclo_vida. (Leitura/escrita.)

Uso nas queries: f-strings, ex. f"SELECT ... FROM {ACC}.ativo_aisn a ...".
"""
from app.config import config

GOV = config.SCHEMA_GOVERNANCA   # governanca
ACC = config.SCHEMA_GESTAO       # gestao_acesso (referência de acesso)
APP = config.SCHEMA_APP          # marketplace_app (workflow)


def substitute_schemas(sql: str, gov: str = None, acc: str = None, app: str = None) -> str:
    """Substitui os placeholders {GOV}/{ACC}/{APP} do DDL pelos nomes de schema. Fonte
    ÚNICA da regra de substituição — usada por db/setup.py (aplica), app/bootstrap.py
    (boot) e scripts/gen_app_sql.py (gera SQL avulso, aí com nomes arbitrários)."""
    return (sql.replace("{GOV}", gov if gov is not None else GOV)
               .replace("{ACC}", acc if acc is not None else ACC)
               .replace("{APP}", app if app is not None else APP))

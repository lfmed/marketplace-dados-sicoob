"""Spec único do schema do Motor (colunas + PK + schema), modelo OFICIAL do cliente.
Usado por: build Delta (UC) e sync Delta->Lakebase. As colunas batem com db/ddl/01+02.
Cada tabela tem um schema lógico: 'gov' (governanca) ou 'acc' (gestao_acesso), resolvido
para os nomes parametrizados em config. Tipos Delta derivados por prefixo.
"""
from app.config import config

GOV = config.SCHEMA_GOVERNANCA   # governanca
ACC = config.SCHEMA_GESTAO       # gestao_acesso

SCD2 = ["datahora_inicio_validade", "datahora_fim_validade", "bol_atual", "bol_excluido"]

# (schema, tabela, [colunas...], [pk...]) — em ordem de dependência (pais antes de filhos).
GOV_TABLES = [
    # ---------- governanca (taxonomia) ----------
    (GOV, "dominio_informacao",
     ["id_dominio_informacao", "nome_dominio", "tag_dominio", "sigla_dominio", "desc_dominio"] + SCD2,
     ["id_dominio_informacao"]),
    (GOV, "subdominio_informacao",
     ["id_subdominio_informacao", "id_dominio_informacao", "nome_subdominio", "tag_subdominio",
      "sigla_subdominio", "desc_subdominio"] + SCD2,
     ["id_subdominio_informacao"]),
    (GOV, "iniciativa_aisn",
     ["id_iniciativa_aisn", "id_subdominio_informacao", "nome_iniciativa", "desc_iniciativa",
      "cod_status_iniciativa"] + SCD2,
     ["id_iniciativa_aisn"]),
    (GOV, "camada_aisn",
     ["id_camada_aisn", "nome_camada", "desc_camada"] + SCD2, ["id_camada_aisn"]),
    (GOV, "ambiente_aisn",
     ["id_ambiente_aisn", "nome_ambiente", "desc_ambiente"] + SCD2, ["id_ambiente_aisn"]),
    (GOV, "iniciativa_camada_ambiente",
     ["id_iniciativa_camada_ambiente", "id_iniciativa_aisn", "id_camada_aisn", "id_ambiente_aisn",
      "nome_iniciativa_camada_ambiente", "desc_iniciativa_camada_ambiente", "bol_elegivel_acesso"] + SCD2,
     ["id_iniciativa_camada_ambiente"]),
    (GOV, "subdominio_camada_ambiente",
     ["id_subdominio_camada_ambiente", "id_subdominio_informacao", "id_camada_aisn", "id_ambiente_aisn",
      "nome_subdominio_camada_ambiente", "desc_subdominio_camada_ambiente", "bol_elegivel_acesso"] + SCD2,
     ["id_subdominio_camada_ambiente"]),
    (GOV, "dominio_camada_ambiente",
     ["id_dominio_camada_ambiente", "id_dominio_informacao", "id_camada_aisn", "id_ambiente_aisn",
      "nome_dominio_camada_ambiente", "desc_dominio_camada_ambiente", "bol_elegivel_acesso"] + SCD2,
     ["id_dominio_camada_ambiente"]),
    (GOV, "tabela_aisn",
     ["id_tabela_aisn", "id_iniciativa_camada_ambiente", "nome_catalogo", "nome_schema",
      "nome_tabela", "desc_tabela", "cod_status_tabela", "bol_elegivel_acesso"] + SCD2,
     ["id_tabela_aisn"]),
    (GOV, "usuario_aisn",
     ["id_usuario_aisn", "nome_usuario", "nome_completo", "desc_nome", "desc_email",
      "desc_sobrenome", "cod_conta_databricks", "datahora_inicio_validade",
      "datahora_fim_validade", "bol_ativo", "bol_atual", "bol_excluido"],
     ["id_usuario_aisn"]),
    (GOV, "dominio_proprietario",
     ["id_dominio_informacao", "id_usuario_aisn", "cod_tipo_proprietario", "bol_principal"] + SCD2,
     ["id_dominio_informacao", "id_usuario_aisn"]),
    (GOV, "subdominio_proprietario",
     ["id_subdominio_informacao", "id_usuario_aisn", "cod_tipo_proprietario", "bol_principal"] + SCD2,
     ["id_subdominio_informacao", "id_usuario_aisn"]),
    (GOV, "iniciativa_proprietario",
     ["id_iniciativa_aisn", "id_usuario_aisn", "cod_tipo_proprietario", "bol_principal"] + SCD2,
     ["id_iniciativa_aisn", "id_usuario_aisn"]),
    # ---------- gestao_acesso (referência de acesso) ----------
    (ACC, "hierarquia_usuario",
     ["id_usuario_aisn", "id_gestor_aisn"] + SCD2, ["id_usuario_aisn", "id_gestor_aisn"]),
    (ACC, "grupo_acesso",
     ["id_grupo_acesso", "id_externo_grupo", "cod_conta_databricks", "nome_grupo"] + SCD2,
     ["id_grupo_acesso"]),
    (ACC, "grupo_acesso_membro",
     ["id_grupo_acesso", "cod_conta_databricks", "tipo_entidade", "id_entidade", "nome_entidade"] + SCD2,
     ["id_grupo_acesso", "id_entidade"]),
    (ACC, "ativo_aisn",
     ["id_ativo_aisn", "id_grupo_acesso", "nome_grupo_ativo", "desc_grupo_ativo", "cod_tipo_ativo",
      "nome_ativo", "desc_ativo", "bol_elegivel_acesso"] + SCD2, ["id_ativo_aisn"]),
    (ACC, "ativo_proprietario",
     ["id_ativo_aisn", "id_usuario_aisn", "cod_tipo_proprietario", "bol_principal"] + SCD2,
     ["id_ativo_aisn", "id_usuario_aisn"]),
]

# Schemas Delta (UC) do Motor — dois, dentro de GOV_CATALOG (cliente: plataforma).
DELTA_SCHEMAS = sorted({t[0] for t in GOV_TABLES})


def delta_type(col: str) -> str:
    if col.startswith("bol_"):
        return "BOOLEAN"
    if col.startswith("datahora_"):
        return "TIMESTAMP"
    return "STRING"


def coerce_from_delta(col: str, val):
    """Converte valor vindo do Delta (string/None) para tipo Postgres."""
    if val is None:
        return None
    if col.startswith("bol_"):
        return str(val).strip().lower() in ("true", "1", "t")
    return val

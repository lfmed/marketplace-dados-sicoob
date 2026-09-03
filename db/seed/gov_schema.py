"""Spec único do schema de governança (colunas + PK + ordem de dependência).
Usado por: build Delta (UC) e sync Delta->Lakebase. As colunas batem com
db/ddl/01_governanca.sql. Tipos Delta são derivados por prefixo (bol_/datahora_/else)."""

SCD2 = ["datahora_inicio_validade", "datahora_fim_validade", "bol_atual", "bol_excluido"]

# (tabela, [colunas...], [pk...]) — em ordem de dependência (pais antes de filhos)
GOV_TABLES = [
    ("dominio_informacao",
     ["id_dominio_informacao", "nome_dominio", "desc_dominio"] + SCD2,
     ["id_dominio_informacao"]),
    ("subdominio_informacao",
     ["id_subdominio_informacao", "id_dominio_informacao", "nome_subdominio", "desc_subdominio"] + SCD2,
     ["id_subdominio_informacao"]),
    ("iniciativa_aisn",
     ["id_iniciativa_aisn", "id_subdominio_informacao", "nome_iniciativa", "desc_iniciativa",
      "cod_status_iniciativa"] + SCD2,
     ["id_iniciativa_aisn"]),
    ("camada_aisn",
     ["id_camada_aisn", "nome_camada", "desc_camada"] + SCD2,
     ["id_camada_aisn"]),
    ("ambiente_aisn",
     ["id_ambiente_aisn", "nome_ambiente", "desc_ambiente"] + SCD2,
     ["id_ambiente_aisn"]),
    ("iniciativa_camada_ambiente",
     ["id_iniciativa_camada_ambiente", "id_iniciativa_aisn", "id_camada_aisn", "id_ambiente_aisn",
      "nome_catalogo", "nome_schema", "bol_elegivel_acesso"] + SCD2,
     ["id_iniciativa_camada_ambiente"]),
    ("tabela_aisn",
     ["id_tabela_aisn", "id_iniciativa_camada_ambiente", "nome_catalogo", "nome_schema",
      "nome_tabela", "desc_tabela", "cod_status_tabela", "bol_elegivel_acesso"] + SCD2,
     ["id_tabela_aisn"]),
    ("usuario_aisn",
     ["id_usuario_aisn", "nome_usuario", "nome_completo", "desc_nome", "desc_email",
      "desc_sobrenome", "cod_conta_databricks", "datahora_inicio_validade",
      "datahora_fim_validade", "bol_ativo", "bol_atual", "bol_excluido"],
     ["id_usuario_aisn"]),
    ("hierarquia_usuario",
     ["id_usuario_aisn", "id_gestor_aisn"] + SCD2,
     ["id_usuario_aisn", "id_gestor_aisn"]),
    ("grupo_acesso",
     ["id_grupo_acesso", "id_externo_grupo", "cod_conta_databricks", "nome_grupo", "tipo_grupo"] + SCD2,
     ["id_grupo_acesso"]),
    ("grupo_acesso_membro",
     ["id_grupo_acesso", "id_entidade", "tipo_entidade", "nome_entidade", "cod_conta_databricks"] + SCD2,
     ["id_grupo_acesso", "id_entidade"]),
    ("iniciativa_proprietario",
     ["id_usuario_aisn", "id_iniciativa_aisn", "cod_tipo_proprietario", "bol_principal"] + SCD2,
     ["id_usuario_aisn", "id_iniciativa_aisn"]),
    # Tabelas do modelo que ficam vazias no seed (criadas p/ fidelidade ao .drawio):
    ("ativo_aisn",
     ["id_ativo_aisn", "id_grupo_acesso", "cod_tipo_ativo", "nome_ativo", "desc_ativo",
      "bol_elegivel_acesso"] + SCD2, ["id_ativo_aisn"]),
    ("dominio_proprietario",
     ["id_usuario_aisn", "id_dominio_informacao", "cod_tipo_proprietario", "bol_principal"] + SCD2,
     ["id_usuario_aisn", "id_dominio_informacao"]),
    ("subdominio_proprietario",
     ["id_usuario_aisn", "id_subdominio_informacao", "cod_tipo_proprietario", "bol_principal"] + SCD2,
     ["id_usuario_aisn", "id_subdominio_informacao"]),
    ("ativo_proprietario",
     ["id_usuario_aisn", "id_ativo_aisn", "cod_tipo_proprietario", "bol_principal"] + SCD2,
     ["id_usuario_aisn", "id_ativo_aisn"]),
]

GOV_SCHEMA_UC = "marketplace_governanca"  # schema Delta no UC (fonte da verdade)


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
    return val  # STRING e TIMESTAMP: Postgres faz o cast a partir do texto ISO

"""Resolve um ATIVO (modelo oficial do cliente) para os objetos concretos do Unity Catalog
e reconstrói o breadcrumb — tudo navegando as relações, sem colunas denormalizadas.

`ativo_aisn.id_ativo_aisn` É a PK da combinação de origem; `cod_tipo_ativo` diz onde resolver:
  1=ICA (iniciativa_camada_ambiente) · 2=TABELA (tabela_aisn) ·
  3=SUBDOMINIO (subdominio_camada_ambiente) · 4=DOMINIO (dominio_camada_ambiente)
O alvo UC (catálogo/schema/tabela) vive SÓ em {GOV}.tabela_aisn, então toda resolução de
escopo passa por ela. Nomes de schema parametrizáveis (app/schemas.py).
"""
from app import db
from app import constants as C
from app.schemas import GOV, ACC  # noqa: F401  (ACC usado por chamadores via ativo em {ACC})


def objetos_do_ativo(ativo):
    """[{tipo, catalogo, schema, tabela}] — TABELA→1 TABLE; ICA/SUB/DOM→N SCHEMA (via tabela_aisn)."""
    tipo = str(ativo.get("cod_tipo_ativo") or "")
    aid = ativo.get("id_ativo_aisn")
    if not aid:
        return []

    if tipo == C.AT_TABELA:
        rows = db.query(
            f"""SELECT nome_catalogo, nome_schema, nome_tabela FROM {GOV}.tabela_aisn
                 WHERE id_tabela_aisn=%s AND bol_atual=true""", (aid,))
        return [{"tipo": "TABLE", "catalogo": r["nome_catalogo"], "schema": r["nome_schema"],
                 "tabela": r["nome_tabela"]} for r in rows]

    if tipo == C.AT_ICA:
        rows = db.query(
            f"""SELECT DISTINCT nome_catalogo, nome_schema FROM {GOV}.tabela_aisn
                 WHERE id_iniciativa_camada_ambiente=%s AND bol_atual=true""", (aid,))
    elif tipo == C.AT_SUBDOMINIO:
        rows = db.query(
            f"""SELECT DISTINCT t.nome_catalogo, t.nome_schema
                  FROM {GOV}.subdominio_camada_ambiente sca
                  JOIN {GOV}.iniciativa_aisn i ON i.id_subdominio_informacao=sca.id_subdominio_informacao
                  JOIN {GOV}.iniciativa_camada_ambiente ica ON ica.id_iniciativa_aisn=i.id_iniciativa_aisn
                       AND ica.id_camada_aisn=sca.id_camada_aisn AND ica.id_ambiente_aisn=sca.id_ambiente_aisn
                  JOIN {GOV}.tabela_aisn t ON t.id_iniciativa_camada_ambiente=ica.id_iniciativa_camada_ambiente
                 WHERE sca.id_subdominio_camada_ambiente=%s AND t.bol_atual=true""", (aid,))
    elif tipo == C.AT_DOMINIO:
        rows = db.query(
            f"""SELECT DISTINCT t.nome_catalogo, t.nome_schema
                  FROM {GOV}.dominio_camada_ambiente dca
                  JOIN {GOV}.subdominio_informacao s ON s.id_dominio_informacao=dca.id_dominio_informacao
                  JOIN {GOV}.iniciativa_aisn i ON i.id_subdominio_informacao=s.id_subdominio_informacao
                  JOIN {GOV}.iniciativa_camada_ambiente ica ON ica.id_iniciativa_aisn=i.id_iniciativa_aisn
                       AND ica.id_camada_aisn=dca.id_camada_aisn AND ica.id_ambiente_aisn=dca.id_ambiente_aisn
                  JOIN {GOV}.tabela_aisn t ON t.id_iniciativa_camada_ambiente=ica.id_iniciativa_camada_ambiente
                 WHERE dca.id_dominio_camada_ambiente=%s AND t.bol_atual=true""", (aid,))
    else:
        rows = []
    return [{"tipo": "SCHEMA", "catalogo": r["nome_catalogo"], "schema": r["nome_schema"],
             "tabela": None} for r in rows]


def rotulo_objeto(o):
    if o["tipo"] == "TABLE":
        return f'{o["catalogo"]}.{o["schema"]}.{o["tabela"]}'
    return f'{o["catalogo"]}.{o["schema"]}'


# =====================================================================
# Reconstrução polimórfica dos DETALHES (breadcrumb + tipo_label) em SQL.
# `alias` = alias da ativo_aisn ({ACC}) na query. Origens em {GOV}. Aliases internos ax*
# fixos, sem colisão com os aliases das queries. Usado UMA vez por query.
# =====================================================================
def ativo_join(alias="a"):
    a = alias
    return f"""
      LEFT JOIN {GOV}.iniciativa_camada_ambiente axi_ica
             ON {a}.cod_tipo_ativo='{C.AT_ICA}' AND axi_ica.id_iniciativa_camada_ambiente={a}.id_ativo_aisn AND axi_ica.bol_atual=true
      LEFT JOIN {GOV}.iniciativa_aisn axi_ini ON axi_ini.id_iniciativa_aisn=axi_ica.id_iniciativa_aisn
      LEFT JOIN {GOV}.subdominio_informacao axi_sub ON axi_sub.id_subdominio_informacao=axi_ini.id_subdominio_informacao
      LEFT JOIN {GOV}.dominio_informacao axi_dom ON axi_dom.id_dominio_informacao=axi_sub.id_dominio_informacao
      LEFT JOIN {GOV}.tabela_aisn axt_tab
             ON {a}.cod_tipo_ativo='{C.AT_TABELA}' AND axt_tab.id_tabela_aisn={a}.id_ativo_aisn AND axt_tab.bol_atual=true
      LEFT JOIN {GOV}.iniciativa_camada_ambiente axt_ica ON axt_ica.id_iniciativa_camada_ambiente=axt_tab.id_iniciativa_camada_ambiente
      LEFT JOIN {GOV}.iniciativa_aisn axt_ini ON axt_ini.id_iniciativa_aisn=axt_ica.id_iniciativa_aisn
      LEFT JOIN {GOV}.subdominio_informacao axt_sub ON axt_sub.id_subdominio_informacao=axt_ini.id_subdominio_informacao
      LEFT JOIN {GOV}.dominio_informacao axt_dom ON axt_dom.id_dominio_informacao=axt_sub.id_dominio_informacao
      LEFT JOIN {GOV}.subdominio_camada_ambiente axs_sca
             ON {a}.cod_tipo_ativo='{C.AT_SUBDOMINIO}' AND axs_sca.id_subdominio_camada_ambiente={a}.id_ativo_aisn AND axs_sca.bol_atual=true
      LEFT JOIN {GOV}.subdominio_informacao axs_sub ON axs_sub.id_subdominio_informacao=axs_sca.id_subdominio_informacao
      LEFT JOIN {GOV}.dominio_informacao axs_dom ON axs_dom.id_dominio_informacao=axs_sub.id_dominio_informacao
      LEFT JOIN {GOV}.dominio_camada_ambiente axd_dca
             ON {a}.cod_tipo_ativo='{C.AT_DOMINIO}' AND axd_dca.id_dominio_camada_ambiente={a}.id_ativo_aisn AND axd_dca.bol_atual=true
      LEFT JOIN {GOV}.dominio_informacao axd_dom ON axd_dom.id_dominio_informacao=axd_dca.id_dominio_informacao
    """


def ativo_cols(alias="a"):
    a = alias
    return f"""
      COALESCE(axi_dom.nome_dominio, axt_dom.nome_dominio, axs_dom.nome_dominio, axd_dom.nome_dominio) AS nome_dominio,
      COALESCE(axi_sub.nome_subdominio, axt_sub.nome_subdominio, axs_sub.nome_subdominio) AS nome_subdominio,
      COALESCE(axi_dom.id_dominio_informacao, axt_dom.id_dominio_informacao, axs_dom.id_dominio_informacao, axd_dom.id_dominio_informacao) AS id_dominio_informacao,
      COALESCE(axi_sub.id_subdominio_informacao, axt_sub.id_subdominio_informacao, axs_sub.id_subdominio_informacao) AS id_subdominio_informacao,
      CASE {a}.cod_tipo_ativo
           WHEN '{C.AT_ICA}' THEN '{C.TIPO_ATIVO_LABEL[C.AT_ICA]}'
           WHEN '{C.AT_TABELA}' THEN '{C.TIPO_ATIVO_LABEL[C.AT_TABELA]}'
           WHEN '{C.AT_SUBDOMINIO}' THEN '{C.TIPO_ATIVO_LABEL[C.AT_SUBDOMINIO]}'
           WHEN '{C.AT_DOMINIO}' THEN '{C.TIPO_ATIVO_LABEL[C.AT_DOMINIO]}'
           ELSE {a}.cod_tipo_ativo END AS tipo_label
    """


def dominio_id_expr():
    return ("COALESCE(axi_dom.id_dominio_informacao, axt_dom.id_dominio_informacao, "
            "axs_dom.id_dominio_informacao, axd_dom.id_dominio_informacao)")


def subdominio_id_expr():
    return ("COALESCE(axi_sub.id_subdominio_informacao, axt_sub.id_subdominio_informacao, "
            "axs_sub.id_subdominio_informacao)")

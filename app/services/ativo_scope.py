"""Resolve um ATIVO para os objetos concretos do Unity Catalog do grant e reconstrói
os detalhes de exibição — SEM colunas denormalizadas.

Modelo (definido pelo cliente): `ativo_aisn.id_ativo_aisn` É a PK da entidade de
origem; `cod_tipo_ativo` (código numérico) diz em qual tabela resolver:
  1=ICA (iniciativa_camada_ambiente) -> 1 schema
  2=TABELA (tabela_aisn)             -> 1 tabela
  3=SUBDOMINIO / 4=DOMINIO           -> N schemas (expande navegando as relações)

Catálogo/schema/tabela e o breadcrumb (domínio/subdomínio) são ALCANÇADOS navegando
os relacionamentos do modelo — nunca copiados para o ativo. Usado pelo catálogo
(exibir escopo), pelo provisionamento do grupo do ativo e pela auditoria.
"""
from app import db
from app import constants as C


def objetos_do_ativo(ativo):
    """Retorna [{tipo, catalogo, schema, tabela}] — tipo ∈ SCHEMA | TABLE.
    TABELA vira 1 objeto TABLE; ICA vira 1 SCHEMA; SUB/DOM expandem para N schemas."""
    tipo = str(ativo.get("cod_tipo_ativo") or "")
    aid = ativo.get("id_ativo_aisn")
    if not aid:
        return []

    if tipo == C.AT_TABELA:
        rows = db.query(
            """SELECT nome_catalogo, nome_schema, nome_tabela
                 FROM governanca.tabela_aisn
                WHERE id_tabela_aisn=%s AND bol_atual=true""", (aid,))
        return [{"tipo": "TABLE", "catalogo": r["nome_catalogo"], "schema": r["nome_schema"],
                 "tabela": r["nome_tabela"]} for r in rows]

    if tipo == C.AT_ICA:
        rows = db.query(
            """SELECT nome_catalogo, nome_schema
                 FROM governanca.iniciativa_camada_ambiente
                WHERE id_iniciativa_camada_ambiente=%s AND bol_atual=true
                  AND nome_schema IS NOT NULL""", (aid,))
    elif tipo == C.AT_SUBDOMINIO:
        rows = db.query(
            """SELECT DISTINCT ica.nome_catalogo, ica.nome_schema
                 FROM governanca.iniciativa_camada_ambiente ica
                 JOIN governanca.iniciativa_aisn i ON i.id_iniciativa_aisn=ica.id_iniciativa_aisn
                WHERE i.id_subdominio_informacao=%s AND ica.bol_atual=true
                  AND ica.nome_schema IS NOT NULL""", (aid,))
    elif tipo == C.AT_DOMINIO:
        rows = db.query(
            """SELECT DISTINCT ica.nome_catalogo, ica.nome_schema
                 FROM governanca.iniciativa_camada_ambiente ica
                 JOIN governanca.iniciativa_aisn i ON i.id_iniciativa_aisn=ica.id_iniciativa_aisn
                 JOIN governanca.subdominio_informacao s
                      ON s.id_subdominio_informacao=i.id_subdominio_informacao
                WHERE s.id_dominio_informacao=%s AND ica.bol_atual=true
                  AND ica.nome_schema IS NOT NULL""", (aid,))
    else:
        rows = []
    return [{"tipo": "SCHEMA", "catalogo": r["nome_catalogo"], "schema": r["nome_schema"],
             "tabela": None} for r in rows]


def rotulo_objeto(o):
    """Rótulo legível de um objeto UC resolvido."""
    if o["tipo"] == "TABLE":
        return f'{o["catalogo"]}.{o["schema"]}.{o["tabela"]}'
    return f'{o["catalogo"]}.{o["schema"]}'


# =====================================================================
# Reconstrução polimórfica dos DETALHES do ativo (breadcrumb + alvo UC)
# diretamente em SQL, para reaproveitar nas consultas dos serviços sem
# denormalizar. `alias` = alias da ativo_aisn na query. Os aliases internos
# (ax*_) são fixos e não colidem com os aliases usados pelas queries chamadoras
# (a, at, s, g, usol, ubenef, ac, p, ...). O bloco é usado UMA vez por query.
# =====================================================================
def ativo_join(alias="a"):
    a = alias
    return f"""
      LEFT JOIN governanca.iniciativa_camada_ambiente axi_ica
             ON {a}.cod_tipo_ativo='{C.AT_ICA}' AND axi_ica.id_iniciativa_camada_ambiente={a}.id_ativo_aisn
            AND axi_ica.bol_atual=true
      LEFT JOIN governanca.iniciativa_aisn axi_ini ON axi_ini.id_iniciativa_aisn=axi_ica.id_iniciativa_aisn
      LEFT JOIN governanca.subdominio_informacao axi_sub ON axi_sub.id_subdominio_informacao=axi_ini.id_subdominio_informacao
      LEFT JOIN governanca.dominio_informacao axi_dom ON axi_dom.id_dominio_informacao=axi_sub.id_dominio_informacao
      LEFT JOIN governanca.tabela_aisn axt_tab
             ON {a}.cod_tipo_ativo='{C.AT_TABELA}' AND axt_tab.id_tabela_aisn={a}.id_ativo_aisn
            AND axt_tab.bol_atual=true
      LEFT JOIN governanca.iniciativa_camada_ambiente axt_ica ON axt_ica.id_iniciativa_camada_ambiente=axt_tab.id_iniciativa_camada_ambiente
      LEFT JOIN governanca.iniciativa_aisn axt_ini ON axt_ini.id_iniciativa_aisn=axt_ica.id_iniciativa_aisn
      LEFT JOIN governanca.subdominio_informacao axt_sub ON axt_sub.id_subdominio_informacao=axt_ini.id_subdominio_informacao
      LEFT JOIN governanca.dominio_informacao axt_dom ON axt_dom.id_dominio_informacao=axt_sub.id_dominio_informacao
      LEFT JOIN governanca.subdominio_informacao axs_sub
             ON {a}.cod_tipo_ativo='{C.AT_SUBDOMINIO}' AND axs_sub.id_subdominio_informacao={a}.id_ativo_aisn
            AND axs_sub.bol_atual=true
      LEFT JOIN governanca.dominio_informacao axs_dom ON axs_dom.id_dominio_informacao=axs_sub.id_dominio_informacao
      LEFT JOIN governanca.dominio_informacao axd_dom
             ON {a}.cod_tipo_ativo='{C.AT_DOMINIO}' AND axd_dom.id_dominio_informacao={a}.id_ativo_aisn
            AND axd_dom.bol_atual=true
    """


def ativo_cols(alias="a"):
    """Colunas DERIVADAS com os MESMOS aliases das antigas colunas denormalizadas,
    para os templates continuarem intactos."""
    a = alias
    return f"""
      COALESCE(axi_dom.nome_dominio, axt_dom.nome_dominio, axs_dom.nome_dominio, axd_dom.nome_dominio) AS nome_dominio,
      COALESCE(axi_sub.nome_subdominio, axt_sub.nome_subdominio, axs_sub.nome_subdominio) AS nome_subdominio,
      COALESCE(axi_ica.nome_catalogo, axt_tab.nome_catalogo) AS nome_catalogo,
      COALESCE(axi_ica.nome_schema, axt_tab.nome_schema) AS nome_schema,
      axt_tab.nome_tabela AS nome_tabela,
      CASE {a}.cod_tipo_ativo
           WHEN '{C.AT_ICA}' THEN '{C.TIPO_ATIVO_LABEL[C.AT_ICA]}'
           WHEN '{C.AT_TABELA}' THEN '{C.TIPO_ATIVO_LABEL[C.AT_TABELA]}'
           WHEN '{C.AT_SUBDOMINIO}' THEN '{C.TIPO_ATIVO_LABEL[C.AT_SUBDOMINIO]}'
           WHEN '{C.AT_DOMINIO}' THEN '{C.TIPO_ATIVO_LABEL[C.AT_DOMINIO]}'
           ELSE {a}.cod_tipo_ativo END AS tipo_label
    """


def dominio_id_expr():
    """Expressão do id de domínio derivado — para usar em WHERE/ORDER."""
    return ("COALESCE(axi_dom.id_dominio_informacao, axt_dom.id_dominio_informacao, "
            "axs_dom.id_dominio_informacao, axd_dom.id_dominio_informacao)")


def subdominio_id_expr():
    return ("COALESCE(axi_sub.id_subdominio_informacao, axt_sub.id_subdominio_informacao, "
            "axs_sub.id_subdominio_informacao)")

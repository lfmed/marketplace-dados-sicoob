"""Resolve um ATIVO (modelo oficial do cliente) para os objetos concretos do Unity Catalog
e reconstrói o breadcrumb — tudo navegando as relações, sem colunas denormalizadas.

`ativo_aisn.id_ativo_aisn` É a PK da combinação de origem; `cod_tipo_ativo` diz onde resolver:
  1=ICA (iniciativa_camada_ambiente) · 2=TABELA (tabela_aisn) ·
  3=SUBDOMINIO (subdominio_camada_ambiente) · 4=DOMINIO (dominio_camada_ambiente)
O alvo UC (catálogo/schema/tabela) vive SÓ em {GOV}.tabela_aisn, então toda resolução de
escopo passa por ela. Nomes de schema parametrizáveis (app/schemas.py).

Toda leitura de tabela de {GOV}/{ACC} (mirrors synced do Motor) filtra por `bol_atual=true`
E `bol_excluido=false` (SCD2 do Motor) — só linhas vigentes e não excluídas. Use `_cur()`.
"""
from app import db
from app import constants as C
from app.schemas import GOV, ACC  # noqa: F401  (ACC usado por chamadores via ativo em {ACC})


def _cur(alias=""):
    """Filtro SCD2 padrão do Motor: só linhas vigentes e não excluídas.
    `alias`='' => colunas sem prefixo (tabela sem alias na query)."""
    p = f"{alias}." if alias else ""
    return f"{p}bol_atual=true AND {p}bol_excluido=false"


def objetos_do_ativo(ativo):
    """[{tipo, catalogo, schema, tabela}] — TABELA→1 TABLE; ICA/SUB/DOM→N SCHEMA (via tabela_aisn)."""
    tipo = str(ativo.get("cod_tipo_ativo") or "")
    aid = ativo.get("id_ativo_aisn")
    if not aid:
        return []

    if tipo == C.AT_TABELA:
        rows = db.query(
            f"""SELECT nome_catalogo, nome_schema, nome_tabela FROM {GOV}.tabela_aisn
                 WHERE id_tabela_aisn=%s AND {_cur()}""", (aid,))
        return [{"tipo": "TABLE", "catalogo": r["nome_catalogo"], "schema": r["nome_schema"],
                 "tabela": r["nome_tabela"]} for r in rows]

    if tipo == C.AT_ICA:
        rows = db.query(
            f"""SELECT DISTINCT nome_catalogo, nome_schema FROM {GOV}.tabela_aisn
                 WHERE id_iniciativa_camada_ambiente=%s AND {_cur()}""", (aid,))
    elif tipo == C.AT_SUBDOMINIO:
        rows = db.query(
            f"""SELECT DISTINCT t.nome_catalogo, t.nome_schema
                  FROM {GOV}.subdominio_camada_ambiente sca
                  JOIN {GOV}.iniciativa_aisn i ON i.id_subdominio_informacao=sca.id_subdominio_informacao
                  JOIN {GOV}.iniciativa_camada_ambiente ica ON ica.id_iniciativa_aisn=i.id_iniciativa_aisn
                       AND ica.id_camada_aisn=sca.id_camada_aisn AND ica.id_ambiente_aisn=sca.id_ambiente_aisn
                  JOIN {GOV}.tabela_aisn t ON t.id_iniciativa_camada_ambiente=ica.id_iniciativa_camada_ambiente
                 WHERE sca.id_subdominio_camada_ambiente=%s
                   AND {_cur('sca')} AND {_cur('i')} AND {_cur('ica')} AND {_cur('t')}""", (aid,))
    elif tipo == C.AT_DOMINIO:
        rows = db.query(
            f"""SELECT DISTINCT t.nome_catalogo, t.nome_schema
                  FROM {GOV}.dominio_camada_ambiente dca
                  JOIN {GOV}.subdominio_informacao s ON s.id_dominio_informacao=dca.id_dominio_informacao
                  JOIN {GOV}.iniciativa_aisn i ON i.id_subdominio_informacao=s.id_subdominio_informacao
                  JOIN {GOV}.iniciativa_camada_ambiente ica ON ica.id_iniciativa_aisn=i.id_iniciativa_aisn
                       AND ica.id_camada_aisn=dca.id_camada_aisn AND ica.id_ambiente_aisn=dca.id_ambiente_aisn
                  JOIN {GOV}.tabela_aisn t ON t.id_iniciativa_camada_ambiente=ica.id_iniciativa_camada_ambiente
                 WHERE dca.id_dominio_camada_ambiente=%s
                   AND {_cur('dca')} AND {_cur('s')} AND {_cur('i')} AND {_cur('ica')} AND {_cur('t')}""", (aid,))
    else:
        rows = []
    return [{"tipo": "SCHEMA", "catalogo": r["nome_catalogo"], "schema": r["nome_schema"],
             "tabela": None} for r in rows]


def tabelas_do_ativo(ativo):
    """Tabelas concretas contidas no ativo, com nome e DESCRIÇÃO (feedback do cliente:
    apresentar todas as tabelas do ativo ao solicitar). Sempre resolve em {GOV}.tabela_aisn."""
    tipo = str(ativo.get("cod_tipo_ativo") or "")
    aid = ativo.get("id_ativo_aisn")
    if not aid:
        return []
    if tipo == C.AT_TABELA:
        return db.query(
            f"""SELECT nome_catalogo, nome_schema, nome_tabela, desc_tabela
                  FROM {GOV}.tabela_aisn WHERE id_tabela_aisn=%s AND {_cur()}""", (aid,))
    if tipo == C.AT_ICA:
        return db.query(
            f"""SELECT nome_catalogo, nome_schema, nome_tabela, desc_tabela
                  FROM {GOV}.tabela_aisn WHERE id_iniciativa_camada_ambiente=%s AND {_cur()}
                 ORDER BY nome_tabela""", (aid,))
    if tipo == C.AT_SUBDOMINIO:
        return db.query(
            f"""SELECT DISTINCT t.nome_catalogo, t.nome_schema, t.nome_tabela, t.desc_tabela
                  FROM {GOV}.subdominio_camada_ambiente sca
                  JOIN {GOV}.iniciativa_aisn i ON i.id_subdominio_informacao=sca.id_subdominio_informacao
                  JOIN {GOV}.iniciativa_camada_ambiente ica ON ica.id_iniciativa_aisn=i.id_iniciativa_aisn
                       AND ica.id_camada_aisn=sca.id_camada_aisn AND ica.id_ambiente_aisn=sca.id_ambiente_aisn
                  JOIN {GOV}.tabela_aisn t ON t.id_iniciativa_camada_ambiente=ica.id_iniciativa_camada_ambiente
                 WHERE sca.id_subdominio_camada_ambiente=%s
                   AND {_cur('sca')} AND {_cur('i')} AND {_cur('ica')} AND {_cur('t')}
                 ORDER BY t.nome_tabela""", (aid,))
    if tipo == C.AT_DOMINIO:
        return db.query(
            f"""SELECT DISTINCT t.nome_catalogo, t.nome_schema, t.nome_tabela, t.desc_tabela
                  FROM {GOV}.dominio_camada_ambiente dca
                  JOIN {GOV}.subdominio_informacao s ON s.id_dominio_informacao=dca.id_dominio_informacao
                  JOIN {GOV}.iniciativa_aisn i ON i.id_subdominio_informacao=s.id_subdominio_informacao
                  JOIN {GOV}.iniciativa_camada_ambiente ica ON ica.id_iniciativa_aisn=i.id_iniciativa_aisn
                       AND ica.id_camada_aisn=dca.id_camada_aisn AND ica.id_ambiente_aisn=dca.id_ambiente_aisn
                  JOIN {GOV}.tabela_aisn t ON t.id_iniciativa_camada_ambiente=ica.id_iniciativa_camada_ambiente
                 WHERE dca.id_dominio_camada_ambiente=%s
                   AND {_cur('dca')} AND {_cur('s')} AND {_cur('i')} AND {_cur('ica')} AND {_cur('t')}
                 ORDER BY t.nome_tabela""", (aid,))
    return []


def rotulo_objeto(o):
    if o["tipo"] == "TABLE":
        return f'{o["catalogo"]}.{o["schema"]}.{o["tabela"]}'
    return f'{o["catalogo"]}.{o["schema"]}'


# =====================================================================
# Reconstrução polimórfica dos DETALHES (breadcrumb + tipo_label) em SQL.
# `alias` = alias da ativo_aisn ({ACC}) na query. Origens em {GOV}. Aliases internos ax*
# fixos, sem colisão com os aliases das queries. Usado UMA vez por query. Todo LEFT JOIN
# filtra bol_atual/bol_excluido na ON (mantém a linha-driver quando não há match vigente).
# =====================================================================
def ativo_join(alias="a"):
    a = alias
    return f"""
      LEFT JOIN {GOV}.iniciativa_camada_ambiente axi_ica
             ON {a}.cod_tipo_ativo='{C.AT_ICA}' AND axi_ica.id_iniciativa_camada_ambiente={a}.id_ativo_aisn AND {_cur('axi_ica')}
      LEFT JOIN {GOV}.iniciativa_aisn axi_ini ON axi_ini.id_iniciativa_aisn=axi_ica.id_iniciativa_aisn AND {_cur('axi_ini')}
      LEFT JOIN {GOV}.subdominio_informacao axi_sub ON axi_sub.id_subdominio_informacao=axi_ini.id_subdominio_informacao AND {_cur('axi_sub')}
      LEFT JOIN {GOV}.dominio_informacao axi_dom ON axi_dom.id_dominio_informacao=axi_sub.id_dominio_informacao AND {_cur('axi_dom')}
      LEFT JOIN {GOV}.tabela_aisn axt_tab
             ON {a}.cod_tipo_ativo='{C.AT_TABELA}' AND axt_tab.id_tabela_aisn={a}.id_ativo_aisn AND {_cur('axt_tab')}
      LEFT JOIN {GOV}.iniciativa_camada_ambiente axt_ica ON axt_ica.id_iniciativa_camada_ambiente=axt_tab.id_iniciativa_camada_ambiente AND {_cur('axt_ica')}
      LEFT JOIN {GOV}.iniciativa_aisn axt_ini ON axt_ini.id_iniciativa_aisn=axt_ica.id_iniciativa_aisn AND {_cur('axt_ini')}
      LEFT JOIN {GOV}.subdominio_informacao axt_sub ON axt_sub.id_subdominio_informacao=axt_ini.id_subdominio_informacao AND {_cur('axt_sub')}
      LEFT JOIN {GOV}.dominio_informacao axt_dom ON axt_dom.id_dominio_informacao=axt_sub.id_dominio_informacao AND {_cur('axt_dom')}
      LEFT JOIN {GOV}.subdominio_camada_ambiente axs_sca
             ON {a}.cod_tipo_ativo='{C.AT_SUBDOMINIO}' AND axs_sca.id_subdominio_camada_ambiente={a}.id_ativo_aisn AND {_cur('axs_sca')}
      LEFT JOIN {GOV}.subdominio_informacao axs_sub ON axs_sub.id_subdominio_informacao=axs_sca.id_subdominio_informacao AND {_cur('axs_sub')}
      LEFT JOIN {GOV}.dominio_informacao axs_dom ON axs_dom.id_dominio_informacao=axs_sub.id_dominio_informacao AND {_cur('axs_dom')}
      LEFT JOIN {GOV}.dominio_camada_ambiente axd_dca
             ON {a}.cod_tipo_ativo='{C.AT_DOMINIO}' AND axd_dca.id_dominio_camada_ambiente={a}.id_ativo_aisn AND {_cur('axd_dca')}
      LEFT JOIN {GOV}.dominio_informacao axd_dom ON axd_dom.id_dominio_informacao=axd_dca.id_dominio_informacao AND {_cur('axd_dom')}
      -- camada/ambiente por tipo (feedback do cliente: exibir camada e ambiente com nome)
      LEFT JOIN {GOV}.camada_aisn   axi_cam ON axi_cam.id_camada_aisn=axi_ica.id_camada_aisn AND {_cur('axi_cam')}
      LEFT JOIN {GOV}.ambiente_aisn axi_amb ON axi_amb.id_ambiente_aisn=axi_ica.id_ambiente_aisn AND {_cur('axi_amb')}
      LEFT JOIN {GOV}.camada_aisn   axt_cam ON axt_cam.id_camada_aisn=axt_ica.id_camada_aisn AND {_cur('axt_cam')}
      LEFT JOIN {GOV}.ambiente_aisn axt_amb ON axt_amb.id_ambiente_aisn=axt_ica.id_ambiente_aisn AND {_cur('axt_amb')}
      LEFT JOIN {GOV}.camada_aisn   axs_cam ON axs_cam.id_camada_aisn=axs_sca.id_camada_aisn AND {_cur('axs_cam')}
      LEFT JOIN {GOV}.ambiente_aisn axs_amb ON axs_amb.id_ambiente_aisn=axs_sca.id_ambiente_aisn AND {_cur('axs_amb')}
      LEFT JOIN {GOV}.camada_aisn   axd_cam ON axd_cam.id_camada_aisn=axd_dca.id_camada_aisn AND {_cur('axd_cam')}
      LEFT JOIN {GOV}.ambiente_aisn axd_amb ON axd_amb.id_ambiente_aisn=axd_dca.id_ambiente_aisn AND {_cur('axd_amb')}
    """


def ativo_cols(alias="a"):
    a = alias
    return f"""
      COALESCE(axi_dom.nome_dominio, axt_dom.nome_dominio, axs_dom.nome_dominio, axd_dom.nome_dominio) AS nome_dominio,
      COALESCE(axi_sub.nome_subdominio, axt_sub.nome_subdominio, axs_sub.nome_subdominio) AS nome_subdominio,
      COALESCE(axi_dom.id_dominio_informacao, axt_dom.id_dominio_informacao, axs_dom.id_dominio_informacao, axd_dom.id_dominio_informacao) AS id_dominio_informacao,
      COALESCE(axi_sub.id_subdominio_informacao, axt_sub.id_subdominio_informacao, axs_sub.id_subdominio_informacao) AS id_subdominio_informacao,
      COALESCE(axi_ini.nome_iniciativa, axt_ini.nome_iniciativa) AS nome_iniciativa,
      COALESCE(axi_cam.nome_camada, axt_cam.nome_camada, axs_cam.nome_camada, axd_cam.nome_camada) AS nome_camada,
      COALESCE(axi_amb.nome_ambiente, axt_amb.nome_ambiente, axs_amb.nome_ambiente, axd_amb.nome_ambiente) AS nome_ambiente,
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

"""Resolve um ATIVO para os objetos concretos do Unity Catalog do grant, por nível.
Substitui a RN-003 (que era só schema): agora o acesso é no nível do ativo —
DOMINIO/SUBDOMINIO expandem para o conjunto de schemas; INICIATIVA → schema(s);
TABELA → tabela específica. Usado pelo catálogo (exibir escopo) e pelo grant_executor.
"""
from app import db


def objetos_do_ativo(ativo):
    """Retorna [{tipo, catalogo, schema, tabela}] — tipo ∈ SCHEMA | TABLE.
    Um ativo de tabela vira 1 objeto TABLE; níveis maiores expandem para os schemas."""
    tipo = ativo.get("cod_tipo_ativo")
    ref = ativo.get("id_referencia")
    if tipo == "TABELA":
        return [{"tipo": "TABLE", "catalogo": ativo.get("nome_catalogo"),
                 "schema": ativo.get("nome_schema"), "tabela": ativo.get("nome_tabela")}]
    if tipo == "INICIATIVA":
        rows = db.query(
            """SELECT DISTINCT nome_catalogo, nome_schema
                 FROM governanca.iniciativa_camada_ambiente
                WHERE id_iniciativa_aisn=%s AND bol_atual=true AND nome_schema IS NOT NULL""",
            (ref,))
    elif tipo == "SUBDOMINIO":
        rows = db.query(
            """SELECT DISTINCT ica.nome_catalogo, ica.nome_schema
                 FROM governanca.iniciativa_camada_ambiente ica
                 JOIN governanca.iniciativa_aisn i ON i.id_iniciativa_aisn=ica.id_iniciativa_aisn
                WHERE i.id_subdominio_informacao=%s AND ica.bol_atual=true AND ica.nome_schema IS NOT NULL""",
            (ref,))
    elif tipo == "DOMINIO":
        rows = db.query(
            """SELECT DISTINCT ica.nome_catalogo, ica.nome_schema
                 FROM governanca.iniciativa_camada_ambiente ica
                 JOIN governanca.iniciativa_aisn i ON i.id_iniciativa_aisn=ica.id_iniciativa_aisn
                 JOIN governanca.subdominio_informacao s ON s.id_subdominio_informacao=i.id_subdominio_informacao
                WHERE s.id_dominio_informacao=%s AND ica.bol_atual=true AND ica.nome_schema IS NOT NULL""",
            (ref,))
    else:
        rows = []
    return [{"tipo": "SCHEMA", "catalogo": r["nome_catalogo"], "schema": r["nome_schema"],
             "tabela": None} for r in rows]


def rotulo_objeto(o):
    """Rótulo legível de um objeto UC resolvido."""
    if o["tipo"] == "TABLE":
        return f'{o["catalogo"]}.{o["schema"]}.{o["tabela"]}'
    return f'{o["catalogo"]}.{o["schema"]}'

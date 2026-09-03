"""Catálogo de produtos de dados (RF-006/007). Só expõe iniciativas COM owner (RN-005)."""
from app import db


def listar_dominios():
    return db.query(
        "SELECT id_dominio_informacao, nome_dominio FROM governanca.dominio_informacao "
        "WHERE bol_atual=true AND bol_excluido=false ORDER BY nome_dominio"
    )


def listar_subdominios(id_dominio=None):
    if id_dominio:
        return db.query(
            "SELECT id_subdominio_informacao, id_dominio_informacao, nome_subdominio "
            "FROM governanca.subdominio_informacao WHERE bol_atual=true AND id_dominio_informacao=%s "
            "ORDER BY nome_subdominio", (id_dominio,))
    return db.query(
        "SELECT id_subdominio_informacao, id_dominio_informacao, nome_subdominio "
        "FROM governanca.subdominio_informacao WHERE bol_atual=true ORDER BY nome_subdominio")


def listar_iniciativas(id_dominio=None, id_subdominio=None, busca=None):
    """Cards do catálogo: iniciativa + domínio/subdomínio + owner + nº de tabelas.
    Apenas iniciativas que possuem owner (RN-005)."""
    where = ["i.bol_atual=true", "i.bol_excluido=false",
             "EXISTS (SELECT 1 FROM governanca.iniciativa_proprietario p "
             "        WHERE p.id_iniciativa_aisn=i.id_iniciativa_aisn AND p.bol_atual=true)"]
    params = []
    if id_dominio:
        where.append("d.id_dominio_informacao=%s"); params.append(id_dominio)
    if id_subdominio:
        where.append("s.id_subdominio_informacao=%s"); params.append(id_subdominio)
    if busca:
        where.append("(lower(i.nome_iniciativa) LIKE %s OR lower(i.desc_iniciativa) LIKE %s)")
        b = f"%{busca.lower()}%"; params += [b, b]
    sql = f"""
        SELECT i.id_iniciativa_aisn, i.nome_iniciativa, i.desc_iniciativa,
               s.id_subdominio_informacao, s.nome_subdominio,
               d.id_dominio_informacao, d.nome_dominio,
               (SELECT string_agg(DISTINCT u.nome_completo, ', ')
                  FROM governanca.iniciativa_proprietario p
                  JOIN governanca.usuario_aisn u ON u.id_usuario_aisn=p.id_usuario_aisn
                 WHERE p.id_iniciativa_aisn=i.id_iniciativa_aisn AND p.bol_atual=true) AS owners,
               (SELECT count(*) FROM governanca.tabela_aisn t
                  JOIN governanca.iniciativa_camada_ambiente ica
                       ON ica.id_iniciativa_camada_ambiente=t.id_iniciativa_camada_ambiente
                 WHERE ica.id_iniciativa_aisn=i.id_iniciativa_aisn AND t.bol_atual=true) AS num_tabelas
          FROM governanca.iniciativa_aisn i
          JOIN governanca.subdominio_informacao s ON s.id_subdominio_informacao=i.id_subdominio_informacao
          JOIN governanca.dominio_informacao d ON d.id_dominio_informacao=s.id_dominio_informacao
         WHERE {' AND '.join(where)}
         ORDER BY d.nome_dominio, s.nome_subdominio, i.nome_iniciativa
    """
    return db.query(sql, params)


def detalhe_iniciativa(id_iniciativa):
    ini = db.query_one("""
        SELECT i.*, s.nome_subdominio, s.id_subdominio_informacao,
               d.nome_dominio, d.id_dominio_informacao
          FROM governanca.iniciativa_aisn i
          JOIN governanca.subdominio_informacao s ON s.id_subdominio_informacao=i.id_subdominio_informacao
          JOIN governanca.dominio_informacao d ON d.id_dominio_informacao=s.id_dominio_informacao
         WHERE i.id_iniciativa_aisn=%s""", (id_iniciativa,))
    if not ini:
        return None
    ini["owners"] = db.query("""
        SELECT u.id_usuario_aisn, u.nome_completo, u.desc_email, p.bol_principal
          FROM governanca.iniciativa_proprietario p
          JOIN governanca.usuario_aisn u ON u.id_usuario_aisn=p.id_usuario_aisn
         WHERE p.id_iniciativa_aisn=%s AND p.bol_atual=true
         ORDER BY p.bol_principal DESC, u.nome_completo""", (id_iniciativa,))
    # Unidades funcionais (camada+ambiente) elegíveis (RN-003: acesso por iniciativa+camada)
    ini["unidades"] = db.query("""
        SELECT ica.id_iniciativa_camada_ambiente, ica.bol_elegivel_acesso,
               ica.nome_catalogo, ica.nome_schema,
               c.id_camada_aisn, c.nome_camada, a.id_ambiente_aisn, a.nome_ambiente,
               (SELECT count(*) FROM governanca.tabela_aisn t
                 WHERE t.id_iniciativa_camada_ambiente=ica.id_iniciativa_camada_ambiente
                   AND t.bol_atual=true) AS num_tabelas
          FROM governanca.iniciativa_camada_ambiente ica
          JOIN governanca.camada_aisn c ON c.id_camada_aisn=ica.id_camada_aisn
          JOIN governanca.ambiente_aisn a ON a.id_ambiente_aisn=ica.id_ambiente_aisn
         WHERE ica.id_iniciativa_aisn=%s AND ica.bol_atual=true
         ORDER BY a.nome_ambiente, c.nome_camada""", (id_iniciativa,))
    # Tabelas elegíveis (para exibir o escopo do acesso)
    ini["tabelas"] = db.query("""
        SELECT t.nome_catalogo, t.nome_schema, t.nome_tabela, t.desc_tabela,
               c.nome_camada, a.nome_ambiente
          FROM governanca.tabela_aisn t
          JOIN governanca.iniciativa_camada_ambiente ica
               ON ica.id_iniciativa_camada_ambiente=t.id_iniciativa_camada_ambiente
          JOIN governanca.camada_aisn c ON c.id_camada_aisn=ica.id_camada_aisn
          JOIN governanca.ambiente_aisn a ON a.id_ambiente_aisn=ica.id_ambiente_aisn
         WHERE ica.id_iniciativa_aisn=%s AND t.bol_atual=true
         ORDER BY c.nome_camada, t.nome_tabela""", (id_iniciativa,))
    return ini


def contar_iniciativas(**kwargs):
    return len(listar_iniciativas(**kwargs))

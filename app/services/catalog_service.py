"""Catálogo de produtos de dados — agora ATIVO-cêntrico (RF-006/007).
O ativo é a unidade liberável (qualquer nível: domínio/subdomínio/iniciativa/tabela),
derivado da governança, com owner próprio e grupo. Só expõe ativos elegíveis e com owner."""
from app import db
from app.services.ativo_scope import objetos_do_ativo, rotulo_objeto

TIPOS_ATIVO = ["DOMINIO", "SUBDOMINIO", "INICIATIVA", "TABELA"]
TIPO_LABEL = {"DOMINIO": "Domínio", "SUBDOMINIO": "Subdomínio",
              "INICIATIVA": "Iniciativa", "TABELA": "Tabela"}


def listar_dominios():
    return db.query(
        "SELECT id_dominio_informacao, nome_dominio FROM governanca.dominio_informacao "
        "WHERE bol_atual=true AND bol_excluido=false ORDER BY nome_dominio")


def listar_subdominios(id_dominio=None):
    if id_dominio:
        return db.query(
            "SELECT id_subdominio_informacao, id_dominio_informacao, nome_subdominio "
            "FROM governanca.subdominio_informacao WHERE bol_atual=true AND id_dominio_informacao=%s "
            "ORDER BY nome_subdominio", (id_dominio,))
    return db.query(
        "SELECT id_subdominio_informacao, id_dominio_informacao, nome_subdominio "
        "FROM governanca.subdominio_informacao WHERE bol_atual=true ORDER BY nome_subdominio")


def listar_ativos(id_dominio=None, id_subdominio=None, tipo=None, busca=None):
    """Cards do catálogo = ativos. Apenas com owner (RN-005) e elegíveis."""
    where = ["a.bol_atual=true", "a.bol_excluido=false", "a.bol_elegivel_acesso=true",
             "EXISTS (SELECT 1 FROM governanca.ativo_proprietario p "
             "        WHERE p.id_ativo_aisn=a.id_ativo_aisn AND p.bol_atual=true)"]
    params = []
    if id_dominio:
        where.append("a.nome_dominio=(SELECT nome_dominio FROM governanca.dominio_informacao "
                     "WHERE id_dominio_informacao=%s)"); params.append(id_dominio)
    if id_subdominio:
        where.append("a.nome_subdominio=(SELECT nome_subdominio FROM governanca.subdominio_informacao "
                     "WHERE id_subdominio_informacao=%s)"); params.append(id_subdominio)
    if tipo:
        where.append("a.cod_tipo_ativo=%s"); params.append(tipo)
    if busca:
        where.append("(lower(a.nome_ativo) LIKE %s OR lower(a.desc_ativo) LIKE %s)")
        b = f"%{busca.lower()}%"; params += [b, b]
    sql = f"""
        SELECT a.id_ativo_aisn, a.cod_tipo_ativo, a.id_referencia, a.nome_ativo, a.desc_ativo,
               a.nome_dominio, a.nome_subdominio, a.nome_catalogo, a.nome_schema, a.nome_tabela,
               g.nome_grupo,
               (SELECT string_agg(DISTINCT u.nome_completo, ', ')
                  FROM governanca.ativo_proprietario p
                  JOIN governanca.usuario_aisn u ON u.id_usuario_aisn=p.id_usuario_aisn
                 WHERE p.id_ativo_aisn=a.id_ativo_aisn AND p.bol_atual=true) AS owners
          FROM governanca.ativo_aisn a
          LEFT JOIN governanca.grupo_acesso g ON g.id_grupo_acesso=a.id_grupo_acesso
         WHERE {' AND '.join(where)}
         ORDER BY CASE a.cod_tipo_ativo WHEN 'DOMINIO' THEN 0 WHEN 'SUBDOMINIO' THEN 1
                       WHEN 'INICIATIVA' THEN 2 ELSE 3 END,
                  a.nome_dominio, a.nome_subdominio, a.nome_ativo
    """
    return db.query(sql, params)


def ativo_por_id(id_ativo):
    return db.query_one(
        """SELECT a.*, g.nome_grupo
             FROM governanca.ativo_aisn a
             LEFT JOIN governanca.grupo_acesso g ON g.id_grupo_acesso=a.id_grupo_acesso
            WHERE a.id_ativo_aisn=%s""", (id_ativo,))


def detalhe_ativo(id_ativo):
    a = ativo_por_id(id_ativo)
    if not a:
        return None
    a["tipo_label"] = TIPO_LABEL.get(a["cod_tipo_ativo"], a["cod_tipo_ativo"])
    a["owners"] = db.query(
        """SELECT u.id_usuario_aisn, u.nome_completo, u.desc_email, p.bol_principal
             FROM governanca.ativo_proprietario p
             JOIN governanca.usuario_aisn u ON u.id_usuario_aisn=p.id_usuario_aisn
            WHERE p.id_ativo_aisn=%s AND p.bol_atual=true
            ORDER BY p.bol_principal DESC, u.nome_completo""", (id_ativo,))
    # Escopo UC concreto (o que será concedido no grant), resolvido pelo nível
    objs = objetos_do_ativo(a)
    for o in objs:
        o["rotulo"] = rotulo_objeto(o)
    a["objetos"] = objs
    return a


def contar_ativos(**kwargs):
    return len(listar_ativos(**kwargs))

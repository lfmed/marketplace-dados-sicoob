"""Catálogo de produtos de dados — ATIVO-cêntrico (RF-006/007).
O ATIVO (`ativo_aisn`) é o driver da vitrine: é a unidade liberável em qualquer nível
(domínio/subdomínio/ICA/tabela). Os DETALHES (breadcrumb + alvo UC) são resolvidos
navegando as relações do modelo (ver ativo_scope), não colunas denormalizadas.
Só expõe ativos elegíveis e com owner (RN-005)."""
from app import db
from app import constants as C
from app.services import ativo_scope
from app.services.ativo_scope import objetos_do_ativo, rotulo_objeto

TIPOS_ATIVO = C.TIPOS_ATIVO          # códigos numéricos, na ordem de exibição
TIPO_LABEL = C.TIPO_ATIVO_LABEL      # código -> rótulo


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
    """Cards do catálogo = ativos. Apenas com owner (RN-005) e elegíveis.
    Breadcrumb (domínio/subdomínio) derivado polimorficamente das relações."""
    where = ["a.bol_atual=true", "a.bol_excluido=false", "a.bol_elegivel_acesso=true",
             "EXISTS (SELECT 1 FROM governanca.ativo_proprietario p "
             "        WHERE p.id_ativo_aisn=a.id_ativo_aisn AND p.bol_atual=true)"]
    params = []
    if id_dominio:
        where.append(f"{ativo_scope.dominio_id_expr()}=%s"); params.append(id_dominio)
    if id_subdominio:
        where.append(f"{ativo_scope.subdominio_id_expr()}=%s"); params.append(id_subdominio)
    if tipo:
        where.append("a.cod_tipo_ativo=%s"); params.append(tipo)
    if busca:
        where.append("(lower(a.nome_ativo) LIKE %s OR lower(a.desc_ativo) LIKE %s)")
        b = f"%{busca.lower()}%"; params += [b, b]
    sql = f"""
        SELECT a.id_ativo_aisn, a.cod_tipo_ativo, a.nome_ativo, a.desc_ativo,
               {ativo_scope.ativo_cols("a")}, g.nome_grupo,
               (SELECT string_agg(DISTINCT u.nome_completo, ', ')
                  FROM governanca.ativo_proprietario p
                  JOIN governanca.usuario_aisn u ON u.id_usuario_aisn=p.id_usuario_aisn
                 WHERE p.id_ativo_aisn=a.id_ativo_aisn AND p.bol_atual=true) AS owners
          FROM governanca.ativo_aisn a
          {ativo_scope.ativo_join("a")}
          LEFT JOIN governanca.grupo_acesso g ON g.id_grupo_acesso=a.id_grupo_acesso
         WHERE {' AND '.join(where)}
         ORDER BY CASE a.cod_tipo_ativo WHEN '{C.AT_DOMINIO}' THEN 0 WHEN '{C.AT_SUBDOMINIO}' THEN 1
                       WHEN '{C.AT_ICA}' THEN 2 ELSE 3 END,
                  nome_dominio, nome_subdominio, a.nome_ativo
    """
    return db.query(sql, params)


def ativo_por_id(id_ativo):
    return db.query_one(
        f"""SELECT a.*, {ativo_scope.ativo_cols("a")}, g.nome_grupo
             FROM governanca.ativo_aisn a
             {ativo_scope.ativo_join("a")}
             LEFT JOIN governanca.grupo_acesso g ON g.id_grupo_acesso=a.id_grupo_acesso
            WHERE a.id_ativo_aisn=%s""", (id_ativo,))


def detalhe_ativo(id_ativo):
    a = ativo_por_id(id_ativo)
    if not a:
        return None
    a["tipo_label"] = TIPO_LABEL.get(a["cod_tipo_ativo"], a.get("tipo_label") or a["cod_tipo_ativo"])
    a["owners"] = db.query(
        """SELECT u.id_usuario_aisn, u.nome_completo, u.desc_email, p.bol_principal
             FROM governanca.ativo_proprietario p
             JOIN governanca.usuario_aisn u ON u.id_usuario_aisn=p.id_usuario_aisn
            WHERE p.id_ativo_aisn=%s AND p.bol_atual=true
            ORDER BY p.bol_principal DESC, u.nome_completo""", (id_ativo,))
    # Escopo UC concreto (o que o GRUPO DO ATIVO detém), resolvido pelo nível
    objs = objetos_do_ativo(a)
    for o in objs:
        o["rotulo"] = rotulo_objeto(o)
    a["objetos"] = objs
    return a


def contar_ativos(**kwargs):
    return len(listar_ativos(**kwargs))

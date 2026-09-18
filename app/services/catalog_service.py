"""Catálogo de produtos de dados — ATIVO-cêntrico (RF-006/007), modelo oficial do cliente.
O ATIVO ({ACC}.ativo_aisn) é o driver; os detalhes (breadcrumb) e o escopo UC são
navegados nas relações de {GOV} (ver ativo_scope). Só expõe ativos elegíveis e com owner."""
from app import db
from app import constants as C
from app.schemas import GOV, ACC
from app.services import ativo_scope
from app.services.ativo_scope import objetos_do_ativo, rotulo_objeto, tabelas_do_ativo

TIPOS_ATIVO = C.TIPOS_ATIVO          # códigos numéricos, na ordem de exibição
TIPO_LABEL = C.TIPO_ATIVO_LABEL      # código -> rótulo


def _titulo(a):
    """Título de exibição (feedback do cliente): para Iniciativa, mostra o nome da iniciativa
    seguido da sigla ("{nome} - {sigla}"); demais tipos mantêm o nome do ativo."""
    if str(a.get("cod_tipo_ativo") or "") == C.AT_ICA and a.get("nome_iniciativa"):
        sigla = a.get("sigla_iniciativa")
        return f"{a['nome_iniciativa']} - {sigla}" if sigla else a["nome_iniciativa"]
    return a.get("nome_ativo")


def listar_dominios():
    return db.query(
        f"SELECT id_dominio_informacao, nome_dominio FROM {GOV}.dominio_informacao "
        f"WHERE bol_atual=true AND bol_excluido=false ORDER BY nome_dominio")


def listar_subdominios(id_dominio=None):
    if id_dominio:
        return db.query(
            f"SELECT id_subdominio_informacao, id_dominio_informacao, nome_subdominio "
            f"FROM {GOV}.subdominio_informacao WHERE bol_atual=true AND bol_excluido=false "
            f"AND id_dominio_informacao=%s ORDER BY nome_subdominio", (id_dominio,))
    return db.query(
        f"SELECT id_subdominio_informacao, id_dominio_informacao, nome_subdominio "
        f"FROM {GOV}.subdominio_informacao WHERE bol_atual=true AND bol_excluido=false "
        f"ORDER BY nome_subdominio")


def listar_grupos_ativos(id_dominio=None, id_subdominio=None, busca=None):
    """Catálogo agrupado por GRUPO ATIVO (nome_grupo_ativo + desc_grupo_ativo). Cada grupo
    reúne vários ativos e pertence a UM domínio/subdomínio (D-cliente). Só grupos com pelo
    menos um ativo elegível e com owner. NÃO é o grupo de acesso (esse fica em grupo_acesso)."""
    where = ["a.bol_atual=true", "a.bol_excluido=false", "a.bol_elegivel_acesso=true",
             "a.nome_grupo_ativo IS NOT NULL",
             f"EXISTS (SELECT 1 FROM {ACC}.ativo_proprietario p "
             f"        WHERE p.id_ativo_aisn=a.id_ativo_aisn AND p.bol_atual=true AND p.bol_excluido=false)"]
    params = []
    if id_dominio:
        where.append(f"{ativo_scope.dominio_id_expr()}=%s"); params.append(id_dominio)
    if id_subdominio:
        where.append(f"{ativo_scope.subdominio_id_expr()}=%s"); params.append(id_subdominio)
    if busca:
        where.append("(lower(a.nome_grupo_ativo) LIKE %s OR lower(a.desc_grupo_ativo) LIKE %s)")
        b = f"%{busca.lower()}%"; params += [b, b]
    sql = f"""
        WITH ativos AS (
          SELECT a.nome_grupo_ativo, a.desc_grupo_ativo, {ativo_scope.ativo_cols("a")}
            FROM {ACC}.ativo_aisn a
            {ativo_scope.ativo_join("a")}
           WHERE {' AND '.join(where)}
        )
        SELECT nome_grupo_ativo,
               max(desc_grupo_ativo)         AS desc_grupo_ativo,
               max(nome_dominio)             AS nome_dominio,
               max(nome_subdominio)          AS nome_subdominio,
               max(id_dominio_informacao)    AS id_dominio_informacao,
               max(id_subdominio_informacao) AS id_subdominio_informacao,
               count(*)                      AS qtd_ativos
          FROM ativos
         GROUP BY nome_grupo_ativo
         ORDER BY max(nome_dominio), max(nome_subdominio), nome_grupo_ativo
    """
    return db.query(sql, params)


def listar_ativos(id_dominio=None, id_subdominio=None, tipo=None, busca=None, grupo=None):
    """Cards de ativos ({ACC}.ativo_aisn). Apenas com owner (RN-005) e elegíveis.
    `grupo` filtra pelos ativos de um grupo ativo (nome_grupo_ativo) — usado no drill-down."""
    where = ["a.bol_atual=true", "a.bol_excluido=false", "a.bol_elegivel_acesso=true",
             f"EXISTS (SELECT 1 FROM {ACC}.ativo_proprietario p "
             f"        WHERE p.id_ativo_aisn=a.id_ativo_aisn AND p.bol_atual=true AND p.bol_excluido=false)"]
    params = []
    if id_dominio:
        where.append(f"{ativo_scope.dominio_id_expr()}=%s"); params.append(id_dominio)
    if id_subdominio:
        where.append(f"{ativo_scope.subdominio_id_expr()}=%s"); params.append(id_subdominio)
    if tipo:
        where.append("a.cod_tipo_ativo=%s"); params.append(tipo)
    if grupo:
        where.append("a.nome_grupo_ativo=%s"); params.append(grupo)
    if busca:
        where.append("(lower(a.nome_ativo) LIKE %s OR lower(a.desc_ativo) LIKE %s)")
        b = f"%{busca.lower()}%"; params += [b, b]
    sql = f"""
        SELECT a.id_ativo_aisn, a.cod_tipo_ativo, a.nome_ativo, a.desc_ativo,
               a.nome_grupo_ativo, a.desc_grupo_ativo, {ativo_scope.ativo_cols("a")},
               (SELECT string_agg(DISTINCT u.nome_completo, ', ')
                  FROM {ACC}.ativo_proprietario p
                  JOIN {GOV}.usuario_aisn u ON u.id_usuario_aisn=p.id_usuario_aisn
                       AND u.bol_atual=true AND u.bol_excluido=false
                 WHERE p.id_ativo_aisn=a.id_ativo_aisn AND p.bol_atual=true AND p.bol_excluido=false) AS owners
          FROM {ACC}.ativo_aisn a
          {ativo_scope.ativo_join("a")}
         WHERE {' AND '.join(where)}
         ORDER BY CASE a.cod_tipo_ativo WHEN '{C.AT_DOMINIO}' THEN 0 WHEN '{C.AT_SUBDOMINIO}' THEN 1
                       WHEN '{C.AT_ICA}' THEN 2 ELSE 3 END,
                  nome_dominio, nome_subdominio, a.nome_ativo
    """
    rows = db.query(sql, params)
    for r in rows:
        r["titulo"] = _titulo(r)
    return rows


def ativo_por_id(id_ativo):
    return db.query_one(
        f"""SELECT a.*, {ativo_scope.ativo_cols("a")}
             FROM {ACC}.ativo_aisn a
             {ativo_scope.ativo_join("a")}
            WHERE a.id_ativo_aisn=%s AND a.bol_atual=true AND a.bol_excluido=false""", (id_ativo,))


def detalhe_ativo(id_ativo):
    a = ativo_por_id(id_ativo)
    if not a:
        return None
    a["tipo_label"] = TIPO_LABEL.get(a["cod_tipo_ativo"], a.get("tipo_label") or a["cod_tipo_ativo"])
    a["owners"] = db.query(
        f"""SELECT u.id_usuario_aisn, u.nome_completo, u.desc_email, p.bol_principal
             FROM {ACC}.ativo_proprietario p
             JOIN {GOV}.usuario_aisn u ON u.id_usuario_aisn=p.id_usuario_aisn
                  AND u.bol_atual=true AND u.bol_excluido=false
            WHERE p.id_ativo_aisn=%s AND p.bol_atual=true AND p.bol_excluido=false
            ORDER BY p.bol_principal DESC, u.nome_completo""", (id_ativo,))
    objs = objetos_do_ativo(a)
    for o in objs:
        o["rotulo"] = rotulo_objeto(o)
    a["objetos"] = objs
    a["tabelas"] = tabelas_do_ativo(a)   # tabelas contidas (nome + descrição) — feedback cliente
    a["titulo"] = _titulo(a)
    return a


def contar_ativos(**kwargs):
    return len(listar_ativos(**kwargs))

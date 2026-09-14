"""Solicitações de acesso (RF-011..021) — ancoradas no ATIVO. Modelo oficial do cliente:
governanca={GOV} (taxonomia), gestao_acesso={ACC} (referência de acesso), workflow={APP}."""
import uuid

from app import db
from app import constants as C
from app.config import config
from app.schemas import GOV, ACC, APP
from app.services import audit_service, ativo_scope
from app.services.ativo_scope import objetos_do_ativo, rotulo_objeto


class RegraNegocioError(Exception):
    """Erro de validação de regra de negócio (mensagem amigável ao usuário)."""


# ---------------- Apoio (hierarquia / grupos) ----------------
def gestor_imediato(id_usuario):
    return db.query_one(
        f"""SELECT u.* FROM {ACC}.hierarquia_usuario h
             JOIN {GOV}.usuario_aisn u ON u.id_usuario_aisn=h.id_gestor_aisn
            WHERE h.id_usuario_aisn=%s AND h.bol_atual=true LIMIT 1""",
        (id_usuario,))


def superiores(id_usuario):
    rows = db.query(
        f"""WITH RECURSIVE sup AS (
             SELECT id_gestor_aisn FROM {ACC}.hierarquia_usuario
              WHERE id_usuario_aisn=%s AND bol_atual=true
             UNION
             SELECT h.id_gestor_aisn FROM {ACC}.hierarquia_usuario h
               JOIN sup ON h.id_usuario_aisn = sup.id_gestor_aisn
              WHERE h.bol_atual=true)
           SELECT id_gestor_aisn FROM sup""",
        (id_usuario,))
    return [r["id_gestor_aisn"] for r in rows]


def e_superior(id_gestor, id_usuario):
    return id_gestor in superiores(id_usuario)


def grupos_do_usuario(id_usuario):
    """Grupos EXPLORATÓRIOS em nome dos quais o usuário pode solicitar (RF-047, RN-007):
    grupos de que ele é membro (grupo_acesso_membro, entidade USUARIO) E cujo
    grupo_acesso.tipo_grupo = 'exploratorio' (case-insensitive, config)."""
    return db.query(
        f"""SELECT g.id_grupo_acesso, g.nome_grupo
             FROM {ACC}.grupo_acesso_membro m
             JOIN {ACC}.grupo_acesso g ON g.id_grupo_acesso=m.id_grupo_acesso
            WHERE m.id_entidade=%s AND m.bol_atual=true AND g.bol_atual=true
              AND (m.tipo_entidade='USUARIO' OR m.tipo_entidade IS NULL)
              AND lower(g.tipo_grupo)=lower(%s)
            ORDER BY g.nome_grupo""",
        (id_usuario, config.GRUPO_TIPO_EXPLORATORIO))


# ---------------- Regras ----------------
def _ativo_com_owner(id_ativo):
    return db.query_one(
        f"""SELECT 1 AS ok FROM {ACC}.ativo_proprietario
             WHERE id_ativo_aisn=%s AND bol_atual=true LIMIT 1""", (id_ativo,)) is not None


def _conflito_duplicidade(tipo_benef, id_benef_user, id_grupo, tipo_acesso, id_ativo):
    """RN-010/RF-018: bloqueia solicitação ativa OU acesso vigente equivalente. Ignora revogados."""
    nominal = tipo_benef == C.B_NOMINAL
    benef_cond = "s.id_usuario_beneficiario=%s" if nominal else "s.id_grupo_acesso=%s"
    benef_val = id_benef_user if nominal else id_grupo
    dup_sol = db.query_one(
        f"""SELECT 1 AS ok FROM {APP}.solicitacao_acesso s
             WHERE s.cod_tipo_beneficiario=%s AND {benef_cond}
               AND s.cod_tipo_acesso=%s AND s.id_ativo_aisn=%s
               AND s.cod_status_solicitacao IN ('PENDENTE_AUTORIZACAO','AUTORIZADA','APROVADA_OWNER')
               AND NOT EXISTS (SELECT 1 FROM {APP}.acesso a
                                WHERE a.id_solicitacao_acesso=s.id_solicitacao_acesso
                                  AND a.cod_status_acesso='REVOGADO')
             LIMIT 1""",
        (tipo_benef, benef_val, tipo_acesso, id_ativo))
    if dup_sol:
        return "já existe uma solicitação ativa para este ativo"
    benef_cond_a = "a.id_usuario_beneficiario=%s" if nominal else "a.id_grupo_acesso=%s"
    dup_ac = db.query_one(
        f"""SELECT 1 AS ok FROM {APP}.acesso a
             WHERE a.cod_tipo_beneficiario=%s AND {benef_cond_a}
               AND a.cod_tipo_acesso=%s AND a.id_ativo_aisn=%s
               AND a.cod_status_acesso IN ('APROVADO_AGUARDANDO_EFETIVACAO','EFETIVADO')
             LIMIT 1""",
        (tipo_benef, benef_val, tipo_acesso, id_ativo))
    if dup_ac:
        return "já existe acesso vigente para este ativo"
    return None


# ---------------- Criação ----------------
def criar_solicitacao(solicitante, tipo_benef, id_ativo, tipo_acesso="LEITURA",
                      justificativa=None, id_grupo=None, id_beneficiario=None):
    """Cria a solicitação (PENDENTE_AUTORIZACAO) para um ATIVO."""
    id_solicitante = solicitante["id_usuario_aisn"]
    if not id_solicitante:
        raise RegraNegocioError("Usuário não cadastrado no catálogo; não é possível solicitar.")

    ativo = db.query_one(
        f"SELECT * FROM {ACC}.ativo_aisn WHERE id_ativo_aisn=%s AND bol_atual=true", (id_ativo,))
    if not ativo:
        raise RegraNegocioError("Ativo não encontrado no catálogo.")
    if not ativo.get("bol_elegivel_acesso"):
        raise RegraNegocioError("Ativo não está elegível para acesso.")
    if not _ativo_com_owner(id_ativo):
        raise RegraNegocioError("Ativo sem owner definido não está disponível para solicitação.")

    if tipo_benef == C.B_GRUPO:
        if not id_grupo:
            raise RegraNegocioError("Grupo beneficiário não informado.")
        membro = db.query_one(
            f"""SELECT 1 AS ok FROM {ACC}.grupo_acesso_membro
                 WHERE id_grupo_acesso=%s AND id_entidade=%s AND bol_atual=true""",
            (id_grupo, id_solicitante))
        if not membro:
            raise RegraNegocioError("Você não é membro do grupo informado (RN-007).")
        id_beneficiario = None
    else:
        tipo_benef = C.B_NOMINAL
        id_beneficiario = id_beneficiario or id_solicitante
        id_grupo = None

    conflito = _conflito_duplicidade(tipo_benef, id_beneficiario, id_grupo, tipo_acesso, id_ativo)
    if conflito:
        raise RegraNegocioError(f"Solicitação impedida: {conflito} (RN-010).")

    gestor = gestor_imediato(id_solicitante)
    if not gestor:
        raise RegraNegocioError("Não foi possível identificar seu gestor imediato para autorização (RN-013).")
    if gestor["id_usuario_aisn"] == id_solicitante:
        raise RegraNegocioError("O solicitante não pode autorizar a própria solicitação (RN-014).")

    id_sol = uuid.uuid4().hex
    with db.get_conn(autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""INSERT INTO {APP}.solicitacao_acesso
                   (id_solicitacao_acesso, id_usuario_solicitante, cod_tipo_beneficiario,
                    id_usuario_beneficiario, id_grupo_acesso, id_ativo_aisn,
                    cod_tipo_acesso, desc_justificativa, cod_status_solicitacao,
                    id_usuario_autorizador_previsto)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (id_sol, id_solicitante, tipo_benef, id_beneficiario, id_grupo, id_ativo,
                 tipo_acesso, justificativa, C.S_PENDENTE_AUTORIZACAO, gestor["id_usuario_aisn"]))
            audit_service.registrar(
                cur, C.EV_SOLICITACAO_CRIADA, id_solicitacao=id_sol, id_usuario=id_solicitante,
                detalhe=f"ativo: {ativo['nome_ativo']} "
                        f"({C.TIPO_ATIVO_LABEL.get(ativo['cod_tipo_ativo'], ativo['cod_tipo_ativo'])}); "
                        f"autorizador previsto: {gestor['nome_completo']}")
        conn.commit()
    return id_sol


# ---------------- Consulta ----------------
def listar_do_usuario(id_usuario):
    return db.query(
        f"""SELECT s.*, a.nome_ativo, a.cod_tipo_ativo, {ativo_scope.ativo_cols("a")},
                  g.nome_grupo, ubenef.nome_completo AS nome_beneficiario, ac.cod_status_acesso
             FROM {APP}.solicitacao_acesso s
             LEFT JOIN {ACC}.ativo_aisn a ON a.id_ativo_aisn=s.id_ativo_aisn
             {ativo_scope.ativo_join("a")}
             LEFT JOIN {ACC}.grupo_acesso g ON g.id_grupo_acesso=s.id_grupo_acesso
             LEFT JOIN {GOV}.usuario_aisn ubenef ON ubenef.id_usuario_aisn=s.id_usuario_beneficiario
             LEFT JOIN {APP}.acesso ac ON ac.id_solicitacao_acesso=s.id_solicitacao_acesso
            WHERE s.id_usuario_solicitante=%s
            ORDER BY s.datahora_criacao DESC""",
        (id_usuario,))


def detalhe(id_solicitacao):
    s = db.query_one(
        f"""SELECT s.*, a.nome_ativo, a.cod_tipo_ativo, {ativo_scope.ativo_cols("a")},
                  g.nome_grupo, ubenef.nome_completo AS nome_beneficiario,
                  usol.nome_completo AS nome_solicitante,
                  uaut.nome_completo AS nome_autorizador_previsto,
                  ac.id_acesso, ac.cod_status_acesso, ac.datahora_efetivacao
             FROM {APP}.solicitacao_acesso s
             LEFT JOIN {ACC}.ativo_aisn a ON a.id_ativo_aisn=s.id_ativo_aisn
             {ativo_scope.ativo_join("a")}
             JOIN {GOV}.usuario_aisn usol ON usol.id_usuario_aisn=s.id_usuario_solicitante
             LEFT JOIN {GOV}.usuario_aisn uaut ON uaut.id_usuario_aisn=s.id_usuario_autorizador_previsto
             LEFT JOIN {ACC}.grupo_acesso g ON g.id_grupo_acesso=s.id_grupo_acesso
             LEFT JOIN {GOV}.usuario_aisn ubenef ON ubenef.id_usuario_aisn=s.id_usuario_beneficiario
             LEFT JOIN {APP}.acesso ac ON ac.id_solicitacao_acesso=s.id_solicitacao_acesso
            WHERE s.id_solicitacao_acesso=%s""",
        (id_solicitacao,))
    if not s:
        return None
    objs = objetos_do_ativo(s)
    for o in objs:
        o["rotulo"] = rotulo_objeto(o)
    s["objetos"] = objs
    s["owners"] = db.query(
        f"""SELECT u.nome_completo, p.bol_principal
             FROM {ACC}.ativo_proprietario p
             JOIN {GOV}.usuario_aisn u ON u.id_usuario_aisn=p.id_usuario_aisn
            WHERE p.id_ativo_aisn=%s AND p.bol_atual=true
            ORDER BY p.bol_principal DESC, u.nome_completo""",
        (s["id_ativo_aisn"],)) if s.get("id_ativo_aisn") else []
    s["eventos"] = audit_service.eventos_da_solicitacao(id_solicitacao)
    return s


def cancelar(id_solicitacao, id_usuario):
    """RN-011: solicitante cancela enquanto elegível."""
    s = db.query_one(
        f"SELECT * FROM {APP}.solicitacao_acesso WHERE id_solicitacao_acesso=%s",
        (id_solicitacao,))
    if not s:
        raise RegraNegocioError("Solicitação não encontrada.")
    if s["id_usuario_solicitante"] != id_usuario:
        raise RegraNegocioError("Somente o solicitante pode cancelar a solicitação.")
    if s["cod_status_solicitacao"] not in C.STATUS_SOLICITACAO_CANCELAVEL:
        raise RegraNegocioError("Solicitação não está em estado cancelável.")
    with db.get_conn(autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""UPDATE {APP}.solicitacao_acesso
                      SET cod_status_solicitacao=%s, datahora_atualizacao=now()
                    WHERE id_solicitacao_acesso=%s""",
                (C.S_CANCELADA, id_solicitacao))
            audit_service.registrar(cur, C.EV_CANCELADA, id_solicitacao=id_solicitacao,
                                    id_usuario=id_usuario)
        conn.commit()

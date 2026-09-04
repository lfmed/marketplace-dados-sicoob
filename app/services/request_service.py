"""Solicitações de acesso (RF-011..021) e regras de negócio associadas."""
import uuid

from app import db
from app import constants as C
from app.services import audit_service


class RegraNegocioError(Exception):
    """Erro de validação de regra de negócio (mensagem amigável ao usuário)."""


# ---------------- Apoio ----------------
def gestor_imediato(id_usuario):
    return db.query_one(
        """SELECT u.* FROM governanca.hierarquia_usuario h
             JOIN governanca.usuario_aisn u ON u.id_usuario_aisn=h.id_gestor_aisn
            WHERE h.id_usuario_aisn=%s AND h.bol_atual=true LIMIT 1""",
        (id_usuario,),
    )


def superiores(id_usuario):
    """Todos os gestores acima do usuário na hierarquia (imediato + níveis superiores) — RF-024/RN-013."""
    rows = db.query(
        """WITH RECURSIVE sup AS (
             SELECT id_gestor_aisn FROM governanca.hierarquia_usuario
              WHERE id_usuario_aisn=%s AND bol_atual=true
             UNION
             SELECT h.id_gestor_aisn FROM governanca.hierarquia_usuario h
               JOIN sup ON h.id_usuario_aisn = sup.id_gestor_aisn
              WHERE h.bol_atual=true)
           SELECT id_gestor_aisn FROM sup""",
        (id_usuario,))
    return [r["id_gestor_aisn"] for r in rows]


def e_superior(id_gestor, id_usuario):
    return id_gestor in superiores(id_usuario)


def grupos_do_usuario(id_usuario):
    """Grupos exploratórios em nome dos quais o usuário pode solicitar (RF-047, RN-007)."""
    return db.query(
        """SELECT g.id_grupo_acesso, g.nome_grupo, g.tipo_grupo
             FROM governanca.grupo_acesso_membro m
             JOIN governanca.grupo_acesso g ON g.id_grupo_acesso=m.id_grupo_acesso
            WHERE m.id_entidade=%s AND m.bol_atual=true AND g.bol_atual=true
            ORDER BY g.nome_grupo""",
        (id_usuario,),
    )


def _icas_da_iniciativa(id_iniciativa, id_ambiente):
    return db.query(
        """SELECT ica.id_iniciativa_camada_ambiente, c.nome_camada
             FROM governanca.iniciativa_camada_ambiente ica
             JOIN governanca.camada_aisn c ON c.id_camada_aisn=ica.id_camada_aisn
            WHERE ica.id_iniciativa_aisn=%s AND ica.id_ambiente_aisn=%s
              AND ica.bol_atual=true AND ica.bol_elegivel_acesso=true""",
        (id_iniciativa, id_ambiente),
    )


def _tem_owner(id_iniciativa):
    return db.query_one(
        """SELECT 1 AS ok FROM governanca.iniciativa_proprietario
            WHERE id_iniciativa_aisn=%s AND bol_atual=true LIMIT 1""",
        (id_iniciativa,),
    ) is not None


def _conflito_duplicidade(tipo_benef, id_benef_user, id_grupo, tipo_acesso, ica_ids):
    """RN-010/RF-018: bloqueia se já há solicitação ativa OU acesso vigente equivalente
    (mesmo beneficiário + tipo de acesso + camada sobreposta)."""
    benef_cond = ("s.id_usuario_beneficiario=%s" if tipo_benef == C.B_NOMINAL
                  else "s.id_grupo_acesso=%s")
    benef_val = id_benef_user if tipo_benef == C.B_NOMINAL else id_grupo
    dup_sol = db.query_one(
        f"""SELECT c.nome_camada FROM gestao_acesso.solicitacao_acesso s
              JOIN gestao_acesso.solicitacao_camada sc ON sc.id_solicitacao_acesso=s.id_solicitacao_acesso
              JOIN governanca.iniciativa_camada_ambiente ica
                   ON ica.id_iniciativa_camada_ambiente=sc.id_iniciativa_camada_ambiente
              JOIN governanca.camada_aisn c ON c.id_camada_aisn=ica.id_camada_aisn
             WHERE s.cod_tipo_beneficiario=%s AND {benef_cond}
               AND s.cod_tipo_acesso=%s
               AND s.cod_status_solicitacao IN ('PENDENTE_AUTORIZACAO','AUTORIZADA','APROVADA_OWNER')
               -- não bloqueia se o acesso gerado já foi revogado: o beneficiário
               -- pode solicitar de novo aquela camada (RN-010 vale só p/ vigentes).
               AND NOT EXISTS (SELECT 1 FROM gestao_acesso.acesso a
                                WHERE a.id_solicitacao_acesso=s.id_solicitacao_acesso
                                  AND a.cod_status_acesso='REVOGADO')
               AND sc.id_iniciativa_camada_ambiente = ANY(%s) LIMIT 1""",
        (tipo_benef, benef_val, tipo_acesso, ica_ids),
    )
    if dup_sol:
        return f"já existe uma solicitação ativa para a camada {dup_sol['nome_camada']}"
    benef_cond_a = ("a.id_usuario_beneficiario=%s" if tipo_benef == C.B_NOMINAL
                    else "a.id_grupo_acesso=%s")
    dup_ac = db.query_one(
        f"""SELECT c.nome_camada FROM gestao_acesso.acesso a
              JOIN gestao_acesso.acesso_camada acc ON acc.id_acesso=a.id_acesso
              JOIN governanca.iniciativa_camada_ambiente ica
                   ON ica.id_iniciativa_camada_ambiente=acc.id_iniciativa_camada_ambiente
              JOIN governanca.camada_aisn c ON c.id_camada_aisn=ica.id_camada_aisn
             WHERE a.cod_tipo_beneficiario=%s AND {benef_cond_a}
               AND a.cod_tipo_acesso=%s
               AND a.cod_status_acesso IN ('APROVADO_AGUARDANDO_EFETIVACAO','EFETIVADO')
               AND acc.id_iniciativa_camada_ambiente = ANY(%s) LIMIT 1""",
        (tipo_benef, benef_val, tipo_acesso, ica_ids),
    )
    if dup_ac:
        return f"já existe acesso vigente para a camada {dup_ac['nome_camada']}"
    return None


# ---------------- Criação ----------------
def criar_solicitacao(solicitante, tipo_benef, id_iniciativa, id_ambiente,
                      ica_ids, tipo_acesso="LEITURA", justificativa=None,
                      id_grupo=None, id_beneficiario=None):
    """Valida as regras e cria a solicitação (status PENDENTE_AUTORIZACAO)."""
    id_solicitante = solicitante["id_usuario_aisn"]
    if not id_solicitante:
        raise RegraNegocioError("Usuário não cadastrado no catálogo; não é possível solicitar.")

    # RN-005: iniciativa precisa ter owner
    if not _tem_owner(id_iniciativa):
        raise RegraNegocioError("Iniciativa sem owner definido não está disponível para solicitação.")

    # RN-003/004: camadas informadas devem pertencer à iniciativa/ambiente e ser elegíveis
    validas = {r["id_iniciativa_camada_ambiente"] for r in _icas_da_iniciativa(id_iniciativa, id_ambiente)}
    ica_ids = [x for x in (ica_ids or []) if x in validas]
    if not ica_ids:
        raise RegraNegocioError("Selecione ao menos uma camada elegível da iniciativa.")

    # Beneficiário
    if tipo_benef == C.B_GRUPO:
        if not id_grupo:
            raise RegraNegocioError("Grupo beneficiário não informado.")
        # RN-007: solicitante deve ser membro do grupo
        membro = db.query_one(
            """SELECT 1 AS ok FROM governanca.grupo_acesso_membro
                WHERE id_grupo_acesso=%s AND id_entidade=%s AND bol_atual=true""",
            (id_grupo, id_solicitante))
        if not membro:
            raise RegraNegocioError("Você não é membro do grupo informado (RN-007).")
        id_beneficiario = None
    else:
        tipo_benef = C.B_NOMINAL
        # nominal: default é o próprio solicitante
        id_beneficiario = id_beneficiario or id_solicitante
        id_grupo = None

    # RN-010/RF-018: duplicidade
    conflito = _conflito_duplicidade(tipo_benef, id_beneficiario, id_grupo, tipo_acesso, ica_ids)
    if conflito:
        raise RegraNegocioError(f"Solicitação impedida: {conflito} (RN-010).")

    # RN-013: autorizador hierárquico = gestor imediato do solicitante
    gestor = gestor_imediato(id_solicitante)
    if not gestor:
        raise RegraNegocioError("Não foi possível identificar seu gestor imediato para autorização (RN-013).")
    # RN-014: solicitante não pode ser seu próprio autorizador
    if gestor["id_usuario_aisn"] == id_solicitante:
        raise RegraNegocioError("O solicitante não pode autorizar a própria solicitação (RN-014).")

    id_sol = uuid.uuid4().hex
    with db.get_conn(autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO gestao_acesso.solicitacao_acesso
                   (id_solicitacao_acesso, id_usuario_solicitante, cod_tipo_beneficiario,
                    id_usuario_beneficiario, id_grupo_acesso, id_iniciativa_aisn, id_ambiente_aisn,
                    cod_tipo_acesso, desc_justificativa, cod_status_solicitacao,
                    id_usuario_autorizador_previsto)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (id_sol, id_solicitante, tipo_benef, id_beneficiario, id_grupo,
                 id_iniciativa, id_ambiente, tipo_acesso, justificativa,
                 C.S_PENDENTE_AUTORIZACAO, gestor["id_usuario_aisn"]))
            for ica in ica_ids:
                cur.execute(
                    """INSERT INTO gestao_acesso.solicitacao_camada
                       (id_solicitacao_acesso, id_iniciativa_camada_ambiente) VALUES (%s,%s)""",
                    (id_sol, ica))
            audit_service.registrar(cur, C.EV_SOLICITACAO_CRIADA, id_solicitacao=id_sol,
                                    id_usuario=id_solicitante,
                                    detalhe=f"{len(ica_ids)} camada(s); autorizador previsto: {gestor['nome_completo']}")
        conn.commit()
    return id_sol


# ---------------- Consulta ----------------
def listar_do_usuario(id_usuario):
    return db.query(
        """SELECT s.*, i.nome_iniciativa, amb.nome_ambiente,
                  g.nome_grupo, ubenef.nome_completo AS nome_beneficiario,
                  ac.cod_status_acesso,
                  (SELECT string_agg(c.nome_camada, ', ' ORDER BY c.nome_camada)
                     FROM gestao_acesso.solicitacao_camada sc
                     JOIN governanca.iniciativa_camada_ambiente ica
                          ON ica.id_iniciativa_camada_ambiente=sc.id_iniciativa_camada_ambiente
                     JOIN governanca.camada_aisn c ON c.id_camada_aisn=ica.id_camada_aisn
                    WHERE sc.id_solicitacao_acesso=s.id_solicitacao_acesso) AS camadas
             FROM gestao_acesso.solicitacao_acesso s
             JOIN governanca.iniciativa_aisn i ON i.id_iniciativa_aisn=s.id_iniciativa_aisn
             JOIN governanca.ambiente_aisn amb ON amb.id_ambiente_aisn=s.id_ambiente_aisn
             LEFT JOIN governanca.grupo_acesso g ON g.id_grupo_acesso=s.id_grupo_acesso
             LEFT JOIN governanca.usuario_aisn ubenef ON ubenef.id_usuario_aisn=s.id_usuario_beneficiario
             LEFT JOIN gestao_acesso.acesso ac ON ac.id_solicitacao_acesso=s.id_solicitacao_acesso
            WHERE s.id_usuario_solicitante=%s
            ORDER BY s.datahora_criacao DESC""",
        (id_usuario,),
    )


def detalhe(id_solicitacao):
    s = db.query_one(
        """SELECT s.*, i.nome_iniciativa, amb.nome_ambiente, g.nome_grupo,
                  ubenef.nome_completo AS nome_beneficiario,
                  usol.nome_completo AS nome_solicitante,
                  uaut.nome_completo AS nome_autorizador_previsto,
                  ac.id_acesso, ac.cod_status_acesso, ac.datahora_efetivacao
             FROM gestao_acesso.solicitacao_acesso s
             JOIN governanca.iniciativa_aisn i ON i.id_iniciativa_aisn=s.id_iniciativa_aisn
             JOIN governanca.ambiente_aisn amb ON amb.id_ambiente_aisn=s.id_ambiente_aisn
             JOIN governanca.usuario_aisn usol ON usol.id_usuario_aisn=s.id_usuario_solicitante
             LEFT JOIN governanca.usuario_aisn uaut ON uaut.id_usuario_aisn=s.id_usuario_autorizador_previsto
             LEFT JOIN governanca.grupo_acesso g ON g.id_grupo_acesso=s.id_grupo_acesso
             LEFT JOIN governanca.usuario_aisn ubenef ON ubenef.id_usuario_aisn=s.id_usuario_beneficiario
             LEFT JOIN gestao_acesso.acesso ac ON ac.id_solicitacao_acesso=s.id_solicitacao_acesso
            WHERE s.id_solicitacao_acesso=%s""",
        (id_solicitacao,),
    )
    if not s:
        return None
    s["camadas"] = db.query(
        """SELECT c.nome_camada, ica.nome_schema, ica.nome_catalogo
             FROM gestao_acesso.solicitacao_camada sc
             JOIN governanca.iniciativa_camada_ambiente ica
                  ON ica.id_iniciativa_camada_ambiente=sc.id_iniciativa_camada_ambiente
             JOIN governanca.camada_aisn c ON c.id_camada_aisn=ica.id_camada_aisn
            WHERE sc.id_solicitacao_acesso=%s ORDER BY c.nome_camada""",
        (id_solicitacao,))
    s["eventos"] = audit_service.eventos_da_solicitacao(id_solicitacao)
    return s


def cancelar(id_solicitacao, id_usuario):
    """RN-011: solicitante cancela enquanto elegível."""
    s = db.query_one(
        "SELECT * FROM gestao_acesso.solicitacao_acesso WHERE id_solicitacao_acesso=%s",
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
                """UPDATE gestao_acesso.solicitacao_acesso
                      SET cod_status_solicitacao=%s, datahora_atualizacao=now()
                    WHERE id_solicitacao_acesso=%s""",
                (C.S_CANCELADA, id_solicitacao))
            audit_service.registrar(cur, C.EV_CANCELADA, id_solicitacao=id_solicitacao,
                                    id_usuario=id_usuario)
        conn.commit()

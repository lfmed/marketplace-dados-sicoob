"""Aprovações: autorização hierárquica (gestor) e aprovação do owner.
RF-026..039. Regras: RN-006, RN-014, RN-015, RN-016, RN-017, RN-026."""
import uuid

from app import db
from app import constants as C
from app.services import audit_service, access_service
from app.services.request_service import RegraNegocioError


# ---------------- Fila do gestor (RF-027) ----------------
def fila_gestor(id_gestor):
    """Solicitações pendentes em que o usuário é gestor imediato OU superior do
    solicitante na hierarquia (RF-024/RN-013)."""
    return db.query(
        """WITH RECURSIVE sub AS (
             SELECT id_usuario_aisn FROM governanca.hierarquia_usuario
              WHERE id_gestor_aisn=%s AND bol_atual=true
             UNION
             SELECT h.id_usuario_aisn FROM governanca.hierarquia_usuario h
               JOIN sub ON h.id_gestor_aisn = sub.id_usuario_aisn
              WHERE h.bol_atual=true)
           SELECT s.*, i.nome_iniciativa, amb.nome_ambiente, g.nome_grupo,
                  usol.nome_completo AS nome_solicitante,
                  ubenef.nome_completo AS nome_beneficiario,
                  (SELECT string_agg(c.nome_camada, ', ' ORDER BY c.nome_camada)
                     FROM gestao_acesso.solicitacao_camada sc
                     JOIN governanca.iniciativa_camada_ambiente ica
                          ON ica.id_iniciativa_camada_ambiente=sc.id_iniciativa_camada_ambiente
                     JOIN governanca.camada_aisn c ON c.id_camada_aisn=ica.id_camada_aisn
                    WHERE sc.id_solicitacao_acesso=s.id_solicitacao_acesso) AS camadas
             FROM gestao_acesso.solicitacao_acesso s
             JOIN governanca.iniciativa_aisn i ON i.id_iniciativa_aisn=s.id_iniciativa_aisn
             JOIN governanca.ambiente_aisn amb ON amb.id_ambiente_aisn=s.id_ambiente_aisn
             JOIN governanca.usuario_aisn usol ON usol.id_usuario_aisn=s.id_usuario_solicitante
             LEFT JOIN governanca.grupo_acesso g ON g.id_grupo_acesso=s.id_grupo_acesso
             LEFT JOIN governanca.usuario_aisn ubenef ON ubenef.id_usuario_aisn=s.id_usuario_beneficiario
            WHERE s.cod_status_solicitacao=%s
              AND (s.id_usuario_autorizador_previsto=%s OR s.id_usuario_solicitante IN (SELECT id_usuario_aisn FROM sub))
            ORDER BY s.datahora_criacao""",
        (id_gestor, C.S_PENDENTE_AUTORIZACAO, id_gestor))


def decidir_autorizacao(id_solicitacao, id_gestor, aprovar, justificativa=None):
    s = db.query_one("SELECT * FROM gestao_acesso.solicitacao_acesso WHERE id_solicitacao_acesso=%s",
                     (id_solicitacao,))
    if not s:
        raise RegraNegocioError("Solicitação não encontrada.")
    if s["cod_status_solicitacao"] != C.S_PENDENTE_AUTORIZACAO:
        raise RegraNegocioError("Solicitação não está pendente de autorização.")
    # RN-014: solicitante não autoriza a própria solicitação
    if id_gestor == s["id_usuario_solicitante"]:
        raise RegraNegocioError("O solicitante não pode autorizar a própria solicitação (RN-014).")
    # RN-013/RF-024: autoriza o gestor imediato OU um superior na hierarquia
    from app.services.request_service import e_superior
    if id_gestor != s["id_usuario_autorizador_previsto"] and not e_superior(id_gestor, s["id_usuario_solicitante"]):
        raise RegraNegocioError("Você não é gestor imediato nem superior hierárquico do solicitante (RN-013).")
    resultado = C.R_APROVADA if aprovar else C.R_REPROVADA
    novo_status = C.S_AUTORIZADA if aprovar else C.S_REPROVADA_GESTOR
    with db.get_conn(autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO gestao_acesso.autorizacao_hierarquica
                   (id_autorizacao_hierarquica, id_solicitacao_acesso, id_usuario_autorizador,
                    cod_resultado, desc_justificativa) VALUES (%s,%s,%s,%s,%s)""",
                (uuid.uuid4().hex, id_solicitacao, id_gestor, resultado, justificativa))
            cur.execute(
                """UPDATE gestao_acesso.solicitacao_acesso
                      SET cod_status_solicitacao=%s, datahora_atualizacao=now()
                    WHERE id_solicitacao_acesso=%s""", (novo_status, id_solicitacao))
            audit_service.registrar(cur, C.EV_AUTORIZADA if aprovar else C.EV_REPROVADA_GESTOR,
                                    id_solicitacao=id_solicitacao, id_usuario=id_gestor,
                                    detalhe=justificativa)
        conn.commit()


# ---------------- Fila do owner (RF-034) ----------------
def fila_owner(id_owner):
    return db.query(
        """SELECT s.*, i.nome_iniciativa, amb.nome_ambiente, g.nome_grupo,
                  usol.nome_completo AS nome_solicitante,
                  ubenef.nome_completo AS nome_beneficiario,
                  (SELECT string_agg(c.nome_camada, ', ' ORDER BY c.nome_camada)
                     FROM gestao_acesso.solicitacao_camada sc
                     JOIN governanca.iniciativa_camada_ambiente ica
                          ON ica.id_iniciativa_camada_ambiente=sc.id_iniciativa_camada_ambiente
                     JOIN governanca.camada_aisn c ON c.id_camada_aisn=ica.id_camada_aisn
                    WHERE sc.id_solicitacao_acesso=s.id_solicitacao_acesso) AS camadas
             FROM gestao_acesso.solicitacao_acesso s
             JOIN governanca.iniciativa_aisn i ON i.id_iniciativa_aisn=s.id_iniciativa_aisn
             JOIN governanca.ambiente_aisn amb ON amb.id_ambiente_aisn=s.id_ambiente_aisn
             JOIN governanca.iniciativa_proprietario p
                  ON p.id_iniciativa_aisn=s.id_iniciativa_aisn AND p.bol_atual=true
             JOIN governanca.usuario_aisn usol ON usol.id_usuario_aisn=s.id_usuario_solicitante
             LEFT JOIN governanca.grupo_acesso g ON g.id_grupo_acesso=s.id_grupo_acesso
             LEFT JOIN governanca.usuario_aisn ubenef ON ubenef.id_usuario_aisn=s.id_usuario_beneficiario
            WHERE s.cod_status_solicitacao=%s AND p.id_usuario_aisn=%s
            ORDER BY s.datahora_criacao""",
        (C.S_AUTORIZADA, id_owner))


def decidir_aprovacao_owner(id_solicitacao, id_owner, aprovar, justificativa=None):
    s = db.query_one("SELECT * FROM gestao_acesso.solicitacao_acesso WHERE id_solicitacao_acesso=%s",
                     (id_solicitacao,))
    if not s:
        raise RegraNegocioError("Solicitação não encontrada.")
    if s["cod_status_solicitacao"] != C.S_AUTORIZADA:
        raise RegraNegocioError("Solicitação precisa estar autorizada pelo gestor antes da aprovação do owner.")
    # RN-006/026: owner precisa ser dono da iniciativa
    dono = db.query_one(
        """SELECT 1 AS ok FROM governanca.iniciativa_proprietario
            WHERE id_iniciativa_aisn=%s AND id_usuario_aisn=%s AND bol_atual=true""",
        (s["id_iniciativa_aisn"], id_owner))
    if not dono:
        raise RegraNegocioError("Você não é owner desta iniciativa (RN-006).")
    # RN-017: owner não aprova acesso nominal para o próprio usuário
    if aprovar and s["cod_tipo_beneficiario"] == C.B_NOMINAL and s["id_usuario_beneficiario"] == id_owner:
        raise RegraNegocioError("O owner não pode aprovar acesso nominal para o próprio usuário (RN-017).")
    resultado = C.R_APROVADA if aprovar else C.R_REPROVADA
    novo_status = C.S_APROVADA_OWNER if aprovar else C.S_REPROVADA_OWNER
    with db.get_conn(autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO gestao_acesso.aprovacao_owner
                   (id_aprovacao_owner, id_solicitacao_acesso, id_usuario_owner,
                    cod_resultado, desc_justificativa) VALUES (%s,%s,%s,%s,%s)""",
                (uuid.uuid4().hex, id_solicitacao, id_owner, resultado, justificativa))
            cur.execute(
                """UPDATE gestao_acesso.solicitacao_acesso
                      SET cod_status_solicitacao=%s, datahora_atualizacao=now()
                    WHERE id_solicitacao_acesso=%s""", (novo_status, id_solicitacao))
            audit_service.registrar(cur, C.EV_APROVADA_OWNER if aprovar else C.EV_REPROVADA_OWNER,
                                    id_solicitacao=id_solicitacao, id_usuario=id_owner,
                                    detalhe=justificativa)
            # RN-018/029: aprovação cria o ACESSO (aguardando efetivação), estado distinto
            if aprovar:
                access_service.criar_acesso(cur, s)
        conn.commit()

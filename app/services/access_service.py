"""Ciclo de vida do acesso (RF-051..080): criação a partir da aprovação, efetivação
técnica assíncrona, revogação. A aprovação (owner) e a efetivação são estados distintos
(RN-018/029). Efetivação em até 30 min (RN-030) — aqui via worker de background."""
import uuid

from app import db
from app import constants as C
from app.services import audit_service, grant_executor


# ---------------- Criação do acesso (dentro da transação de aprovação do owner) ----------------
def criar_acesso(cur, solicitacao):
    """Cria o acesso (AGUARDANDO_EFETIVACAO) + camadas + execução técnica PENDENTE."""
    id_acesso = uuid.uuid4().hex
    cur.execute(
        """INSERT INTO gestao_acesso.acesso
           (id_acesso, id_solicitacao_acesso, cod_tipo_beneficiario, id_usuario_beneficiario,
            id_grupo_acesso, id_iniciativa_aisn, id_ambiente_aisn, cod_tipo_acesso, cod_status_acesso)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (id_acesso, solicitacao["id_solicitacao_acesso"], solicitacao["cod_tipo_beneficiario"],
         solicitacao["id_usuario_beneficiario"], solicitacao["id_grupo_acesso"],
         solicitacao["id_iniciativa_aisn"], solicitacao["id_ambiente_aisn"],
         solicitacao["cod_tipo_acesso"], C.A_AGUARDANDO_EFETIVACAO))
    # copia as camadas da solicitação
    cur.execute(
        """INSERT INTO gestao_acesso.acesso_camada (id_acesso, id_iniciativa_camada_ambiente)
           SELECT %s, id_iniciativa_camada_ambiente FROM gestao_acesso.solicitacao_camada
            WHERE id_solicitacao_acesso=%s""",
        (id_acesso, solicitacao["id_solicitacao_acesso"]))
    # execução técnica pendente (concessão)
    cur.execute(
        """INSERT INTO gestao_acesso.execucao_tecnica
           (id_execucao_tecnica, id_acesso, cod_tipo_operacao, cod_status_execucao)
           VALUES (%s,%s,%s,%s)""",
        (uuid.uuid4().hex, id_acesso, C.OP_CONCESSAO, C.E_PENDENTE))
    audit_service.registrar(cur, C.EV_ACESSO_CRIADO, id_solicitacao=solicitacao["id_solicitacao_acesso"],
                            id_acesso=id_acesso, detalhe="acesso aprovado, aguardando efetivação")
    return id_acesso


# ---------------- Consultas ----------------
def acessos_do_usuario(id_usuario):
    """Acessos nominais do usuário + acessos por grupo do qual é membro (RF-051/052, RN-025)."""
    return db.query(
        """SELECT a.*, i.nome_iniciativa, amb.nome_ambiente, g.nome_grupo,
                  CASE WHEN a.cod_tipo_beneficiario='NOMINAL' THEN 'Nominal'
                       ELSE 'Grupo: ' || g.nome_grupo END AS origem,
                  (SELECT string_agg(c.nome_camada, ', ' ORDER BY c.nome_camada)
                     FROM gestao_acesso.acesso_camada acc
                     JOIN governanca.iniciativa_camada_ambiente ica
                          ON ica.id_iniciativa_camada_ambiente=acc.id_iniciativa_camada_ambiente
                     JOIN governanca.camada_aisn c ON c.id_camada_aisn=ica.id_camada_aisn
                    WHERE acc.id_acesso=a.id_acesso) AS camadas
             FROM gestao_acesso.acesso a
             JOIN governanca.iniciativa_aisn i ON i.id_iniciativa_aisn=a.id_iniciativa_aisn
             JOIN governanca.ambiente_aisn amb ON amb.id_ambiente_aisn=a.id_ambiente_aisn
             LEFT JOIN governanca.grupo_acesso g ON g.id_grupo_acesso=a.id_grupo_acesso
            WHERE (a.cod_tipo_beneficiario='NOMINAL' AND a.id_usuario_beneficiario=%s)
               OR (a.cod_tipo_beneficiario='GRUPO' AND a.id_grupo_acesso IN (
                     SELECT id_grupo_acesso FROM governanca.grupo_acesso_membro
                      WHERE id_entidade=%s AND bol_atual=true))
            ORDER BY a.datahora_aprovacao DESC""",
        (id_usuario, id_usuario))


def acessos_do_owner(id_owner):
    """Acessos concedidos no escopo do owner (RF-040/041)."""
    return db.query(
        """SELECT a.*, i.nome_iniciativa, amb.nome_ambiente, g.nome_grupo,
                  ubenef.nome_completo AS nome_beneficiario,
                  CASE WHEN a.cod_tipo_beneficiario='NOMINAL' THEN ubenef.nome_completo
                       ELSE 'Grupo: ' || g.nome_grupo END AS origem
             FROM gestao_acesso.acesso a
             JOIN governanca.iniciativa_aisn i ON i.id_iniciativa_aisn=a.id_iniciativa_aisn
             JOIN governanca.ambiente_aisn amb ON amb.id_ambiente_aisn=a.id_ambiente_aisn
             JOIN governanca.iniciativa_proprietario p
                  ON p.id_iniciativa_aisn=a.id_iniciativa_aisn AND p.bol_atual=true
             LEFT JOIN governanca.grupo_acesso g ON g.id_grupo_acesso=a.id_grupo_acesso
             LEFT JOIN governanca.usuario_aisn ubenef ON ubenef.id_usuario_aisn=a.id_usuario_beneficiario
            WHERE p.id_usuario_aisn=%s AND a.cod_status_acesso <> 'REVOGADO'
            ORDER BY a.datahora_aprovacao DESC""",
        (id_owner,))


def _acesso(id_acesso):
    return db.query_one("SELECT * FROM gestao_acesso.acesso WHERE id_acesso=%s", (id_acesso,))


# ---------------- Revogação (RF-042/043, RF-072..075) ----------------
def solicitar_revogacao(id_acesso, id_owner, justificativa=None):
    from app.services.request_service import RegraNegocioError
    ac = _acesso(id_acesso)
    if not ac:
        raise RegraNegocioError("Acesso não encontrado.")
    # RN-026: owner só administra no seu escopo
    escopo = db.query_one(
        """SELECT 1 AS ok FROM governanca.iniciativa_proprietario
            WHERE id_iniciativa_aisn=%s AND id_usuario_aisn=%s AND bol_atual=true""",
        (ac["id_iniciativa_aisn"], id_owner))
    if not escopo:
        raise RegraNegocioError("Você não é owner desta iniciativa (RN-026).")
    if ac["cod_status_acesso"] not in (C.A_EFETIVADO, C.A_ERRO_EFETIVACAO):
        raise RegraNegocioError("Somente acessos efetivados podem ser revogados.")
    with db.get_conn(autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO gestao_acesso.revogacao_acesso
                   (id_revogacao_acesso, id_acesso, id_usuario_solicitante, desc_justificativa,
                    cod_status_revogacao) VALUES (%s,%s,%s,%s,%s)""",
                (uuid.uuid4().hex, id_acesso, id_owner, justificativa, "SOLICITADA"))
            cur.execute(
                """INSERT INTO gestao_acesso.execucao_tecnica
                   (id_execucao_tecnica, id_acesso, cod_tipo_operacao, cod_status_execucao)
                   VALUES (%s,%s,%s,%s)""",
                (uuid.uuid4().hex, id_acesso, C.OP_REVOGACAO, C.E_PENDENTE))
            audit_service.registrar(cur, C.EV_REVOGACAO_SOLICITADA, id_acesso=id_acesso,
                                    id_usuario=id_owner, detalhe=justificativa)
        conn.commit()


# ---------------- Worker de efetivação (RN-030/041) ----------------
def processar_execucoes_pendentes(limite=20):
    """Processa execuções técnicas PENDENTE. Usa advisory lock p/ evitar concorrência
    entre workers (gunicorn multi-processo). Retorna nº processadas."""
    processadas = 0
    with db.get_conn(autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_xact_lock(918273645) AS got")
            if not cur.fetchone()["got"]:
                return 0  # outro worker está processando
            cur.execute(
                """SELECT e.*, a.cod_tipo_beneficiario, a.id_usuario_beneficiario,
                          a.id_grupo_acesso
                     FROM gestao_acesso.execucao_tecnica e
                     JOIN gestao_acesso.acesso a ON a.id_acesso=e.id_acesso
                    WHERE e.cod_status_execucao=%s
                    ORDER BY e.datahora_inicio LIMIT %s""",
                (C.E_PENDENTE, limite))
            pendentes = cur.fetchall()

            for e in pendentes:
                acesso = _acesso(e["id_acesso"])
                ok, comando, erro = grant_executor.executar(e["cod_tipo_operacao"], acesso)
                if ok:
                    cur.execute(
                        """UPDATE gestao_acesso.execucao_tecnica
                              SET cod_status_execucao=%s, desc_comando=%s, desc_erro=NULL,
                                  datahora_fim=now()
                            WHERE id_execucao_tecnica=%s""",
                        (C.E_EFETIVADA, comando, e["id_execucao_tecnica"]))
                    if e["cod_tipo_operacao"] == C.OP_CONCESSAO:
                        cur.execute(
                            """UPDATE gestao_acesso.acesso
                                  SET cod_status_acesso=%s, datahora_efetivacao=now()
                                WHERE id_acesso=%s""", (C.A_EFETIVADO, e["id_acesso"]))
                        audit_service.registrar(cur, C.EV_EFETIVADO, id_acesso=e["id_acesso"],
                                                detalhe="concessão efetivada no Unity Catalog")
                    else:
                        cur.execute(
                            """UPDATE gestao_acesso.acesso
                                  SET cod_status_acesso=%s, datahora_revogacao=now()
                                WHERE id_acesso=%s""", (C.A_REVOGADO, e["id_acesso"]))
                        cur.execute(
                            """UPDATE gestao_acesso.revogacao_acesso
                                  SET cod_status_revogacao='EFETIVADA', datahora_conclusao=now()
                                WHERE id_acesso=%s AND cod_status_revogacao='SOLICITADA'""",
                            (e["id_acesso"],))
                        audit_service.registrar(cur, C.EV_REVOGADO, id_acesso=e["id_acesso"],
                                                detalhe="revogação efetivada no Unity Catalog")
                else:
                    cur.execute(
                        """UPDATE gestao_acesso.execucao_tecnica
                              SET cod_status_execucao=%s, desc_comando=%s, desc_erro=%s,
                                  datahora_fim=now(), num_tentativa=num_tentativa+1
                            WHERE id_execucao_tecnica=%s""",
                        (C.E_ERRO, comando, erro, e["id_execucao_tecnica"]))
                    if e["cod_tipo_operacao"] == C.OP_CONCESSAO:
                        cur.execute(
                            """UPDATE gestao_acesso.acesso SET cod_status_acesso=%s
                                WHERE id_acesso=%s""", (C.A_ERRO_EFETIVACAO, e["id_acesso"]))
                    else:
                        cur.execute(
                            """UPDATE gestao_acesso.revogacao_acesso SET cod_status_revogacao='ERRO'
                                WHERE id_acesso=%s AND cod_status_revogacao='SOLICITADA'""",
                            (e["id_acesso"],))
                    audit_service.registrar(cur, C.EV_ERRO_EFETIVACAO, id_acesso=e["id_acesso"],
                                            detalhe=(erro or "")[:1900])
                processadas += 1
        conn.commit()
    return processadas


def reprocessar(id_acesso):
    """Recria execução PENDENTE para um acesso em erro (RF-080)."""
    ac = _acesso(id_acesso)
    if not ac:
        return
    op = C.OP_CONCESSAO if ac["cod_status_acesso"] == C.A_ERRO_EFETIVACAO else C.OP_REVOGACAO
    with db.get_conn(autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO gestao_acesso.execucao_tecnica
                   (id_execucao_tecnica, id_acesso, cod_tipo_operacao, cod_status_execucao)
                   VALUES (%s,%s,%s,%s)""",
                (uuid.uuid4().hex, id_acesso, op, C.E_PENDENTE))
        conn.commit()

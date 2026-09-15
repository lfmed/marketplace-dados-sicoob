"""Ciclo de vida do acesso (RF-051..080), ancorado no ATIVO. Modelo oficial:
workflow={APP}, referência de acesso={ACC}, taxonomia={GOV}. Concessão por associação a grupo."""
import uuid
from datetime import datetime, timedelta, timezone

from app import db
from app import constants as C
from app.config import config
from app.schemas import GOV, ACC, APP
from app.services import audit_service, membership_executor, ativo_scope


def _anotar_sla(rows):
    agora = datetime.now(timezone.utc).replace(tzinfo=None)
    for r in rows:
        r["sla_restante_min"] = None
        r["sla_estourado"] = False
        if r.get("cod_status_acesso") == C.A_AGUARDANDO_EFETIVACAO and r.get("datahora_aprovacao"):
            prazo = r["datahora_aprovacao"] + timedelta(minutes=config.EFETIVACAO_SLA_MIN)
            delta = (prazo - agora).total_seconds() / 60.0
            r["sla_restante_min"] = int(delta)
            r["sla_estourado"] = delta < 0
    return rows


# ---------------- Criação do acesso (dentro da transação de aprovação do owner) ----------------
def criar_acesso(cur, solicitacao):
    """Cria o acesso (AGUARDANDO_EFETIVACAO) + execução técnica PENDENTE, ancorado no ativo."""
    id_acesso = uuid.uuid4().hex
    cur.execute(
        f"""INSERT INTO {APP}.acesso
           (id_acesso, id_solicitacao_acesso, cod_tipo_beneficiario, id_usuario_beneficiario,
            id_grupo_acesso, id_ativo_aisn, cod_tipo_acesso, cod_status_acesso)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
        (id_acesso, solicitacao["id_solicitacao_acesso"], solicitacao["cod_tipo_beneficiario"],
         solicitacao["id_usuario_beneficiario"], solicitacao["id_grupo_acesso"],
         solicitacao.get("id_ativo_aisn"), solicitacao["cod_tipo_acesso"], C.A_AGUARDANDO_EFETIVACAO))
    cur.execute(
        f"""INSERT INTO {APP}.execucao_tecnica
           (id_execucao_tecnica, id_acesso, cod_tipo_operacao, cod_status_execucao)
           VALUES (%s,%s,%s,%s)""",
        (uuid.uuid4().hex, id_acesso, C.OP_CONCESSAO, C.E_PENDENTE))
    audit_service.registrar(cur, C.EV_ACESSO_CRIADO, id_solicitacao=solicitacao["id_solicitacao_acesso"],
                            id_acesso=id_acesso, detalhe="acesso aprovado, aguardando efetivação")
    return id_acesso


# ---------------- Consultas ----------------
def acessos_do_usuario(id_usuario):
    """Acessos nominais do usuário + por grupo do qual é membro (RF-051/052, RN-025)."""
    rows = db.query(
        f"""SELECT a.*, at.nome_ativo, at.cod_tipo_ativo, {ativo_scope.ativo_cols("at")}, g.nome_grupo,
                  CASE WHEN a.cod_tipo_beneficiario='NOMINAL' THEN 'Nominal'
                       ELSE 'Grupo: ' || g.nome_grupo END AS origem
             FROM {APP}.acesso a
             LEFT JOIN {ACC}.ativo_aisn at ON at.id_ativo_aisn=a.id_ativo_aisn
                       AND at.bol_atual=true AND at.bol_excluido=false
             {ativo_scope.ativo_join("at")}
             LEFT JOIN {ACC}.grupo_acesso g ON g.id_grupo_acesso=a.id_grupo_acesso
                       AND g.bol_atual=true AND g.bol_excluido=false
            WHERE (a.cod_tipo_beneficiario='NOMINAL' AND a.id_usuario_beneficiario=%s)
               OR (a.cod_tipo_beneficiario='GRUPO' AND a.id_grupo_acesso IN (
                     SELECT id_grupo_acesso FROM {ACC}.grupo_acesso_membro
                      WHERE id_entidade=%s AND bol_atual=true AND bol_excluido=false))
            ORDER BY a.datahora_aprovacao DESC""",
        (id_usuario, id_usuario))
    return _anotar_sla(rows)


def acesso_padrao_owner(id_usuario):
    """RN-016: owners têm acesso padrão aos ATIVOS sob sua responsabilidade."""
    return db.query(
        f"""SELECT a.id_ativo_aisn, a.nome_ativo, a.cod_tipo_ativo, {ativo_scope.ativo_cols("a")}
             FROM {ACC}.ativo_proprietario p
             JOIN {ACC}.ativo_aisn a ON a.id_ativo_aisn=p.id_ativo_aisn
             {ativo_scope.ativo_join("a")}
            WHERE p.id_usuario_aisn=%s AND p.bol_atual=true AND p.bol_excluido=false
              AND a.bol_atual=true AND a.bol_excluido=false
            ORDER BY a.cod_tipo_ativo, a.nome_ativo""",
        (id_usuario,))


def acessos_do_owner(id_owner):
    """Acessos concedidos no escopo do owner do ativo (RF-040/041)."""
    rows = db.query(
        f"""SELECT a.*, at.nome_ativo, at.cod_tipo_ativo, {ativo_scope.ativo_cols("at")}, g.nome_grupo,
                  ubenef.nome_completo AS nome_beneficiario,
                  CASE WHEN a.cod_tipo_beneficiario='NOMINAL' THEN ubenef.nome_completo
                       ELSE 'Grupo: ' || g.nome_grupo END AS origem
             FROM {APP}.acesso a
             JOIN {ACC}.ativo_aisn at ON at.id_ativo_aisn=a.id_ativo_aisn
                  AND at.bol_atual=true AND at.bol_excluido=false
             {ativo_scope.ativo_join("at")}
             JOIN {ACC}.ativo_proprietario p
                  ON p.id_ativo_aisn=a.id_ativo_aisn AND p.bol_atual=true AND p.bol_excluido=false
             LEFT JOIN {ACC}.grupo_acesso g ON g.id_grupo_acesso=a.id_grupo_acesso
                       AND g.bol_atual=true AND g.bol_excluido=false
             LEFT JOIN {GOV}.usuario_aisn ubenef ON ubenef.id_usuario_aisn=a.id_usuario_beneficiario
                       AND ubenef.bol_atual=true AND ubenef.bol_excluido=false
            WHERE p.id_usuario_aisn=%s AND a.cod_status_acesso <> 'REVOGADO'
            ORDER BY a.datahora_aprovacao DESC""",
        (id_owner,))
    return _anotar_sla(rows)


def _acesso(id_acesso):
    return db.query_one(f"SELECT * FROM {APP}.acesso WHERE id_acesso=%s", (id_acesso,))


# ---------------- Revogação (RF-042/043, RF-072..075) ----------------
def solicitar_revogacao(id_acesso, id_owner, justificativa=None):
    from app.services.request_service import RegraNegocioError
    ac = _acesso(id_acesso)
    if not ac:
        raise RegraNegocioError("Acesso não encontrado.")
    escopo = db.query_one(
        f"""SELECT 1 AS ok FROM {ACC}.ativo_proprietario
             WHERE id_ativo_aisn=%s AND id_usuario_aisn=%s AND bol_atual=true AND bol_excluido=false""",
        (ac["id_ativo_aisn"], id_owner))
    if not escopo:
        raise RegraNegocioError("Você não é owner deste ativo (RN-026).")
    if ac["cod_status_acesso"] not in (C.A_EFETIVADO, C.A_ERRO_EFETIVACAO):
        raise RegraNegocioError("Somente acessos efetivados podem ser revogados.")
    with db.get_conn(autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""INSERT INTO {APP}.revogacao_acesso
                   (id_revogacao_acesso, id_acesso, id_usuario_solicitante, desc_justificativa,
                    cod_status_revogacao) VALUES (%s,%s,%s,%s,%s)""",
                (uuid.uuid4().hex, id_acesso, id_owner, justificativa, "SOLICITADA"))
            cur.execute(
                f"""INSERT INTO {APP}.execucao_tecnica
                   (id_execucao_tecnica, id_acesso, cod_tipo_operacao, cod_status_execucao)
                   VALUES (%s,%s,%s,%s)""",
                (uuid.uuid4().hex, id_acesso, C.OP_REVOGACAO, C.E_PENDENTE))
            audit_service.registrar(cur, C.EV_REVOGACAO_SOLICITADA,
                                    id_solicitacao=ac["id_solicitacao_acesso"], id_acesso=id_acesso,
                                    id_usuario=id_owner, detalhe=justificativa)
        conn.commit()


# ---------------- Worker de efetivação (RN-030/041) ----------------
def processar_execucoes_pendentes(limite=20):
    processadas = 0
    with db.get_conn(autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_xact_lock(918273645) AS got")
            if not cur.fetchone()["got"]:
                return 0
            cur.execute(
                f"""SELECT e.* FROM {APP}.execucao_tecnica e
                     WHERE e.cod_status_execucao=%s
                     ORDER BY e.datahora_inicio LIMIT %s""",
                (C.E_PENDENTE, limite))
            pendentes = cur.fetchall()

            for e in pendentes:
                acesso = _acesso(e["id_acesso"])
                ok, comando, erro = membership_executor.executar(e["cod_tipo_operacao"], acesso)
                if ok:
                    cur.execute(
                        f"""UPDATE {APP}.execucao_tecnica
                              SET cod_status_execucao=%s, desc_comando=%s, desc_erro=NULL,
                                  datahora_fim=now()
                            WHERE id_execucao_tecnica=%s""",
                        (C.E_EFETIVADA, comando, e["id_execucao_tecnica"]))
                    if e["cod_tipo_operacao"] == C.OP_CONCESSAO:
                        cur.execute(
                            f"""UPDATE {APP}.acesso
                                  SET cod_status_acesso=%s, datahora_efetivacao=now()
                                WHERE id_acesso=%s""", (C.A_EFETIVADO, e["id_acesso"]))
                        audit_service.registrar(cur, C.EV_EFETIVADO,
                                                id_solicitacao=acesso["id_solicitacao_acesso"],
                                                id_acesso=e["id_acesso"],
                                                detalhe="acesso efetivado: beneficiário associado ao grupo do ativo")
                    else:
                        cur.execute(
                            f"""UPDATE {APP}.acesso
                                  SET cod_status_acesso=%s, datahora_revogacao=now()
                                WHERE id_acesso=%s""", (C.A_REVOGADO, e["id_acesso"]))
                        cur.execute(
                            f"""UPDATE {APP}.revogacao_acesso
                                  SET cod_status_revogacao='EFETIVADA', datahora_conclusao=now()
                                WHERE id_acesso=%s AND cod_status_revogacao='SOLICITADA'""",
                            (e["id_acesso"],))
                        audit_service.registrar(cur, C.EV_REVOGADO,
                                                id_solicitacao=acesso["id_solicitacao_acesso"],
                                                id_acesso=e["id_acesso"],
                                                detalhe="revogação efetivada: beneficiário removido do grupo do ativo")
                else:
                    cur.execute(
                        f"""UPDATE {APP}.execucao_tecnica
                              SET cod_status_execucao=%s, desc_comando=%s, desc_erro=%s,
                                  datahora_fim=now(), num_tentativa=num_tentativa+1
                            WHERE id_execucao_tecnica=%s""",
                        (C.E_ERRO, comando, erro, e["id_execucao_tecnica"]))
                    if e["cod_tipo_operacao"] == C.OP_CONCESSAO:
                        cur.execute(
                            f"""UPDATE {APP}.acesso SET cod_status_acesso=%s
                                WHERE id_acesso=%s""", (C.A_ERRO_EFETIVACAO, e["id_acesso"]))
                    else:
                        cur.execute(
                            f"""UPDATE {APP}.revogacao_acesso SET cod_status_revogacao='ERRO'
                                WHERE id_acesso=%s AND cod_status_revogacao='SOLICITADA'""",
                            (e["id_acesso"],))
                    audit_service.registrar(cur, C.EV_ERRO_EFETIVACAO,
                                            id_solicitacao=acesso["id_solicitacao_acesso"],
                                            id_acesso=e["id_acesso"], detalhe=(erro or "")[:1900])
                processadas += 1
        conn.commit()
    return processadas


def reprocessar(id_acesso):
    ac = _acesso(id_acesso)
    if not ac:
        return
    op = C.OP_CONCESSAO if ac["cod_status_acesso"] == C.A_ERRO_EFETIVACAO else C.OP_REVOGACAO
    with db.get_conn(autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""INSERT INTO {APP}.execucao_tecnica
                   (id_execucao_tecnica, id_acesso, cod_tipo_operacao, cod_status_execucao)
                   VALUES (%s,%s,%s,%s)""",
                (uuid.uuid4().hex, id_acesso, op, C.E_PENDENTE))
        conn.commit()

"""Trilha de auditoria / histórico do ciclo de vida (RN-027, RF-056, RF-081..088).
Eventos no workflow ({APP}); breadcrumb/ativo em {ACC}/{GOV}."""
import uuid
from app import db
from app.schemas import GOV, ACC, APP
from app.services import ativo_scope


def registrar(cur, cod_evento, id_solicitacao=None, id_acesso=None, id_usuario=None, detalhe=None):
    cur.execute(
        f"""INSERT INTO {APP}.evento_ciclo_vida
           (id_evento_ciclo_vida, id_solicitacao_acesso, id_acesso, cod_evento,
            desc_detalhe, id_usuario_evento)
           VALUES (%s,%s,%s,%s,%s,%s)""",
        (uuid.uuid4().hex, id_solicitacao, id_acesso, cod_evento, detalhe, id_usuario),
    )


def eventos_da_solicitacao(id_solicitacao):
    # Eventos ligados à solicitação OU ao acesso dela (efetivação/revogação são gravadas
    # com id_acesso) — resgatados pela ligação acesso->solicitação (RF-081..088).
    return db.query(
        f"""SELECT e.*, u.nome_completo AS nome_usuario_evento
             FROM {APP}.evento_ciclo_vida e
             LEFT JOIN {GOV}.usuario_aisn u ON u.id_usuario_aisn=e.id_usuario_evento
            WHERE e.id_solicitacao_acesso=%s
               OR e.id_acesso IN (SELECT id_acesso FROM {APP}.acesso
                                   WHERE id_solicitacao_acesso=%s)
            ORDER BY e.datahora_evento""",
        (id_solicitacao, id_solicitacao),
    )


def auditoria_do_owner(id_owner):
    """Visão de auditoria restrita ao escopo do owner (RF-088, RN-026)."""
    return db.query(
        f"""SELECT s.id_solicitacao_acesso, s.cod_status_solicitacao, s.datahora_criacao,
                  s.cod_tipo_beneficiario, s.cod_tipo_acesso,
                  a.nome_ativo, a.cod_tipo_ativo, {ativo_scope.ativo_cols("a")},
                  usol.nome_completo AS solicitante,
                  ubenef.nome_completo AS beneficiario_nominal,
                  g.nome_grupo AS beneficiario_grupo,
                  ac.id_acesso, ac.cod_status_acesso, ac.datahora_efetivacao
             FROM {APP}.solicitacao_acesso s
             JOIN {ACC}.ativo_aisn a ON a.id_ativo_aisn=s.id_ativo_aisn
             {ativo_scope.ativo_join("a")}
             JOIN {ACC}.ativo_proprietario p
                  ON p.id_ativo_aisn=s.id_ativo_aisn AND p.bol_atual=true
             JOIN {GOV}.usuario_aisn usol ON usol.id_usuario_aisn=s.id_usuario_solicitante
             LEFT JOIN {GOV}.usuario_aisn ubenef ON ubenef.id_usuario_aisn=s.id_usuario_beneficiario
             LEFT JOIN {ACC}.grupo_acesso g ON g.id_grupo_acesso=s.id_grupo_acesso
             LEFT JOIN {APP}.acesso ac ON ac.id_solicitacao_acesso=s.id_solicitacao_acesso
            WHERE p.id_usuario_aisn=%s
            ORDER BY s.datahora_criacao DESC""",
        (id_owner,),
    )

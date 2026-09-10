"""Trilha de auditoria / histórico do ciclo de vida (RN-027, RF-056, RF-081..088)."""
import uuid
from app import db
from app.services import ativo_scope


def registrar(cur, cod_evento, id_solicitacao=None, id_acesso=None, id_usuario=None, detalhe=None):
    """Registra um evento usando um cursor de transação já aberto."""
    cur.execute(
        """INSERT INTO gestao_acesso.evento_ciclo_vida
           (id_evento_ciclo_vida, id_solicitacao_acesso, id_acesso, cod_evento,
            desc_detalhe, id_usuario_evento)
           VALUES (%s,%s,%s,%s,%s,%s)""",
        (uuid.uuid4().hex, id_solicitacao, id_acesso, cod_evento, detalhe, id_usuario),
    )


def eventos_da_solicitacao(id_solicitacao):
    # Eventos ligados diretamente à solicitação OU ao acesso dela: os eventos de
    # ciclo de vida do acesso (efetivação, revogação solicitada, revogado, erro)
    # são gravados com id_acesso, então precisam ser resgatados pela ligação
    # acesso→solicitação para aparecerem no histórico (RF-081..088).
    return db.query(
        """SELECT e.*, u.nome_completo AS nome_usuario_evento
             FROM gestao_acesso.evento_ciclo_vida e
             LEFT JOIN governanca.usuario_aisn u ON u.id_usuario_aisn=e.id_usuario_evento
            WHERE e.id_solicitacao_acesso=%s
               OR e.id_acesso IN (SELECT id_acesso FROM gestao_acesso.acesso
                                   WHERE id_solicitacao_acesso=%s)
            ORDER BY e.datahora_evento""",
        (id_solicitacao, id_solicitacao),
    )


def resumo_dominio():
    """Visão agregada por domínio (RF-089-ish / apoio gerencial).
    O domínio de cada ativo é derivado polimorficamente (ativo_scope), não copiado."""
    dom_expr = ativo_scope.dominio_id_expr()
    join = ativo_scope.ativo_join("a")
    return db.query(
        f"""SELECT d.id_dominio_informacao, d.nome_dominio,
                  (SELECT count(*) FROM governanca.ativo_aisn a {join}
                    WHERE a.bol_atual=true AND {dom_expr}=d.id_dominio_informacao) AS num_ativos,
                  (SELECT count(*) FROM gestao_acesso.acesso ac
                     JOIN governanca.ativo_aisn a ON a.id_ativo_aisn=ac.id_ativo_aisn {join}
                    WHERE {dom_expr}=d.id_dominio_informacao
                      AND ac.cod_status_acesso='EFETIVADO') AS acessos_ativos,
                  (SELECT count(*) FROM gestao_acesso.solicitacao_acesso so
                     JOIN governanca.ativo_aisn a ON a.id_ativo_aisn=so.id_ativo_aisn {join}
                    WHERE {dom_expr}=d.id_dominio_informacao
                      AND so.cod_status_solicitacao IN ('PENDENTE_AUTORIZACAO','AUTORIZADA')) AS solicitacoes_abertas
             FROM governanca.dominio_informacao d
            WHERE d.bol_atual=true
            ORDER BY d.nome_dominio""")


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
             FROM gestao_acesso.solicitacao_acesso s
             JOIN governanca.ativo_aisn a ON a.id_ativo_aisn=s.id_ativo_aisn
             {ativo_scope.ativo_join("a")}
             JOIN governanca.ativo_proprietario p
                  ON p.id_ativo_aisn=s.id_ativo_aisn AND p.bol_atual=true
             JOIN governanca.usuario_aisn usol ON usol.id_usuario_aisn=s.id_usuario_solicitante
             LEFT JOIN governanca.usuario_aisn ubenef ON ubenef.id_usuario_aisn=s.id_usuario_beneficiario
             LEFT JOIN governanca.grupo_acesso g ON g.id_grupo_acesso=s.id_grupo_acesso
             LEFT JOIN gestao_acesso.acesso ac ON ac.id_solicitacao_acesso=s.id_solicitacao_acesso
            WHERE p.id_usuario_aisn=%s
            ORDER BY s.datahora_criacao DESC""",
        (id_owner,),
    )

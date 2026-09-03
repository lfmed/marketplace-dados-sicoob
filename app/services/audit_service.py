"""Trilha de auditoria / histórico do ciclo de vida (RN-027, RF-056, RF-081..088)."""
import uuid
from app import db


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
    return db.query(
        """SELECT e.*, u.nome_completo AS nome_usuario_evento
             FROM gestao_acesso.evento_ciclo_vida e
             LEFT JOIN governanca.usuario_aisn u ON u.id_usuario_aisn=e.id_usuario_evento
            WHERE e.id_solicitacao_acesso=%s
            ORDER BY e.datahora_evento""",
        (id_solicitacao,),
    )


def resumo_dominio():
    """Visão agregada por domínio (RF-089-ish / apoio gerencial)."""
    return db.query(
        """SELECT d.id_dominio_informacao, d.nome_dominio,
                  count(DISTINCT i.id_iniciativa_aisn) AS num_iniciativas,
                  count(DISTINCT t.id_tabela_aisn) AS num_tabelas,
                  (SELECT count(*) FROM gestao_acesso.acesso a
                     WHERE a.id_iniciativa_aisn IN (
                        SELECT i2.id_iniciativa_aisn FROM governanca.iniciativa_aisn i2
                        JOIN governanca.subdominio_informacao s2 ON s2.id_subdominio_informacao=i2.id_subdominio_informacao
                        WHERE s2.id_dominio_informacao=d.id_dominio_informacao)
                       AND a.cod_status_acesso='EFETIVADO') AS acessos_ativos,
                  (SELECT count(*) FROM gestao_acesso.solicitacao_acesso so
                     WHERE so.id_iniciativa_aisn IN (
                        SELECT i3.id_iniciativa_aisn FROM governanca.iniciativa_aisn i3
                        JOIN governanca.subdominio_informacao s3 ON s3.id_subdominio_informacao=i3.id_subdominio_informacao
                        WHERE s3.id_dominio_informacao=d.id_dominio_informacao)
                       AND so.cod_status_solicitacao IN ('PENDENTE_AUTORIZACAO','AUTORIZADA')) AS solicitacoes_abertas
             FROM governanca.dominio_informacao d
             LEFT JOIN governanca.subdominio_informacao s ON s.id_dominio_informacao=d.id_dominio_informacao
             LEFT JOIN governanca.iniciativa_aisn i ON i.id_subdominio_informacao=s.id_subdominio_informacao
             LEFT JOIN governanca.iniciativa_camada_ambiente ica ON ica.id_iniciativa_aisn=i.id_iniciativa_aisn
             LEFT JOIN governanca.tabela_aisn t ON t.id_iniciativa_camada_ambiente=ica.id_iniciativa_camada_ambiente
            WHERE d.bol_atual=true
            GROUP BY d.id_dominio_informacao, d.nome_dominio
            ORDER BY d.nome_dominio""")


def auditoria_do_owner(id_owner):
    """Visão de auditoria restrita ao escopo do owner (RF-088, RN-026)."""
    return db.query(
        """SELECT s.id_solicitacao_acesso, s.cod_status_solicitacao, s.datahora_criacao,
                  s.cod_tipo_beneficiario, s.cod_tipo_acesso,
                  i.nome_iniciativa, amb.nome_ambiente,
                  usol.nome_completo AS solicitante,
                  ubenef.nome_completo AS beneficiario_nominal,
                  g.nome_grupo AS beneficiario_grupo,
                  ac.id_acesso, ac.cod_status_acesso, ac.datahora_efetivacao
             FROM gestao_acesso.solicitacao_acesso s
             JOIN governanca.iniciativa_aisn i ON i.id_iniciativa_aisn=s.id_iniciativa_aisn
             JOIN governanca.ambiente_aisn amb ON amb.id_ambiente_aisn=s.id_ambiente_aisn
             JOIN governanca.iniciativa_proprietario p
                  ON p.id_iniciativa_aisn=s.id_iniciativa_aisn AND p.bol_atual=true
             JOIN governanca.usuario_aisn usol ON usol.id_usuario_aisn=s.id_usuario_solicitante
             LEFT JOIN governanca.usuario_aisn ubenef ON ubenef.id_usuario_aisn=s.id_usuario_beneficiario
             LEFT JOIN governanca.grupo_acesso g ON g.id_grupo_acesso=s.id_grupo_acesso
             LEFT JOIN gestao_acesso.acesso ac ON ac.id_solicitacao_acesso=s.id_solicitacao_acesso
            WHERE p.id_usuario_aisn=%s
            ORDER BY s.datahora_criacao DESC""",
        (id_owner,),
    )

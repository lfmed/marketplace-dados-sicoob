"""Fábrica da aplicação Flask do Marketplace de Dados Sicoob."""
from flask import Flask

from app.config import config
from app import constants as C


def create_app():
    app = Flask(__name__)
    app.secret_key = config.SECRET_KEY

    # Blueprints
    from app.routes.main import bp as main_bp
    from app.routes.catalog import bp as catalog_bp
    from app.routes.requests import bp as requests_bp
    from app.routes.approvals import bp as approvals_bp
    from app.routes.accesses import bp as accesses_bp
    from app.routes.audit import bp as audit_bp
    for bp in (main_bp, catalog_bp, requests_bp, approvals_bp, accesses_bp, audit_bp):
        app.register_blueprint(bp)

    # Contexto global para os templates (usuário atual, papéis, labels)
    from app import identity
    from app.services import request_service

    @app.context_processor
    def inject_context():
        u = identity.usuario_atual()
        uid = u.get("id_usuario_aisn") if u else None
        papeis = {"gestor": False, "owner": False, "dono_grupo": False}
        grupos = []
        if uid:
            # gestor = 1ª etapa (autorização hierárquica). owner = 2ª etapa p/ pedido nominal
            # (dono do ativo). dono_grupo = 2ª etapa p/ pedido de grupo (dono do grupo).
            papeis["gestor"] = _e_gestor(uid)
            papeis["owner"] = _e_owner(uid)
            papeis["dono_grupo"] = _e_prop_grupo(uid)
            grupos = request_service.grupos_do_usuario(uid)
        proxy_ok = identity.proxy_liberado()
        return dict(usuario=u, papeis=papeis, meus_grupos=grupos,
                    enable_proxy=proxy_ok,
                    S=C, STATUS_SOL=C.STATUS_SOLICITACAO_LABEL,
                    STATUS_AC=C.STATUS_ACESSO_LABEL,
                    personas=(identity.listar_personas() if proxy_ok else []))

    # Provisionamento na subida (deploy sem CLI): cria o schema de workflow no Lakebase e
    # loga em detalhe cada ponto provisionado/verificado. Idempotente; nunca derruba a app.
    if config.AUTO_BOOTSTRAP:
        try:
            from app import bootstrap
            bootstrap.run()
        except Exception as e:  # bootstrap é best-effort — a app sobe mesmo assim
            print(f"[bootstrap] erro inesperado (app segue): {str(e)[:300]}", flush=True)

    # Worker de efetivação (desligável em testes via APP_DISABLE_WORKER=true)
    import os
    if os.getenv("APP_DISABLE_WORKER", "false").lower() not in ("1", "true", "yes"):
        from app import worker
        worker.start()

    return app


def _e_gestor(uid):
    from app import db
    from app.schemas import ACC
    return db.query_one(
        f"SELECT 1 AS ok FROM {ACC}.hierarquia_usuario WHERE id_gestor_aisn=%s "
        f"AND bol_atual=true AND bol_excluido=false LIMIT 1",
        (uid,)) is not None


def _e_prop_grupo(uid):
    # Proprietário de algum grupo exploratório (grupo_acesso_proprietario, em {ACC}) —
    # autoriza (aprovação hierárquica) os acessos pedidos em nome do grupo.
    from app import db
    from app.schemas import ACC
    return db.query_one(
        f"SELECT 1 AS ok FROM {ACC}.grupo_acesso_proprietario WHERE id_usuario_aisn=%s "
        f"AND bol_atual=true AND bol_excluido=false LIMIT 1",
        (uid,)) is not None


def _e_owner(uid):
    # Owner = proprietário de algum ATIVO (ativo_proprietario, em {ACC}), consistente com
    # aprovação/acessos/auditoria.
    from app import db
    from app.schemas import ACC
    return db.query_one(
        f"SELECT 1 AS ok FROM {ACC}.ativo_proprietario WHERE id_usuario_aisn=%s "
        f"AND bol_atual=true AND bol_excluido=false LIMIT 1",
        (uid,)) is not None


# Instância para o Gunicorn (app:app)
app = create_app()

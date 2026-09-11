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
        papeis = {"gestor": False, "owner": False}
        grupos = []
        if uid:
            papeis["gestor"] = _e_gestor(uid)
            papeis["owner"] = _e_owner(uid)
            grupos = request_service.grupos_do_usuario(uid)
        return dict(usuario=u, papeis=papeis, meus_grupos=grupos,
                    enable_proxy=config.ENABLE_PROXY,
                    S=C, STATUS_SOL=C.STATUS_SOLICITACAO_LABEL,
                    STATUS_AC=C.STATUS_ACESSO_LABEL,
                    personas=(identity.listar_personas() if config.ENABLE_PROXY else []))

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
        f"SELECT 1 AS ok FROM {ACC}.hierarquia_usuario WHERE id_gestor_aisn=%s AND bol_atual=true LIMIT 1",
        (uid,)) is not None


def _e_owner(uid):
    # Owner = proprietário de algum ATIVO (ativo_proprietario, em {ACC}), consistente com
    # aprovação/acessos/auditoria.
    from app import db
    from app.schemas import ACC
    return db.query_one(
        f"SELECT 1 AS ok FROM {ACC}.ativo_proprietario WHERE id_usuario_aisn=%s AND bol_atual=true LIMIT 1",
        (uid,)) is not None


# Instância para o Gunicorn (app:app)
app = create_app()

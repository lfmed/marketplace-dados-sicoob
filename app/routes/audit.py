from flask import Blueprint, render_template

from app import identity
from app.services import audit_service

bp = Blueprint("audit", __name__)


@bp.route("/auditoria")
def auditoria():
    u = identity.usuario_atual()
    uid = u.get("id_usuario_aisn") if u else None
    linhas = audit_service.auditoria_do_owner(uid) if uid else []
    return render_template("auditoria.html", linhas=linhas)

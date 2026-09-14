from flask import Blueprint, redirect, url_for, request, flash

from app import identity

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    return redirect(url_for("catalog.catalogo"))


@bp.route("/health")
def health():
    return {"status": "ok"}


@bp.route("/proxy", methods=["POST"])
def proxy():
    """Troca o usuário atuante (proxy) — só se liberado para o usuário real (D-005)."""
    if identity.proxy_liberado():
        uid = request.form.get("proxy_user_id")
        if uid:
            identity.definir_proxy(uid)
        else:
            identity.limpar_proxy()
    return redirect(request.referrer or url_for("catalog.catalogo"))

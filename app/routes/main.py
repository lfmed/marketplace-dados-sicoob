from flask import Blueprint, redirect, url_for, request, flash

from app import identity
from app.config import config

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    return redirect(url_for("catalog.catalogo"))


@bp.route("/health")
def health():
    return {"status": "ok"}


@bp.route("/proxy", methods=["POST"])
def proxy():
    """Troca o usuário atuante (proxy) — apenas em modo dev/demo (D-005)."""
    if config.ENABLE_PROXY:
        uid = request.form.get("proxy_user_id")
        if uid:
            identity.definir_proxy(uid)
        else:
            identity.limpar_proxy()
    return redirect(request.referrer or url_for("catalog.catalogo"))

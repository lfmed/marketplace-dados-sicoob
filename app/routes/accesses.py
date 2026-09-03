from flask import Blueprint, render_template, request, redirect, url_for, flash

from app import identity
from app.services import access_service
from app.services.request_service import RegraNegocioError

bp = Blueprint("accesses", __name__)


@bp.route("/meus-acessos")
def meus():
    u = identity.usuario_atual()
    uid = u.get("id_usuario_aisn") if u else None
    acessos = access_service.acessos_do_usuario(uid) if uid else []
    padrao_owner = access_service.acesso_padrao_owner(uid) if uid else []
    return render_template("meus_acessos.html", acessos=acessos, padrao_owner=padrao_owner)


@bp.route("/acessos-owner")
def owner():
    u = identity.usuario_atual()
    uid = u.get("id_usuario_aisn") if u else None
    acessos = access_service.acessos_do_owner(uid) if uid else []
    return render_template("acessos_owner.html", acessos=acessos)


@bp.route("/acesso/<id_acesso>/revogar", methods=["POST"])
def revogar(id_acesso):
    u = identity.usuario_atual()
    uid = u.get("id_usuario_aisn") if u else None
    justificativa = request.form.get("justificativa")
    try:
        access_service.solicitar_revogacao(id_acesso, uid, justificativa)
        flash("Revogação solicitada — será efetivada em instantes.", "ok")
    except RegraNegocioError as e:
        flash(str(e), "erro")
    return redirect(url_for("accesses.owner"))


@bp.route("/acesso/<id_acesso>/reprocessar", methods=["POST"])
def reprocessar(id_acesso):
    access_service.reprocessar(id_acesso)
    flash("Reprocessamento enfileirado.", "ok")
    return redirect(request.referrer or url_for("accesses.owner"))

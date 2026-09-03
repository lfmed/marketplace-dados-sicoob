from flask import Blueprint, render_template, request, redirect, url_for, flash

from app import identity
from app.services import approval_service
from app.services.request_service import RegraNegocioError

bp = Blueprint("approvals", __name__)


@bp.route("/aprovacoes")
def aprovacoes():
    u = identity.usuario_atual()
    uid = u.get("id_usuario_aisn") if u else None
    fila_g = approval_service.fila_gestor(uid) if uid else []
    fila_o = approval_service.fila_owner(uid) if uid else []
    return render_template("aprovacoes.html", fila_gestor=fila_g, fila_owner=fila_o)


@bp.route("/aprovacoes/<id_solicitacao>/gestor", methods=["POST"])
def decidir_gestor(id_solicitacao):
    u = identity.usuario_atual()
    uid = u.get("id_usuario_aisn") if u else None
    aprovar = request.form.get("acao") == "aprovar"
    justificativa = request.form.get("justificativa")
    try:
        approval_service.decidir_autorizacao(id_solicitacao, uid, aprovar, justificativa)
        flash("Autorização registrada." if aprovar else "Solicitação reprovada.", "ok")
    except RegraNegocioError as e:
        flash(str(e), "erro")
    return redirect(url_for("approvals.aprovacoes"))


@bp.route("/aprovacoes/<id_solicitacao>/owner", methods=["POST"])
def decidir_owner(id_solicitacao):
    u = identity.usuario_atual()
    uid = u.get("id_usuario_aisn") if u else None
    aprovar = request.form.get("acao") == "aprovar"
    justificativa = request.form.get("justificativa")
    try:
        approval_service.decidir_aprovacao_owner(id_solicitacao, uid, aprovar, justificativa)
        flash("Acesso aprovado — aguardando efetivação." if aprovar else "Solicitação reprovada.", "ok")
    except RegraNegocioError as e:
        flash(str(e), "erro")
    return redirect(url_for("approvals.aprovacoes"))

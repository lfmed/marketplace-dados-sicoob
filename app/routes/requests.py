from flask import Blueprint, render_template, request, redirect, url_for, flash, abort

from app import identity, constants as C
from app.services import request_service
from app.services.request_service import RegraNegocioError

bp = Blueprint("requests", __name__)


@bp.route("/solicitar", methods=["POST"])
def solicitar():
    u = identity.usuario_atual()
    if not u or not u.get("id_usuario_aisn"):
        flash("Usuário não identificado no catálogo.", "erro")
        return redirect(url_for("catalog.catalogo"))
    tipo_benef = request.form.get("tipo_beneficiario", C.B_NOMINAL)
    id_iniciativa = request.form.get("id_iniciativa")
    id_ambiente = request.form.get("id_ambiente")
    ica_ids = request.form.getlist("camadas")
    justificativa = request.form.get("justificativa")
    id_grupo = request.form.get("id_grupo_acesso") or None
    try:
        id_sol = request_service.criar_solicitacao(
            u, tipo_benef, id_iniciativa, id_ambiente, ica_ids,
            justificativa=justificativa, id_grupo=id_grupo)
        flash("Solicitação criada com sucesso.", "ok")
        return redirect(url_for("requests.detalhe", id_solicitacao=id_sol))
    except RegraNegocioError as e:
        flash(str(e), "erro")
        return redirect(url_for("catalog.iniciativa", id_iniciativa=id_iniciativa))


@bp.route("/minhas-solicitacoes")
def minhas():
    u = identity.usuario_atual()
    uid = u.get("id_usuario_aisn") if u else None
    sols = request_service.listar_do_usuario(uid) if uid else []
    return render_template("minhas_solicitacoes.html", solicitacoes=sols)


@bp.route("/solicitacao/<id_solicitacao>")
def detalhe(id_solicitacao):
    s = request_service.detalhe(id_solicitacao)
    if not s:
        abort(404)
    return render_template("solicitacao_detalhe.html", s=s)


@bp.route("/solicitacao/<id_solicitacao>/cancelar", methods=["POST"])
def cancelar(id_solicitacao):
    u = identity.usuario_atual()
    uid = u.get("id_usuario_aisn") if u else None
    try:
        request_service.cancelar(id_solicitacao, uid)
        flash("Solicitação cancelada.", "ok")
    except RegraNegocioError as e:
        flash(str(e), "erro")
    return redirect(url_for("requests.detalhe", id_solicitacao=id_solicitacao))

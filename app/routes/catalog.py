from flask import Blueprint, render_template, request, abort

from app.services import catalog_service, request_service
from app import identity

bp = Blueprint("catalog", __name__)


@bp.route("/catalogo")
def catalogo():
    id_dominio = request.args.get("dominio") or None
    id_subdominio = request.args.get("subdominio") or None
    busca = request.args.get("busca") or None
    iniciativas = catalog_service.listar_iniciativas(id_dominio, id_subdominio, busca)
    return render_template(
        "catalogo.html",
        iniciativas=iniciativas,
        dominios=catalog_service.listar_dominios(),
        subdominios=catalog_service.listar_subdominios(id_dominio),
        f_dominio=id_dominio, f_subdominio=id_subdominio, f_busca=busca,
        total=len(iniciativas),
    )


@bp.route("/iniciativa/<id_iniciativa>")
def iniciativa(id_iniciativa):
    ini = catalog_service.detalhe_iniciativa(id_iniciativa)
    if not ini:
        abort(404)
    u = identity.usuario_atual()
    uid = u.get("id_usuario_aisn") if u else None
    grupos = request_service.grupos_do_usuario(uid) if uid else []
    return render_template("iniciativa.html", ini=ini, meus_grupos=grupos)

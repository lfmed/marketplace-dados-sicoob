from flask import Blueprint, render_template, request, abort

from app.services import catalog_service, request_service
from app import identity

bp = Blueprint("catalog", __name__)


@bp.route("/catalogo")
def catalogo():
    id_dominio = request.args.get("dominio") or None
    id_subdominio = request.args.get("subdominio") or None
    busca = request.args.get("busca") or None
    grupo = request.args.get("grupo") or None
    # Filtro "Nível" (tipo do ativo) removido a pedido do cliente.
    if grupo:
        # Drill-down: ativos de um grupo ativo (o usuário pede acesso ativo por ativo).
        ativos = catalog_service.listar_ativos(id_dominio, id_subdominio, None, busca, grupo=grupo)
        desc = ativos[0].get("desc_grupo_ativo") if ativos else None
        return render_template(
            "grupo_ativo.html", ativos=ativos, grupo=grupo, desc=desc, total=len(ativos),
            f_dominio=id_dominio, f_subdominio=id_subdominio, f_busca=busca,
        )
    # Catálogo = cards de GRUPOS ATIVOS (nome + descrição); clicar abre os ativos do grupo.
    grupos = catalog_service.listar_grupos_ativos(id_dominio, id_subdominio, busca)
    return render_template(
        "catalogo.html",
        grupos=grupos,
        dominios=catalog_service.listar_dominios(),
        subdominios=catalog_service.listar_subdominios(id_dominio),
        f_dominio=id_dominio, f_subdominio=id_subdominio, f_busca=busca,
        total=len(grupos),
    )


@bp.route("/ativo/<id_ativo>")
def ativo(id_ativo):
    a = catalog_service.detalhe_ativo(id_ativo)
    if not a:
        abort(404)
    u = identity.usuario_atual()
    uid = u.get("id_usuario_aisn") if u else None
    grupos = request_service.grupos_do_usuario(uid) if uid else []
    return render_template("ativo.html", ativo=a, meus_grupos=grupos)

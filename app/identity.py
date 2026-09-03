"""Identidade do usuário corrente.

Produção: identidade via SSO do Databricks Apps (header `X-Forwarded-Email`).
Dev/protótipo: seletor "Atuar como (proxy)" (D-005) — permite navegar como qualquer
persona do seed para demonstrar solicitante/gestor/owner sem múltiplos logins.
"""
from flask import request, session

from app.config import config
from app import db


def _email_do_sso():
    # Databricks Apps injeta o e-mail do usuário autenticado neste header.
    return request.headers.get("X-Forwarded-Email") or request.headers.get("X-Forwarded-User")


def usuario_por_email(email):
    if not email:
        return None
    return db.query_one(
        "SELECT * FROM governanca.usuario_aisn WHERE lower(desc_email)=lower(%s) AND bol_atual=true",
        (email,),
    )


def usuario_por_id(uid):
    if not uid:
        return None
    return db.query_one(
        "SELECT * FROM governanca.usuario_aisn WHERE id_usuario_aisn=%s", (uid,)
    )


def listar_personas():
    """Personas disponíveis para o seletor de proxy (dev)."""
    return db.query(
        "SELECT id_usuario_aisn, nome_completo, desc_email FROM governanca.usuario_aisn "
        "WHERE bol_atual=true ORDER BY nome_completo"
    )


def usuario_atual():
    """Resolve o usuário corrente.

    1) Se há proxy ativo na sessão (dev), usa-o.
    2) Senão, usa o e-mail do SSO.
    3) Fallback dev: DEV_FALLBACK_EMAIL.
    """
    if config.ENABLE_PROXY and session.get("proxy_user_id"):
        u = usuario_por_id(session["proxy_user_id"])
        if u:
            return u
    email = _email_do_sso() or (config.DEV_FALLBACK_EMAIL if config.ENABLE_PROXY else None)
    u = usuario_por_email(email)
    if u:
        return u
    # Usuário autenticado não mapeado no catálogo: retorna um "stub" só com e-mail.
    if email:
        return {"id_usuario_aisn": None, "nome_completo": email, "desc_email": email}
    return None


def definir_proxy(uid):
    session["proxy_user_id"] = uid


def limpar_proxy():
    session.pop("proxy_user_id", None)

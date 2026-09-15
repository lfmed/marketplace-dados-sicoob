"""Identidade do usuário corrente.

Produção: identidade via SSO do Databricks Apps (header `X-Forwarded-Email`).
Dev/protótipo: seletor "Atuar como (proxy)" (D-005) — permite navegar como qualquer
persona do seed para demonstrar solicitante/gestor/owner sem múltiplos logins.
"""
from flask import request, session

from app.config import config
from app import db
from app.schemas import GOV


def _email_do_sso():
    # Databricks Apps injeta o e-mail do usuário autenticado neste header.
    return request.headers.get("X-Forwarded-Email") or request.headers.get("X-Forwarded-User")


def usuario_por_email(email):
    if not email:
        return None
    return db.query_one(
        f"SELECT * FROM {GOV}.usuario_aisn WHERE lower(desc_email)=lower(%s) "
        f"AND bol_atual=true AND bol_excluido=false",
        (email,),
    )


def usuario_por_id(uid):
    if not uid:
        return None
    return db.query_one(
        f"SELECT * FROM {GOV}.usuario_aisn WHERE id_usuario_aisn=%s "
        f"AND bol_atual=true AND bol_excluido=false", (uid,)
    )


def listar_personas():
    """Personas disponíveis para o seletor de proxy (dev)."""
    return db.query(
        f"SELECT id_usuario_aisn, nome_completo, desc_email FROM {GOV}.usuario_aisn "
        f"WHERE bol_atual=true AND bol_excluido=false ORDER BY nome_completo"
    )


def _email_real():
    """E-mail do usuário REAL (SSO), ignorando o proxy — base da whitelist de proxy.
    Em dev (sem header), cai no DEV_FALLBACK_EMAIL quando ENABLE_PROXY."""
    return _email_do_sso() or (config.DEV_FALLBACK_EMAIL if config.ENABLE_PROXY else None)


def proxy_liberado():
    """O proxy 'atuar como' está disponível para o usuário REAL? Exige ENABLE_PROXY e, se
    houver whitelist (APP_PROXY_ALLOWED_EMAILS), o e-mail real do SSO estar nela. Sem lista
    => liberado p/ todos (dev). Gateia pelo SSO, não pela persona assumida (não burla)."""
    if not config.ENABLE_PROXY:
        return False
    if not config.PROXY_ALLOWED_EMAILS:
        return True
    return (_email_real() or "").strip().lower() in config.PROXY_ALLOWED_EMAILS


def usuario_atual():
    """Resolve o usuário corrente.

    1) Se há proxy ativo na sessão E liberado p/ o usuário real, usa-o.
    2) Senão, usa o e-mail do SSO.
    3) Fallback dev: DEV_FALLBACK_EMAIL.
    """
    if proxy_liberado() and session.get("proxy_user_id"):
        u = usuario_por_id(session["proxy_user_id"])
        if u:
            return u
    email = _email_real()
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

"""Executor de CONCESSÃO/REVOGAÇÃO por ASSOCIAÇÃO A GRUPO (modelo do cliente).

O acesso é concedido incluindo o beneficiário no GRUPO DO ATIVO
(`ativo_aisn.id_grupo_acesso`), que detém o privilégio no Unity Catalog:
  - beneficiário NOMINAL  -> inclui o USUÁRIO (por e-mail/SP) como membro do grupo do ativo;
  - beneficiário GRUPO    -> inclui o GRUPO EXPLORATÓRIO do usuário (grupo aninhado).
Revogar = remover essa associação. Idempotente (RN-041).

Na CONCESSÃO também garante (best-effort) o GRANT do grupo do ativo nos objetos UC
(ver grant_executor.provisionar_ativo).

ESCOPO DOS GRUPOS (config.GROUPS_SCOPE): em PRODUÇÃO os grupos são de CONTA
(`account`) — geridos via AccountClient e principais válidos p/ GRANT no UC. Em DEV,
sem acesso à conta, são workspace-local (`workspace`). O cliente SCIM é resolvido por
`db.get_groups_client()`, que expõe a mesma interface nos dois escopos, então este
executor é agnóstico. Em produção, garanta que o SP do app tenha direito de gerente
dos grupos de conta (ou admin de conta).
"""
from app.config import config
from app import db
from app import constants as C
from app.services import grant_executor


def _grupo_do_ativo(id_ativo):
    return db.query_one(
        """SELECT g.id_grupo_acesso, g.nome_grupo
             FROM governanca.ativo_aisn a
             JOIN governanca.grupo_acesso g ON g.id_grupo_acesso=a.id_grupo_acesso
            WHERE a.id_ativo_aisn=%s""", (id_ativo,))


def _beneficiario(acesso):
    """(tipo_membro, chave) do membro a incluir: ('USUARIO', email) | ('GRUPO', nome_grupo)."""
    if acesso["cod_tipo_beneficiario"] == C.B_NOMINAL:
        u = db.query_one("SELECT desc_email FROM governanca.usuario_aisn WHERE id_usuario_aisn=%s",
                         (acesso["id_usuario_beneficiario"],))
        return "USUARIO", (u or {}).get("desc_email")
    g = db.query_one("SELECT nome_grupo FROM governanca.grupo_acesso WHERE id_grupo_acesso=%s",
                     (acesso["id_grupo_acesso"],))
    return "GRUPO", (g or {}).get("nome_grupo")


# ---------------- Integração SCIM (workspace/account groups) ----------------
def _ensure_group(w, nome_grupo):
    """Resolve (ou cria) o grupo do ativo no workspace/conta e retorna seu id SCIM."""
    existing = list(w.groups.list(filter=f'displayName eq "{nome_grupo}"'))
    if existing:
        return existing[0].id
    return w.groups.create(display_name=nome_grupo).id


def _resolver_membro(w, tipo_membro, chave):
    """id SCIM do membro. USUARIO tenta usuário (userName) e, se não achar, SP (applicationId)."""
    if tipo_membro == "GRUPO":
        gs = list(w.groups.list(filter=f'displayName eq "{chave}"'))
        return gs[0].id if gs else None
    us = list(w.users.list(filter=f'userName eq "{chave}"'))
    if us:
        return us[0].id
    sps = list(w.service_principals.list(filter=f'applicationId eq "{chave}"'))
    return sps[0].id if sps else None


def _e_membro(w, group_id, member_id):
    g = w.groups.get(group_id)
    return any((m.value == member_id) for m in (g.members or []))


def _add_member(w, group_id, member_id, iam):
    if _e_membro(w, group_id, member_id):
        return
    w.groups.patch(
        group_id,
        operations=[iam.Patch(op=iam.PatchOp.ADD, path="members", value=[{"value": member_id}])],
        schemas=[iam.PatchSchema.URN_IETF_PARAMS_SCIM_API_MESSAGES_2_0_PATCH_OP])


def _remove_member(w, group_id, member_id, iam):
    if not _e_membro(w, group_id, member_id):
        return
    w.groups.patch(
        group_id,
        operations=[iam.Patch(op=iam.PatchOp.REMOVE, path=f'members[value eq "{member_id}"]')],
        schemas=[iam.PatchSchema.URN_IETF_PARAMS_SCIM_API_MESSAGES_2_0_PATCH_OP])


def executar(operacao, acesso):
    """Executa a operação de associação. Retorna (ok: bool, comando: str, erro: str|None)."""
    grupo = _grupo_do_ativo(acesso.get("id_ativo_aisn"))
    if not grupo or not grupo.get("nome_grupo"):
        return False, "", "ativo sem grupo de acesso definido (id_grupo_acesso)"
    nome_grupo_ativo = grupo["nome_grupo"]
    tipo_membro, chave = _beneficiario(acesso)
    if not chave:
        return False, "", "beneficiário sem principal resolvido (usuário/grupo)"

    acao = "ADICIONAR" if operacao == C.OP_CONCESSAO else "REMOVER"
    linhas = [f"-- {acao} membro {tipo_membro}:{chave} <-> grupo do ativo {nome_grupo_ativo}"]

    if not config.GRANT_EXECUTE_REAL:
        return True, "\n".join(linhas) + "\n-- [SIMULADO: GRANT_EXECUTE_REAL=false]", None

    from app.db import get_groups_client
    from databricks.sdk.service import iam
    w = get_groups_client()  # AccountClient (produção) ou WorkspaceClient (dev)
    try:
        gid = _ensure_group(w, nome_grupo_ativo)
        if operacao == C.OP_CONCESSAO:
            # provisiona o grupo do ativo nos objetos UC (best-effort — não bloqueia a associação)
            ativo = db.query_one("SELECT * FROM governanca.ativo_aisn WHERE id_ativo_aisn=%s",
                                 (acesso["id_ativo_aisn"],))
            ok_p, cmds_p, err_p = grant_executor.provisionar_ativo(
                ativo, nome_grupo_ativo, acesso.get("cod_tipo_acesso"))
            linhas += [f"-- provisionamento do grupo: {'ok' if ok_p else 'aviso: ' + (err_p or '')}"]
            linhas += cmds_p
            mid = _resolver_membro(w, tipo_membro, chave)
            if not mid:
                return False, "\n".join(linhas), f"membro '{chave}' não encontrado no workspace/conta"
            _add_member(w, gid, mid, iam)
            linhas.append(f"-- membro associado (scim id {mid})")
        else:
            mid = _resolver_membro(w, tipo_membro, chave)
            if mid:
                _remove_member(w, gid, mid, iam)
                linhas.append(f"-- membro desassociado (scim id {mid})")
            else:
                linhas.append("-- membro já ausente (idempotente)")
        return True, "\n".join(linhas), None
    except Exception as e:
        return False, "\n".join(linhas), str(e)[:3900]

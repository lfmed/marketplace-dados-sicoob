"""Executor de CONCESSÃO/REVOGAÇÃO por ASSOCIAÇÃO A GRUPO (modelo oficial do cliente).

Concede incluindo o beneficiário no GRUPO DE ACESSO do ativo (`grupo_acesso`, resolvido via
`ativo_aisn.id_grupo_acesso`), que detém o privilégio no Unity Catalog. (O campo
`nome_grupo_ativo` é só rótulo de agrupamento de ativos p/ exibição — NÃO é o grupo de acesso.)
  - NOMINAL -> inclui o USUÁRIO (por e-mail/SP) como membro do grupo de acesso;
  - GRUPO   -> inclui o GRUPO exploratório do usuário (grupo aninhado).
Revogar = remover a associação. Idempotente (RN-041).

Provisionamento do GRANT do grupo (grant_executor.provisionar_ativo) só quando
config.PROVISION_GROUP_GRANT (dev). Em PRODUÇÃO o grupo já vem concedido pelo Motor ->
o app faz apenas a associação. Escopo dos grupos via db.get_groups_client()
(account em produção; workspace em dev). Requer o SP como gerente dos grupos (D-014).
"""
from app.config import config
from app import db
from app import constants as C
from app.schemas import GOV, ACC
from app.services import grant_executor


def _grupo_do_ativo(id_ativo):
    # O grupo que LIBERA o acesso é o grupo_acesso (via id_grupo_acesso) — é ele que detém
    # o privilégio no UC. O campo nome_grupo_ativo NÃO é o grupo de acesso: é só um rótulo de
    # agrupamento de ativos para exibição (correção do cliente). Nunca usar nome_grupo_ativo aqui.
    return db.query_one(
        f"""SELECT a.id_grupo_acesso, g.nome_grupo
             FROM {ACC}.ativo_aisn a
             JOIN {ACC}.grupo_acesso g ON g.id_grupo_acesso=a.id_grupo_acesso
            WHERE a.id_ativo_aisn=%s""", (id_ativo,))


def _beneficiario(acesso):
    """(tipo_membro, chave): ('USUARIO', email) | ('GRUPO', nome_grupo)."""
    if acesso["cod_tipo_beneficiario"] == C.B_NOMINAL:
        u = db.query_one(f"SELECT desc_email FROM {GOV}.usuario_aisn WHERE id_usuario_aisn=%s",
                         (acesso["id_usuario_beneficiario"],))
        return "USUARIO", (u or {}).get("desc_email")
    g = db.query_one(f"SELECT nome_grupo FROM {ACC}.grupo_acesso WHERE id_grupo_acesso=%s",
                     (acesso["id_grupo_acesso"],))
    return "GRUPO", (g or {}).get("nome_grupo")


# ---------------- Integração SCIM (workspace/account groups) ----------------
def _ensure_group(w, nome_grupo):
    existing = list(w.groups.list(filter=f'displayName eq "{nome_grupo}"'))
    if existing:
        return existing[0].id
    return w.groups.create(display_name=nome_grupo).id


def _resolver_membro(w, tipo_membro, chave):
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
    """Executa a associação. Retorna (ok: bool, comando: str, erro: str|None)."""
    grupo = _grupo_do_ativo(acesso.get("id_ativo_aisn"))
    if not grupo or not grupo.get("nome_grupo"):
        return False, "", "ativo sem grupo de acesso definido (nome_grupo_ativo)"
    nome_grupo_acesso = grupo["nome_grupo"]
    tipo_membro, chave = _beneficiario(acesso)
    if not chave:
        return False, "", "beneficiário sem principal resolvido (usuário/grupo)"

    acao = "ADICIONAR" if operacao == C.OP_CONCESSAO else "REMOVER"
    linhas = [f"-- {acao} membro {tipo_membro}:{chave} <-> grupo de acesso {nome_grupo_acesso}"]

    if not config.GRANT_EXECUTE_REAL:
        return True, "\n".join(linhas) + "\n-- [SIMULADO: GRANT_EXECUTE_REAL=false]", None

    from app.db import get_groups_client
    from databricks.sdk.service import iam
    w = get_groups_client()  # AccountClient (produção) ou WorkspaceClient (dev)
    try:
        gid = _ensure_group(w, nome_grupo_acesso)
        if operacao == C.OP_CONCESSAO:
            if config.PROVISION_GROUP_GRANT:  # dev: garante o GRANT do grupo (prod: Motor faz)
                ativo = db.query_one(f"SELECT * FROM {ACC}.ativo_aisn WHERE id_ativo_aisn=%s",
                                     (acesso["id_ativo_aisn"],))
                ok_p, cmds_p, err_p = grant_executor.provisionar_ativo(
                    ativo, nome_grupo_acesso, acesso.get("cod_tipo_acesso"))
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

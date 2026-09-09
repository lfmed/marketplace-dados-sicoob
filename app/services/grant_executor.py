"""Executor técnico de concessão/revogação no Unity Catalog, por NÍVEL do ativo.
Resolve o ativo → objetos UC concretos (SCHEMA/TABLE) e gera os GRANT/REVOKE:
TABELA → `... ON TABLE`; INICIATIVA/SUBDOMINIO/DOMINIO → `... ON SCHEMA` (expandido).
Nominal → `TO <email>`; grupo → `TO <nome_grupo>` (exige grupo de conta no UC, D-009).
Idempotente (RN-041)."""
from app.config import config
from app import db
from app import constants as C
from app.services.ativo_scope import objetos_do_ativo


def _principal(acesso):
    if acesso["cod_tipo_beneficiario"] == C.B_NOMINAL:
        u = db.query_one(
            "SELECT desc_email FROM governanca.usuario_aisn WHERE id_usuario_aisn=%s",
            (acesso["id_usuario_beneficiario"],))
        return (u or {}).get("desc_email")
    g = db.query_one(
        "SELECT nome_grupo FROM governanca.grupo_acesso WHERE id_grupo_acesso=%s",
        (acesso["id_grupo_acesso"],))
    return (g or {}).get("nome_grupo")


def _objetos_do_acesso(acesso):
    ativo = db.query_one("SELECT * FROM governanca.ativo_aisn WHERE id_ativo_aisn=%s",
                         (acesso.get("id_ativo_aisn"),))
    if not ativo:
        return []
    return objetos_do_ativo(ativo)


def _privilegios(cod_tipo_acesso):
    return C.TIPOS_ACESSO.get(cod_tipo_acesso or "LEITURA", ["SELECT"])


def montar_comandos(operacao, principal, objetos, privilegios=None):
    """Gera os comandos SQL de GRANT/REVOKE por objeto (SCHEMA ou TABLE).
    `objetos` = [{tipo, catalogo, schema, tabela}]. `principal` vai entre crases."""
    privilegios = privilegios or ["SELECT"]
    priv_str = ", ".join(privilegios)
    p = f"`{principal}`"
    cmds = []
    catalogos = {o["catalogo"] for o in objetos}
    schemas = {(o["catalogo"], o["schema"]) for o in objetos if o.get("schema")}
    if operacao == C.OP_CONCESSAO:
        # pré-requisitos de navegação (USE CATALOG / USE SCHEMA)
        for cat in catalogos:
            cmds.append(f"GRANT USE CATALOG ON CATALOG {cat} TO {p}")
        for cat, sch in schemas:
            cmds.append(f"GRANT USE SCHEMA ON SCHEMA {cat}.{sch} TO {p}")
    for o in objetos:
        if o["tipo"] == "TABLE":
            alvo = f'{o["catalogo"]}.{o["schema"]}.{o["tabela"]}'
            if operacao == C.OP_CONCESSAO:
                cmds.append(f"GRANT {priv_str} ON TABLE {alvo} TO {p}")
            else:
                cmds.append(f"REVOKE {priv_str} ON TABLE {alvo} FROM {p}")
        else:  # SCHEMA
            alvo = f'{o["catalogo"]}.{o["schema"]}'
            if operacao == C.OP_CONCESSAO:
                cmds.append(f"GRANT {priv_str} ON SCHEMA {alvo} TO {p}")
            else:
                cmds.append(f"REVOKE {priv_str}, USE SCHEMA ON SCHEMA {alvo} FROM {p}")
    return cmds


def executar(operacao, acesso):
    """Executa a operação. Retorna (ok: bool, comando: str, erro: str|None)."""
    principal = _principal(acesso)
    if not principal:
        return False, "", "beneficiário sem principal (e-mail/grupo) resolvido"
    objetos = _objetos_do_acesso(acesso)
    if not objetos:
        return False, "", "nenhum objeto UC resolvido para o ativo"
    cmds = montar_comandos(operacao, principal, objetos, _privilegios(acesso.get("cod_tipo_acesso")))
    comando_str = ";\n".join(cmds)

    if not config.GRANT_EXECUTE_REAL:
        return True, comando_str + "\n-- [SIMULADO: GRANT_EXECUTE_REAL=false]", None

    for cmd in cmds:
        try:
            db.run_uc_sql(cmd, warehouse_id=config.WAREHOUSE_ID)
        except Exception as e:
            msg = str(e)
            if operacao == C.OP_REVOGACAO and "PRINCIPAL_DOES_NOT_EXIST" in msg:
                continue
            return False, comando_str, msg[:3900]
    return True, comando_str, None

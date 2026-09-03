"""Executor técnico de concessão/revogação no Unity Catalog (D-003/D-008).

Concede/revoga no nível de SCHEMA (RN-003: sem granularidade por tabela). Nominal ->
`TO <email>`; grupo -> `TO <nome_grupo>` (exige grupo de conta no UC — ver D-009).
Idempotente (GRANT/REVOKE repetidos são inócuos, RN-041).
"""
from app.config import config
from app import db
from app import constants as C


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


def _schemas_do_acesso(id_acesso):
    return db.query(
        """SELECT DISTINCT ica.nome_catalogo, ica.nome_schema
             FROM gestao_acesso.acesso_camada acc
             JOIN governanca.iniciativa_camada_ambiente ica
                  ON ica.id_iniciativa_camada_ambiente=acc.id_iniciativa_camada_ambiente
            WHERE acc.id_acesso=%s AND ica.nome_schema IS NOT NULL""",
        (id_acesso,))


def _privilegios(cod_tipo_acesso):
    return C.TIPOS_ACESSO.get(cod_tipo_acesso or "LEITURA", ["SELECT"])


def montar_comandos(operacao, principal, schemas, privilegios=None):
    """Gera os comandos SQL de GRANT/REVOKE conforme o tipo de acesso (RF-014).
    `principal` entre crases. `privilegios` = lista (ex.: ['SELECT','MODIFY'])."""
    privilegios = privilegios or ["SELECT"]
    priv_str = ", ".join(privilegios)
    p = f"`{principal}`"
    cmds = []
    catalogos = {s["nome_catalogo"] for s in schemas}
    for cat in catalogos:
        if operacao == C.OP_CONCESSAO:
            cmds.append(f"GRANT USE CATALOG ON CATALOG {cat} TO {p}")
    for s in schemas:
        alvo = f'{s["nome_catalogo"]}.{s["nome_schema"]}'
        if operacao == C.OP_CONCESSAO:
            cmds.append(f"GRANT USE SCHEMA, {priv_str} ON SCHEMA {alvo} TO {p}")
        else:
            cmds.append(f"REVOKE {priv_str}, USE SCHEMA ON SCHEMA {alvo} FROM {p}")
    return cmds


def executar(operacao, acesso):
    """Executa a operação. Retorna (ok: bool, comando: str, erro: str|None)."""
    principal = _principal(acesso)
    if not principal:
        return False, "", "beneficiário sem principal (e-mail/grupo) resolvido"
    schemas = _schemas_do_acesso(acesso["id_acesso"])
    if not schemas:
        return False, "", "nenhum schema UC associado ao acesso"
    cmds = montar_comandos(operacao, principal, schemas, _privilegios(acesso.get("cod_tipo_acesso")))
    comando_str = ";\n".join(cmds)

    if not config.GRANT_EXECUTE_REAL:
        return True, comando_str + "\n-- [SIMULADO: GRANT_EXECUTE_REAL=false]", None

    for cmd in cmds:
        try:
            db.run_uc_sql(cmd, warehouse_id=config.WAREHOUSE_ID)
        except Exception as e:
            msg = str(e)
            # REVOKE de algo já ausente não é erro fatal
            if operacao == C.OP_REVOGACAO and "PRINCIPAL_DOES_NOT_EXIST" in msg:
                continue
            return False, comando_str, msg[:3900]
    return True, comando_str, None

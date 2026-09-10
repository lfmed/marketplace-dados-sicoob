"""Provisionamento do GRANT do UC no GRUPO DO ATIVO, por NÍVEL do ativo.

No modelo do cliente o acesso é concedido por ASSOCIAÇÃO A GRUPO (ver
membership_executor): quem detém o privilégio no Unity Catalog é o GRUPO DO ATIVO
(`ativo_aisn.id_grupo_acesso`). Este módulo resolve o ativo -> objetos UC (SCHEMA/
TABLE) e concede/garante esses privilégios ao grupo (idempotente, RN-041).
TABELA -> `ON TABLE`; ICA/SUBDOMINIO/DOMINIO -> `ON SCHEMA` (expandido).
"""
from app.config import config
from app import db
from app import constants as C
from app.services.ativo_scope import objetos_do_ativo


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


def provisionar_ativo(ativo, nome_grupo, cod_tipo_acesso="LEITURA"):
    """Garante que o GRUPO DO ATIVO tenha o privilégio nos objetos UC do ativo.
    Idempotente e best-effort: em produção este passo é do Motor/governança; em dev
    depende de o grupo ser principal de conta no UC (D-009). Retorna (ok, cmds, erro)."""
    objetos = objetos_do_ativo(ativo)
    if not objetos:
        return False, [], "nenhum objeto UC resolvido para o ativo"
    cmds = montar_comandos(C.OP_CONCESSAO, nome_grupo, objetos, _privilegios(cod_tipo_acesso))
    if not config.GRANT_EXECUTE_REAL:
        return True, cmds + ["-- [SIMULADO: GRANT_EXECUTE_REAL=false]"], None
    for cmd in cmds:
        try:
            db.run_uc_sql(cmd, warehouse_id=config.WAREHOUSE_ID)
        except Exception as e:
            return False, cmds, str(e)[:500]
    return True, cmds, None

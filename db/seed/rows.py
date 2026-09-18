"""Constrói as linhas do Motor (dicts) a partir de db/seed/data.py, no modelo OFICIAL
do cliente. Chaveado por NOME de tabela; reutilizado para popular as tabelas Delta.
"""
from db.seed import data
from app import constants as C


def _scd2(extra=None):
    base = {"datahora_inicio_validade": None, "datahora_fim_validade": None,
            "bol_atual": True, "bol_excluido": False}
    if extra:
        base.update(extra)
    return base


def _short(x, prefix):
    return x[len(prefix):] if x.startswith(prefix) else x


def build_rows(icas):
    import importlib
    gov_schema = importlib.import_module("db.seed.gov_schema")
    from app.config import config
    r = {t[1]: [] for t in gov_schema.GOV_TABLES}   # chaveado por nome de tabela

    # ---------- Taxonomia ----------
    for did, nome, desc in data.DOMINIOS:
        s = _short(did, "dom_")
        r["dominio_informacao"].append({
            "id_dominio_informacao": did, "nome_dominio": nome,
            "tag_dominio": f"dom.{s}", "sigla_dominio": s[:3].upper(),
            "desc_dominio": desc, **_scd2()})
    for sid, did, nome in data.SUBDOMINIOS:
        s = _short(sid, "sub_")
        r["subdominio_informacao"].append({
            "id_subdominio_informacao": sid, "id_dominio_informacao": did,
            "nome_subdominio": nome, "tag_subdominio": f"sub.{s}", "sigla_subdominio": s[:3].upper(),
            "desc_subdominio": nome, **_scd2()})
    for ini_id, sub, sigla, nome, desc, owner, camadas in data.INICIATIVAS:
        r["iniciativa_aisn"].append({
            "id_iniciativa_aisn": ini_id, "id_subdominio_informacao": sub,
            "sigla_iniciativa": sigla, "nome_iniciativa": nome, "desc_iniciativa": desc,
            "cod_status_iniciativa": "ATIVA", **_scd2()})
        r["iniciativa_proprietario"].append({
            "id_iniciativa_aisn": ini_id, "id_usuario_aisn": owner,
            "cod_tipo_proprietario": "OWNER", "bol_principal": True, **_scd2()})
    cam_nome = {c: n for c, n, _ in data.CAMADAS}
    for cid, nome, desc in data.CAMADAS:
        r["camada_aisn"].append({"id_camada_aisn": cid, "nome_camada": nome, "desc_camada": desc, **_scd2()})
    for aid, nome, desc in data.AMBIENTES:
        r["ambiente_aisn"].append({"id_ambiente_aisn": aid, "nome_ambiente": nome, "desc_ambiente": desc, **_scd2()})

    # ---------- ICA + tabelas (o alvo UC vive só em tabela_aisn) ----------
    cat = config.UC_CATALOG
    ini2sub = {i: sub for i, sub, *_ in data.INICIATIVAS}
    ini2nome = {i: nome for i, _s, _sig, nome, *_ in data.INICIATIVAS}
    ini2owner = {i: owner for i, _s, _sig, _n, _d, owner, _c in data.INICIATIVAS}
    sub2dom = {s: d for s, d, _ in data.SUBDOMINIOS}
    dom_nome = {d: n for d, n, _ in data.DOMINIOS}
    sub_nome = {s: n for s, _d, n in data.SUBDOMINIOS}
    for ica_id, ini_id, cam, amb, schema_uc in icas:
        r["iniciativa_camada_ambiente"].append({
            "id_iniciativa_camada_ambiente": ica_id, "id_iniciativa_aisn": ini_id,
            "id_camada_aisn": cam, "id_ambiente_aisn": amb,
            "nome_iniciativa_camada_ambiente": f"{ini2nome[ini_id]} · {cam_nome.get(cam, cam)}",
            "desc_iniciativa_camada_ambiente": f"Schema {schema_uc}",
            "bol_elegivel_acesso": True, **_scd2()})
        for nome_tab, _cols in data.TABELAS_EXEMPLO.get(cam, []):
            tid = f"tab_{ica_id}_{nome_tab}"
            r["tabela_aisn"].append({
                "id_tabela_aisn": tid, "id_iniciativa_camada_ambiente": ica_id,
                "nome_catalogo": cat, "nome_schema": schema_uc, "nome_tabela": nome_tab,
                "desc_tabela": f"{nome_tab} ({cam_nome.get(cam, cam)})", "cod_status_tabela": "ATIVA",
                "bol_elegivel_acesso": True, **_scd2()})

    # ---------- Combinações subdomínio/domínio × camada × ambiente ----------
    sub_combos, dom_combos = {}, {}
    for ica_id, ini_id, cam, amb, _schema in icas:
        sub = ini2sub[ini_id]; dom = sub2dom[sub]
        sub_combos.setdefault((sub, cam, amb), None)
        dom_combos.setdefault((dom, cam, amb), None)
    sca_id_of, dca_id_of = {}, {}
    for (sub, cam, amb) in sub_combos:
        sca_id = f"sca_{_short(sub, 'sub_')}_{_short(cam, 'cam_')}"
        sca_id_of[(sub, cam, amb)] = sca_id
        r["subdominio_camada_ambiente"].append({
            "id_subdominio_camada_ambiente": sca_id, "id_subdominio_informacao": sub,
            "id_camada_aisn": cam, "id_ambiente_aisn": amb,
            "nome_subdominio_camada_ambiente": f"{sub_nome[sub]} · {cam_nome.get(cam, cam)}",
            "desc_subdominio_camada_ambiente": f"{sub_nome[sub]} ({cam_nome.get(cam, cam)})",
            "bol_elegivel_acesso": True, **_scd2()})
    for (dom, cam, amb) in dom_combos:
        dca_id = f"dca_{_short(dom, 'dom_')}_{_short(cam, 'cam_')}"
        dca_id_of[(dom, cam, amb)] = dca_id
        r["dominio_camada_ambiente"].append({
            "id_dominio_camada_ambiente": dca_id, "id_dominio_informacao": dom,
            "id_camada_aisn": cam, "id_ambiente_aisn": amb,
            "nome_dominio_camada_ambiente": f"{dom_nome[dom]} · {cam_nome.get(cam, cam)}",
            "desc_dominio_camada_ambiente": f"{dom_nome[dom]} ({cam_nome.get(cam, cam)})",
            "bol_elegivel_acesso": True, **_scd2()})

    # ---------- Usuários / hierarquia / grupos exploratórios ----------
    for uid, nome, email, papel in data.USUARIOS:
        partes = nome.split(" ", 1)
        r["usuario_aisn"].append({
            "id_usuario_aisn": uid, "nome_usuario": email.split("@")[0], "nome_completo": nome,
            "desc_nome": nome, "desc_email": email, "desc_sobrenome": partes[1] if len(partes) > 1 else "",
            "cod_conta_databricks": None, "datahora_inicio_validade": None, "datahora_fim_validade": None,
            "bol_ativo": True, "bol_atual": True, "bol_excluido": False})
    for u, g in data.HIERARQUIA:
        r["hierarquia_usuario"].append({"id_usuario_aisn": u, "id_gestor_aisn": g, **_scd2()})
    for gid, nome_grupo, tipo_grupo, membros in data.GRUPOS:   # tipo_grupo: EXPLORATORIO etc.
        r["grupo_acesso"].append({
            "id_grupo_acesso": gid, "id_externo_grupo": None, "cod_conta_databricks": None,
            "nome_grupo": nome_grupo, "tipo_grupo": tipo_grupo, **_scd2()})
        for m in membros:
            r["grupo_acesso_membro"].append({
                "id_grupo_acesso": gid, "cod_conta_databricks": None, "tipo_entidade": "USUARIO",
                "id_entidade": m, "nome_entidade": m, **_scd2()})
    # Proprietário do grupo exploratório (autoriza acessos pedidos em nome do grupo).
    for gid, uid in data.GRUPO_PROPRIETARIOS.items():
        r["grupo_acesso_proprietario"].append({
            "id_grupo_acesso": gid, "id_usuario_aisn": uid,
            "cod_tipo_proprietario": "OWNER", "bol_principal": True, **_scd2()})

    # Proprietários de domínio/subdomínio (herdados p/ fidelidade ao modelo)
    sub2owner, dom2owner = {}, {}
    for i, sub, _sig, _n, _d, owner, _c in data.INICIATIVAS:
        sub2owner.setdefault(sub, owner)
    for s, d, _n in data.SUBDOMINIOS:
        if s in sub2owner:
            dom2owner.setdefault(d, sub2owner[s])
    for sid, did, _n in data.SUBDOMINIOS:
        if sub2owner.get(sid):
            r["subdominio_proprietario"].append({
                "id_subdominio_informacao": sid, "id_usuario_aisn": sub2owner[sid],
                "cod_tipo_proprietario": "OWNER", "bol_principal": True, **_scd2()})
    for did, _n, _d in data.DOMINIOS:
        if dom2owner.get(did):
            r["dominio_proprietario"].append({
                "id_dominio_informacao": did, "id_usuario_aisn": dom2owner[did],
                "cod_tipo_proprietario": "OWNER", "bol_principal": True, **_scd2()})

    # ---------- ATIVOS (gestao_acesso): id = PK da combinação de origem ----------
    # cod_tipo_ativo: 1=ICA, 2=TABELA, 3=SUBDOMINIO, 4=DOMINIO. 1 grupo por ativo.
    def _add_ativo(aid, tipo, nome, desc, owner):
        gid = f"grpat_{aid}"
        nome_grupo = f"{config.UC_SCHEMA_PREFIX}_at_{aid}"
        # Grupo de acesso do ativo — NÃO é exploratório (tipo_grupo nulo).
        r["grupo_acesso"].append({
            "id_grupo_acesso": gid, "id_externo_grupo": None, "cod_conta_databricks": None,
            "nome_grupo": nome_grupo, "tipo_grupo": None, **_scd2()})
        r["ativo_aisn"].append({
            "id_ativo_aisn": aid, "id_grupo_acesso": gid, "nome_grupo_ativo": nome_grupo,
            "desc_grupo_ativo": f"Grupo do ativo {nome}", "cod_tipo_ativo": tipo,
            "nome_ativo": nome, "desc_ativo": desc, "bol_elegivel_acesso": True, **_scd2()})
        if owner:
            r["ativo_proprietario"].append({
                "id_ativo_aisn": aid, "id_usuario_aisn": owner,
                "cod_tipo_proprietario": "OWNER", "bol_principal": True, **_scd2()})

    for ica_id, ini_id, cam, _amb, _schema in icas:                       # ICA (1)
        _add_ativo(ica_id, C.AT_ICA, f"{ini2nome[ini_id]} · {cam_nome.get(cam, cam)}",
                   f"Iniciativa/camada {ini2nome[ini_id]}", ini2owner[ini_id])
    for ica_id, ini_id, cam, _amb, _schema in icas:                       # TABELA (2)
        for nome_tab, _cols in data.TABELAS_EXEMPLO.get(cam, []):
            tid = f"tab_{ica_id}_{nome_tab}"
            _add_ativo(tid, C.AT_TABELA, f"{ini2nome[ini_id]} · {nome_tab}",
                       f"Tabela {nome_tab}", ini2owner[ini_id])
    for (sub, cam, amb), sca_id in sca_id_of.items():                     # SUBDOMINIO (3)
        _add_ativo(sca_id, C.AT_SUBDOMINIO, f"{sub_nome[sub]} · {cam_nome.get(cam, cam)}",
                   f"Subdomínio {sub_nome[sub]}", sub2owner.get(sub) or dom2owner.get(sub2dom[sub]))
    for (dom, cam, amb), dca_id in dca_id_of.items():                     # DOMINIO (4)
        _add_ativo(dca_id, C.AT_DOMINIO, f"{dom_nome[dom]} · {cam_nome.get(cam, cam)}",
                   f"Domínio {dom_nome[dom]}", dom2owner.get(dom))
    return r

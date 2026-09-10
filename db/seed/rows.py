"""Constrói as linhas de governança (dicts) a partir de db/seed/data.py.
Reutilizado para popular as tabelas Delta (fonte da verdade)."""
from db.seed import data


def _scd2(extra=None):
    base = {"datahora_inicio_validade": None, "datahora_fim_validade": None,
            "bol_atual": True, "bol_excluido": False}
    if extra:
        base.update(extra)
    return base


def build_rows(icas):
    r = {t[0]: [] for t in __import__("db.seed.gov_schema", fromlist=["GOV_TABLES"]).GOV_TABLES}

    for did, nome, desc in data.DOMINIOS:
        r["dominio_informacao"].append({"id_dominio_informacao": did, "nome_dominio": nome,
                                        "desc_dominio": desc, **_scd2()})
    for sid, did, nome in data.SUBDOMINIOS:
        r["subdominio_informacao"].append({"id_subdominio_informacao": sid, "id_dominio_informacao": did,
                                           "nome_subdominio": nome, "desc_subdominio": nome, **_scd2()})
    for ini_id, sub, nome, desc, owner, camadas in data.INICIATIVAS:
        r["iniciativa_aisn"].append({"id_iniciativa_aisn": ini_id, "id_subdominio_informacao": sub,
                                     "nome_iniciativa": nome, "desc_iniciativa": desc,
                                     "cod_status_iniciativa": "ATIVA", **_scd2()})
        r["iniciativa_proprietario"].append({"id_usuario_aisn": owner, "id_iniciativa_aisn": ini_id,
                                             "cod_tipo_proprietario": "OWNER", "bol_principal": True, **_scd2()})
    for cid, nome, desc in data.CAMADAS:
        r["camada_aisn"].append({"id_camada_aisn": cid, "nome_camada": nome, "desc_camada": desc, **_scd2()})
    for aid, nome, desc in data.AMBIENTES:
        r["ambiente_aisn"].append({"id_ambiente_aisn": aid, "nome_ambiente": nome, "desc_ambiente": desc, **_scd2()})

    cat = None
    for ica_id, ini_id, cam, amb, schema_uc in icas:
        from app.config import config
        cat = config.UC_CATALOG
        r["iniciativa_camada_ambiente"].append({
            "id_iniciativa_camada_ambiente": ica_id, "id_iniciativa_aisn": ini_id,
            "id_camada_aisn": cam, "id_ambiente_aisn": amb, "nome_catalogo": cat,
            "nome_schema": schema_uc, "bol_elegivel_acesso": True, **_scd2()})
        for nome_tab, _cols in data.TABELAS_EXEMPLO.get(cam, []):
            tid = f"tab_{ica_id}_{nome_tab}"
            r["tabela_aisn"].append({
                "id_tabela_aisn": tid, "id_iniciativa_camada_ambiente": ica_id,
                "nome_catalogo": cat, "nome_schema": schema_uc, "nome_tabela": nome_tab,
                "desc_tabela": f"{nome_tab} ({cam})", "cod_status_tabela": "ATIVA",
                "bol_elegivel_acesso": True, **_scd2()})

    for uid, nome, email, papel in data.USUARIOS:
        partes = nome.split(" ", 1)
        r["usuario_aisn"].append({
            "id_usuario_aisn": uid, "nome_usuario": email.split("@")[0], "nome_completo": nome,
            "desc_nome": nome, "desc_email": email, "desc_sobrenome": partes[1] if len(partes) > 1 else "",
            "cod_conta_databricks": None, "datahora_inicio_validade": None, "datahora_fim_validade": None,
            "bol_ativo": True, "bol_atual": True, "bol_excluido": False})
    for u, g in data.HIERARQUIA:
        r["hierarquia_usuario"].append({"id_usuario_aisn": u, "id_gestor_aisn": g, **_scd2()})
    for gid, nome_grupo, tipo, membros in data.GRUPOS:
        r["grupo_acesso"].append({"id_grupo_acesso": gid, "id_externo_grupo": None,
                                  "cod_conta_databricks": None, "nome_grupo": nome_grupo,
                                  "tipo_grupo": tipo, **_scd2()})
        for m in membros:
            r["grupo_acesso_membro"].append({"id_grupo_acesso": gid, "id_entidade": m,
                                             "tipo_entidade": "USUARIO", "nome_entidade": m,
                                             "cod_conta_databricks": None, **_scd2()})

    # ---------- Derivação dos ATIVOS (unidade liberável do marketplace) ----------
    # Modelo do cliente: id_ativo_aisn É a PK da entidade de origem; cod_tipo_ativo
    # (numérico) diz onde resolver (1=ICA, 2=TABELA, 3=SUBDOMINIO, 4=DOMINIO). SEM colunas
    # denormalizadas: breadcrumb/alvo UC são navegados (ativo_scope). Cada ativo tem seu
    # PRÓPRIO grupo (least-privilege): o grupo é concedido exatamente nos objetos do ativo
    # e é nele que o usuário/grupo do solicitante é incluído. Em produção vem do Motor.
    from app import constants as C
    from app.config import config
    ini2nome = {i: nome for i, _sub, nome, *_ in data.INICIATIVAS}
    ini2owner = {i: owner for i, _s, _n, _d, owner, _c in data.INICIATIVAS}
    cam_nome = {c: n for c, n, _ in data.CAMADAS}
    sub2owner, dom2owner = {}, {}
    for i, sub, _n, _d, owner, _c in data.INICIATIVAS:
        sub2owner.setdefault(sub, owner)
    for s, d, _n in data.SUBDOMINIOS:
        if s in sub2owner:
            dom2owner.setdefault(d, sub2owner[s])

    def _add_ativo(aid, tipo, nome, desc, owner):
        # grupo próprio do ativo (nome UC = alvo do GRANT e da associação de membros)
        gid = f"grpat_{aid}"
        r["grupo_acesso"].append({
            "id_grupo_acesso": gid, "id_externo_grupo": None, "cod_conta_databricks": None,
            "nome_grupo": f"{config.UC_SCHEMA_PREFIX}_at_{aid}", "tipo_grupo": "ATIVO", **_scd2()})
        r["ativo_aisn"].append({
            "id_ativo_aisn": aid, "id_grupo_acesso": gid, "cod_tipo_ativo": tipo,
            "nome_ativo": nome, "desc_ativo": desc, "bol_elegivel_acesso": True, **_scd2()})
        if owner:
            r["ativo_proprietario"].append({"id_usuario_aisn": owner, "id_ativo_aisn": aid,
                                            "cod_tipo_proprietario": "OWNER", "bol_principal": True, **_scd2()})

    # DOMINIO (tipo 4) — id = id_dominio_informacao
    for did, nome, desc in data.DOMINIOS:
        _add_ativo(did, C.AT_DOMINIO, nome, desc, dom2owner.get(did))
    # SUBDOMINIO (tipo 3) — id = id_subdominio_informacao
    for sid, did, nome in data.SUBDOMINIOS:
        _add_ativo(sid, C.AT_SUBDOMINIO, nome, f"Subdomínio {nome}",
                   sub2owner.get(sid) or dom2owner.get(did))
    # ICA (tipo 1) — id = id_iniciativa_camada_ambiente (1 schema, por D-008)
    for ica_id, ini_id, cam, _amb, schema_uc in icas:
        _add_ativo(ica_id, C.AT_ICA, f"{ini2nome[ini_id]} · {cam_nome.get(cam, cam)}",
                   f"Schema {schema_uc} ({cam_nome.get(cam, cam)})", ini2owner[ini_id])
    # TABELA (tipo 2) — id = id_tabela_aisn
    for ica_id, ini_id, cam, _amb, _schema_uc in icas:
        for nome_tab, _cols in data.TABELAS_EXEMPLO.get(cam, []):
            tid = f"tab_{ica_id}_{nome_tab}"
            _add_ativo(tid, C.AT_TABELA, f"{ini2nome[ini_id]} · {nome_tab}",
                       f"Tabela {nome_tab} ({cam_nome.get(cam, cam)})", ini2owner[ini_id])
    return r

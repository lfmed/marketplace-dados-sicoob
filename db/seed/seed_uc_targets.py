#!/usr/bin/env python3
"""Cria os ALVOS reais de GRANT no Unity Catalog:
  - grupos UC (com o usuário real como membro) para grants de grupo
  - 1 schema UC por unidade funcional (iniciativa+camada+ambiente) + tabelas de exemplo
Esses objetos são referenciados por iniciativa_camada_ambiente.nome_schema / tabela_aisn.
"""
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.config import config  # noqa: E402
from app.db import get_client  # noqa: E402
from scripts.uc_sql import run_sql  # noqa: E402
from db.seed import data  # noqa: E402


def short(x, prefix):
    return x[len(prefix):] if x.startswith(prefix) else x


def build_icas():
    """(id_ica, id_ini, id_cam, id_amb, nome_schema_uc)."""
    icas = []
    amb = data.AMBIENTES[0][0]
    for ini in data.INICIATIVAS:
        ini_id, _sub, _nome, _desc, _owner, camadas = ini
        for cam in camadas:
            ica_id = f"ica_{short(ini_id,'ini_')}_{short(cam,'cam_')}"
            schema_uc = f"{config.UC_SCHEMA_PREFIX}_{short(ini_id,'ini_')}_{short(cam,'cam_')}"
            icas.append((ica_id, ini_id, cam, amb, schema_uc))
    return icas


def create_uc_groups():
    w = get_client()
    me = w.current_user.me()
    from databricks.sdk.service import iam
    for gid, nome_grupo, tipo, membros in data.GRUPOS:
        try:
            existing = list(w.groups.list(filter=f'displayName eq "{nome_grupo}"'))
            g = existing[0] if existing else w.groups.create(display_name=nome_grupo)
            member_ids = {m.value for m in (g.members or [])}
            if me.id not in member_ids:
                w.groups.patch(
                    g.id,
                    operations=[iam.Patch(op=iam.PatchOp.ADD, path="members", value=[{"value": me.id}])],
                    schemas=[iam.PatchSchema.URN_IETF_PARAMS_SCIM_API_MESSAGES_2_0_PATCH_OP])
            print(f"  grupo UC OK: {nome_grupo}")
        except Exception as e:
            print(f"  [aviso] grupo {nome_grupo}: {str(e)[:120]}")


def create_uc_schema(ica):
    ica_id, ini_id, cam, amb, schema_uc = ica
    cat = config.UC_CATALOG
    run_sql(f"CREATE SCHEMA IF NOT EXISTS {cat}.{schema_uc} COMMENT 'Marketplace Sicoob - {ica_id}'")
    for nome_tab, cols in data.TABELAS_EXEMPLO.get(cam, []):
        run_sql(f"CREATE TABLE IF NOT EXISTS {cat}.{schema_uc}.{nome_tab} ({cols})")
    return schema_uc


def create_uc_objects():
    icas = build_icas()
    print(f"Criando {len(icas)} schemas UC (alvos de GRANT) + tabelas...")
    create_uc_groups()
    ok = 0
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(create_uc_schema, ica): ica for ica in icas}
        for fut in as_completed(futs):
            try:
                fut.result(); ok += 1
            except Exception as e:
                print(f"  [erro] {futs[fut][4]}: {str(e)[:150]}")
    print(f"  schemas UC criados/ok: {ok}/{len(icas)}")
    return icas


if __name__ == "__main__":
    create_uc_objects()

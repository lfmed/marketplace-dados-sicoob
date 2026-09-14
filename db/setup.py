#!/usr/bin/env python3
"""Provisionamento COMPLETO e reproduzível do banco em QUALQUER workspace.

  python -m db.setup --mode dev                 # protótipo: sync controlado + seed sintético
  python -m db.setup --mode native --no-seed    # cliente: synced tables NATIVAS, sem seed

Distribuição (nomes de schema PARAMETRIZÁVEIS via config):
  {GOV} governanca      -> taxonomia (Motor de Governança)               [dev: mirror]
  {ACC} gestao_acesso   -> referência de acesso (Motor de Acesso)        [dev: mirror]
  {APP} marketplace_app -> workflow do App (solicitação/aprovação/...)   [SEMPRE nativo]

Passos (idempotentes):
  1. Cria o schema {APP} + tabelas de workflow (sempre).
  2. [dev] Cria os schemas mirror {GOV} e {ACC} no Lakebase.
  3. [seed] Cria tabelas Delta de governanca+gestao_acesso sintéticas + carrega seed +
     cria os alvos UC (schemas/tabelas reais de exemplo + grupos).
  4. Popula {GOV}/{ACC} no Lakebase: sync controlado (dev) OU synced tables nativas (native).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Este entrypoint provisiona pelos seus próprios passos; o import da app NÃO deve disparar
# o bootstrap-no-boot (evita ✗ de mirror espúrios num banco recém-criado) nem o worker.
os.environ.setdefault("AUTO_BOOTSTRAP_APP_SCHEMA", "false")
os.environ.setdefault("APP_DISABLE_WORKER", "true")

from app.config import config  # noqa: E402
from app.db import run_script  # noqa: E402

DDL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ddl")


def apply_ddl(fname):
    from app.schemas import substitute_schemas
    with open(os.path.join(DDL_DIR, fname), encoding="utf-8") as fh:
        # {GOV}/{ACC}/{APP} -> nomes de config (regra compartilhada — app/schemas.py).
        sql = substitute_schemas(fh.read())
    run_script(sql)
    print(f"  DDL aplicado: {fname}")


def main():
    ap = argparse.ArgumentParser(description="Provisiona o banco do Marketplace de Dados.")
    ap.add_argument("--mode", choices=["dev", "native"], default="dev",
                    help="dev = sync controlado (protótipo); native = synced tables (cliente).")
    ap.add_argument("--seed", action=argparse.BooleanOptionalAction, default=None,
                    help="Cria dados sintéticos (governança fake + schemas UC de teste). "
                         "Default: liga em --mode dev, desliga em --mode native.")
    args = ap.parse_args()
    seed = (args.mode == "dev") if args.seed is None else args.seed

    print(f"=== SETUP DB (mode={args.mode}, seed={seed}) ===")
    print(f"[1] schema do App ({config.SCHEMA_APP}) — workflow (sempre)")
    apply_ddl("03_app.sql")
    if args.mode == "dev":
        print(f"[2] schemas mirror ({config.SCHEMA_GOVERNANCA} + {config.SCHEMA_GESTAO})")
        apply_ddl("01_governanca.sql")
        apply_ddl("02_gestao_acesso.sql")

    if seed:
        print("[3] tabelas Delta (governanca + gestao_acesso) sintéticas + seed")
        from db.seed.delta_governanca import main as build_delta
        build_delta()
        print("[3b] alvos de GRANT sintéticos no UC (grupos + schemas por iniciativa/camada)")
        from db.seed.seed_uc_targets import create_uc_objects
        create_uc_objects()
    else:
        print("[3] seed DESLIGADO — usando governança e schemas reais do cliente.")

    print("[4] popular governanca + gestao_acesso no Lakebase")
    if args.mode == "dev":
        from db.sync.sync_governanca import sync
        sync()
    else:
        from db.native_sync_setup import main as native_setup
        native_setup()

    print("=== SETUP concluído ===")


if __name__ == "__main__":
    main()

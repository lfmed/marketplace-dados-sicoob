#!/usr/bin/env python3
"""Provisionamento COMPLETO e reproduzível do banco em QUALQUER workspace.
Atende ao requisito de manter todo o código de banco pronto para o cliente.

  python -m db.setup --mode dev      # protótipo: sync controlado Delta->Lakebase
  python -m db.setup --mode native   # cliente: synced tables NATIVAS (requer CREATE CATALOG)

Passos (idempotentes):
  1. Cria schemas Lakebase: gestao_acesso (sempre) + governanca (só em --mode dev,
     pois em native o schema governanca é criado pelas synced tables).
  2. Cria tabelas Delta de governança (fonte da verdade) + carrega seed sintético.
  3. Cria alvos reais de GRANT no UC (grupos + 1 schema por iniciativa+camada).
  4. Popula governanca no Lakebase: sync controlado (dev) OU synced tables nativas (native).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import run_script  # noqa: E402

DDL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ddl")


def apply_ddl(fname):
    with open(os.path.join(DDL_DIR, fname), encoding="utf-8") as fh:
        run_script(fh.read())
    print(f"  DDL aplicado: {fname}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["dev", "native"], default="dev")
    args = ap.parse_args()

    print(f"=== SETUP DB (mode={args.mode}) ===")
    print("[1] schemas Lakebase")
    apply_ddl("02_gestao_acesso.sql")
    if args.mode == "dev":
        apply_ddl("01_governanca.sql")

    print("[2] tabelas Delta de governança + seed")
    from db.seed.delta_governanca import main as build_delta
    build_delta()

    print("[3] alvos de GRANT no UC (grupos + schemas por iniciativa/camada)")
    from db.seed.seed_uc_targets import create_uc_objects
    create_uc_objects()

    print("[4] popular governanca no Lakebase")
    if args.mode == "dev":
        from db.sync.sync_governanca import sync
        sync()
    else:
        from db.native_sync_setup import main as native_setup
        native_setup()

    print("=== SETUP concluído ===")


if __name__ == "__main__":
    main()

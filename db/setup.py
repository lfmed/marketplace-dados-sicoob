#!/usr/bin/env python3
"""Provisionamento COMPLETO e reproduzível do banco em QUALQUER workspace.
Atende ao requisito de manter todo o código de banco pronto para o cliente.

  python -m db.setup --mode dev                 # protótipo: sync controlado + seed sintético
  python -m db.setup --mode native --no-seed    # cliente: synced tables NATIVAS, sem seed

Passos (idempotentes):
  1. Cria schemas Lakebase: gestao_acesso (sempre) + governanca (só em --mode dev,
     pois em native o schema governanca é criado pelas synced tables).
  2. [seed] Cria tabelas Delta de governança sintéticas (fonte da verdade) + carrega seed.
  3. [seed] Cria alvos de GRANT sintéticos no UC (grupos + 1 schema por iniciativa+camada).
  4. Popula governanca no Lakebase: sync controlado (dev) OU synced tables nativas (native).

O seed (passos 2 e 3) é OPCIONAL: --seed / --no-seed. Default: liga em --mode dev,
desliga em --mode native. Em produção use --no-seed — a governança vem do Motor de
Governança do cliente e os alvos de grant são os schemas reais já existentes.
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
    ap = argparse.ArgumentParser(description="Provisiona o banco do Marketplace de Dados.")
    ap.add_argument("--mode", choices=["dev", "native"], default="dev",
                    help="dev = sync controlado (protótipo); native = synced tables (cliente).")
    ap.add_argument("--seed", action=argparse.BooleanOptionalAction, default=None,
                    help="Cria dados sintéticos (governança fake + schemas UC de teste). "
                         "Default: liga em --mode dev, desliga em --mode native.")
    args = ap.parse_args()
    # Resolve o default do seed conforme o modo (dev semeia; native/produção não).
    seed = (args.mode == "dev") if args.seed is None else args.seed

    print(f"=== SETUP DB (mode={args.mode}, seed={seed}) ===")
    print("[1] schemas Lakebase")
    apply_ddl("02_gestao_acesso.sql")
    if args.mode == "dev":
        apply_ddl("01_governanca.sql")

    if seed:
        print("[2] tabelas Delta de governança sintéticas + seed")
        from db.seed.delta_governanca import main as build_delta
        build_delta()

        print("[3] alvos de GRANT sintéticos no UC (grupos + schemas por iniciativa/camada)")
        from db.seed.seed_uc_targets import create_uc_objects
        create_uc_objects()
    else:
        print("[2-3] seed DESLIGADO — usando governança e schemas reais do cliente "
              "(nada sintético é criado).")

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

#!/usr/bin/env python3
"""Gera o SQL avulso do schema de workflow do app (marketplace_app) a partir de
db/ddl/03_app.sql — FONTE ÚNICA de DDL. Para quem preferir rodar direto no editor SQL do
Lakebase (rota SEM CLI e sem subir o app): basta colar o arquivo gerado.

Uso:
  python scripts/gen_app_sql.py                       # nomes padrão -> db/ddl/marketplace_app.sql
  python scripts/gen_app_sql.py --app meu_schema_app  # troca o nome do schema do app
  python scripts/gen_app_sql.py -o /caminho/saida.sql
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
# Codegen puro: o import de app.schemas NÃO deve disparar o bootstrap-no-boot nem o worker.
os.environ.setdefault("AUTO_BOOTSTRAP_APP_SCHEMA", "false")
os.environ.setdefault("APP_DISABLE_WORKER", "true")

SRC = os.path.join(ROOT, "db", "ddl", "03_app.sql")
DEFAULT_OUT = os.path.join(ROOT, "db", "ddl", "marketplace_app.sql")

CABECALHO = """-- =====================================================================
-- Marketplace de Dados — schema de WORKFLOW do app ({app})
-- GERADO por scripts/gen_app_sql.py a partir de db/ddl/03_app.sql (NÃO editar à mão).
--
-- Rota SEM CLI: cole este arquivo no editor SQL do Lakebase (Postgres) e execute como o
-- role/owner do database. Idempotente (CREATE ... IF NOT EXISTS) — pode rodar de novo.
-- Alternativa recomendada: a própria app cria este schema no boot (AUTO_BOOTSTRAP_APP_SCHEMA=true).
-- Os schemas de leitura {gov}/{acc} são synced tables do Motor e NÃO são criados aqui.
-- =====================================================================

"""


def gerar(app="marketplace_app", gov="governanca", acc="gestao_acesso"):
    from app.schemas import substitute_schemas  # regra de substituição compartilhada
    with open(SRC, encoding="utf-8") as fh:
        sql = substitute_schemas(fh.read(), gov=gov, acc=acc, app=app)
    return CABECALHO.format(app=app, gov=gov, acc=acc) + sql


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--app", default="marketplace_app", help="nome do schema de workflow")
    ap.add_argument("--gov", default="governanca", help="nome do schema de governança (leitura)")
    ap.add_argument("--acc", default="gestao_acesso", help="nome do schema de gestão de acesso (leitura)")
    ap.add_argument("-o", "--out", default=DEFAULT_OUT, help="arquivo de saída")
    args = ap.parse_args()
    conteudo = gerar(args.app, args.gov, args.acc)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(conteudo)
    print(f"SQL gerado: {args.out}  (schema do app = {args.app})")


if __name__ == "__main__":
    main()

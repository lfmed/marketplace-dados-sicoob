"""Garante que o SQL avulso db/ddl/marketplace_app.sql NÃO fica defasado da fonte
db/ddl/03_app.sql. Se este teste falhar, rode: python scripts/gen_app_sql.py

Não toca em rede/banco — é puramente sobre arquivos (roda mesmo sem Lakebase)."""
import os

from scripts.gen_app_sql import gerar, DEFAULT_OUT


def test_marketplace_app_sql_em_sincronia():
    assert os.path.exists(DEFAULT_OUT), "db/ddl/marketplace_app.sql ausente — rode scripts/gen_app_sql.py"
    esperado = gerar()  # regenera a partir de db/ddl/03_app.sql (nomes padrão)
    with open(DEFAULT_OUT, encoding="utf-8") as fh:
        commitado = fh.read()
    assert commitado == esperado, (
        "db/ddl/marketplace_app.sql está defasado de db/ddl/03_app.sql. "
        "Rode: python scripts/gen_app_sql.py")

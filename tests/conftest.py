"""Fixtures dos testes de integração (rodam contra o Lakebase/UC de dev já semeado).
Requer DATABRICKS_CONFIG_PROFILE (default DEFAULT) e o seed aplicado (python -m db.setup --mode dev).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABRICKS_CONFIG_PROFILE", "DEFAULT")
os.environ.setdefault("APP_DISABLE_WORKER", "true")

import pytest  # noqa: E402
from app import db  # noqa: E402


@pytest.fixture(scope="session")
def conectado():
    try:
        db.query_one("SELECT 1 AS ok")
    except Exception as e:
        pytest.skip(f"sem conexão Lakebase/seed: {e}")
    return True


def limpar_solicitacao(id_sol):
    """Remove uma solicitação e tudo que dela deriva (para testes idempotentes)."""
    if not id_sol:
        return
    ac = db.query_one("SELECT id_acesso FROM gestao_acesso.acesso WHERE id_solicitacao_acesso=%s", (id_sol,))
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            if ac:
                aid = ac["id_acesso"]
                for t in ("execucao_tecnica", "revogacao_acesso", "acesso_camada"):
                    cur.execute(f"DELETE FROM gestao_acesso.{t} WHERE id_acesso=%s", (aid,))
                cur.execute("DELETE FROM gestao_acesso.evento_ciclo_vida WHERE id_acesso=%s", (aid,))
                cur.execute("DELETE FROM gestao_acesso.acesso WHERE id_acesso=%s", (aid,))
            cur.execute("DELETE FROM gestao_acesso.evento_ciclo_vida WHERE id_solicitacao_acesso=%s", (id_sol,))
            for t in ("autorizacao_hierarquica", "aprovacao_owner", "solicitacao_camada"):
                cur.execute(f"DELETE FROM gestao_acesso.{t} WHERE id_solicitacao_acesso=%s", (id_sol,))
            cur.execute("DELETE FROM gestao_acesso.solicitacao_acesso WHERE id_solicitacao_acesso=%s", (id_sol,))


@pytest.fixture
def usuario():
    def _u(uid):
        return db.query_one("SELECT * FROM governanca.usuario_aisn WHERE id_usuario_aisn=%s", (uid,))
    return _u

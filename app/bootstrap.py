"""Provisionamento na SUBIDA do app — deploy SEM a CLI databricks.

Quando o cliente não consegue usar a CLI (ex.: firewall) mas o repositório já está
clonado no Databricks, o deploy passa a ser feito pela UI de Apps apontando para a pasta
do repo. Este módulo faz o resto NO PRÓPRIO APP, no startup, usando a conexão que a app já
tem com o Lakebase (service principal, server-side — o firewall local não interfere):

  1. Cria o schema de WORKFLOW do app ({APP} = marketplace_app) e suas tabelas.
     Idempotente (CREATE ... IF NOT EXISTS) e serializado entre os workers do gunicorn por
     um advisory lock do Postgres (evita corrida no boot com múltiplos processos).
  2. VERIFICA (só-leitura) os schemas espelho do Motor ({GOV} governanca, {ACC}
     gestao_acesso): existência + contagem das tabelas-chave. A app NÃO cria esses schemas
     — são synced tables mantidas pelo Motor do cliente; aqui apenas confirmamos que a app
     as enxerga (diagnóstico no log).

Emite LOGS DETALHADOS em stdout (aparecem em `databricks apps logs <app>`) marcando cada
ponto provisionado/verificado, para o cliente ver facilmente o que aconteceu na subida.

Também roda avulso — útil de um NOTEBOOK no repo já clonado (rota sem CLI). Desligue o
bootstrap-no-import e o worker antes de importar a app, para provisionar UMA vez:

    %pip install -r requirements.txt
    import os
    os.environ["AUTO_BOOTSTRAP_APP_SCHEMA"] = "false"   # evita rodar no import da app
    os.environ["APP_DISABLE_WORKER"] = "true"           # não precisamos do worker só p/ provisionar
    from app.bootstrap import run
    run()

Ou como script:  python app/bootstrap.py
"""
import os
import sys

# chave arbitrária p/ pg_advisory_lock — serializa o DDL entre workers gunicorn no boot
_LOCK_KEY = 728041
_TAG = f"[bootstrap pid={os.getpid()}]"
_RULE = "─" * 64


def _log(msg, mark="•"):
    print(f"{_TAG} {mark} {msg}", flush=True)


def _ddl_app_sql():
    """Lê db/ddl/03_app.sql (fonte única de DDL) e substitui os placeholders pelos nomes
    de schema de config, via app.schemas.substitute_schemas (regra compartilhada)."""
    from app.schemas import substitute_schemas
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "db", "ddl", "03_app.sql"), encoding="utf-8") as fh:
        return substitute_schemas(fh.read())


def _tables_in(schema):
    from app import db
    rows = db.query(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema=%s ORDER BY table_name", (schema,))
    return [r["table_name"] for r in rows]


def banner():
    from app.config import config
    _log(_RULE, " ")
    _log("PROVISIONAMENTO NA SUBIDA DO APP — Marketplace de Dados", "»")
    _log(f"catálogo Delta do Motor      GOV_CATALOG          = {config.GOV_CATALOG}")
    _log(f"schema governança (leitura)  SCHEMA_GOVERNANCA    = {config.SCHEMA_GOVERNANCA}")
    _log(f"schema gestão acesso (leit.) SCHEMA_GESTAO        = {config.SCHEMA_GESTAO}")
    _log(f"schema workflow app (R/W)    SCHEMA_APP           = {config.SCHEMA_APP}")
    _log(f"Lakebase endpoint            LAKEBASE_ENDPOINT    = {config.LAKEBASE_ENDPOINT}")
    _log(f"Lakebase database            LAKEBASE_DBNAME      = {config.LAKEBASE_DBNAME}")
    _log(f"escopo de grupos             GROUPS_SCOPE         = {config.GROUPS_SCOPE}")
    _log(f"provisiona GRANT grupo (dev) PROVISION_GROUP_GRANT= {config.PROVISION_GROUP_GRANT}")
    _log(_RULE, " ")


def check_connection():
    from app import db
    _log("[1/3] conectando ao Lakebase (Postgres, via service principal)…", "»")
    try:
        who = db.query_one("SELECT current_user AS u, current_database() AS d, version() AS v")
        _log(f"conexão OK — usuário={who['u']} database={who['d']}", "✓")
        _log(f"  {who['v'].split(' on ')[0]}")
        return True
    except Exception as e:
        _log(f"FALHA ao conectar no Lakebase: {str(e)[:300]}", "✗")
        _log("  verifique LAKEBASE_ENDPOINT/LAKEBASE_DBNAME e o role Postgres do SP do app", " ")
        return False


def ensure_app_schema():
    """Cria o schema de workflow do app + tabelas (idempotente, com advisory lock)."""
    from app import db
    from app.config import config
    app_schema = config.SCHEMA_APP
    _log(f"[2/3] provisionando schema de workflow '{app_schema}' (idempotente)…", "»")
    antes = set(_tables_in(app_schema))
    if antes:
        _log(f"  '{app_schema}' já tem {len(antes)} tabelas — aplicando DDL para garantir tudo")
    ddl = _ddl_app_sql()
    with db.get_conn(autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(%s)", (_LOCK_KEY,))
            try:
                cur.execute(ddl)
            finally:
                cur.execute("SELECT pg_advisory_unlock(%s)", (_LOCK_KEY,))
    depois = _tables_in(app_schema)
    novas = [t for t in depois if t not in antes]
    for t in depois:
        _log(f"  tabela {app_schema}.{t} — {'＋ CRIADA' if t in novas else 'já existia'}")
    _log(f"schema '{app_schema}' pronto: {len(depois)} tabelas "
         f"({len(novas)} criadas agora)", "✓")
    return True


# schemas espelho do Motor + tabelas-chave que a app precisa enxergar (só verificação)
_MIRRORS = (
    ("governanca (Motor de Governança)", "SCHEMA_GOVERNANCA",
     ["dominio_informacao", "iniciativa_aisn", "tabela_aisn", "usuario_aisn"]),
    ("gestao_acesso (Motor de Acesso)", "SCHEMA_GESTAO",
     ["ativo_aisn", "grupo_acesso", "ativo_proprietario", "hierarquia_usuario"]),
)


def verify_mirrors():
    """Verifica (só-leitura) os schemas espelho do Motor: presença + contagem das
    tabelas-chave. A app não os cria — são synced tables do cliente."""
    from app import db
    from app.config import config
    _log("[3/3] verificando schemas espelho do Motor (só-leitura, não são criados aqui)…", "»")
    ok = True
    for rotulo, attr, chaves in _MIRRORS:
        schema = getattr(config, attr)
        tabs = set(_tables_in(schema))
        if not tabs:
            _log(f"schema espelho '{schema}' ({rotulo}) VAZIO/ausente — as synced tables do "
                 f"Motor precisam existir para a app funcionar", "✗")
            ok = False
            continue
        _log(f"schema espelho '{schema}' ({rotulo}): {len(tabs)} tabelas visíveis", "✓")
        for t in chaves:
            if t not in tabs:
                _log(f"  {schema}.{t}: AUSENTE (esperada pela app)", "✗")
                ok = False
                continue
            try:
                n = db.query_one(f"SELECT count(*) AS n FROM {schema}.{t}")["n"]
                _log(f"  {schema}.{t}: {n} linhas", "✓")
            except Exception as e:
                _log(f"  {schema}.{t}: erro ao ler ({str(e)[:120]})", "✗")
                ok = False
    return ok


def run():
    """Orquestra o provisionamento. Nunca levanta exceção (a app sobe mesmo se algo falhar);
    os problemas ficam explícitos no log com marca ✗."""
    banner()
    if not check_connection():
        _log("BOOTSTRAP ABORTADO (sem Lakebase). A app sobe assim mesmo; corrija a conexão "
             "e reinicie.", "✗")
        return False
    ok_app = False
    try:
        ok_app = ensure_app_schema()
    except Exception as e:
        _log(f"FALHA ao provisionar o schema do app: {str(e)[:300]}", "✗")
        _log("  o SP do app precisa poder CREATE SCHEMA/TABLE no database Lakebase", " ")
    try:
        ok_mirror = verify_mirrors()
    except Exception as e:
        _log(f"FALHA ao verificar schemas espelho: {str(e)[:300]}", "✗")
        ok_mirror = False
    _log(_RULE, " ")
    if ok_app and ok_mirror:
        _log("PROVISIONAMENTO OK — app pronto para atender.", "✓")
    else:
        _log("PROVISIONAMENTO PARCIAL — reveja os ✗ acima (a app subiu mesmo assim).", "✗")
    _log(_RULE, " ")
    return ok_app


if __name__ == "__main__":
    # Provisiona UMA vez: desliga o bootstrap-no-import e o worker ANTES de importar a app.
    os.environ["AUTO_BOOTSTRAP_APP_SCHEMA"] = "false"
    os.environ["APP_DISABLE_WORKER"] = "true"
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    run()

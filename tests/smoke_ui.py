import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("APP_DISABLE_WORKER", "true")

from app import app  # noqa: E402
app.testing = True
c = app.test_client()

falhas = 0

def check(path, must=None, proxy=None):
    global falhas
    if proxy is not None:
        with c.session_transaction() as s:
            s["proxy_user_id"] = proxy
    r = c.get(path)
    ok = r.status_code == 200
    body = r.get_data(as_text=True)
    extra = ""
    if must and ok:
        miss = [m for m in must if m not in body]
        extra = (" | OK conteúdo" if not miss else f" | FALTA: {miss}")
        if miss: ok = False
    print(f"{'OK ' if ok else 'ERR'} {r.status_code} {path}{extra}")
    if not ok:
        falhas += 1
        print("   ", body[:500])

check("/catalogo", ["Catálogo de Produtos de Dados", "Limpar filtros"], proxy="u_ana")
check("/catalogo?dominio=dom_cliente")
check("/minhas-solicitacoes")
check("/aprovacoes", ["Aprovações"])
check("/meus-acessos")
check("/acessos-owner")
check("/auditoria")
check("/health")

print("SMOKE UI:", "✅ OK" if falhas == 0 else f"❌ {falhas} falha(s)")
sys.exit(1 if falhas else 0)

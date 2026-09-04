# Demo — Marketplace de Dados Sicoob (vídeo)

Vídeo anotado do fluxo ponta a ponta, gravado **no app publicado no Databricks Apps** e
no **Unity Catalog real** da workspace.

- **Arquivo:** `reel.mp4` (H.264, 1600×1000, ~38s, ~6 MB — toca inline no Slack/e-mail).
- **Storyboard:** `scenes.json` (legendas, destaques). Frames em `frames/`.

## Roteiro (8 cenas)
1. Catálogo de dados — consumidor explora por domínio/subdomínio.
2. **Unity Catalog ANTES** — o service principal consumidor NÃO tem acesso ao schema.
3. Solicitação — iniciativa, camada, tipo de acesso e justificativa.
4. 1ª aprovação — gestor imediato.
5. 2ª aprovação — owner do dado.
6. Acesso efetivado automaticamente pelo app (SLA 30 min).
7. **Unity Catalog DEPOIS** — SELECT concedido ao service principal (auditável).
8. Revogação pelo owner — acesso removido do Unity Catalog.

> A demo usa um **service principal** (`sp-consumidor-marketplace`) como beneficiário
> justamente para o antes/depois ficar limpo: um SP não herda o `ALL PRIVILEGES` de
> "account users", então a linha `SELECT` aparece e some de forma inequívoca no catálogo.

## Como reproduzir/re-renderizar
```bash
PY=$(bash .../ui-demo-reel/scripts/setup_venv.sh)      # requer ffmpeg
RENDER=$(bash .../ui-demo-reel/scripts/resolve_engine.sh)
"$PY" "$RENDER" --scenes demo/scenes.json               # regera demo/reel.mp4
```
Para editar legendas/destaques, ajuste `scenes.json` e re-renderize (sem recapturar).

## Como enviar ao cliente
O `reel.mp4` é um arquivo local — anexe por e-mail, arraste no Slack (toca inline) ou
suba no seu Drive. (Nada é publicado automaticamente; o envio é feito por você.)

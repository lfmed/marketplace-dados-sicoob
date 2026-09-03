"""Worker de background: efetiva execuções pendentes (concessão/revogação) periodicamente.
RN-030 exige efetivação em até 30 min; aqui o poll é curto para demo. O advisory lock
em processar_execucoes_pendentes garante segurança com múltiplos workers (gunicorn)."""
import threading
import time

_started = False
_lock = threading.Lock()


def _loop(intervalo):
    from app.services import access_service
    while True:
        try:
            access_service.processar_execucoes_pendentes()
        except Exception as e:  # nunca derruba o worker
            print(f"[worker] erro: {str(e)[:200]}")
        time.sleep(intervalo)


def start(intervalo=15):
    global _started
    with _lock:
        if _started:
            return
        _started = True
    t = threading.Thread(target=_loop, args=(intervalo,), daemon=True, name="efetivacao-worker")
    t.start()
    print(f"[worker] iniciado (poll={intervalo}s)")

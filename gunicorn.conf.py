import os

# Databricks Apps injeta DATABRICKS_APP_PORT (default 8000). Nunca usar 8080.
bind = f"0.0.0.0:{os.environ.get('DATABRICKS_APP_PORT', '8000')}"
workers = int(os.environ.get("GUNICORN_WORKERS", "2"))
threads = int(os.environ.get("GUNICORN_THREADS", "4"))
timeout = 120
graceful_timeout = 30
loglevel = os.environ.get("GUNICORN_LOGLEVEL", "info")

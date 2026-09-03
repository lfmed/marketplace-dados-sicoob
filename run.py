"""Execução local (dev): DATABRICKS_CONFIG_PROFILE=DEFAULT python run.py
No Databricks Apps usa-se gunicorn (ver app.yaml)."""
import os
from app import app

if __name__ == "__main__":
    port = int(os.getenv("DATABRICKS_APP_PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=os.getenv("FLASK_DEBUG", "false").lower() == "true")

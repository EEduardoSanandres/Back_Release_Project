# run.py (o tu entrypoint)
import logging
import uvicorn
import subprocess
import sys

from backend.app.database import app

try:
    # Actualiza pip
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
    # Instala requisitos del proyecto
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "backend/requirements.txt"]);
except subprocess.CalledProcessError as e:
    print(f"⚠️ Error instalando dependencias: {e}", file=sys.stderr)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print(app.docs_url)
    uvicorn.run(
        "backend.app.database:app",   # la ruta a tu FastAPI
        host="127.0.0.1",
        port=8000,
        reload=True
    )

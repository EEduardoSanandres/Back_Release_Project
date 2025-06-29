# run.py (o tu entrypoint)
import logging
import uvicorn
from backend.app.database import app

print("🚀 run.py arrancado")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.info("📑 Rutas disponibles:")
    for route in app.routes:
        logging.info(f"{','.join(route.methods):10s} {route.path}")
    uvicorn.run(
        "backend.app.database:app",   # la ruta a tu FastAPI
        host="127.0.0.1",
        port=8000,
        reload=True
    )

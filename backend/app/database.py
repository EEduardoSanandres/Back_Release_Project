# File: backend/app/database.py
import os, logging
from dotenv import load_dotenv
from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient         # Motor async :contentReference[oaicite:2]{index=2}
from pymongo import ASCENDING, DESCENDING                  # Helpers índices :contentReference[oaicite:3]{index=3}

load_dotenv(".env")

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
client     = AsyncIOMotorClient(MONGO_URI)                # conexión única
db         = client["tdp_prototype"]

INDEX_MAP = {
    "users":          [({"email": ASCENDING}, {"unique": True})],
    "projects":       [({"code": ASCENDING}, {"unique": True})],
    "pdf_files":      [({"project_id": ASCENDING,
                         "upload_date": DESCENDING}, {})],
    "epics":          [({"project_id": ASCENDING}, {})],
    "user_stories":   [
        ({"project_id": ASCENDING, "priority": ASCENDING}, {}),
        ({"epic_id": ASCENDING}, {}),
    ],
    "story_versions": [({"story_id": ASCENDING,
                         "version":  DESCENDING}, {})],
    "releases":       [({"project_id": ASCENDING,
                         "generated_at": DESCENDING}, {})],
}

async def init_indexes() -> None:
    for coll, specs in INDEX_MAP.items():
        for keys, opts in specs:
            await db[coll].create_index(list(keys.items()), **opts)  # idempotente

app = FastAPI(docs_url="/docs", redoc_url=None)

# Incluye UNA VEZ el api_router con prefijo /api
from .routers import api_router
app.include_router(api_router, prefix="/api")

@app.on_event("startup")
async def startup() -> None:
    await init_indexes()
    logging.info("✔ MongoDB indexes ready")

@app.on_event("shutdown")
def shutdown() -> None:
    client.close()

@app.get("/ping", tags=["utils"])
async def ping():
    return {"pong": True}
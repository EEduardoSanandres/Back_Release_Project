import logging
from fastapi import FastAPI
from pymongo import ASCENDING

from backend.app.db import db, mongo_client
from backend.api.routers.llm  import api_router as main_router
from backend.api.routers.crud import router     as crud_router
from backend.api.routers.extra import router    as extra_router

# ── Índices ────────────────────────────────────
INDEX_MAP = {
    "users":        [({"email": ASCENDING}, {"unique": True})],
    "projects":     [({"code":  ASCENDING}, {"unique": True})],
    "user_stories": [({"project_id": ASCENDING}, {}),
                     ({"code": ASCENDING}, {"unique": True})],
    "dependencies": [({"project_id": ASCENDING}, {})],
}

async def init_indexes():
    for coll, specs in INDEX_MAP.items():
        for keys, opts in specs:
            await db[coll].create_index(list(keys.items()), **opts)
    logging.info("✔ MongoDB indexes ready")

# ── FastAPI ────────────────────────────────────
app = FastAPI(docs_url="/docs", redoc_url=None)

@app.on_event("startup")
async def startup():
    await init_indexes()

@app.on_event("shutdown")
def shutdown():
    mongo_client.close()

# ── Rutas ──────────────────────────────────────
app.include_router(main_router, prefix="/api")
app.include_router(crud_router,  prefix="/api")
app.include_router(extra_router, prefix="/api")
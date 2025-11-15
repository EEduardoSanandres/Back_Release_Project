import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pymongo import ASCENDING

from .db import db, mongo_client

# ── Índices ────────────────────────────────────
INDEX_MAP = {
    "users":        [({"email": ASCENDING}, {"unique": True})],
    "projects":     [({"code":  ASCENDING}, {"unique": True})],
    "user_stories": [({"project_id": ASCENDING}, {}),
                     ({"project_id": ASCENDING, "code": ASCENDING}, {"unique": True})],
    "dependencies": [({"project_id": ASCENDING}, {})],
    "project_configs": [({"project_id": ASCENDING}, {"unique": True})],
}

async def init_indexes():
    for coll, specs in INDEX_MAP.items():
        for keys, opts in specs:
            await db[coll].create_index(list(keys.items()), **opts)
    logging.info("✔ MongoDB indexes ready")

# ── FastAPI ────────────────────────────────────
app = FastAPI(docs_url="/docs", redoc_url=None)

# ── CORS Configuration ─────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    # Import routers here to avoid circular imports
    from ..api.routers.llm  import api_router as main_router
    from ..api.routers.crud import router     as crud_router
    from ..api.routers.extra import router    as extra_router
    from ..api.routers.auth import router     as auth_router
    
    # Include routers
    app.include_router(main_router, prefix="/api")
    app.include_router(crud_router,  prefix="/api")
    app.include_router(extra_router, prefix="/api")
    app.include_router(auth_router, prefix="/api")
    
    await init_indexes()
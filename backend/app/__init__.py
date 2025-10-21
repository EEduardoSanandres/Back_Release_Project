import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pymongo import ASCENDING
from pymongo.errors import OperationFailure

from .db import db, mongo_client
from ..api.routers.llm  import api_router as main_router
from ..api.routers.crud import router     as crud_router
from ..api.routers.extra import router    as extra_router
from ..api.routers.auth import router     as auth_router

# ── Índices base (no incluyen user_stories; lo tratamos aparte con migración segura) ──
INDEX_MAP = {
    "users": [
        ({"email": ASCENDING}, {"unique": True, "name": "uniq_user_email"})
    ],
    "projects": [
        ({"code": ASCENDING}, {"unique": True, "name": "uniq_project_code"})
    ],
    # nombre correcto de la colección de dependencias:
    "dependencies_graph": [
        ({"project_id": ASCENDING}, {"name": "depgraph_project"})
    ],
}

async def ensure_user_stories_indexes():
    """
    Migra y asegura índices correctos para user_stories:
      - Quita 'code_1' si fuera único global.
      - Crea índice único compuesto {project_id, code}.
      - Crea índices auxiliares no-únicos.
    """
    coll = db["user_stories"]

    # Cargar índices existentes
    existing = {ix["name"]: ix async for ix in coll.list_indexes()}

    # 1) Si existe 'code_1' y es único, lo eliminamos (rompe reimportaciones entre proyectos)
    if "code_1" in existing and existing["code_1"].get("unique", False):
        try:
            await coll.drop_index("code_1")
            logging.info("🧹 Dropped unique global index user_stories.code_1")
        except OperationFailure as e:
            logging.warning(f"No se pudo eliminar code_1: {e}")

    # 2) Índice único por proyecto+code
    if "uniq_project_code" not in existing:
        await coll.create_index(
            [("project_id", ASCENDING), ("code", ASCENDING)],
            unique=True,
            name="uniq_project_code",
        )
        logging.info("✅ Created unique index user_stories.uniq_project_code")

    # 3) Auxiliares no-únicos
    if "userstories_project" not in existing:
        await coll.create_index([("project_id", ASCENDING)], name="userstories_project")
    if "userstories_code_nonunique" not in existing:
        await coll.create_index([("code", ASCENDING)], name="userstories_code_nonunique")

async def init_indexes():
    # Primero crear/asegurar índices base
    for coll, specs in INDEX_MAP.items():
        for keys, opts in specs:
            await db[coll].create_index(list(keys.items()), **opts)
    # Luego migración/aseguramiento específico de user_stories
    await ensure_user_stories_indexes()
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
    await init_indexes()

@app.on_event("shutdown")
def shutdown():
    mongo_client.close()

# ── Rutas ──────────────────────────────────────
app.include_router(main_router, prefix="/api")
app.include_router(crud_router,  prefix="/api")
app.include_router(extra_router, prefix="/api")
app.include_router(auth_router,  prefix="/api")

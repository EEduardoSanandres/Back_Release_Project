import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
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

# ── Tags Metadata ──────────────────────────────
tags_metadata = [
    {
        "name": "Auth",
        "description": "Operaciones de autenticación, login y registro de usuarios.",
    },
    {
        "name": "Users",
        "description": "Gestión de perfiles de usuario y visualización de miembros del equipo.",
    },
    {
        "name": "Projects",
        "description": "CRUD de proyectos y obtención de estadísticas y eventos de calendario.",
    },
    {
        "name": "User Stories",
        "description": "Gestión del Product Backlog, historias de usuario y sus criterios de aceptación.",
    },
    {
        "name": "Refinement",
        "description": "Herramientas de refinamiento de historias de usuario (DoR, INVEST).",
    },
    {
        "name": "AI Analysis",
        "description": "Procesamiento de requerimientos mediante IA (PDF, Release Planning, Backlog).",
    },
    {
        "name": "Dependencies",
        "description": "Gestión y visualización del grafo de dependencias entre historias.",
    },
]

# ── FastAPI ────────────────────────────────────
# Configure for Cloud Run - trust proxy headers
app = FastAPI(
    title="SprintMind API",
    description="""
API para la gestión de proyectos ágiles con soporte de IA. 

Permite:
* **Importar requerimientos** desde archivos PDF.
* **Gestionar el Product Backlog** con análisis de prioridades y dependencias.
* **Planificar Releases** automáticamente basándose en la capacidad del equipo.
* **Refinar historias de usuario** asegurando que cumplan con criterios DoR e INVEST.
    """,
    version="1.0.0",
    contact={
        "name": "Soporte SprintMind",
        "url": "https://sprintmind.app/support",
    },
    openapi_tags=tags_metadata,
    docs_url="/docs", 
    redoc_url=None,
    root_path="",
    # Trust forwarded headers from Cloud Run
    servers=[
        {"url": "https://back-release-project-142164661472.southamerica-west1.run.app", "description": "Production"},
        {"url": "http://localhost:8000", "description": "Local"}
    ]
)

# ── Proxy Headers Middleware ──────────────────
@app.middleware("http")
async def add_proxy_headers(request: Request, call_next):
    """Handle X-Forwarded-Proto header from Cloud Run to ensure HTTPS URLs"""
    # Check if request comes through Cloud Run proxy
    forwarded_proto = request.headers.get("x-forwarded-proto", "")
    
    if forwarded_proto == "https":
        # Override the URL scheme to https for URL generation
        request.scope["scheme"] = "https"
    
    response = await call_next(request)
    return response

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
    from ..api.routers.refinement import router as refinement_router
    
    # Include routers
    app.include_router(main_router, prefix="/api")
    app.include_router(crud_router,  prefix="/api")
    app.include_router(extra_router, prefix="/api")
    app.include_router(auth_router, prefix="/api")
    app.include_router(refinement_router, prefix="/api")
    
    await init_indexes()
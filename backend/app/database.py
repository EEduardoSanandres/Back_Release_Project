import os, logging
from dotenv import load_dotenv
from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, DESCENDING

load_dotenv(".env")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
mongo_client = AsyncIOMotorClient(MONGO_URI)
db = mongo_client["tdp_prototype"]

# Index configuration (same as before)
INDEX_MAP = {
    "users":          [({"email": ASCENDING}, {"unique": True})],
    "projects":       [({"code": ASCENDING}, {"unique": True})],
    "pdf_files":      [({"project_id": ASCENDING, "upload_date": DESCENDING}, {})],
    "epics":          [({"project_id": ASCENDING}, {})],
    "user_stories":   [
        ({"project_id": ASCENDING, "priority": ASCENDING}, {}),
        ({"epic_id": ASCENDING}, {}),
    ],
    "story_versions": [({"story_id": ASCENDING, "version": DESCENDING}, {})],
    "releases":       [({"project_id": ASCENDING, "generated_at": DESCENDING}, {})],
}

async def init_indexes() -> None:
    for coll, specs in INDEX_MAP.items():
        for keys, opts in specs:
            await db[coll].create_index(list(keys.items()), **opts)
    logging.info("✔ MongoDB indexes ready")

app = FastAPI(docs_url="/docs", redoc_url=None)

@app.on_event("startup")
async def startup():
    await init_indexes()

@app.on_event("shutdown")
def shutdown():
    mongo_client.close()

from backend.api.routers.llm import api_router as main_router
app.include_router(main_router, prefix="/api")

@app.get("/ping", tags=["utils"])
async def ping():
    return {"pong": True}

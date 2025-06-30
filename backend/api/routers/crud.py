"""
backend/api/routers/crud.py
"""

from fastapi import APIRouter
from fastapi_crudrouter_mongodb import CRUDRouter

# 👉 Re-use the **single** Motor connection that lives in backend/app
from backend.app.database import db                 # <— Motor client
from backend.app.schemas import (                   # <— MongoModels
    User, Project, PDFFile, Epic, UserStory,
    StoryVersion, Graph, Release, WorkPackage, Cost
)

# ------------------------------------------------------------------
router = APIRouter(tags=["CRUD"])       # <— no prefix here!

def _mount(name: str, collection, schema) -> None:
    """Attach one CRUDRouter instance to `router`."""
    router.include_router(
        CRUDRouter(
            model=schema,
            db=db,
            collection_name=name,
            prefix=f"/{name}",          # e.g.  /users
            tags=["CRUD"],
        )
    )

# Register every collection once
for _name, _coll, _schema in [
    ("users",          db.users,          User),
    ("projects",       db.projects,       Project),
    ("pdf_files",      db.pdf_files,      PDFFile),
    ("epics",          db.epics,          Epic),
    ("user_stories",   db.user_stories,   UserStory),
    ("story_versions", db.story_versions, StoryVersion),
    ("story_graph",    db.story_graph,    Graph),
    ("releases",       db.releases,       Release),
    ("work_packages",  db.work_packages,  WorkPackage),
    ("costs",          db.costs,          Cost),
]:
    _mount(_name, _coll, _schema)

# What gets imported from elsewhere:
__all__ = ["router"]

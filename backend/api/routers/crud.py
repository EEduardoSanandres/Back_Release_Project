from fastapi import APIRouter
from fastapi_crudrouter_mongodb import CRUDRouter

from backend.app.db import db                     # ← conexión
from backend.app.schemas import (                 # ← modelos
    User, Project, UserStory, Dependency
)

router = APIRouter()

def _mount(name: str, collection, schema):
    tag = name.replace("_", " ").title()
    router.include_router(
        CRUDRouter(
            model=schema,
            db=db,
            collection_name=name,
            prefix=f"/{name}",        # /users, /projects, …
            tags=[tag],               # <- se agrupa por este nombre
        )
    )

for _name, _coll, _schema in [
    ("users",        db.users,        User),
    ("projects",     db.projects,     Project),
    ("user_stories", db.user_stories, UserStory),
    ("dependencies", db.dependencies, Dependency),
]:
    _mount(_name, _coll, _schema)

__all__ = ["router"]

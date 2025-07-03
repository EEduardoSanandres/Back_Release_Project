from fastapi import APIRouter
from fastapi_crudrouter_mongodb import CRUDRouter

from backend.app.db import db
from backend.app.schemas import (
    User, Project, UserStory, DependencyGraph
)

router = APIRouter()

def _mount(name: str, collection, schema):
    tag = name.replace("_", " ").title()
    router.include_router(
        CRUDRouter(
            model=schema,
            db=db,
            collection_name=name,
            prefix=f"/{name}",
            tags=[tag],
        )
    )

for _name, _coll, _schema in [
    ("users",             db.users,             User),
    ("projects",          db.projects,          Project),
    ("user_stories",      db.user_stories,      UserStory),
    ("dependencies_graph", db.dependencies_graph, DependencyGraph),
]:
    _mount(_name, _coll, _schema)

__all__ = ["router"]

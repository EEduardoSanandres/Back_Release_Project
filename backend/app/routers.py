# backend/app/routers.py
from fastapi import APIRouter
from fastapi_crudrouter_mongodb import CRUDRouter
from .database import db
from .schemas import (
    User, Project, PDFFile, Epic, UserStory,
    StoryVersion, Graph, Release, WorkPackage, Cost
)

# Crea un router que luego montaremos en el FastAPI principal
api_router = APIRouter(tags=["CRUD"])

def mount(name: str, collection, schema):
    router = CRUDRouter(
        model           = schema,
        db              = db,
        collection_name = name,
        prefix          = f"/{name}",
        tags            = ["CRUD"],
    )
    api_router.include_router(router)

# Monta cada CRUD en api_router, NO en app directamente
mount("users",          db.users,          User)
mount("projects",       db.projects,       Project)
mount("pdf_files",      db.pdf_files,      PDFFile)
mount("epics",          db.epics,          Epic)
mount("user_stories",   db.user_stories,   UserStory)
mount("story_versions", db.story_versions, StoryVersion)
mount("story_graph",    db.story_graph,    Graph)
mount("releases",       db.releases,       Release)
mount("work_packages",  db.work_packages,  WorkPackage)
mount("costs",          db.costs,          Cost)

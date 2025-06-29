from fastapi import APIRouter
from pydantic import BaseModel
from openai import OpenAI
from fastapi_crudrouter_mongodb import CRUDRouter
from .database import db
from .schemas import (
    User, Project, PDFFile, Epic,
    UserStory, StoryVersion, Graph,
    Release, WorkPackage, Cost
)

# Chat router using OpenAI-compatible HTTP API
chat_router = APIRouter(prefix="/chat", tags=["chat"])
client = OpenAI(base_url="http://localhost:1234/v1", api_key="lm-studio")

class ChatRequest(BaseModel):
    message: str

@chat_router.post("/", response_model=dict)
async def chat_endpoint(req: ChatRequest):
    res = client.chat.completions.create(
        model="mistral-7b-instruct-v0.3",
        messages=[{"role":"user","content":req.message}]
    )
    return {"response": res.choices[0].message.content}

# CRUD router for MongoDB collections
api_router = APIRouter(prefix="/api", tags=["CRUD"])
def mount(name: str, collection, schema):
    router = CRUDRouter(
        model=schema, db=db,
        collection_name=name,
        prefix=f"/{name}", tags=["CRUD"]
    )
    api_router.include_router(router)

for nm, coll, sch in [
    ("users", db.users, User),
    ("projects", db.projects, Project),
    ("pdf_files", db.pdf_files, PDFFile),
    ("epics", db.epics, Epic),
    ("user_stories", db.user_stories, UserStory),
    ("story_versions", db.story_versions, StoryVersion),
    ("story_graph", db.story_graph, Graph),
    ("releases", db.releases, Release),
    ("work_packages", db.work_packages, WorkPackage),
    ("costs", db.costs, Cost),
]:
    mount(nm, coll, sch)

api_router.include_router(chat_router)

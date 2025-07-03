from __future__ import annotations
from fastapi import APIRouter, HTTPException, Body, status
from bson import ObjectId
from typing import List

from backend.app.db import db
from backend.app.schemas import User, Project, UserStory, DependencyGraph
from backend.api.services.dependency_service import DependencyService

router = APIRouter(tags=["Extra utils"])

# ─────────────────────────────── USERS ────────────────────────────────
@router.get("/users/by-email/{email}", response_model=User)
async def get_user_by_email(email: str):
    doc = await db.users.find_one({"email": email})
    if not doc:
        raise HTTPException(404, "User not found")
    return doc

@router.get("/users/by-role/{role}", response_model=list[User])
async def list_users_by_role(role: str):
    if role not in {"student", "advisor", "po", "admin"}:
        raise HTTPException(400, "Invalid role")
    return await db.users.find({"role": role}).to_list(None)

# ───────────────────────────── PROJECTS ───────────────────────────────
@router.get("/projects/by-owner/{owner_id}", response_model=list[Project])
async def projects_by_owner(owner_id: str):
    oid = ObjectId(owner_id)
    return await db.projects.find({"owner_id": oid}).to_list(None)

@router.get("/projects/search", response_model=list[Project])
async def search_projects(q: str):
    regex = {"$regex": q, "$options": "i"}
    return await db.projects.find({"$or": [{"code": regex}, {"name": regex}]}).to_list(None)

# ─────────────────────────── USER STORIES ─────────────────────────────
@router.get("/projects/{project_id}/stories", response_model=list[UserStory])
async def stories_of_project(project_id: str):
    oid = ObjectId(project_id)
    return await db.user_stories.find({"project_id": oid}).to_list(None)

@router.post(
    "/projects/{project_id}/stories/bulk",
    status_code=status.HTTP_201_CREATED,
    response_model=list[UserStory],
)
async def bulk_insert_stories(
    project_id: str,
    stories: List[UserStory] = Body(..., embed=True),
):
    pid = ObjectId(project_id)
    codes = [s.code for s in stories]
    existing = await db.user_stories.find(
        {"code": {"$in": codes}}
    ).project({"code": 1}).to_list(None)
    if existing:
        dup = ", ".join(d["code"] for d in existing)
        raise HTTPException(409, f"Códigos duplicados: {dup}")
    docs = [s.model_dump(by_alias=True) | {"project_id": pid} for s in stories]
    await db.user_stories.insert_many(docs)
    return docs

# ─────────────────────── DEPENDENCY GRAPH (nuevo) ──────────────────────
@router.get("/projects/{project_id}/dependency-graph", response_model=DependencyGraph)
async def get_dependency_graph(project_id: str):
    pid  = ObjectId(project_id)
    doc = await db.dependencies_graph.find_one({"project_id": pid})
    if not doc:
        raise HTTPException(404, "Graph not found")
    return doc

@router.post(
    "/projects/{project_id}/dependency-graph/generate",
    response_model=DependencyGraph,
    status_code=status.HTTP_201_CREATED,
)
async def generate_dependency_graph(project_id: str):
    svc = DependencyService()
    return await svc.build_graph(project_id)

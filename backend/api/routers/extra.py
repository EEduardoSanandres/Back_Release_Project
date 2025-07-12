from __future__ import annotations
from fastapi import APIRouter, HTTPException, Body, status, Depends
from bson import ObjectId
from typing import List

from ...app.db import db
from ...app.schemas import User, Project, UserStory, DependencyGraph
from ..services.dependency_service import DependencyService
from ..services.release_backlog_service import ReleaseBacklogService
from ..schemas.responses import ReleaseBacklogOut

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
    try:
        oid = ObjectId(project_id)
        stories = await db.user_stories.find({"project_id": oid}).to_list(None)
        return stories
    except Exception as e:
        import logging
        logging.error(f"Error getting stories for project {project_id}: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Error retrieving stories: {str(e)}"
        )

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

# ─────────────────────── DIAGNOSTIC ENDPOINTS ──────────────────────
@router.get("/diagnostic/db-status")
async def check_db_status():
    """Check database connectivity and basic stats."""
    try:
        # Test database connection
        server_info = await db.client.server_info()
        
        # Count documents in collections
        counts = {}
        for collection_name in ["users", "projects", "user_stories", "dependencies_graph"]:
            try:
                count = await db[collection_name].count_documents({})
                counts[collection_name] = count
            except Exception as e:
                counts[collection_name] = f"Error: {str(e)}"
        
        return {
            "status": "connected",
            "server_info": {
                "version": server_info.get("version", "unknown"),
                "ok": server_info.get("ok", False)
            },
            "collection_counts": counts
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Database connection error: {str(e)}"
        )

@router.get("/diagnostic/test-project/{project_id}")
async def test_project_stories(project_id: str):
    """Test if a specific project exists and has stories."""
    try:
        oid = ObjectId(project_id)
        
        # Check if project exists
        project = await db.projects.find_one({"_id": oid})
        
        # Count stories for this project
        story_count = await db.user_stories.count_documents({"project_id": oid})
        
        # Get sample stories
        sample_stories = await db.user_stories.find({"project_id": oid}).limit(3).to_list(None)
        
        # Convert ObjectId to strings for JSON serialization
        if project:
            project["_id"] = str(project["_id"])
            if "owner_id" in project and project["owner_id"]:
                project["owner_id"] = str(project["owner_id"])
        
        for story in sample_stories:
            story["_id"] = str(story["_id"])
            story["project_id"] = str(story["project_id"])
        
        return {
            "project_id": project_id,
            "project_exists": project is not None,
            "project_data": project,
            "story_count": story_count,
            "sample_stories": sample_stories
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error checking project: {str(e)}"
        )

@router.post("/projects/{project_id}/release-backlog/generate", response_model=ReleaseBacklogOut, status_code=status.HTTP_201_CREATED)
async def generate_project_release_backlog(
    project_id: str,
    service: ReleaseBacklogService = Depends()
):
    """
    Genera (o regenera) el Release Backlog ordenado para un proyecto
    basándose en sus Historias de Usuario y dependencias.
    """
    return await service.generate_backlog(project_id)

@router.get("/projects/{project_id}/release-backlog", response_model=ReleaseBacklogOut)
async def get_project_release_backlog(
    project_id: str,
    service: ReleaseBacklogService = Depends()
):
    """
    Obtiene el Release Backlog existente para un proyecto.
    """
    return await service.get_backlog(project_id)

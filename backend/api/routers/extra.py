from __future__ import annotations
from fastapi import APIRouter, HTTPException, Body, status, Depends
from bson import ObjectId
from typing import List

from ...app.db import db
from ...app.schemas import User, Project, UserStory, DependencyGraph
from ..services.dependency_service import DependencyService
from ..services.release_backlog_service import ReleaseBacklogService
from ..services.release_planning_service import ReleasePlanningService
from ..schemas.responses import ReleaseBacklogOut, ReleasePlanningOut

router = APIRouter()

# ─────────────────────────────── USERS ────────────────────────────────
@router.get(
    "/users/by-email/{email}", 
    response_model=User, 
    tags=["Users"],
    summary="Buscar usuario por email"
)
async def get_user_by_email(email: str):
    doc = await db.users.find_one({"email": email})
    if not doc:
        raise HTTPException(404, "User not found")
    return doc

@router.get(
    "/users/by-role/{role}", 
    response_model=list[User], 
    tags=["Users"],
    summary="Listar usuarios por rol"
)
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

@router.get("/projects/{project_id}/epics", response_model=list[str])
async def get_project_epics(project_id: str):
    """Obtener lista única de épicas de un proyecto."""
    try:
        oid = ObjectId(project_id)
        epics = await db.user_stories.distinct("epica", {"project_id": oid})
        # Filtrar valores nulos o vacíos
        return [e for e in epics if e]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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

# ─────────────────────── DEPENDENCY GRAPH ──────────────────────
@router.get(
    "/projects/{project_id}/dependency-graph", 
    response_model=DependencyGraph,
    tags=["Dependencies"],
    summary="Obtener grafo de dependencias",
    description="Retorna el grafo de dependencias calculado para un proyecto."
)
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
    tags=["Dependencies"],
    summary="Generar grafo de dependencias",
    description="Analiza todas las historias de usuario del proyecto y usa IA para detectar dependencias técnicas y funcionales."
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



@router.post(
    "/projects/{project_id}/release-backlog/generate", 
    response_model=ReleaseBacklogOut, 
    status_code=status.HTTP_201_CREATED,
    tags=["AI Analysis"],
    summary="Generar Release Backlog",
    description="Ordena el backlog del proyecto de forma óptima para el release usando IA."
)
async def generate_project_release_backlog(
    project_id: str,
    service: ReleaseBacklogService = Depends()
):
    """
    Genera (o regenera) el Release Backlog ordenado para un proyecto
    basándose en sus Historias de Usuario y dependencias.
    """
    try:
        return await service.generate_backlog(project_id)
    except Exception as e:
        import logging
        logging.error(f"Error generando Release Backlog para proyecto {project_id}: {str(e)}", exc_info=True)
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Error interno al generar release backlog: {str(e)}")

@router.get(
    "/projects/{project_id}/release-backlog", 
    response_model=ReleaseBacklogOut,
    tags=["AI Analysis"],
    summary="Obtener Release Backlog"
)
async def get_project_release_backlog(
    project_id: str,
    service: ReleaseBacklogService = Depends()
):
    """
    Obtiene el Release Backlog existente para un proyecto.
    """
    return await service.get_backlog(project_id)

@router.post(
    "/projects/{project_id}/release-planning/generate", 
    response_model=ReleasePlanningOut,
    tags=["AI Analysis"],
    summary="Generar Plan de Release",
    description="Crea una planificación detallada de releases y sprints basada en la velocidad del equipo y prioridad de las historias."
)
async def generate_release_planning(
    project_id: str,
    num_releases: int = 1,
    service: ReleasePlanningService = Depends()
):
    """
    Genera un plan de release completo para un proyecto dividido en múltiples releases.
    
    Args:
        project_id: ID del proyecto
        num_releases: Cantidad de releases a generar (default: 1)
    
    El plan incluye sprints distribuidos en releases, con título, descripción, riesgos y recomendaciones.
    """
    try:
        return await service.generate_release_plan(project_id, num_releases)
    except Exception as e:
        import logging
        logging.error(f"Error generando Release Planning para proyecto {project_id}: {str(e)}", exc_info=True)
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Error interno al generar release planning: {str(e)}")

@router.get(
    "/projects/{project_id}/release-planning", 
    response_model=ReleasePlanningOut,
    tags=["AI Analysis"],
    summary="Obtener Plan de Release"
)
async def get_release_planning(
    project_id: str,
    service: ReleasePlanningService = Depends()
):
    """
    Obtiene el plan de release existente para un proyecto.
    """
    return await service.get_release_plan(project_id)

from fastapi import APIRouter, HTTPException, Depends
from fastapi_crudrouter_mongodb import CRUDRouter
from pydantic import BaseModel
from typing import List
from datetime import datetime, date
from bson import ObjectId
import logging

from backend.app.db import db
from backend.app.schemas import (
    User, Project, UserStory, DependencyGraph, ProjectConfig
)
from backend.api.schemas.responses import UserOut, ProjectConfigOut
from backend.api.schemas.requests import ProjectConfigCreateIn, ProjectConfigUpdateIn
from backend.api.services.auth_service import AuthService, auth_service
from backend.api.schemas.requests import UserCreateIn

router = APIRouter()

# Custom User router con manejo de contraseñas
user_router = APIRouter(prefix="/users", tags=["Users"])

@user_router.post("/", response_model=UserOut, status_code=201)
async def create_user(
    user_data: UserCreateIn,
    auth_svc: AuthService = Depends(auth_service)
):
    """Crear un nuevo usuario con contraseña."""
    user = await auth_svc.create_user(user_data)
    return UserOut(
        id=str(user.id),
        email=user.email,
        name=user.name,
        role=user.role,
        created_at=user.created_at if user.created_at else datetime.utcnow()
    )

@user_router.get("/", response_model=List[UserOut])
async def get_users():
    """Obtener todos los usuarios sin datos sensibles."""
    users = await db.users.find().to_list(None)
    return [
        UserOut(
            id=str(user["_id"]),
            email=user["email"],
            name=user["name"],
            role=user["role"],
            created_at=user.get("created_at", datetime.utcnow())
        )
        for user in users
    ]

@user_router.get("/{user_id}", response_model=UserOut)
async def get_user(user_id: str):
    """Obtener un usuario por ID sin datos sensibles."""
    from bson import ObjectId
    
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    return UserOut(
        id=str(user["_id"]),
        email=user["email"],
        name=user["name"],
        role=user["role"],
        created_at=user.get("created_at", datetime.utcnow())
    )

# Incluir el router personalizado para usuarios
router.include_router(user_router)

# Routers para otras entidades (sin cambios)
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
    ("projects",          db.projects,          Project),
    ("user_stories",      db.user_stories,      UserStory),
    ("dependencies_graph", db.dependencies_graph, DependencyGraph),
]:
    _mount(_name, _coll, _schema)

__all__ = ["router"]

# Endpoint personalizado que REEMPLAZA al GET /user_stories/ del CRUDRouter
# (Se registra DESPUÉS para tener prioridad sobre el automático)
@router.get("/user_stories/", tags=["User Stories"])
async def get_user_stories(projectId: str = None):
    """Obtener historias de usuario, opcionalmente filtradas por projectId."""
    try:
        logging.info(f"Endpoint /user_stories/ llamado con projectId: {projectId}")
        
        # Verificar que db esté disponible
        if not hasattr(db, 'user_stories'):
            logging.error("db.user_stories no está disponible")
            raise HTTPException(status_code=500, detail="Base de datos no disponible")
        
        filtro = {}
        if projectId:
            logging.info(f"Filtrando historias por projectId: {projectId}")
            try:
                # Intentar convertir a ObjectId, si falla usar como string
                try:
                    object_id = ObjectId(projectId)
                    # Buscar por ambos posibles nombres de campo para compatibilidad
                    filtro = {"$or": [
                        {"projectId": object_id},
                        {"project_id": object_id}
                    ]}
                    logging.info(f"Usando filtro ObjectId: {filtro}")
                except Exception as oid_error:
                    logging.warning(f"projectId no es ObjectId válido ({oid_error}), buscando como string")
                    # Si no es un ObjectId válido, buscar como string en ambos campos
                    filtro = {"$or": [
                        {"projectId": projectId},
                        {"project_id": projectId}
                    ]}
                    logging.info(f"Usando filtro string: {filtro}")
            except Exception as e:
                logging.warning(f"Error al procesar projectId {projectId}: {e}")
                # En caso de error, no filtrar
                filtro = {}
        else:
            logging.info("No se proporcionó projectId, trayendo todas las historias")
        
        logging.info(f"Ejecutando query con filtro: {filtro}")
        historias = await db.user_stories.find(filtro).to_list(None)
        logging.info(f"Encontradas {len(historias)} historias con filtro: {filtro}")
        
        result = []
        for h in historias:
            result.append({
                "id": str(h.get("_id", "")),
                "project_id": str(h.get("projectId", h.get("project_id", ""))),
                "code": h.get("code", ""),
                "epica": h.get("epica", ""),
                "nombre": h.get("nombre", ""),
                "descripcion": h.get("descripcion", ""),
                "criterios": h.get("criterios", []),
                "created_at": h.get("createdAt", h.get("created_at", "")),
                "priority": h.get("priority", "Medium"),
                "story_points": h.get("storyPoints", h.get("story_points", 0)),
                "dor": h.get("dor", 0),
                "status": h.get("status", "Ready"),
                "deps": h.get("deps", 0),
                "ai": h.get("ai", False),
            })
        
        logging.info(f"Retornando {len(result)} historias")
        return result
        
    except HTTPException:
        # Re-lanzar HTTPExceptions sin modificar
        raise
    except Exception as e:
        logging.error(f"Error interno en get_user_stories: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

# Endpoint adicional para Product Backlog
@router.get("/user_stories/product_backlog", tags=["User Stories"])
async def get_user_stories_product_backlog(product_id: str = None):
    # Buscar por ambos formatos de project_id
    filtro = {}
    if product_id:
        filtro = {"$or": [
            {"project_id": product_id},
            {"projectId": product_id}
        ]}
    historias = await db.user_stories.find(filtro).to_list(None)
    result = []
    for h in historias:
        result.append({
            "code": h.get("code", ""),
            "title": h.get("nombre", ""),
            "epica": h.get("epica", ""),
            "priority": h.get("priority", "Medium"),
            "story_points": h.get("story_points", 0),
            "dor": h.get("dor", 0),
            "status": h.get("status", "Ready"),
            "deps": h.get("deps", 0),
            "ai": h.get("ai", False),
            "_id": str(h.get("_id", "")),
            "project_id": h.get("project_id", h.get("projectId", "")),
        })
    return result

# Nuevo endpoint para filtrar US por proyecto
@router.get("/user_stories/by-project/{projectId}", tags=["User Stories"])
async def get_user_stories_by_project(projectId: str):
    """Obtener historias de usuario filtradas por projectId."""
    try:
        logging.info(f"Endpoint /user_stories/by-project/{{projectId}} llamado con projectId: {projectId}")
        
        if not hasattr(db, 'user_stories'):
            logging.error("db.user_stories no está disponible")
            raise HTTPException(status_code=500, detail="Base de datos no disponible")
        
        filtro = {}
        logging.info(f"Filtrando historias por projectId: {projectId}")
        try:
            try:
                object_id = ObjectId(projectId)
                filtro = {"$or": [
                    {"projectId": object_id},
                    {"project_id": object_id}
                ]}
                logging.info(f"Usando filtro ObjectId: {filtro}")
            except Exception as oid_error:
                logging.warning(f"projectId no es ObjectId válido ({oid_error}), buscando como string")
                filtro = {"$or": [
                    {"projectId": projectId},
                    {"project_id": projectId}
                ]}
                logging.info(f"Usando filtro string: {filtro}")
        except Exception as e:
            logging.warning(f"Error al procesar projectId {projectId}: {e}")
            # En caso de error, no filtrar
            filtro = {}
        
        logging.info(f"Ejecutando query con filtro: {filtro}")
        historias = await db.user_stories.find(filtro).to_list(None)
        logging.info(f"Encontradas {len(historias)} historias con filtro: {filtro}")
        
        result = []
        for h in historias:
            result.append({
                "id": str(h.get("_id", "")),
                "project_id": str(h.get("projectId", h.get("project_id", ""))),
                "code": h.get("code", ""),
                "epica": h.get("epica", ""),
                "nombre": h.get("nombre", ""),
                "descripcion": h.get("descripcion", ""),
                "criterios": h.get("criterios", []),
                "created_at": h.get("createdAt", h.get("created_at", "")),
                "priority": h.get("priority", "Medium"),
                "story_points": h.get("storyPoints", h.get("story_points", 0)),
                "dor": h.get("dor", 0),
                "status": h.get("status", "Ready"),
                "deps": h.get("deps", 0),
                "ai": h.get("ai", False),
            })
        
        logging.info(f"Retornando {len(result)} historias")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error interno en get_user_stories_by_project: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

# ── Endpoints para Project Config ──────────────────────────────────────

@router.post("/project_configs/", response_model=ProjectConfigOut, tags=["Project Config"])
async def create_project_config(config_data: ProjectConfigCreateIn):
    """Crear configuración para un proyecto."""
    logging.info("=== INICIANDO CREACIÓN DE CONFIGURACIÓN ===")
    try:
        logging.info(f"Creando configuración para proyecto: {config_data.project_id}")
        logging.info(f"Datos recibidos: {config_data.model_dump()}")

        # Verificar que el proyecto existe
        logging.info("Verificando existencia del proyecto...")
        project = await db.projects.find_one({"_id": ObjectId(config_data.project_id)})
        if not project:
            logging.error(f"Proyecto no encontrado: {config_data.project_id}")
            raise HTTPException(status_code=404, detail="Proyecto no encontrado")
        logging.info(f"Proyecto encontrado: {project.get('name', 'Unknown')}")

        # Verificar que no existe ya una configuración para este proyecto
        logging.info("Verificando configuración existente...")
        existing_config = await db.project_configs.find_one({"project_id": ObjectId(config_data.project_id)})
        if existing_config:
            logging.warning(f"Ya existe configuración para proyecto: {config_data.project_id}")
            raise HTTPException(status_code=400, detail="Ya existe configuración para este proyecto")

        # Crear la configuración
        logging.info("Creando diccionario de configuración...")
        config_dict = config_data.model_dump()
        config_dict["project_id"] = ObjectId(config_dict["project_id"])
        # Convertir date a datetime para MongoDB
        if isinstance(config_dict["release_target_date"], date):
            config_dict["release_target_date"] = datetime.combine(config_dict["release_target_date"], datetime.min.time())
        config_dict["created_at"] = datetime.utcnow()
        config_dict["updated_at"] = datetime.utcnow()

        logging.info(f"Insertando configuración: {config_dict}")
        result = await db.project_configs.insert_one(config_dict)
        created_config = await db.project_configs.find_one({"_id": result.inserted_id})

        logging.info(f"Configuración creada exitosamente: {created_config}")
        response = ProjectConfigOut(
            id=str(created_config["_id"]),
            project_id=str(created_config["project_id"]),
            num_devs=created_config["num_devs"],
            team_velocity=created_config["team_velocity"],
            sprint_duration=created_config["sprint_duration"],
            prioritization_metric=created_config["prioritization_metric"],
            release_target_date=created_config["release_target_date"],  # Ya es datetime, no convertir
            team_capacity=created_config.get("team_capacity"),
            optimistic_scenario=created_config.get("optimistic_scenario"),
            realistic_scenario=created_config.get("realistic_scenario"),
            pessimistic_scenario=created_config.get("pessimistic_scenario"),
            created_at=created_config["created_at"],
            updated_at=created_config["updated_at"]
        )
        logging.info("=== CONFIGURACIÓN CREADA EXITOSAMENTE ===")
        return response

    except HTTPException:
        logging.info("=== HTTP EXCEPTION LANZADA ===")
        raise
    except Exception as e:
        logging.error(f"=== ERROR INTERNO: {e} ===", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

@router.get("/project_configs/{project_id}", response_model=ProjectConfigOut, tags=["Project Config"])
async def get_project_config(project_id: str):
    """Obtener configuración de un proyecto."""
    try:
        config = await db.project_configs.find_one({"project_id": ObjectId(project_id)})
        if not config:
            raise HTTPException(status_code=404, detail="Configuración no encontrada para este proyecto")

        return ProjectConfigOut(
            id=str(config["_id"]),
            project_id=str(config["project_id"]),
            num_devs=config["num_devs"],
            team_velocity=config["team_velocity"],
            sprint_duration=config["sprint_duration"],
            prioritization_metric=config["prioritization_metric"],
            release_target_date=config["release_target_date"],
            team_capacity=config.get("team_capacity"),
            optimistic_scenario=config.get("optimistic_scenario"),
            realistic_scenario=config.get("realistic_scenario"),
            pessimistic_scenario=config.get("pessimistic_scenario"),
            created_at=config["created_at"],
            updated_at=config["updated_at"]
        )

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error obteniendo configuración del proyecto: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

@router.put("/project_configs/{project_id}", response_model=ProjectConfigOut, tags=["Project Config"])
async def update_project_config(project_id: str, config_data: ProjectConfigUpdateIn):
    """Actualizar configuración de un proyecto."""
    try:
        # Verificar que existe la configuración
        existing_config = await db.project_configs.find_one({"project_id": ObjectId(project_id)})
        if not existing_config:
            raise HTTPException(status_code=404, detail="Configuración no encontrada para este proyecto")

        # Preparar los datos de actualización
        update_data = config_data.model_dump(exclude_unset=True)
        # Convertir date a datetime para MongoDB si está presente
        if "release_target_date" in update_data and isinstance(update_data["release_target_date"], date):
            update_data["release_target_date"] = datetime.combine(update_data["release_target_date"], datetime.min.time())
        update_data["updated_at"] = datetime.utcnow()

        # Actualizar
        await db.project_configs.update_one(
            {"project_id": ObjectId(project_id)},
            {"$set": update_data}
        )

        # Obtener la configuración actualizada
        updated_config = await db.project_configs.find_one({"project_id": ObjectId(project_id)})

        return ProjectConfigOut(
            id=str(updated_config["_id"]),
            project_id=str(updated_config["project_id"]),
            num_devs=updated_config["num_devs"],
            team_velocity=updated_config["team_velocity"],
            sprint_duration=updated_config["sprint_duration"],
            prioritization_metric=updated_config["prioritization_metric"],
            release_target_date=updated_config["release_target_date"],
            team_capacity=updated_config.get("team_capacity"),
            optimistic_scenario=updated_config.get("optimistic_scenario"),
            realistic_scenario=updated_config.get("realistic_scenario"),
            pessimistic_scenario=updated_config.get("pessimistic_scenario"),
            created_at=updated_config["created_at"],
            updated_at=updated_config["updated_at"]
        )

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error actualizando configuración del proyecto: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

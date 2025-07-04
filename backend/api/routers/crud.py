from fastapi import APIRouter, HTTPException, Depends
from fastapi_crudrouter_mongodb import CRUDRouter
from pydantic import BaseModel
from typing import List
from datetime import datetime

from ...app.db import db
from ...app.schemas import (
    User, Project, UserStory, DependencyGraph
)
from ..schemas.responses import UserOut
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

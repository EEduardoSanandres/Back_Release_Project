from datetime import datetime
from typing import Annotated, Optional, Literal, List
from bson import ObjectId
from pydantic import Field, EmailStr, BaseModel
from fastapi_crudrouter_mongodb import MongoModel, MongoObjectId

class User(MongoModel):
    id: Annotated[ObjectId, MongoObjectId] | None = Field(default=None, alias="_id")
    email: EmailStr
    name: str
    password_hash: str = Field(..., description="Hashed password")
    role: Literal["student", "advisor", "po", "admin"]
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Project(MongoModel):
    id: Annotated[ObjectId, MongoObjectId] | None = Field(default=None, alias="_id")
    code: str
    name: str
    description: Optional[str] = None
    owner_id: Annotated[ObjectId, MongoObjectId] | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

class UserStory(MongoModel):
    id: Annotated[ObjectId, MongoObjectId] | None = Field(default=None, alias="_id")
    project_id: Annotated[ObjectId, MongoObjectId]
    code: str
    epica: str
    nombre: str
    descripcion: str
    criterios: List[str]
    created_at: datetime = Field(default_factory=datetime.utcnow)

class DependencyPair(BaseModel):
    frm: str
    to: List[str]

class DependencyGraph(MongoModel):
    id         : Annotated[ObjectId, MongoObjectId] | None = Field(default=None, alias="_id")
    project_id : Annotated[ObjectId, MongoObjectId]
    pairs      : list[DependencyPair]
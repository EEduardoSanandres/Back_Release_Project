from datetime import datetime, date
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
    total_prompt_tokens: int = Field(default=0)
    total_completion_tokens: int = Field(default=0)
    total_processing_time_ms: float = Field(default=0.0)

class UserStory(MongoModel):
    id: Annotated[ObjectId, MongoObjectId] | None = Field(default=None, alias="_id")
    project_id: Annotated[ObjectId, MongoObjectId]
    code: str
    epica: str
    nombre: str
    descripcion: str
    criterios: List[str]
    created_at: datetime = Field(default_factory=datetime.utcnow)
    # Campos adicionales para Product Backlog
    priority: str = Field(default="Medium")
    story_points: int = Field(default=0)
    dor: int = Field(default=0)
    status: str = Field(default="Ready")
    deps: int = Field(default=0)
    ai: bool = Field(default=False)

class DependencyPair(BaseModel):
    frm: str
    to: List[str]

class DependencyGraph(MongoModel):
    id         : Annotated[ObjectId, MongoObjectId] | None = Field(default=None, alias="_id")
    project_id : Annotated[ObjectId, MongoObjectId]
    pairs      : list[DependencyPair]
    total_prompt_tokens: int = Field(default=0)
    total_completion_tokens: int = Field(default=0)
    total_processing_time_ms: float = Field(default=0.0)

class ReleaseBacklog(MongoModel):
    id: Annotated[ObjectId, MongoObjectId] | None = Field(default=None, alias="_id")
    project_id: Annotated[ObjectId, MongoObjectId]
    us_codes: List[str] = Field(description="Lista ordenada de códigos de HU para el release.")
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    total_prompt_tokens: int = Field(default=0)
    total_completion_tokens: int = Field(default=0)
    total_processing_time_ms: float = Field(default=0.0)

class ProjectConfig(MongoModel):
    id: Annotated[ObjectId, MongoObjectId] | None = Field(default=None, alias="_id")
    project_id: Annotated[ObjectId, MongoObjectId]
    num_devs: int = Field(..., description="Número de desarrolladores en el equipo")
    team_velocity: int = Field(..., description="Velocidad del equipo (story points por sprint)")
    sprint_duration: int = Field(..., description="Duración del sprint en semanas")
    prioritization_metric: str = Field(..., description="Métrica de priorización (ej: businessValue, storyPoints)")
    release_target_date: date = Field(..., description="Fecha objetivo de release")
    team_capacity: Optional[int] = Field(None, description="Capacidad del equipo en horas por sprint")
    # Escenarios de estimación
    optimistic_scenario: Optional[int] = Field(None, description="Escenario optimista (porcentaje)")
    realistic_scenario: Optional[int] = Field(None, description="Escenario realista (porcentaje)")
    pessimistic_scenario: Optional[int] = Field(None, description="Escenario pesimista (porcentaje)")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
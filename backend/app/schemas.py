from datetime import datetime, date
from typing import Annotated, Optional, Literal, List
from bson import ObjectId
from pydantic import Field, EmailStr, BaseModel
from fastapi_crudrouter_mongodb import MongoModel, MongoObjectId

class User(MongoModel):
    id: Annotated[ObjectId, MongoObjectId] | None = Field(default=None, alias="_id", description="ID único del usuario")
    email: EmailStr = Field(..., description="Correo electrónico del usuario", example="user@example.com")
    name: str = Field(..., description="Nombre completo del usuario", example="Juan Pérez")
    password_hash: str = Field(..., description="Contraseña hasheada (bcrypt)")
    role: Literal["student", "advisor", "po", "admin"] = Field(..., description="Rol asignado al usuario")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Fecha de creación de la cuenta")

class Project(MongoModel):
    id: Annotated[ObjectId, MongoObjectId] | None = Field(default=None, alias="_id", description="ID único del proyecto")
    code: str = Field(..., description="Código corto del proyecto", example="SM-2024")
    name: str = Field(..., description="Nombre del proyecto", example="SprintMind Backend")
    description: Optional[str] = Field(None, description="Descripción detallada del proyecto")
    owner_id: Annotated[ObjectId, MongoObjectId] | None = Field(None, description="ID del usuario dueño del proyecto")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Fecha de creación del proyecto")
    total_prompt_tokens: int = Field(default=0, description="Total de tokens de prompt usados por la IA")
    total_completion_tokens: int = Field(default=0, description="Total de tokens de completitud generados por la IA")
    total_processing_time_ms: float = Field(default=0.0, description="Tiempo total de procesamiento de IA en milisegundos")

class UserStory(MongoModel):
    id: Annotated[ObjectId, MongoObjectId] | None = Field(default=None, alias="_id", description="ID único de la historia de usuario")
    project_id: Annotated[ObjectId, MongoObjectId] = Field(..., description="ID del proyecto al que pertenece la HU")
    code: str = Field(..., description="Código identificador (ej: US-01)", example="US-01")
    epica: str = Field(..., description="Nombre de la épica relacionada", example="Autenticación")
    nombre: str = Field(..., description="Título de la historia", example="Login de usuario")
    descripcion: str = Field(..., description="Descripción detallada (Como [rol] quiero [acción] para [beneficio])")
    criterios: List[str] = Field(..., description="Lista de criterios de aceptación")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Fecha de creación de la HU")
    # Campos adicionales para Product Backlog
    priority: str = Field(default="Medium", description="Prioridad de la historia (Low, Medium, High, Must Have, etc.)", example="High")
    story_points: int = Field(default=0, description="Puntos de historia estimados", example=5)
    dor: int = Field(default=0, description="Definition of Ready (0-100%)", example=85)
    status: str = Field(default="Ready", description="Estado actual de la historia", example="Backlog")
    deps: int = Field(default=0, description="Número de dependencias activas")
    ai: bool = Field(default=False, description="Indica si fue generada o analizada por IA")

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
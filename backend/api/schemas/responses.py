# backend/api/schemas/responses.py
from datetime import date, datetime
from typing import List, Literal
from pydantic import BaseModel, EmailStr

class PdfStoryOut(BaseModel):
    epic: str
    us: str
    nombre: str
    criterios: List[str]
    descripcion: str
    priority: str
    story_points: int
    dor: int
    status: str
    deps: int

class PdfImportOut(BaseModel):
    project_id: str
    historias: list[PdfStoryOut]
    total_prompt_tokens: int
    total_completion_tokens: int
    total_processing_time_ms: float

class UserOut(BaseModel):
    """Respuesta de usuario sin datos sensibles como la contraseña."""
    id: str
    email: EmailStr
    name: str
    role: Literal["student", "advisor", "po", "admin"]
    created_at: datetime

class ReleaseBacklogOut(BaseModel):
    id: str
    project_id: str
    us_codes: List[str]
    generated_at: datetime
    total_prompt_tokens: int
    total_completion_tokens: int
    total_processing_time_ms: float

class ReleasePlanningOut(BaseModel):
    id: str
    project_id: str
    release_plan: dict  # Plan completo generado por IA
    generated_at: datetime
    total_prompt_tokens: int
    total_completion_tokens: int
    total_processing_time_ms: float

class ProjectConfigOut(BaseModel):
    id: str
    project_id: str
    num_devs: int
    team_velocity: int
    sprint_duration: int
    prioritization_metric: str
    release_target_date: datetime  # Cambiar de date a datetime
    team_capacity: int | None
    optimistic_scenario: int | None
    realistic_scenario: int | None
    pessimistic_scenario: int | None
    created_at: datetime
    updated_at: datetime
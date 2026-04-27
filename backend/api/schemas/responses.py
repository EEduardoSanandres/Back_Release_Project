# backend/api/schemas/responses.py
from datetime import date, datetime
from typing import List, Literal
from pydantic import BaseModel, EmailStr, Field

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
    id: str = Field(..., description="ID único del usuario", example="65e123abc...")
    email: EmailStr = Field(..., description="Correo electrónico", example="usuario@example.com")
    name: str = Field(..., description="Nombre completo", example="Juan Pérez")
    role: Literal["student", "advisor", "po", "admin"] = Field(..., description="Rol del usuario")
    created_at: datetime = Field(..., description="Fecha de creación del registro")

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
    releases: list[dict]
    num_releases: int
    project_analysis: dict
    overall_risks: list[dict]
    overall_recommendations: list[str]
    generated_at: datetime
    total_prompt_tokens: int
    total_completion_tokens: int
    total_processing_time_ms: float
    suggested_config: dict | None = None

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

class DashboardStatsOut(BaseModel):
    total_projects: int = Field(..., description="Número total de proyectos en el sistema", example=12)
    projects_growth: str = Field(..., description="Texto descriptivo del crecimiento mensual", example="+2 este mes")
    total_active_stories: int = Field(..., description="Total de historias que no están en estado 'Done'", example=45)
    pending_refinement: int = Field(..., description="Historias con DoR < 80%", example=8)
    planned_releases: int = Field(..., description="Número de releases planificados", example=3)
    next_release_date: str | None = Field(None, description="Fecha del próximo release (YYYY-MM-DD)", example="2024-06-15")
    ai_analysis_count: int = Field(..., description="Número de análisis realizados por la IA recientemente", example=150)
    ai_analysis_period: str = Field(..., description="Periodo de tiempo del conteo de IA", example="Esta semana")

class ProjectStatsOut(BaseModel):
    total_stories: int = Field(..., description="Total de historias de usuario del proyecto", example=20)
    in_development: int = Field(..., description="Historias en desarrollo", example=5)
    completed: int = Field(..., description="Historias completadas", example=10)
    pending: int = Field(..., description="Historias pendientes", example=5)
    releases_count: int = Field(..., description="Número de releases planificados", example=2)
    total_story_points: int = Field(..., description="Story points totales del proyecto", example=100)
    completed_story_points: int = Field(..., description="Story points completados", example=60)
    progress_percentage: float = Field(..., description="Porcentaje de avance basado en story points", example=60.0)

class CalendarEventOut(BaseModel):
    id: str
    title: str
    type: str
    start_date: str
    end_date: str
    color: str
    text_color: str
    release_id: str | None = None
    sprint_number: int | None = None
    description: str

class EventDetailOut(BaseModel):
    id: str
    title: str
    location: str
    time: str
    date: str
    color: str
    event_type: str
    sprint_number: int | None = None
    release_id: str | None = None
    description: str

class CalendarEventsOut(BaseModel):
    events: list[CalendarEventOut]
    event_details: list[EventDetailOut]
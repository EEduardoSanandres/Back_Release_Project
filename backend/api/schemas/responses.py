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
    releases: list[dict]
    num_releases: int
    project_analysis: dict
    overall_risks: list[dict]
    overall_recommendations: list[str]
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

class DashboardStatsOut(BaseModel):
    total_projects: int
    projects_growth: str
    total_active_stories: int
    pending_refinement: int
    planned_releases: int
    next_release_date: str | None 
    ai_analysis_count: int
    ai_analysis_period: str

class ProjectStatsOut(BaseModel):
    total_stories: int
    in_development: int
    completed: int
    pending: int
    releases_count: int
    total_story_points: int
    completed_story_points: int
    progress_percentage: float

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
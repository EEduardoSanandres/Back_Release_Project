from __future__ import annotations
from datetime import date
from typing import Literal, List
from pydantic import BaseModel, HttpUrl, Field, EmailStr

# ---------- User ----------
class UserCreateIn(BaseModel):
    email: EmailStr
    name: str
    password: str = Field(
        ..., 
        min_length=6, 
        max_length=72,
        description="Password must be between 6 and 72 characters (bcrypt limit)"
    )
    role: Literal["student", "advisor", "po", "admin"]

# ---------- Chat ----------
class ChatIn(BaseModel):
    message: str = Field(..., min_length=1)

# ---------- PDF ----------
class PdfIn(BaseModel):
    pdf_url: HttpUrl | None = None
    pdf_b64: str  | None = None
    user_id: str = Field(..., description="ID del usuario que sube el PDF")

# ---------- Project Config ----------
class ProjectConfigCreateIn(BaseModel):
    project_id: str = Field(..., description="ID del proyecto")
    num_devs: int = Field(..., description="Número de desarrolladores en el equipo")
    team_velocity: int = Field(..., description="Velocidad del equipo (story points por sprint)")
    sprint_duration: int = Field(..., description="Duración del sprint en semanas")
    prioritization_metric: str = Field(..., description="Métrica de priorización (ej: businessValue, storyPoints)")
    release_target_date: date = Field(..., description="Fecha objetivo de release")
    team_capacity: int | None = Field(None, description="Capacidad del equipo en horas por sprint")
    # Escenarios de estimación
    optimistic_scenario: int | None = Field(None, description="Escenario optimista (porcentaje)")
    realistic_scenario: int | None = Field(None, description="Escenario realista (porcentaje)")
    pessimistic_scenario: int | None = Field(None, description="Escenario pesimista (porcentaje)")

class ProjectConfigUpdateIn(BaseModel):
    num_devs: int | None = Field(None, description="Número de desarrolladores en el equipo")
    team_velocity: int | None = Field(None, description="Velocidad del equipo (story points por sprint)")
    sprint_duration: int | None = Field(None, description="Duración del sprint en semanas")
    prioritization_metric: str | None = Field(None, description="Métrica de priorización (ej: businessValue, storyPoints)")
    release_target_date: date | None = Field(None, description="Fecha objetivo de release")
    team_capacity: int | None = Field(None, description="Capacidad del equipo en horas por sprint")
    # Escenarios de estimación
    optimistic_scenario: int | None = Field(None, description="Escenario optimista (porcentaje)")
    realistic_scenario: int | None = Field(None, description="Escenario realista (porcentaje)")
    pessimistic_scenario: int | None = Field(None, description="Escenario pesimista (porcentaje)")

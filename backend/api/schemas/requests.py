from __future__ import annotations
from datetime import date, datetime
from typing import Literal, List
from pydantic import BaseModel, HttpUrl, Field, EmailStr

# ---------- User ----------
class UserCreateIn(BaseModel):
    email: EmailStr = Field(..., description="Correo electrónico del nuevo usuario", example="nuevo.usuario@example.com")
    name: str = Field(..., description="Nombre completo del nuevo usuario", example="Andrés Manuel")
    password: str = Field(
        ..., 
        min_length=6, 
        max_length=72,
        description="Contraseña (mínimo 6 caracteres, máximo 72 debido al límite de bcrypt)",
        example="Password123!"
    )
    role: Literal["student", "advisor", "po", "admin"] = Field(..., description="Rol del usuario en el sistema", example="student")

# ---------- Chat ----------
class ChatIn(BaseModel):
    message: str = Field(..., min_length=1, description="Mensaje a enviar a la IA", example="¿Cómo puedo priorizar mis historias de usuario?")

# ---------- PDF ----------
class PdfIn(BaseModel):
    pdf_url: HttpUrl | None = Field(None, description="URL pública del archivo PDF a procesar")
    pdf_b64: str  | None = Field(None, description="Archivo PDF codificado en Base64")
    user_id: str = Field(..., description="ID del usuario que sube el PDF para asignarlo como dueño del proyecto", example="65e123abc...")

# ---------- Project Config ----------
class ProjectConfigCreateIn(BaseModel):
    project_id: str = Field(..., description="ID del proyecto")
    num_devs: int = Field(..., description="Número de desarrolladores en el equipo")
    team_velocity: int = Field(..., description="Velocidad del equipo (story points por sprint)")
    sprint_duration: int = Field(..., description="Duración del sprint en semanas")
    prioritization_metric: str = Field(..., description="Métrica de priorización (ej: businessValue, storyPoints)")
    release_target_date: datetime = Field(..., description="Fecha objetivo de release")
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
    release_target_date: datetime | None = Field(None, description="Fecha objetivo de release")
    team_capacity: int | None = Field(None, description="Capacidad del equipo en horas por sprint")
    # Escenarios de estimación
    optimistic_scenario: int | None = Field(None, description="Escenario optimista (porcentaje)")
    realistic_scenario: int | None = Field(None, description="Escenario realista (porcentaje)")
    pessimistic_scenario: int | None = Field(None, description="Escenario pesimista (porcentaje)")

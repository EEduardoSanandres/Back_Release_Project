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
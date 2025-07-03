# backend/api/schemas/responses.py
from datetime import date, datetime
from typing import List
from pydantic import BaseModel

class PdfStoryOut(BaseModel):
    epic: str
    us: str
    nombre: str
    criterios: List[str]
    descripcion: str

class PdfImportOut(BaseModel):
    project_id: str
    historias: list[PdfStoryOut]

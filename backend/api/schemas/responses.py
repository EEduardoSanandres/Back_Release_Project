from datetime import date, datetime
from typing import List, Any
from pydantic import BaseModel

class ChatOut(BaseModel):
    response: str

class StoryOut(BaseModel):
    id: str
    role: str
    action: str
    benefit: str
    status: str
    priority: int | None = None

class PdfStoryOut(BaseModel):
    epic: str
    us: str
    nombre: str
    criterios: List[str]
    descripcion: str

class GraphOut(BaseModel):
    project_id: str
    nodes: list[Any]
    links: list[Any]

class ReleaseItemOut(BaseModel):
    story_id: str
    points: int

class ReleaseOut(BaseModel):
    project_id: str
    name: str
    start: date
    end: date
    capacity_pts: int
    items: List[ReleaseItemOut]
    generated_at: datetime

class PdfImportOut(BaseModel):
    project_id: str
    historias: list[PdfStoryOut]
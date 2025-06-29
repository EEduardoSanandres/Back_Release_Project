from datetime import datetime
from typing import List, Optional, Annotated, Union, Literal
from bson import ObjectId
from pydantic import Field, EmailStr
from fastapi_crudrouter_mongodb import MongoModel, MongoObjectId

# ──────────────────────────────────────────────────────────────
class User(MongoModel):
    id: Annotated[ObjectId, MongoObjectId] | None = Field(default=None, alias="_id")
    email: EmailStr
    name: str
    role: Literal["student", "advisor", "po", "admin"]
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Project(MongoModel):
    id: Annotated[ObjectId, MongoObjectId] | None = Field(default=None, alias="_id")
    code: str
    name: str
    description: Optional[str] = None
    owner_id: Annotated[ObjectId, MongoObjectId]
    created_at: datetime = Field(default_factory=datetime.utcnow)

class PDFFile(MongoModel):
    id: Annotated[ObjectId, MongoObjectId] | None = Field(default=None, alias="_id")
    project_id: Annotated[ObjectId, MongoObjectId]
    filename: str
    upload_date: datetime = Field(default_factory=datetime.utcnow)
    parse_status: Literal["pending", "done", "error"] = "pending"
    extracted_story_ids: List[Annotated[ObjectId, MongoObjectId]] = []

class Epic(MongoModel):
    id: Annotated[ObjectId, MongoObjectId] | None = Field(default=None, alias="_id")
    project_id: Annotated[ObjectId, MongoObjectId]
    code: str
    title: str
    description: Optional[str] = None

class Acceptance(MongoModel):
    text: str

class UserStory(MongoModel):
    id: Annotated[ObjectId, MongoObjectId] | None = Field(default=None, alias="_id")
    project_id: Annotated[ObjectId, MongoObjectId]
    epic_id: Annotated[ObjectId, MongoObjectId] | None = None
    role: str
    action: str
    benefit: str
    acceptance: List[Acceptance]
    status: Literal["new", "refined", "selected", "done"] = "new"
    story_points: Optional[int] = None
    priority: Optional[int] = None
    dependencies: List[Annotated[ObjectId, MongoObjectId]] = []
    created_at: datetime = Field(default_factory=datetime.utcnow)

class StoryVersion(MongoModel):
    id: Annotated[ObjectId, MongoObjectId] | None = Field(default=None, alias="_id")
    story_id: Annotated[ObjectId, MongoObjectId]
    version: int
    source: Literal["original", "gemini"]
    text: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Graph(MongoModel):
    id: Annotated[ObjectId, MongoObjectId] | None = Field(default=None, alias="_id")
    project_id: Annotated[ObjectId, MongoObjectId]
    nodes: list
    links: list
    generated_at: datetime = Field(default_factory=datetime.utcnow)

class ReleaseItem(MongoModel):
    story_id: Annotated[ObjectId, MongoObjectId]
    points: int

class Release(MongoModel):
    id: Annotated[ObjectId, MongoObjectId] | None = Field(default=None, alias="_id")
    project_id: Annotated[ObjectId, MongoObjectId]
    name: str
    start: datetime
    end: datetime
    capacity_pts: int
    items: List[ReleaseItem]
    generated_by: Literal["user", "gemini"]
    generated_at: datetime = Field(default_factory=datetime.utcnow)

class WorkPackage(MongoModel):
    id: Annotated[ObjectId, MongoObjectId] | None = Field(default=None, alias="_id")
    project_id: Annotated[ObjectId, MongoObjectId]
    wp_code: str
    description: str
    status: Literal["todo", "wip", "done"] = "todo"

class Cost(MongoModel):
    id: Annotated[ObjectId, MongoObjectId] | None = Field(default=None, alias="_id")
    project_id: Annotated[ObjectId, MongoObjectId]
    category: Literal["personal", "general", "assets"]
    concept: str
    amount: float

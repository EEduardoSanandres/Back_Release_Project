from __future__ import annotations
from datetime import date
from typing import Literal, List
from pydantic import BaseModel, HttpUrl, Field, EmailStr

# ---------- User ----------
class UserCreateIn(BaseModel):
    email: EmailStr
    name: str
    password: str = Field(..., min_length=6, description="Password must be at least 6 characters")
    role: Literal["student", "advisor", "po", "admin"]

# ---------- Chat ----------
class ChatIn(BaseModel):
    message: str = Field(..., min_length=1)

# ---------- PDF ----------
class PdfIn(BaseModel):
    pdf_url: HttpUrl | None = None
    pdf_b64: str  | None = None
    user_id: str = Field(..., description="ID del usuario que sube el PDF")

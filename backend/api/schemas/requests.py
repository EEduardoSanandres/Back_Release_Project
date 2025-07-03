from __future__ import annotations
from datetime import date
from typing import Literal, List
from pydantic import BaseModel, HttpUrl, Field

# ---------- Chat ----------
class ChatIn(BaseModel):
    message: str = Field(..., min_length=1)

# ---------- PDF ----------
class PdfIn(BaseModel):
    pdf_url: HttpUrl | None = None
    pdf_b64: str  | None = None

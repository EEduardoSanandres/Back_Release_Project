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

# ---------- Improve HU ----------
class ImproveStoriesIn(BaseModel):
    story_ids: List[str] | None = None
    text_block: str      | None = None
    prompt: str = "Refine user story"

# ---------- Graph ----------
class GraphIn(BaseModel):
    project_id: str
    layout: Literal["dagre", "circular", "hier"] = "dagre"
    filter_tags: list[str] | None = None

# ---------- Release ----------
class ReleaseIn(BaseModel):
    project_id: str
    start: date | None = None
    end:   date | None = None
    capacity_pts: int | None = None
    push_to_jira: bool = False
    format: Literal["pretty", "raw"] = "pretty"

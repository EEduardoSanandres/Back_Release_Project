from __future__ import annotations

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, BackgroundTasks
from pydantic import HttpUrl
from openai import OpenAI

from backend.api.schemas.requests import (
    ChatIn,
    ImproveStoriesIn,
    GraphIn,
    ReleaseIn,
)
from backend.api.schemas.responses import (
    ChatOut,
    StoryOut,
    GraphOut,
    ReleaseOut,
    PdfStoryOut,
)

# servicios (se inyectan con Depends)
from backend.api.services.pdf_service import PdfService
from backend.api.services.story_service import StoryService
from backend.api.services.graph_service import GraphService
from backend.api.services.release_service import ReleaseService
from backend.api.schemas.responses import PdfImportOut

# router CRUD ya generado
from backend.api.routers.crud import router as crud_router

# --------------------------------------------------------------------------- #
#                                  Routers                                    #
# --------------------------------------------------------------------------- #

router = APIRouter(prefix="/chat", tags=["chat"])
_oai = OpenAI(base_url="http://localhost:1234/v1", api_key="lm-studio")

# 0 ──────────────────────────────── Chat raw ─────────────────────────────── #

@router.post("/", response_model=ChatOut)
async def chat(req: ChatIn):
    """Passthrough sencillo a LM Studio."""
    res = _oai.chat.completions.create(
        model="mistral-7b-instruct-v0.3",
        messages=[{"role": "user", "content": req.message}],
    )
    return {"response": res.choices[0].message.content}


# 1 ─────────────── PDF → borrador de historias de usuario ──────────────── #

@router.post("/pdf/to-userstories", response_model=PdfImportOut)
async def pdf_to_stories(
    pdf_file: UploadFile | None = File(default=None),
    pdf_url : HttpUrl     | None = None,
    pdf_b64: str          | None = None,
    svc: PdfService = Depends(),
):
    return await svc.extract_stories(pdf_file=pdf_file, pdf_url=pdf_url, pdf_b64=pdf_b64)

# 2 ─────────────────── Refinar historias existentes ────────────────────── #

@router.post("/stories/improve", response_model=list[StoryOut])
async def improve(
    body: ImproveStoriesIn,
    svc: StoryService = Depends(),
):
    return await svc.refine_stories(body)


# 3 ───────────────────── Generar grafo de dependencias ──────────────────── #

@router.post("/graph/generate", response_model=GraphOut)
async def build_graph(
    body: GraphIn,
    svc: GraphService = Depends(),
):
    return await svc.create_graph(body)


# 4 ────────────────────────── Plan de release ──────────────────────────── #

@router.post("/release/generate", response_model=ReleaseOut)
async def generate_release(
    body: ReleaseIn,
    svc: ReleaseService = Depends(),
):
    return await svc.generate_release(body)


# --------------------------------------------------------------------------- #
#                 Router combinado (CRUD + endpoints de chat)                 #
# --------------------------------------------------------------------------- #

api_router = APIRouter(prefix="/api")
api_router.include_router(crud_router)   # CRUD de Mongo
api_router.include_router(router)        # chat + pdf + graph + release

__all__ = ["api_router"]  # se importa desde backend/app/database.py

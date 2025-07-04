from __future__ import annotations

from fastapi import APIRouter, UploadFile, File, Depends
from pydantic import HttpUrl

# Servicio que hace todo el trabajo pesado
from ..services.pdf_service import PdfService

# Esquema de respuesta: project_id + historias
from ..schemas.responses import PdfImportOut


# --------------------------------------------------------------------------- #
#                                Router único                                 #
# --------------------------------------------------------------------------- #

router = APIRouter(
    prefix="/pdf",          # 👉  /api/pdf/to-userstories
    tags=["pdf"],
)

@router.post("/to-userstories", response_model=PdfImportOut)
async def pdf_to_stories(
    pdf_file: UploadFile | None = File(default=None),
    pdf_url : HttpUrl     | None = None,
    pdf_b64: str          | None = None,
    user_id: str          = None,
    svc: PdfService       = Depends(),
):
    """
    • Crea un registro en `projects` por cada PDF subido.  
    • Devuelve `project_id` + las historias extraídas (campos en español).  
    • Inserta las HU en `user_stories`, mapeando la descripción → role / action / benefit.
    • Guarda el `user_id` como `owner_id` del proyecto.
    """
    return await svc.extract_stories(
        pdf_file=pdf_file,
        pdf_url=pdf_url,
        pdf_b64=pdf_b64,
        user_id=user_id,
    )


# --------------------------------------------------------------------------- #
#            Router principal que se importa desde `backend/app`              #
# --------------------------------------------------------------------------- #

api_router = APIRouter()
api_router.include_router(router)

__all__ = ["api_router"]

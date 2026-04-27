from __future__ import annotations
from fastapi import APIRouter, Depends, Body, HTTPException
from typing import List
from ..services.refinement_service import RefinementService

router = APIRouter(prefix="/refinement", tags=["Refinement"])

@router.post(
    "/fix-quality",
    summary="Mejorar calidad (INVEST)",
    description="Analiza y mejora las historias de usuario para que cumplan con el estándar INVEST (Independiente, Negociable, Valiosa, Estimable, Pequeña, Testeable)."
)
async def fix_quality(
    story_ids: List[str] = Body(..., embed=True),
    service: RefinementService = Depends()
):
    """
    Mejora la calidad de las historias seleccionadas.
    """
    try:
        return await service.fix_quality(story_ids)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post(
    "/generate-gherkin",
    summary="Generar Gherkin",
    description="Convierte los criterios de aceptación tradicionales a formato Gherkin (Given/When/Then) para facilitar las pruebas automatizadas."
)
async def generate_gherkin(
    story_ids: List[str] = Body(..., embed=True),
    service: RefinementService = Depends()
):
    """
    Genera criterios en formato Gherkin.
    """
    try:
        return await service.generate_gherkin(story_ids)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post(
    "/estimate-points",
    summary="Estimar Story Points",
    description="Sugiere una estimación de puntos de historia basada en la complejidad y descripción de la HU."
)
async def estimate_points(
    story_ids: List[str] = Body(..., embed=True),
    service: RefinementService = Depends()
):
    """
    Sugiere estimación de puntos de historia.
    """
    try:
        return await service.estimate_points(story_ids)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post(
    "/detect-duplicates",
    summary="Detectar duplicados",
    description="Identifica historias de usuario que podrían estar solapadas o ser duplicadas dentro del mismo proyecto."
)
async def detect_duplicates(
    story_ids: List[str] = Body(..., embed=True),
    service: RefinementService = Depends()
):
    """
    Detecta historias duplicadas o redundantes.
    """
    try:
        return await service.detect_duplicates(story_ids)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

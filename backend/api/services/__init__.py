# backend/api/services/__init__.py

from .pdf_service import PdfService

def pdf_service() -> PdfService:
    """Factory para inyectar PdfService con Depends()."""
    return PdfService()

__all__ = ["pdf_service", "PdfService"]

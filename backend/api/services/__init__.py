# backend/api/services/__init__.py

from .pdf_service import PdfService
from .auth_service import AuthService, auth_service

def pdf_service() -> PdfService:
    """Factory para inyectar PdfService con Depends()."""
    return PdfService()

__all__ = ["pdf_service", "PdfService", "auth_service", "AuthService"]

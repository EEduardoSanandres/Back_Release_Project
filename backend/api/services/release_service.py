# backend/api/services/release_service.py
from __future__ import annotations

from datetime import datetime, date
from typing import List

from backend.api.schemas.requests import ReleaseIn
from backend.api.schemas.responses import ReleaseOut, ReleaseItemOut
from backend.app.database import db        # motor client (si decides persistir)

class ReleaseService:
    async def generate_release(self, body: ReleaseIn) -> ReleaseOut:
        """
        Construye un release básico:
        • Usa capacidad por defecto 100 pts si no se indica.
        • De momento deja items vacío; llena esta lista cuando
          implementes tu algoritmo de asignación.
        """
        now = datetime.utcnow()
        return ReleaseOut(
            project_id=body.project_id,
            name=f"Release-{now:%Y%m%d}",
            start=body.start or date.today(),
            end=body.end or date.today(),
            capacity_pts=body.capacity_pts or 100,
            items=[],                      # TODO: populate with ReleaseItemOut
            generated_at=now,
        )

    async def push_to_jira(self, rel: ReleaseOut) -> None:
        """Stub: publica el release en Jira cuando esté implementado."""
        pass

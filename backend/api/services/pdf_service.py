"""
PDF → Historias + proyecto   (usa LM Studio vía API OpenAI-compatible)

• Crea un registro en `projects` por cada PDF subido.
• Devuelve project_id + historias (campos españoles).
• Inserta las HU en `user_stories` mapeando descripcion → role/action/benefit.
"""

from __future__ import annotations
import base64, io, re
from datetime import datetime
from typing import List

import httpx
from fastapi import UploadFile, HTTPException
from pydantic import HttpUrl
from pypdf import PdfReader, errors as pdf_errors
from openai import OpenAI
from bson import ObjectId

from backend.api.schemas.responses import PdfStoryOut, PdfImportOut
from backend.app.database import db

# ───── Configuración LM Studio ──────────────────────────────────────────
_oai = OpenAI(base_url="http://localhost:1234/v1", api_key="lm-studio")
MODEL = "mistral-7b-instruct-v0.3"
CHARS = 6_000  # ≈1 500 tokens

PROMPT = (
    "Eres un analista ágil.\n"
    "Del texto devuelve SÓLO las historias en JSON, una por línea, con claves "
    "{epic, us, nombre, criterios, descripcion}.\n"
)

OBJ_RGX   = re.compile(r"\{.*?\}", re.S)
DESC_RGX  = re.compile(
    r"Como\s+(?P<role>.+?)\s+quiero\s+(?P<action>.+?)\s+para\s+(?P<benefit>.+)",
    re.I
)

# ───── Servicio ──────────────────────────────────────────────────────────
class PdfService:
    async def extract_stories(
        self,
        *,
        pdf_file: UploadFile | None,
        pdf_url:  HttpUrl     | None,
        pdf_b64:  str        | None,
    ) -> PdfImportOut:
        # 1 leer PDF → texto
        pdf_bytes = await self._read(pdf_file, pdf_url, pdf_b64)
        plain     = self._pdf_to_text(pdf_bytes)

        # 2 nuevo proyecto
        project_id = await self._create_project(self._filename(pdf_file, pdf_url))

        # 3 Generar historias
        historias: list[PdfStoryOut] = []
        for chunk in self._chunks(plain):
            raw  = await self._chat(chunk)
            historias.extend(self._parse_objs(raw))

        # 4 Persistir HU
        if historias:
            await db.user_stories.insert_many(
                [
                    {
                        "project_id": project_id,
                        **self._desc_to_rab(h.descripcion),
                        "acceptance": [{"text": c} for c in h.criterios],
                        "status": "new",
                        "created_at": datetime.utcnow(),
                    }
                    for h in historias
                ]
            )

        return PdfImportOut(project_id=str(project_id), historias=historias)

    # ───────── helpers principales ─────────
    async def _chat(self, chunk: str) -> str:
        r = _oai.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": PROMPT + chunk}],
            temperature=0.2,
        )
        return r.choices[0].message.content

    def _parse_objs(self, raw: str) -> List[PdfStoryOut]:
        out = []
        for js in OBJ_RGX.findall(raw):
            try:
                out.append(PdfStoryOut.model_validate_json(js))
            except Exception:
                continue
        return out

    def _desc_to_rab(self, desc: str) -> dict[str, str]:
        """
        Convierte 'Como X quiero Y para Z' → role/action/benefit
        Devuelve diccionario listo para Mongo.
        """
        m = DESC_RGX.search(desc.replace("\n", " "))
        if not m:
            return {"role": "", "action": "", "benefit": desc}
        return {
            "role": m["role"].strip(),
            "action": m["action"].strip(),
            "benefit": m["benefit"].strip().rstrip("."),
        }

    # ───────── creación de proyecto ─────────
    async def _create_project(self, name: str) -> ObjectId:
        last = await db.projects.find_one(sort=[("created_at", -1)])
        seq  = int(last["code"].split("-")[1]) + 1 if last else 1
        code = f"PROJ-{seq:03d}"
        res = await db.projects.insert_one(
            {
                "code": code,
                "name": name,
                "description": "",
                "owner_id": None,
                "created_at": datetime.utcnow(),
            }
        )
        return res.inserted_id

    # ───────── utilidades PDF y troceo ──────
    async def _read(self, f, url, b64) -> bytes:
        if f:
            data = await f.read()
        elif url:
            async with httpx.AsyncClient() as c:
                data = (await c.get(str(url))).content
        elif b64:
            data = base64.b64decode(b64)
        else:
            raise HTTPException(400, "Proporciona pdf_file, pdf_url o pdf_b64")
        if not data.startswith(b"%PDF"):
            raise HTTPException(415, "El archivo no es PDF")
        return data

    def _pdf_to_text(self, b: bytes) -> str:
        try:
            reader = PdfReader(io.BytesIO(b))
        except pdf_errors.PdfStreamError:
            raise HTTPException(400, "PDF dañado")
        return "\n".join(p.extract_text() or "" for p in reader.pages)

    def _chunks(self, text: str, size: int = CHARS):
        return [text[i : i + size] for i in range(0, len(text), size)]

    @staticmethod
    def _filename(f: UploadFile | None, url: HttpUrl | None) -> str:
        if f:
            return f.filename
        if url:
            return url.path.rsplit("/", 1)[-1]
        return "PDF importado"

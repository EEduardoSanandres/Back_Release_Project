"""
PDF → Historias de usuario (LM Studio).
Devuelve ‘PdfStoryOut’ con épica, nº US, nombre, criterios y descripción.
"""

from __future__ import annotations
import base64, io, re, itertools
from typing import List

import httpx
from fastapi import UploadFile, HTTPException
from pydantic import HttpUrl
from pypdf import PdfReader, errors as pdf_errors
from openai import OpenAI

from backend.api.schemas.responses import PdfStoryOut
# Si quieres seguir guardando en Mongo ajusta los campos a tu gusto
# from backend.app.database import db, ObjectId

_oai = OpenAI(base_url="http://localhost:1234/v1", api_key="lm-studio")
MODEL = "mistral-7b-instruct-v0.3"
CHUNK = 6_000  # caracteres ≈ 1 500 tokens

PROMPT = (
    "Eres un analista ágil.\n"
    "A partir del fragmento devuélveme SOLO las historias en JSON, "
    "una por línea, con las claves:\n"
    "{epic, us, nombre, criterios, descripcion}.\n"
    "• epic y us son los números.\n"
    "• criterios es lista de strings.\n"
    "• descripcion es la frase 'Como <rol> quiero ...'.\n\n"
)

JSON_RGX = re.compile(r"\{.*?\}", re.S)  # captura cada objeto json

class PdfService:
    async def extract_stories(
        self,
        *,
        pdf_file: UploadFile | None,
        pdf_url:  HttpUrl     | None,
        pdf_b64:  str        | None,
    ) -> List[PdfStoryOut]:
        pdf_bytes = await self._read_pdf(pdf_file, pdf_url, pdf_b64)
        plain     = self._pdf_to_text(pdf_bytes)

        stories: list[PdfStoryOut] = []
        for chunk in self._chunks(plain):
            respuesta = await self._ask_llm(chunk)
            stories.extend(self._parse_json_objects(respuesta))

        return stories   # << se devuelven en la misma respuesta

    # ---------- LLM ----------
    async def _ask_llm(self, text: str) -> str:
        res = _oai.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": PROMPT + text}],
            temperature=0.2,
        )
        return res.choices[0].message.content

    # ---------- parsing ----------
    def _parse_json_objects(self, raw: str) -> List[PdfStoryOut]:
        objs = JSON_RGX.findall(raw)
        out  = []
        for js in objs:
            try:
                data = PdfStoryOut.model_validate_json(js)
                out.append(data)
            except Exception:
                continue  # ignora líneas mal formateadas
        return out

    # ---------- utils PDF ----------
    async def _read_pdf(
        self,
        f: UploadFile | None,
        url: HttpUrl | None,
        b64: str | None,
    ) -> bytes:
        if f:
            content = await f.read()
        elif url:
            async with httpx.AsyncClient() as c:
                content = (await c.get(str(url))).content
        elif b64:
            content = base64.b64decode(b64)
        else:
            raise HTTPException(400, "Proporciona pdf_file, pdf_url o pdf_b64")

        if not content.startswith(b"%PDF"):
            raise HTTPException(415, "El archivo no parece un PDF")
        return content

    def _pdf_to_text(self, data: bytes) -> str:
        try:
            reader = PdfReader(io.BytesIO(data))
        except pdf_errors.PdfStreamError:
            raise HTTPException(400, "PDF dañado o incompleto")
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    def _chunks(self, text: str, size: int = CHUNK) -> List[str]:
        return [text[i : i + size] for i in range(0, len(text), size)]

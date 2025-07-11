from __future__ import annotations
import base64, io, json, logging, os, anyio
from datetime import datetime
import time # Importar el módulo time
from typing import List

import google.generativeai as genai
import httpx
from fastapi import UploadFile, HTTPException
from pydantic import HttpUrl
from pypdf import PdfReader, errors as pdf_errors
from bson import ObjectId
from pymongo.errors import BulkWriteError

from ..schemas.responses import PdfStoryOut, PdfImportOut
from ...app.db import db

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
MODEL = "gemini-1.5-pro"
CHARS = 15_000

PROMPT = """
Eres un extractor experto de Historias de Usuario (HU).
Analiza el texto suministrado y genera EXCLUSIVAMENTE el bloque comprendido entre
BEGIN_JSON y END_JSON (no incluyas ni BEGIN_JSON ni END_JSON en la respuesta),
sin explicaciones adicionales.

↳ Formato (JSON por línea):
{
  "epic"       : "<código o título de la épica>",
  "us"         : "<código de la historia, ej. '001' o 'us-045'>",
  "nombre"     : "<nombre breve de la HU>",
  "descripcion": "<frase 'Como … quiero … para …'>",
  "criterios"  : ["<Criterio 1>", "<Criterio 2>", …]
}

Reglas estrictas
1. Devuelve UNA línea JSON por historia.
2. Usa exactamente las claves indicadas, en español, en ese orden.
3. Todos los valores son strings, excepto "criterios", que es un array de strings.
4. Sin saltos de línea dentro de un valor.
5. No incluyas comentarios ni caracteres fuera del bloque JSON.
6. Si no tienes criterios, devuelve "criterios": []
7. No uses retornos de carro ni tabulaciones: cada historia en **una sola línea**.
8. La salida debe ser JSON válido según RFC 8259.

Ejemplo
BEGIN_JSON
{"epic":"001","us":"001","nombre":"Búsqueda por palabra clave","descripcion":"Como Comprador quiero buscar productos por palabra clave para encontrar rápidamente lo que necesito.","criterios":["La búsqueda devuelve solo coincidencias de título o descripción.","La respuesta tarda < 30 ms.","Mensaje \"No se encontraron productos\" si no hay coincidencias."]}
END_JSON

El texto a analizar es:
"""

# ───── Servicio ──────────────────────────────────────────────────────────
class PdfService:
    async def extract_stories(
        self,
        *,
        pdf_file: UploadFile | None,
        pdf_url:  HttpUrl    | None,
        pdf_b64:  str        | None,
        user_id:  str        | None = None,
    ) -> PdfImportOut:
        # 1) Leer PDF → texto
        pdf_bytes = await self._read(pdf_file, pdf_url, pdf_b64)
        plain     = self._pdf_to_text(pdf_bytes)

        # 2) Crear proyecto
        project_id = await self._create_project(self._filename(pdf_file, pdf_url), user_id)

        # 3) Generar historias
        historias: list[PdfStoryOut] = []
        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_processing_time_ms = 0.0

        for chunk in self._chunks(plain):
            # Si _chat devuelve una cadena vacía, _parse_objs devolverá []
            # y el bucle continuará con el siguiente chunk sin fallar.
            raw, prompt_t, completion_t, proc_t = await self._chat(chunk)
            historias.extend(self._parse_objs(raw))
            total_prompt_tokens += prompt_t
            total_completion_tokens += completion_t
            total_processing_time_ms += proc_t

        # 4) Eliminar códigos duplicados (en BD y dentro del lote)
        existing_codes = {
            d["code"]
            async for d in db.user_stories.find(
                {"project_id": project_id}, {"code": 1, "_id": 0}
            )
        }
        docs, seen = [], set(existing_codes)
        for h in historias:
            if h.us in seen:
                continue
            seen.add(h.us)
            docs.append(
                {
                    "project_id":  project_id,
                    "epica":       h.epic,
                    "nombre":      h.nombre,
                    "descripcion": h.descripcion,
                    "criterios":   h.criterios,
                    "code":        h.us,
                    "created_at":  datetime.utcnow(),
                }
            )

        # 5) Insertar lote (sin detenerse por otros duplicados inesperados)
        if docs:
            try:
                await db.user_stories.insert_many(docs, ordered=False)
            except BulkWriteError:
                pass
        
        await db.projects.update_one(
            {"_id": project_id},
            {
                "$set": {
                    "total_prompt_tokens": total_prompt_tokens,
                    "total_completion_tokens": total_completion_tokens,
                    "total_processing_time_ms": total_processing_time_ms,
                }
            }
        )

        return PdfImportOut(
            project_id=str(project_id),
            historias=historias,
            total_prompt_tokens=total_prompt_tokens,
            total_completion_tokens=total_completion_tokens,
            total_processing_time_ms=total_processing_time_ms,
        )

    # ───────── helpers principales ─────────
    async def _chat(self, chunk: str) -> tuple[str, int, int, float]:
        """
        Llama al modelo Gemini en un hilo aparte para no bloquear el event-loop.
        Ahora es tolerante a fallos: si Gemini no devuelve contenido,
        retorna una cadena vacía en lugar de lanzar una excepción.
        Retorna el contenido, prompt_tokens, completion_tokens y tiempo de procesamiento.
        """
        model = genai.GenerativeModel(MODEL)
        prompt_tokens = 0
        completion_tokens = 0
        processing_time_ms = 0.0

        def _generate():
            nonlocal prompt_tokens, completion_tokens, processing_time_ms
            try:
                start_time = time.perf_counter() # Iniciar el contador de tiempo
                resp = model.generate_content(
                    PROMPT + chunk,
                    generation_config={
                        "temperature": 0.2, # Un poco más determinista para JSON
                        "max_output_tokens": 8192,
                    },
                    safety_settings={
                        'HARM_CATEGORY_HARASSMENT': 'BLOCK_NONE',
                        'HARM_CATEGORY_HATE_SPEECH': 'BLOCK_NONE',
                        'HARM_CATEGORY_SEXUALLY_EXPLICIT': 'BLOCK_NONE',
                        'HARM_CATEGORY_DANGEROUS_CONTENT': 'BLOCK_NONE',
                    }
                )
                end_time = time.perf_counter() # Finalizar el contador de tiempo
                processing_time_ms = (end_time - start_time) * 1000 # Convertir a milisegundos

                if resp.usage_metadata:
                    prompt_tokens = resp.usage_metadata.prompt_token_count
                    completion_tokens = resp.usage_metadata.candidates_token_count
                return resp.text
            except ValueError:
                finish_reason = "DESCONOCIDA"
                if resp.candidates and resp.candidates[0].finish_reason:
                    finish_reason = resp.candidates[0].finish_reason.name

                logging.warning(
                    "Gemini no devolvió contenido para un chunk. "
                    f"Razón de finalización probable: {finish_reason}"
                )
                return "" # Devolver una cadena vacía para no detener el proceso
            except Exception as e:
                logging.error(f"Error inesperado al llamar a la API de Gemini: {e}")
                return ""


        raw_text = await anyio.to_thread.run_sync(_generate)
        return raw_text, prompt_tokens, completion_tokens, processing_time_ms

    def _parse_objs(self, raw: str) -> List[PdfStoryOut]:
        """
        Lee línea a línea el bloque devuelto por el LLM y valida solo
        las que sean JSON completo.  Descarta silenciosamente líneas inválidas.
        """
        historias: list[PdfStoryOut] = []
        if not raw: # Si la entrada es vacía, no hay nada que hacer.
            return historias

        for line in raw.splitlines():
            line = line.strip()
            # Una comprobación más flexible para JSON que pudiera estar indentado
            if line.startswith("{") and line.endswith("}"):
                try:
                    data = json.loads(line)
                    # Aseguramos que la clave "criterios" siempre exista
                    if "criterios" not in data:
                        data["criterios"] = []
                    historias.append(PdfStoryOut(**data))
                except (json.JSONDecodeError, TypeError, KeyError) as err:
                    logging.warning(f"Línea JSON descartada por error de parseo: {err} | Línea: '{line}'")
        return historias

    # ───────── creación de proyecto ─────────
    async def _create_project(self, name: str, user_id: str | None = None) -> ObjectId:
        last = await db.projects.find_one(sort=[("created_at", -1)])
        seq  = int(last["code"].split("-")[1]) + 1 if last else 1
        
        owner_id = ObjectId(user_id) if user_id else None
        
        res = await db.projects.insert_one(
            {
                "code":        f"PROJ-{seq:03d}",
                "name":        name,
                "description": "",
                "owner_id":    owner_id,
                "created_at":  datetime.utcnow(),
                "total_prompt_tokens": 0,
                "total_completion_tokens": 0,
                "total_processing_time_ms": 0.0,
            }
        )
        return res.inserted_id

    # ───────── utilidades PDF y troceo (sin cambios) ──────
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
        """Divide sin solape para minimizar repeticiones."""
        return [text[i : i + size] for i in range(0, len(text), size)]

    @staticmethod
    def _filename(f: UploadFile | None, url: HttpUrl | None) -> str:
        if f:
            return f.filename
        if url:
            return url.path.rsplit("/", 1)[-1]
        return "PDF importado"
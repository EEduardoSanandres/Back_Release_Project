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
MODEL = "gemini-2.5-pro"
CHARS = 15_000

PROMPT = """
Eres un experto analista de requisitos y creador de Historias de Usuario (HU).
Analiza las especificaciones del proyecto suministradas y genera TODAS las Historias de Usuario necesarias para implementar completamente el sistema.

↳ Formato de salida (JSON por línea):
{
  "epic"       : "<nombre de la épica o módulo>",
  "us"         : "<código único de la historia, ej. 'US-001', 'AUTH-001'>",
  "nombre"     : "<nombre breve y descriptivo de la HU>",
  "descripcion": "<frase completa 'Como [usuario] quiero [funcionalidad] para [beneficio]'>",
  "criterios"  : ["<Criterio de aceptación 1>", "<Criterio 2>", "<Criterio 3>", ...],
  "priority"   : "<High|Medium|Low - basado en importancia para el negocio>",
  "story_points": <número entero: 1,2,3,5,8,13,21 - basado en complejidad técnica>,
  "dor"        : <número entero 0-100: porcentaje de definición completado>,
  "status"     : "<Ready|Needs Refinement - inicialmente todas son Ready>",
  "deps"       : <número entero: dependencias identificadas con otras HU>
}

INSTRUCCIONES ESPECÍFICAS:
1. Analiza COMPLETAMENTE las especificaciones del proyecto
2. Identifica TODOS los módulos, funcionalidades y características mencionadas
3. Crea historias de usuario GRANULARES para cada funcionalidad específica
4. Cada historia debe ser independiente y testable
5. Usa épicas lógicas para agrupar funcionalidades relacionadas
6. Genera códigos únicos que identifiquen claramente la funcionalidad
7. Incluye criterios de aceptación específicos y verificables
8. Evalúa la prioridad basada en impacto en el negocio y usuarios
9. Estima story points basándote en complejidad técnica realista
10. Inicialmente todas las historias son "Ready" con DoR alto

REGLAS TÉCNICAS:
- Devuelve UNA línea JSON por historia
- Usa exactamente las claves indicadas
- Todos los valores son strings excepto "criterios"(array), "story_points"(int), "dor"(int), "deps"(int)
- Sin saltos de línea dentro de valores
- Cada historia en una sola línea
- JSON válido según RFC 8259

Ejemplo de historias generadas:
BEGIN_JSON
{"epic":"Autenticación","us":"AUTH-001","nombre":"Registro de usuarios","descripcion":"Como usuario nuevo quiero registrarme en la plataforma para acceder a mis funcionalidades.","criterios":["El formulario solicita email y contraseña","Se valida formato de email","Se verifica contraseña segura","Se envía email de confirmación"],"priority":"High","story_points":5,"dor":90,"status":"Ready","deps":0}
{"epic":"Autenticación","us":"AUTH-002","nombre":"Inicio de sesión","descripcion":"Como usuario registrado quiero iniciar sesión para acceder a mi cuenta.","criterios":["El login acepta email/contraseña","Se valida credenciales","Se genera token de sesión","Se redirige al dashboard"],"priority":"High","story_points":3,"dor":85,"status":"Ready","deps":1}
END_JSON

El texto a analizar es:
"""

# ───── Servicio ──────────────────────────────────────────────────────────
class PdfService:
    async def process_project_requirements(
        self,
        *,
        pdf_file: UploadFile | None,
        pdf_url:  HttpUrl    | None,
        pdf_b64:  str        | None,
        user_id:  str        | None = None,
    ) -> PdfImportOut:
        """
        Procesa PDFs con especificaciones de proyecto o historias de usuario existentes.
        
        Si el PDF contiene especificaciones del proyecto, genera automáticamente
        todas las historias de usuario necesarias con análisis de prioridad,
        story points, DoR, estado y dependencias.
        
        Si el PDF contiene historias de usuario existentes, las extrae y
        completa con el análisis de Product Backlog.
        
        Args:
            pdf_file: Archivo PDF subido
            pdf_url: URL del PDF
            pdf_b64: PDF en base64
            user_id: ID del usuario que hace la petición
            
        Returns:
            PdfImportOut con las historias procesadas/generadas
        """
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
        skipped_count = 0
        for h in historias:
            if h.us in seen:
                logging.warning(f"Saltando historia duplicada: {h.us} (ya existe en proyecto {project_id})")
                skipped_count += 1
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
                    # Campos adicionales para Product Backlog generados por IA
                    "priority": h.priority,
                    "story_points": h.story_points,
                    "dor": h.dor,
                    "status": h.status,
                    "deps": h.deps,
                    "ai": True,  # Estas historias vienen de IA
                }
            )

        # 5) Insertar lote con mejor manejo de errores
        inserted_count = 0
        if docs:
            try:
                result = await db.user_stories.insert_many(docs, ordered=False)
                inserted_count = len(result.inserted_ids)
                logging.info(f"Insertadas {inserted_count} historias de usuario en proyecto {project_id}")
            except BulkWriteError as e:
                # Algunos documentos pudieron insertarse, otros fallaron
                inserted_count = e.details.get('nInserted', 0)
                failed_count = len(e.details.get('writeErrors', []))
                logging.warning(f"Insertadas {inserted_count} historias, {failed_count} fallaron en proyecto {project_id}")
                for error in e.details.get('writeErrors', []):
                    logging.warning(f"Error al insertar historia {error.get('op', {}).get('code', 'unknown')}: {error.get('errmsg', 'Unknown error')}")
            except Exception as e:
                logging.error(f"Error inesperado al insertar historias en proyecto {project_id}: {e}")
                raise
        
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

        # Log resumen final
        total_processed = len(historias)
        logging.info(f"Procesamiento completado: {total_processed} historias analizadas, {skipped_count} duplicadas saltadas, {inserted_count} insertadas en proyecto {project_id}")

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
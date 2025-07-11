# backend/api/services/release_backlog_service.py
"""
Genera y almacena un Release Backlog ordenado,
basándose en las Historias de Usuario de un proyecto y sus dependencias.
"""
from __future__ import annotations

import os, json, logging, anyio
import time
from typing import List, Tuple
from datetime import datetime # ¡IMPORTAR datetime aquí!

import google.generativeai as genai
from fastapi import HTTPException
from bson import ObjectId
from pymongo.errors import BulkWriteError

from ...app.db import db
from ...app.schemas import UserStory, DependencyGraph, ReleaseBacklog # <--- Asegúrate de que UserStory, DependencyGraph, ReleaseBacklog vengan de models
from ...api.schemas.responses import ReleaseBacklogOut # Para el retorno del servicio

# ────────────────────────── Configuración Gemini ──────────────────────────
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
MODEL = "gemini-1.5-pro"

# ───────────────────────────── PROMPT para Gemini ─────────────────────────
RELEASE_BACKLOG_PROMPT = """
Eres un experto en planificación de proyectos y gestión de backlogs ágiles.
Recibirás una lista de Historias de Usuario (HU) con sus códigos, títulos
y descripciones, así como una lista de dependencias entre ellas.
Tu tarea es generar una **lista ordenada de los códigos de las HU que deberían formar el PRIMER RELEASE**.

Considera las siguientes reglas para determinar el contenido y orden del PRIMER RELEASE:
1.  **Fundacionalidad**: Incluye primero las HU que no tienen dependencias (pre-requisitos) o cuyas dependencias son mínimas y fácilmente satisfacibles. Estas suelen ser las bases del sistema.
2.  **Habilitadoras**: Prioriza las HU que son pre-requisitos para muchas otras HU. Completar estas HU "desbloqueará" un gran número de funcionalidades futuras.
3.  **Coherencia y Valor**: El primer release debe formar un conjunto de funcionalidades coherente y de valor mínimo entregable, incluso si no es el sistema completo. No incluyas HUs que no aporten a esta coherencia mínima si puedes evitarlo.
4.  **Minimiza dependencias no resueltas**: Una HU que es dependiente de otra NO PUEDE aparecer en el release antes que su pre-requisito. Asegúrate de que todas las dependencias *dentro del release* se cumplan. Si una HU tiene dependencias *fuera* del release (es decir, en releases posteriores), solo inclúyela si es estrictamente necesaria para el valor del primer release o si es una HU fundamental.
5.  **Longitud razonable**: El primer release no debe intentar incluir todo el proyecto. Concéntrate en la funcionalidad central o mínima viable. Intenta mantener el número de HUs en el primer release en un rango manejable, por ejemplo, entre 5 y 15 HUs, a menos que el proyecto sea muy pequeño.
6.  **Desempate secundario**: Si varias HU cumplen criterios similares, puedes usar el orden alfabético de los códigos como desempate.
7.  El resultado debe ser ÚNICAMENTE una lista JSON plana de los códigos de las HU, sin texto adicional.

Formato de salida (JSON):
["<codigo_hu_1>", "<codigo_hu_2>", ..., "<codigo_hu_N>"]

Ejemplo:
["us-001", "us-005", "us-002", "us-003"]

---
Lista de Historias de Usuario (código - título - descripción):
{hu_list_str}

---
Dependencias (frm -> to):
{dependencies_str}

Genera el Release Backlog para el **PRIMER RELEASE**:
"""

# ───────────────────────────── Servicio IA ────────────────────────────────
class ReleaseBacklogService:
    """Genera y gestiona el grafo de dependencias para un proyecto."""

    async def generate_backlog(self, project_id: str) -> ReleaseBacklogOut:
        pid = ObjectId(project_id)

        # 1. Obtener todas las historias de usuario del proyecto
        stories_cursor = db.user_stories.find(
            {"project_id": pid}, {"code": 1, "nombre": 1, "descripcion": 1, "_id": 0}
        )
        stories = await stories_cursor.to_list(None)

        if not stories:
            raise HTTPException(404, "El proyecto no tiene historias de usuario para generar un backlog.")

        # 2. Obtener el grafo de dependencias del proyecto
        # Asegúrate de que DependencyGraph aquí sea el modelo de DB, no el de esquema si lo tienes repetido
        dependency_graph_doc = await db.dependencies_graph.find_one(
            {"project_id": pid}
        )
        # Si DependencyGraph fuera un MongoModel, podría inicializarse directamente con el dict de MongoDB
        # Pero si es BaseModel (como lo mostraste en schemas/responses.py), está bien así.
        dependencies_graph = DependencyGraph(**dependency_graph_doc) if dependency_graph_doc else None


        if not dependencies_graph:
            logging.warning(f"No se encontró grafo de dependencias para el proyecto {project_id}. Se generará un backlog sin considerar dependencias.")
            dependencies_str = "No hay dependencias definidas."
        else:
            dependencies_str = "\n".join(
                f"- {p.frm} -> {', '.join(p.to)}" for p in dependencies_graph.pairs
            )


        # Preparar los datos para el prompt de Gemini
        hu_list_str = "\n".join(
            f"- {s['code']} - {s['nombre']} - {s['descripcion']}" for s in stories
        )

        full_prompt = RELEASE_BACKLOG_PROMPT.format(
            hu_list_str=hu_list_str,
            dependencies_str=dependencies_str
        )

        # 3. Llamar a Gemini para generar el backlog
        backlog_codes, prompt_t, completion_t, proc_t = await self._ask_gemini(full_prompt)

        # Validar que Gemini devolvió una lista de códigos válidos
        existing_codes = {s['code'] for s in stories}
        valid_backlog_codes = [code for code in backlog_codes if code in existing_codes]

        if not valid_backlog_codes:
            logging.warning(f"Gemini no pudo generar un Release Backlog válido para el proyecto {project_id}. Se devolverá un backlog por orden alfabético de códigos.")
            valid_backlog_codes = sorted([s['code'] for s in stories])


        # 4. Guardar el Release Backlog en la base de datos
        # Crear un documento siguiendo el esquema de MongoDB (db/models.py)
        # Aquí 'project_id' puede ser ObjectId
        release_backlog_data_for_db = {
            "project_id": pid, # ObjectId
            "us_codes": valid_backlog_codes,
            "generated_at": datetime.utcnow(),
            "total_prompt_tokens": prompt_t,
            "total_completion_tokens": completion_t,
            "total_processing_time_ms": proc_t,
        }

        # Usar replace_one con upsert=True para insertar o actualizar el backlog
        result = await db.release_backlogs.replace_one(
            {"project_id": pid},
            release_backlog_data_for_db,
            upsert=True
        )

        # 5. Preparar el documento para la respuesta de la API (ReleaseBacklogOut)
        # Aquí 'id' es requerido y 'project_id' debe ser string
        final_backlog_doc_for_api = release_backlog_data_for_db.copy() # Copiar para no modificar el dict que se va a la DB

        if result.upserted_id:
            final_backlog_doc_for_api["_id"] = result.upserted_id # El nuevo ID generado por MongoDB
        else:
            # Si no se insertó uno nuevo (porque ya existía), obtenemos el _id del documento que se actualizó.
            # No podemos usar el 'pid' directamente como '_id' porque 'pid' es el ID del PROYECTO, no del ReleaseBacklog.
            # Debemos obtener el ID del documento de ReleaseBacklog.
            existing_doc_from_db = await db.release_backlogs.find_one({"project_id": pid}, {"_id": 1})
            if existing_doc_from_db:
                final_backlog_doc_for_api["_id"] = existing_doc_from_db["_id"]
            else:
                # Esto es un fallback extremo, no debería pasar con upsert=True
                logging.error(f"Error crítico: No se pudo obtener el _id del Release Backlog para el proyecto {project_id} después de upsert.")
                raise HTTPException(status_code=500, detail="Error interno al procesar el Release Backlog (ID no encontrado).")

        # Convertir ObjectId a string para el modelo de respuesta Pydantic
        final_backlog_doc_for_api["id"] = str(final_backlog_doc_for_api["_id"])
        final_backlog_doc_for_api["project_id"] = str(final_backlog_doc_for_api["project_id"])

        # Quitar el campo original '_id' que Pydantic no necesita y podría confundir
        del final_backlog_doc_for_api["_id"]

        return ReleaseBacklogOut(**final_backlog_doc_for_api)

    async def get_backlog(self, project_id: str) -> ReleaseBacklogOut:
        pid = ObjectId(project_id)
        release_backlog_doc = await db.release_backlogs.find_one({"project_id": pid})
        if not release_backlog_doc:
            raise HTTPException(404, f"No se encontró un Release Backlog para el proyecto {project_id}. Genera uno primero.")

        # Convertir ObjectId a string para el modelo de respuesta Pydantic
        release_backlog_doc["id"] = str(release_backlog_doc["_id"])
        release_backlog_doc["project_id"] = str(release_backlog_doc["project_id"])
        del release_backlog_doc["_id"] # Eliminar el campo _id original

        return ReleaseBacklogOut(**release_backlog_doc)


    async def _ask_gemini(self, prompt: str) -> Tuple[List[str], int, int, float]:
        """
        Llama al modelo Gemini para generar el Release Backlog.
        Retorna la lista de códigos de HU, los tokens de entrada, los tokens de salida
        y el tiempo de procesamiento en ms.
        """
        model = genai.GenerativeModel(MODEL)
        prompt_tokens = 0
        completion_tokens = 0
        processing_time_ms = 0.0

        def _generate() -> str:
            nonlocal prompt_tokens, completion_tokens, processing_time_ms
            try:
                start_time = time.perf_counter()
                res = model.generate_content(
                    prompt,
                    generation_config={
                        "temperature": 0.2, # Queremos un orden más determinista
                        "max_output_tokens": 4096 # Suficiente para una lista larga
                    }
                )
                end_time = time.perf_counter()
                processing_time_ms = (end_time - start_time) * 1000

                if res.usage_metadata:
                    prompt_tokens = res.usage_metadata.prompt_token_count
                    completion_tokens = res.usage_metadata.candidates_token_count
                return res.text
            except ValueError:
                logging.warning("Gemini no devolvió contenido (bloqueado por seguridad) para el Release Backlog.")
                return "[]" # Devolver una lista JSON vacía si se bloquea
            except Exception as e:
                logging.error(f"Error inesperado al llamar a la API de Gemini para el Release Backlog: {e}")
                return "[]"

        raw_response = await anyio.to_thread.run_sync(_generate)

        try:
            # Esperamos una lista JSON de strings
            backlog_list = json.loads(raw_response)
            if not isinstance(backlog_list, list) or not all(isinstance(x, str) for x in backlog_list):
                logging.warning(f"La respuesta de Gemini no es un JSON de lista de strings válido: {raw_response}")
                return [], prompt_tokens, completion_tokens, processing_time_ms
            return backlog_list, prompt_tokens, completion_tokens, processing_time_ms
        except json.JSONDecodeError as e:
            logging.warning(f"Error al parsear el JSON de Gemini para el Release Backlog: {e} | Raw: '{raw_response}'")
            return [], prompt_tokens, completion_tokens, processing_time_ms
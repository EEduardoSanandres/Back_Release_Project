# backend/api/services/dependency_service.py
"""
Genera y almacena el grafo de dependencias entre Historias de Usuario
a partir de un proyecto
Expuesto en:
    POST /projects/{project_id}/dependency-graph/generate
    GET  /projects/{project_id}/dependency-graph
"""
from __future__ import annotations

import os, json, logging, anyio
import time 
from typing import List, Set, Tuple

import google.generativeai as genai
from fastapi import HTTPException
from bson import ObjectId

from ...app.db import db
from ...app.schemas import DependencyPair, DependencyGraph

# ────────────────────────── Configuración Gemini ──────────────────────────
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
# Cambiado a un modelo válido (gemini-1.5-flash es excelente para extracciones de este tipo)
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

DEPENDENCY_PROMPT = """
Eres un analista experto en Historias de Usuario (HU).
Tu tarea es identificar las dependencias lógicas entre las siguientes Historias de Usuario.

Una historia A es prerrequisito de B (A -> B) si:
1. B requiere datos o funcionalidad creada en A.
2. B no puede ser completada funcionalmente sin A.
3. Existe una secuencia lógica de negocio.

Recibirás una lista de HU (código - título). Devuelve ÚNICAMENTE líneas JSON en este formato:
{"frm":"<HU prerequisito>", "to":["<HU dependiente>", ...]}

Reglas:
1. Una línea por cada HU que sea prerequisito de otras.
2. 'to' debe ser siempre un array de códigos de historias que dependen de 'frm'.
3. 'frm' y cada elemento de 'to' deben ser códigos exactos de la lista proporcionada.
4. Evita dependencias circulares.
5. NO incluyas texto explicativo, solo el JSON.

Lista de Historias de Usuario:
"""

# ───────────────────────────── Servicio IA ────────────────────────────────
class DependencyService:
    """Construye (o reconstruye) el grafo de dependencias para un proyecto."""

    def __init__(self):
        self.model = genai.GenerativeModel(MODEL_NAME)

    async def build_graph(self, project_id: str) -> DependencyGraph:
        try:
            pid = ObjectId(project_id)
        except Exception:
            raise HTTPException(400, "ID de proyecto inválido")

        stories = await db.user_stories.find(
            {"project_id": pid}, {"code": 1, "nombre": 1, "_id": 0}
        ).to_list(None)

        if not stories:
            logging.error(f"No se encontraron historias para el proyecto {project_id}")
            raise HTTPException(404, "El proyecto no tiene historias de usuario")
            
        logging.info(f"Generando grafo para {len(stories)} historias.")
        hu_list = "\n".join(f"{s['code']} - {s['nombre']}" for s in stories)

        # Llamada a Gemini
        pairs, prompt_tokens, completion_tokens, processing_time_ms = await self._ask_gemini(DEPENDENCY_PROMPT + hu_list)

        graph_doc = {
            "project_id": pid,
            "pairs": [p.model_dump() for p in pairs],
            "total_prompt_tokens": prompt_tokens,
            "total_completion_tokens": completion_tokens,
            "total_processing_time_ms": processing_time_ms,
        }

        # Guardar en DB
        await db.dependencies_graph.replace_one(
            {"project_id": pid},
            graph_doc,
            upsert=True
        )
        
        logging.info(f"Grafo generado exitosamente para proyecto {project_id}")
        return DependencyGraph(**graph_doc)

    async def _ask_gemini(self, prompt: str) -> Tuple[List[DependencyPair], int, int, float]:
        prompt_tokens = 0
        completion_tokens = 0
        processing_time_ms = 0.0

        try:
            start_time = time.perf_counter()
            # Usamos la versión asíncrona nativa de la librería genai
            response = await self.model.generate_content_async(
                prompt,
                generation_config={
                    "temperature": 0.1, # Menor temperatura para mayor consistencia en JSON
                    "max_output_tokens": 4096
                }
            )
            end_time = time.perf_counter()
            processing_time_ms = (end_time - start_time) * 1000

            if response.usage_metadata:
                prompt_tokens = response.usage_metadata.prompt_token_count
                completion_tokens = response.usage_metadata.candidates_token_count
            
            raw = response.text
        except Exception as e:
            logging.error(f"Error llamando a Gemini para dependencias: {e}")
            return [], 0, 0, 0.0

        bucket: dict[str, Set[str]] = {}

        # Parsear la respuesta línea por línea buscando JSONs
        for line in raw.splitlines():
            line = line.strip()
            # Limpiar posibles bloques de código markdown
            if line.startswith("```"): continue
            if not line: continue
            
            # Buscar el inicio y fin de un objeto JSON en la línea
            start = line.find('{')
            end = line.rfind('}')
            if start != -1 and end != -1:
                try:
                    json_str = line[start:end+1]
                    j = json.loads(json_str)
                    frm = j.get("frm")
                    to_lst = j.get("to", [])
                    
                    if frm and isinstance(to_lst, list):
                        if frm not in bucket:
                            bucket[frm] = set()
                        bucket[frm].update([str(t) for t in to_lst if t])
                except Exception as e:
                    logging.warning(f"Error parseando línea de dependencia: {e} | {line}")

        pairs = [
            DependencyPair(frm=frm, to=sorted(list(tos)))
            for frm, tos in bucket.items()
        ]
        
        return pairs, prompt_tokens, completion_tokens, processing_time_ms
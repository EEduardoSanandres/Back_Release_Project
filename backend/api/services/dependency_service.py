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
import time # Importar el módulo time
from typing import List, Set, Tuple

import google.generativeai as genai
from fastapi import HTTPException
from bson import ObjectId

from ...app.db import db
from ...app.schemas import DependencyPair, DependencyGraph

# ────────────────────────── Configuración Gemini ──────────────────────────
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
MODEL = "gemini-1.5-pro"

DEPENDENCY_PROMPT = """
Eres un analista experto en Historias de Usuario (HU).
Recibirás una lista de HU (código - título). Devuelve ÚNICAMENTE líneas JSON
donde cada línea represente un prerequisito y todas sus dependencias.

Formato por línea:
{"frm":"<HU prerequisito>", "to":["<HU dependiente>", …]}

Reglas:
1. Una línea por prerequisito.
2. 'to' debe ser siempre un array (aunque tenga 1 elemento).
3. frm y cada to deben existir en la lista.
4. No repitas dependencias duplicadas ni invertidas.
5. Sin texto extra.

Ejemplo:
{"frm":"us-001","to":["us-003","us-005"]}
{"frm":"us-002","to":["us-004"]}

Lista de HU:
"""

# ───────────────────────────── Servicio IA ────────────────────────────────
class DependencyService:
    """Construye (o reconstruye) el grafo de dependencias para un proyecto."""

    async def build_graph(self, project_id: str) -> DependencyGraph:
        pid = ObjectId(project_id)

        stories = await db.user_stories.find(
            {"project_id": pid}, {"code": 1, "nombre": 1, "_id": 0}
        ).to_list(None)

        if not stories:
            raise HTTPException(404, "El proyecto no tiene historias de usuario")

        hu_list = "\n".join(f"{s['code']} - {s['nombre']}" for s in stories)

        # Capturar las métricas de Gemini
        pairs, prompt_tokens, completion_tokens, processing_time_ms = await self._ask_gemini(DEPENDENCY_PROMPT + hu_list)

        graph_doc = {
            "project_id": pid,
            "pairs": [p.model_dump() for p in pairs],
            "total_prompt_tokens": prompt_tokens,      # Guardar métricas
            "total_completion_tokens": completion_tokens,
            "total_processing_time_ms": processing_time_ms,
        }

        # Usamos replace_one con upsert=True para insertar o actualizar el grafo
        await db.dependencies_graph.replace_one(
            {"project_id": pid},
            graph_doc,
            upsert=True
        )

        # Si el usuario quiere el objeto DependencyGraph de vuelta en la API
        # deberíamos devolverlo con las métricas ya incluidas
        return DependencyGraph(**graph_doc)

    async def _ask_gemini(self, prompt: str) -> Tuple[List[DependencyPair], int, int, float]:
        """
        Llama al modelo Gemini para generar las dependencias.
        Retorna la lista de pares, los tokens de entrada, los tokens de salida
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
                        "temperature": 0.3,
                        "max_output_tokens": 2048
                    }
                )
                end_time = time.perf_counter()
                processing_time_ms = (end_time - start_time) * 1000

                if res.usage_metadata:
                    prompt_tokens = res.usage_metadata.prompt_token_count
                    completion_tokens = res.usage_metadata.candidates_token_count
                return res.text
            except ValueError:
                # Esto ocurre si Gemini bloquea el contenido
                logging.warning("Gemini no devolvió contenido (bloqueado por seguridad).")
                return ""
            except Exception as e:
                logging.error(f"Error inesperado al llamar a la API de Gemini: {e}")
                return ""

        raw = await anyio.to_thread.run_sync(_generate)

        bucket: dict[str, Set[str]] = {}

        for line in raw.splitlines():
            line = line.strip()
            if not (line.startswith("{") and line.endswith("}")):
                continue
            try:
                j = json.loads(line)
                frm, to_lst = j["frm"], j["to"]
                if isinstance(to_lst, str):
                    to_lst = [to_lst]
                bucket.setdefault(frm, set()).update(to_lst)
            except Exception as e:
                logging.warning(f"Línea descartada por error de parseo: {e} | {line!r}")

        pairs = [
            DependencyPair(frm=frm, to=sorted(tos))
            for frm, tos in bucket.items()
        ]
        return pairs, prompt_tokens, completion_tokens, processing_time_ms
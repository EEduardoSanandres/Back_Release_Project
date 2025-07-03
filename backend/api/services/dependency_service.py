# backend/api/services/dependency_service.py
"""
Genera y almacena el grafo de dependencias entre Historias de Usuario
a partir de un proyecto, usando Gemini 1.5-Pro.
Expuesto en:
    POST /projects/{project_id}/dependency-graph/generate
    GET  /projects/{project_id}/dependency-graph
"""
from __future__ import annotations

import os, json, logging, anyio
from typing import List, Set

import google.generativeai as genai
from fastapi import HTTPException
from bson import ObjectId

from backend.app.db import db
from backend.app.schemas import DependencyPair, DependencyGraph

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

        pairs = await self._ask_gemini(DEPENDENCY_PROMPT + hu_list)

        graph_doc = {"project_id": pid, "pairs": [p.model_dump() for p in pairs]}
        await db.dependencies_graph.replace_one({"project_id": pid},
                                                graph_doc, upsert=True)

        return DependencyGraph(**graph_doc)

    async def _ask_gemini(self, prompt: str) -> List[DependencyPair]:
        model = genai.GenerativeModel(MODEL)

        def _generate() -> str:
            res = model.generate_content(prompt,
                    generation_config={"temperature": 0.3,
                                       "max_output_tokens": 2048})
            return res.text

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
                logging.warning(f"Línea descartada: {e} | {line!r}")

        return [
            DependencyPair(frm=frm, to=sorted(tos))
            for frm, tos in bucket.items()
        ]

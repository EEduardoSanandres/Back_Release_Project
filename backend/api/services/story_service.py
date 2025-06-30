# backend/api/services/story_service.py

from __future__ import annotations

import json
import unicodedata
from datetime import datetime
from typing import Any, Dict, List

from bson import ObjectId
from fastapi import HTTPException
from openai import OpenAI

from backend.api.schemas.requests import ImproveStoriesIn, ImproveByProjectIn
from backend.api.schemas.responses import StoryOut, StoryDiffOut
from backend.app.database import db

# ─────────────────────── LM Studio conf ────────────────────────────────
_oai = OpenAI(base_url="http://localhost:1234/v1", api_key="lm-studio")
MODEL_NAME = "mistral-7b-instruct-v0.3"

REFINE_PROMPT = """
You are an Agile BA. Refine the user story below following INVEST
guidelines. Return ONLY the rewritten story in the same single-line
format “As a <role>, I want <action> so that <benefit>”.

USER STORY:
{original}
""".strip()

IMPROVE_PROMPT = """
Eres un analista ágil. Mejora el nombre, la descripción (“Como …”)
y los criterios de la historia. Devuélveme SOLO JSON en una línea con esta forma:
{ "nombre": "...", "descripcion": "...", "criterios": [ ... ] }
""".strip()


class StoryService:
    # ────────────────────────────────────────────────────────────────
    async def refine_stories(self, body: ImproveStoriesIn) -> List[StoryOut]:
        """
        • Si se pasa `story_ids`, busca esas historias en MongoDB.
        • Si se pasa `text_block`, lo trata como historias sin guardar.
        • Llama a LM Studio para refinar cada historia según INVEST.
        • Devuelve la lista refinada y, si hubo IDs, actualiza Mongo.
        """
        originals: List[str] = []
        mongo_ids: List[ObjectId] = []

        if body.story_ids:
            for sid in body.story_ids:
                doc = await db.user_stories.find_one({"_id": ObjectId(sid)})
                if not doc:
                    continue
                originals.append(
                    f"As a {doc['role']}, I want {doc['action']} so that {doc['benefit']}"
                )
                mongo_ids.append(doc["_id"])

        if body.text_block:
            originals.extend(
                [ln.strip() for ln in body.text_block.splitlines() if ln.strip()]
            )

        if not originals:
            return []

        refined: List[StoryOut] = []
        for src in originals:
            resp = _oai.chat.completions.create(
                model=MODEL_NAME,
                messages=[{"role": "user", "content": REFINE_PROMPT.format(original=src)}],
            )
            clean = resp.choices[0].message.content.strip()

            try:
                role_part, rest = clean.split(", I want ", 1)
                role = role_part.replace("As a", "").replace("As an", "").strip()
                action, benefit = rest.split(" so that ", 1)
                refined.append(
                    StoryOut(
                        id="",
                        role=role,
                        action=action.strip(),
                        benefit=benefit.strip().rstrip("."),
                        status="refined",
                        priority=None,
                    )
                )
            except ValueError:
                refined.append(
                    StoryOut(
                        id="",
                        role="",
                        action=clean,
                        benefit="",
                        status="refined",
                        priority=None,
                    )
                )

        if mongo_ids:
            for _id, story in zip(mongo_ids, refined):
                await db.user_stories.update_one(
                    {"_id": _id},
                    {
                        "$set": {
                            "role": story.role,
                            "action": story.action,
                            "benefit": story.benefit,
                            "status": "refined",
                        }
                    },
                )

        return refined

    # ────────────────────────────────────────────────────────────────
    async def improve_by_project(self, body: ImproveByProjectIn) -> List[StoryDiffOut]:
        """
        • Coge todas las historias de un proyecto (o subset si se pasan IDs).
        • Para cada una llama a LM Studio para mejorar nombre, descripción y criterios.
        • Normaliza las claves JSON de la respuesta (tilde→sin tilde).
        • Calcula diff y devuelve solo las historias que cambian.
        • Guarda versión y actualiza Mongo.
        """
        query: Dict[str, Any] = {"project_id": ObjectId(body.project_id)}
        if body.story_ids:
            query["_id"] = {"$in": [ObjectId(s) for s in body.story_ids]}

        originals = await db.user_stories.find(query).to_list(None)
        if not originals:
            raise HTTPException(404, "No se encontraron historias para ese proyecto")

        diffs: List[StoryDiffOut] = []
        for doc in originals:
            raw = await self._call_lmstudio(doc)
            improved = self._normalize_keys(raw)
            diff = self._compute_diff(doc, improved)
            if diff:
                diffs.append(diff)
                await self._save_version(doc["_id"], improved)
                await db.user_stories.update_one(
                    {"_id": doc["_id"]}, {"$set": improved}
                )

        return diffs

    # ────────────────────────────────────────────────────────────────
    async def _call_lmstudio(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        nombre = doc.get("nombre") or doc.get("name") or ""
        descripcion = doc.get("descripcion") or doc.get("description") or doc.get("descripción") or ""
        criterios = doc.get("criterios") or doc.get("acceptance") or []

        crit_lines = "\n- ".join(
            c if isinstance(c, str) else c.get("text", "") for c in criterios
        )
        original_block = (
            f"Nombre: {nombre}\n"
            f"Descripción: {descripcion}\n"
            f"Criterios:\n- {crit_lines}"
        )

        res = _oai.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": IMPROVE_PROMPT + "\n\n" + original_block}],
            temperature=0.3,
        )
        text = res.choices[0].message.content.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Si no devuelven JSON válido, devolvemos lo original
            return {"nombre": nombre, "descripcion": descripcion, "criterios": criterios}

    def _normalize_keys(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """
        Mapea claves con tildes o en inglés a nuestras claves:
        - descripción / description → descripcion
        - criterios / acceptance → criterios
        - nombre / name → nombre
        """
        norm: Dict[str, Any] = {}
        for k, v in raw.items():
            # Quita tildes y pasa a minúsculas
            key = unicodedata.normalize("NFKD", k).encode("ascii", "ignore").decode().lower()
            if key in ("descripcion", "description"):
                norm["descripcion"] = v
            elif key in ("criterios", "criterio", "acceptance"):
                norm["criterios"] = v
            elif key in ("nombre", "name"):
                norm["nombre"] = v
            else:
                norm[key] = v
        return norm

    @staticmethod
    def _norm_criterios(val: Any) -> List[str]:
        """
        Acepta list[str] o list[dict{"text": str}], devuelve siempre List[str].
        """
        if not isinstance(val, list):
            return []
        out: List[str] = []
        for item in val:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict):
                out.append(item.get("text") or str(item))
        return out

    def _compute_diff(self, before: Dict[str, Any], after: Dict[str, Any]) -> StoryDiffOut | None:
        nombre_bef = before.get("nombre") or before.get("name")
        desc_bef = before.get("descripcion") or before.get("description")
        crit_bef = self._norm_criterios(before.get("criterios") or before.get("acceptance"))

        nombre_aft = after.get("nombre") or after.get("name")
        desc_aft = after.get("descripcion") or after.get("description")
        crit_aft = self._norm_criterios(after.get("criterios") or after.get("acceptance"))

        changes: Dict[str, Any] = {}
        if nombre_bef != nombre_aft:
            changes.update({"nombre_before": nombre_bef, "nombre_after": nombre_aft})
        if desc_bef != desc_aft:
            changes.update({"descripcion_before": desc_bef, "descripcion_after": desc_aft})
        if crit_bef != crit_aft:
            changes.update({"criterios_before": crit_bef, "criterios_after": crit_aft})

        return StoryDiffOut(id=str(before["_id"]), **changes) if changes else None

    async def _save_version(self, story_id: ObjectId, new_data: Dict[str, Any]) -> None:
        last = await db.story_versions.find_one(
            {"story_id": story_id}, sort=[("version", -1)]
        )
        next_v = (last["version"] + 1) if last else 1
        await db.story_versions.insert_one(
            {
                "story_id": story_id,
                "version": next_v,
                "source": "lmstudio",
                "text": new_data,
                "created_at": datetime.utcnow(),
            }
        )

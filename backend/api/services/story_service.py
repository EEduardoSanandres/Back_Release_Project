# backend/api/services/story_service.py
from __future__ import annotations

from typing import List

from openai import OpenAI
from bson import ObjectId

from backend.api.schemas.requests import ImproveStoriesIn
from backend.api.schemas.responses import StoryOut
from backend.app.database import db

_oai = OpenAI(base_url="http://localhost:1234/v1", api_key="lm-studio")
MODEL_NAME = "mistral-7b-instruct-v0.3"

PROMPT_TEMPLATE = """
You are an Agile BA. Refine the user story below following INVEST
guidelines. Return ONLY the rewritten story in the same single-line
format “As a <role>, I want <action> so that <benefit>”.

USER STORY:
{original}
"""

class StoryService:
    async def refine_stories(self, body: ImproveStoriesIn) -> List[StoryOut]:
        """
        • Si se pasa `story_ids`, busca esas historias en MongoDB.
        • Si se pasa `text_block`, lo trata como historias sin guardar.
        • Llama a LM Studio para refinar cada historia.
        • Devuelve la lista refinada y, si corresponde, actualiza Mongo.
        """
        # 1) Recopilar historias origen ------------------------------------
        originals: list[str] = []
        mongo_ids: list[ObjectId] = []

        if body.story_ids:
            for sid in body.story_ids:
                doc = await db.user_stories.find_one({"_id": ObjectId(sid)})
                if not doc:
                    continue
                originals.append(f"As a {doc['role']}, I want {doc['action']} so that {doc['benefit']}")
                mongo_ids.append(doc["_id"])

        if body.text_block:
            originals.extend(
                [line.strip() for line in body.text_block.splitlines() if line.strip()]
            )

        if not originals:
            return []

        # 2) Llamar modelo --------------------------------------------------
        refined: list[StoryOut] = []
        for src in originals:
            resp = _oai.chat.completions.create(
                model=MODEL_NAME,
                messages=[{"role": "user", "content": PROMPT_TEMPLATE.format(original=src)}],
            )
            clean = resp.choices[0].message.content.strip()

            # Parse simple split
            try:
                # "As a X, I want Y so that Z"
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
                # Si no cumple formato, lo devuelvo como texto plano
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

        # 3) Persistir en Mongo (opcional) -----------------------------------
        if mongo_ids:
            for mongo_id, story in zip(mongo_ids, refined):
                await db.user_stories.update_one(
                    {"_id": mongo_id},
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

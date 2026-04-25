from __future__ import annotations
import os
import json
import logging
from typing import List, Optional
from bson import ObjectId
import google.generativeai as genai
from ...app.db import db
from ...app.schemas import UserStory

# Configuración de Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-1.5-flash") # Usando flash para mayor velocidad en refinamiento

class RefinementService:
    def __init__(self):
        self.model = genai.GenerativeModel(MODEL_NAME)

    def _serialize_mongo_doc(self, data):
        """Recursivamente convierte ObjectId a string."""
        if isinstance(data, list):
            return [self._serialize_mongo_doc(item) for item in data]
        if isinstance(data, dict):
            return {k: self._serialize_mongo_doc(v) for k, v in data.items()}
        if isinstance(data, ObjectId):
            return str(data)
        return data

    async def get_stories_by_ids(self, story_ids: List[str]) -> List[dict]:
        oids = [ObjectId(sid) for sid in story_ids]
        return await db.user_stories.find({"_id": {"$in": oids}}).to_list(None)

    async def fix_quality(self, story_ids: List[str]) -> List[dict]:
        stories = await self.get_stories_by_ids(story_ids)
        if not stories:
            return []

        refined_stories = []
        for story in stories:
            prompt = f"""
            Eres un experto en Product Backlog y calidad de requisitos (INVEST).
            Tu tarea es mejorar la calidad de la siguiente Historia de Usuario:

            Título: {story.get('nombre', '')}
            Descripción: {story.get('descripcion', '')}
            Criterios de Aceptación: {json.dumps(story.get('criterios', []))}

            MEJORAS REQUERIDAS:
            1. Asegúrate de que la descripción siga el formato: "Como [rol], quiero [funcionalidad], para [beneficio]".
            2. Mejora la claridad y especificidad de los criterios de aceptación.
            3. Corrige ortografía y gramática.
            4. Ajusta el DoR (Definition of Ready) score basado en la nueva calidad (0-100).

            RESPUESTA:
            Devuelve un JSON estrictamente con esta estructura:
            {{
                "nombre": "título mejorado",
                "descripcion": "descripción mejorada",
                "criterios": ["criterio 1", "criterio 2", ...],
                "dor": 95,
                "status": "Ready"
            }}
            """
            response = await self.model.generate_content_async(prompt)
            try:
                # Extraer JSON de la respuesta
                text = response.text
                if "```json" in text:
                    text = text.split("```json")[1].split("```")[0]
                elif "```" in text:
                    text = text.split("```")[1].split("```")[0]
                
                refined_data = json.loads(text.strip())
                refined_stories.append({
                    "id": str(story['_id']),
                    "original": self._serialize_mongo_doc(story),
                    "refined": refined_data
                })
            except Exception as e:
                logging.error(f"Error parsing Gemini response for fix_quality: {e}")
                continue

        return refined_stories

    async def generate_gherkin(self, story_ids: List[str]) -> List[dict]:
        stories = await self.get_stories_by_ids(story_ids)
        if not stories:
            return []

        refined_stories = []
        for story in stories:
            prompt = f"""
            Eres un experto en BDD (Behavior Driven Development) y Gherkin.
            Tu tarea es transformar los Criterios de Aceptación tradicionales de la siguiente Historia de Usuario en escenarios Gherkin profesionales.

            Título: {story.get('nombre', '')}
            Criterios Originales: {json.dumps(story.get('criterios', []))}

            REGLAS:
            1. Crea UN escenario Gherkin por cada criterio de aceptación original.
            2. Usa palabras clave: Escenario, Dado, Cuando, Entonces, Y.
            3. Mantén el idioma en ESPAÑOL.
            4. Cada escenario debe ser una cadena independiente en la lista de respuesta.
            5. Agrega saltos de línea (\n) dentro de cada cadena para separar Dado, Cuando y Entonces.

            RESPUESTA:
            Devuelve un JSON estrictamente con esta estructura:
            {{
                "criterios_gherkin": [
                    "Escenario: Búsqueda exitosa\\nDado que estoy en el home\\nCuando busco \"celular\"\\nEntonces veo resultados",
                    "Escenario: Búsqueda sin resultados\\nDado que estoy en el home\\nCuando busco \"xyz123\"\\nEntonces veo mensaje de error"
                ]
            }}
            """
            response = await self.model.generate_content_async(prompt)
            try:
                text = response.text
                if "```json" in text:
                    text = text.split("```json")[1].split("```")[0]
                refined_data = json.loads(text.strip())
                
                # Combinamos con los datos originales para el preview
                refined_stories.append({
                    "id": str(story['_id']),
                    "original": self._serialize_mongo_doc(story),
                    "refined": {
                        "criterios": refined_data.get("criterios_gherkin", [])
                    }
                })
            except Exception as e:
                logging.error(f"Error parsing Gemini response for generate_gherkin: {e}")
                continue

        return refined_stories

    async def estimate_points(self, story_ids: List[str]) -> List[dict]:
        stories = await self.get_stories_by_ids(story_ids)
        if not stories:
            return []

        refined_stories = []
        for story in stories:
            prompt = f"""
            Eres un experto en estimación de software usando Puntos de Historia (escala Fibonacci: 1, 2, 3, 5, 8, 13, 21).
            Analiza la complejidad de esta Historia de Usuario:

            Título: {story.get('nombre', '')}
            Descripción: {story.get('descripcion', '')}
            Criterios: {json.dumps(story.get('criterios', []))}

            Considera:
            1. Complejidad técnica.
            2. Esfuerzo de implementación.
            3. Ambigüedad/Incertidumbre.

            RESPUESTA:
            Devuelve un JSON con esta estructura:
            {{
                "story_points": 5,
                "justificacion": "Breve explicación de por qué este puntaje"
            }}
            """
            response = await self.model.generate_content_async(prompt)
            try:
                text = response.text
                if "```json" in text:
                    text = text.split("```json")[1].split("```")[0]
                refined_data = json.loads(text.strip())
                
                refined_stories.append({
                    "id": str(story['_id']),
                    "original": self._serialize_mongo_doc(story),
                    "refined": {
                        "story_points": refined_data.get("story_points")
                    }
                })
            except Exception as e:
                logging.error(f"Error parsing Gemini response for estimate_points: {e}")
                continue

        return refined_stories

    async def detect_duplicates(self, story_ids: List[str]) -> List[dict]:
        # En este caso, analizamos el conjunto completo enviado
        stories = await self.get_stories_by_ids(story_ids)
        if len(stories) < 2:
            return []

        # Construir una lista simplificada para el prompt
        stories_summary = [{"id": str(s['_id']), "nombre": s.get('nombre'), "descripcion": s.get('descripcion')} for s in stories]

        prompt = f"""
        Analiza estas Historias de Usuario e identifica posibles duplicados o redundancias semánticas.

        Historias:
        {json.dumps(stories_summary)}

        RESPUESTA:
        Devuelve un JSON con una lista de grupos de duplicados:
        {{
            "duplicados": [
                {{
                    "ids": ["id1", "id2"],
                    "razon": "Explicación de por qué son duplicados"
                }}
              ]
        }}
        Si no hay duplicados, devuelve una lista vacía.
        """
        response = await self.model.generate_content_async(prompt)
        try:
            text = response.text
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            return json.loads(text.strip())
        except Exception as e:
            logging.error(f"Error parsing Gemini response for detect_duplicates: {e}")
            return {"duplicados": []}

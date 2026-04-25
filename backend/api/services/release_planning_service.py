# backend/api/services/release_planning_service.py
"""
Genera un plan de release completo basado en la configuración del proyecto
y las historias de usuario, utilizando IA para crear un plan detallado.
"""
from __future__ import annotations

import os, json, logging, anyio
import time
from typing import List, Dict, Any
from datetime import datetime

import google.generativeai as genai
from fastapi import HTTPException
from bson import ObjectId

from ...app.db import db
from ...app.schemas import ProjectConfig
from ...api.schemas.responses import ReleasePlanningOut

# ────────────────────────── Configuración Gemini ──────────────────────────
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-pro-preview")

# ───────────────────────────── PROMPT para Gemini ─────────────────────────
RELEASE_PLANNING_PROMPT = """
INSTRUCCIONES CRÍTICAS:
- Responde ÚNICAMENTE con JSON válido
- NO uses markdown, NO uses ```json
- Comienza DIRECTAMENTE con {{
- Termina DIRECTAMENTE con }}

TAREA: Genera un plan de release dividido en {num_releases} releases considerando las dependencias entre historias.

DATOS DEL PROYECTO:
- Historias: {len_stories} totales, {total_story_points} story points
- Equipo: {num_devs} desarrolladores, velocidad {team_velocity} SP/sprint
- Sprint duration: {sprint_duration} semanas
- Fecha objetivo: {release_target_date}
- Número de releases: {num_releases}

INSTRUCCIONES IMPORTANTES:
1. **RELEASES**: Debes dividir el proyecto en EXACTAMENTE {num_releases} releases. Cada release debe tener un título descriptivo y una descripción clara de sus objetivos.
2. **DISTRIBUCIÓN**: Distribuye los sprints equitativamente entre los {num_releases} releases. Cada release agrupa varios sprints consecutivos.
3. **DEPENDENCIAS**: Las historias con dependencias deben programarse ANTES que las que dependen de ellas.
4. **ORDENAMIENTO**: Si historia A tiene "Dependencias: 2", significa que 2 historias dependen de A, por lo que A debe ir en un sprint anterior.
5. **INCLUIR TODAS**: Debes incluir las {len_stories} historias exactamente una vez cada una.
6. **FECHAS REALISTAS**: El primer sprint comienza el {sprint_start_date} y termina el {sprint_end_date}.

FORMATO JSON REQUERIDO:
{{
  "project_analysis": {{
    "total_story_points": {total_story_points},
    "estimated_sprints": {estimated_sprints},
    "total_duration_weeks": {estimated_sprints} * {sprint_duration},
    "target_date_feasible": true,
    "recommended_adjustments": []
  }},
  "releases": [
    {{
      "release_number": 1,
      "title": "Release 1: Infraestructura Base",
      "description": "Establecer la infraestructura fundamental y componentes core del sistema",
      "start_date": "{sprint_start_date}",
      "end_date": "YYYY-MM-DD",
      "sprints": [
        {{
          "sprint_number": 1,
          "start_date": "{sprint_start_date}",
          "end_date": "{sprint_end_date}",
          "story_points_planned": 30,
          "capacity_used_percentage": 100,
          "stories": [
            {{
              "code": "HISTORIA-1",
              "name": "Nombre de historia",
              "story_points": 5,
              "priority": "HIGH",
              "dependencies": []
            }}
          ]
        }}
      ],
      "total_story_points": 100,
      "risks": [
        {{
          "level": "HIGH",
          "description": "Descripción del riesgo específico de este release",
          "mitigation": "Estrategia de mitigación"
        }}
      ],
      "recommendations": [
        "Recomendación específica para este release"
      ]
    }}
  ],
  "overall_risks": [
    {{
      "level": "HIGH",
      "description": "Riesgo general del proyecto",
      "mitigation": "Estrategia general"
    }}
  ],
  "overall_recommendations": [
    "Recomendación general del proyecto"
  ]
}}

DATOS DE LAS HISTORIAS:
{stories_data}
"""

class ReleasePlanningService:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    async def generate_release_plan(self, project_id: str, num_releases: int = 1) -> ReleasePlanningOut:
        """
        Genera un plan de release completo para un proyecto dividido en múltiples releases.
        
        Args:
            project_id: ID del proyecto
            num_releases: Cantidad de releases a generar (default: 1)
        """
        start_time = time.time()

        try:
            self.logger.info(f"Generando plan de release para proyecto: {project_id} con {num_releases} releases")

            # 1. Obtener configuración del proyecto
            project_config = await self._get_project_config(project_id)
            if not project_config:
                raise HTTPException(
                    status_code=404,
                    detail="Configuración del proyecto no encontrada. Configure el proyecto primero."
                )

            # 2. Obtener historias de usuario del proyecto
            user_stories = await self._get_project_stories(project_id)
            if not user_stories:
                logging.error(f"No se encontraron historias de usuario para el proyecto {project_id}")
                raise HTTPException(
                    status_code=404,
                    detail="No se encontraron historias de usuario para este proyecto."
                )
            logging.info(f"Se recuperaron {len(user_stories)} historias de usuario.")

            # 3. Preparar datos para la IA
            stories_data = self._format_stories_for_ai(user_stories)
            total_story_points = sum(story.get('story_points', 0) for story in user_stories)

            # Calcular sprints necesarios teóricamente
            team_velocity = project_config["team_velocity"]
            estimated_sprints_needed = max(1, round(total_story_points / team_velocity)) if team_velocity > 0 else 1

            self.logger.info(f"📊 Enviando {len(user_stories)} historias de usuario a la IA para planificación de release")
            self.logger.info(f"📝 Total story points: {total_story_points}, Velocidad equipo: {team_velocity}")
            self.logger.info(f"🎯 Sprints estimados necesarios: {estimated_sprints_needed}")

            # Verificar que todas las historias estén en el prompt
            story_codes_in_prompt = set()
            for line in stories_data.split('\n'):
                if line.startswith('Código: '):
                    code = line.replace('Código: ', '').strip()
                    story_codes_in_prompt.add(code)

            self.logger.info(f"🔍 Códigos de historias en prompt: {len(story_codes_in_prompt)}")
            all_story_codes = {story['code'] for story in user_stories}
            missing_in_prompt = all_story_codes - story_codes_in_prompt
            if missing_in_prompt:
                self.logger.warning(f"⚠️ Historias faltantes en prompt: {missing_in_prompt}")

            # Verificar viabilidad del proyecto DESPUÉS de generar el plan
            # (no antes, porque la IA puede optimizar mejor la distribución)

            # 4. Generar plan con IA (ahora con múltiples releases)
            release_plan = await self._generate_plan_with_ai(
                project_config, stories_data, len(user_stories), total_story_points, estimated_sprints_needed, num_releases
            )

            # Verificar que todas las historias estén incluidas en el plan (ahora dentro de releases)
            if release_plan and "releases" in release_plan:
                total_stories_in_plan = 0
                for release in release_plan["releases"]:
                    for sprint in release.get("sprints", []):
                        total_stories_in_plan += len(sprint.get("stories", []))
                
                total_sprints = sum(len(release.get("sprints", [])) for release in release_plan["releases"])
                self.logger.info(f"Plan generado: {len(release_plan['releases'])} releases, {total_sprints} sprints, {total_stories_in_plan} historias incluidas")

                if total_stories_in_plan < len(user_stories):
                    self.logger.warning(f"FALTAN HISTORIAS: Enviadas {len(user_stories)}, incluidas en plan {total_stories_in_plan}")

            # Validar viabilidad del plan generado
            plan_viability = self._validate_generated_plan_viability_multi_release(release_plan, project_config)
            if not plan_viability["is_viable"]:
                self.logger.warning(f"🚫 PLAN GENERADO NO VIABLE: {plan_viability['reason']}")
                # Actualizar el análisis del proyecto
                if "project_analysis" in release_plan:
                    release_plan["project_analysis"]["target_date_feasible"] = False
                    if "recommended_adjustments" not in release_plan["project_analysis"]:
                        release_plan["project_analysis"]["recommended_adjustments"] = []
                    release_plan["project_analysis"]["recommended_adjustments"].extend(plan_viability["recommendations"])

                # Agregar riesgos y recomendaciones generales
                if "overall_risks" not in release_plan:
                    release_plan["overall_risks"] = []
                release_plan["overall_risks"].extend(plan_viability["risks"])

                if "overall_recommendations" not in release_plan:
                    release_plan["overall_recommendations"] = []
                release_plan["overall_recommendations"].extend(plan_viability["recommendations"])

            # 5. Calcular métricas de uso de tokens
            end_time = time.time()
            processing_time = (end_time - start_time) * 1000

            # 6. Crear y guardar el plan de release (ahora con múltiples releases)
            plan_doc = {
                "project_id": ObjectId(project_id),
                "project_config_id": ObjectId(project_config["id"]),
                "user_story_ids": [ObjectId(story["id"]) for story in user_stories],
                "releases": release_plan.get("releases", []),
                "num_releases": num_releases,
                "project_analysis": release_plan.get("project_analysis", {}),
                "overall_risks": release_plan.get("overall_risks", []),
                "overall_recommendations": release_plan.get("overall_recommendations", []),
                "generated_at": datetime.utcnow(),
                "total_prompt_tokens": release_plan.get("usage", {}).get("prompt_tokens", 0),
                "total_completion_tokens": release_plan.get("usage", {}).get("completion_tokens", 0),
                "total_processing_time_ms": processing_time
            }

            # Eliminar plan anterior si existe (solo un plan por proyecto)
            await db.release_plans.delete_many({"project_id": ObjectId(project_id)})

            result = await db.release_plans.insert_one(plan_doc)

            return ReleasePlanningOut(
                id=str(result.inserted_id),
                project_id=project_id,
                releases=plan_doc["releases"],
                num_releases=num_releases,
                project_analysis=plan_doc["project_analysis"],
                overall_risks=plan_doc["overall_risks"],
                overall_recommendations=plan_doc["overall_recommendations"],
                generated_at=plan_doc["generated_at"],
                total_prompt_tokens=plan_doc["total_prompt_tokens"],
                total_completion_tokens=plan_doc["total_completion_tokens"],
                total_processing_time_ms=plan_doc["total_processing_time_ms"]
            )

        except Exception as e:
            self.logger.error(f"Error generando plan de release: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error generando plan de release: {str(e)}"
            )

    async def get_release_plan(self, project_id: str) -> ReleasePlanningOut:
        """
        Obtiene el plan de release existente para un proyecto (ahora con múltiples releases).
        """
        plan = await db.release_plans.find_one({"project_id": ObjectId(project_id)})
        if not plan:
            raise HTTPException(
                status_code=404,
                detail="Plan de release no encontrado para este proyecto."
            )

        return ReleasePlanningOut(
            id=str(plan["_id"]),
            project_id=str(plan["project_id"]),
            releases=plan.get("releases", []),
            num_releases=plan.get("num_releases", 1),
            project_analysis=plan.get("project_analysis", {}),
            overall_risks=plan.get("overall_risks", []),
            overall_recommendations=plan.get("overall_recommendations", []),
            generated_at=plan["generated_at"],
            total_prompt_tokens=plan.get("total_prompt_tokens", 0),
            total_completion_tokens=plan.get("total_completion_tokens", 0),
            total_processing_time_ms=plan.get("total_processing_time_ms", 0)
        )

    async def _get_project_config(self, project_id: str) -> Dict[str, Any]:
        """Obtiene la configuración del proyecto."""
        config = await db.project_configs.find_one({"project_id": ObjectId(project_id)})
        if not config:
            return None

        # Convertir ObjectId a string y datetime a string para serialización
        return {
            "id": str(config["_id"]),
            "project_id": str(config["project_id"]),
            "num_devs": config["num_devs"],
            "team_velocity": config["team_velocity"],
            "sprint_duration": config["sprint_duration"],
            "prioritization_metric": config["prioritization_metric"],
            "release_target_date": config["release_target_date"].isoformat() if hasattr(config["release_target_date"], 'isoformat') else str(config["release_target_date"]),
            "team_capacity": config.get("team_capacity"),
            "optimistic_scenario": config.get("optimistic_scenario"),
            "realistic_scenario": config.get("realistic_scenario"),
            "pessimistic_scenario": config.get("pessimistic_scenario"),
            "created_at": config["created_at"].isoformat(),
            "updated_at": config["updated_at"].isoformat()
        }

    async def _get_project_stories(self, project_id: str) -> List[Dict[str, Any]]:
        """Obtiene todas las historias de usuario del proyecto."""
        stories_cursor = db.user_stories.find({"project_id": ObjectId(project_id)})
        stories = await stories_cursor.to_list(length=None)

        # Convertir ObjectId y datetime para serialización
        formatted_stories = []
        for story in stories:
            formatted_story = {
                "id": str(story["_id"]),
                "project_id": str(story["project_id"]),
                "code": story["code"],
                "epica": story["epica"],
                "nombre": story["nombre"],
                "descripcion": story["descripcion"],
                "criterios": story["criterios"],
                "priority": story.get("priority", "Medium"),
                "story_points": story.get("story_points", 0),
                "dor": story.get("dor", 0),
                "status": story.get("status", "Ready"),
                "deps": story.get("deps", 0),
                "ai": story.get("ai", False),
                "created_at": story["created_at"].isoformat()
            }
            formatted_stories.append(formatted_story)

        return formatted_stories

    def _format_stories_for_ai(self, stories: List[Dict[str, Any]]) -> str:
        """Formatea las historias para enviar a la IA."""
        formatted = []
        for story in stories:
            # Incluir dependencias si existen
            deps_info = ""
            if story.get('deps', 0) > 0:
                deps_info = f"Dependencias: {story['deps']} (número de historias que dependen de esta)"
            elif story.get('deps', 0) == 0:
                deps_info = "Dependencias: Ninguna"

            formatted.append(f"""
Código: {story['code']}
Épica: {story['epica']}
Nombre: {story['nombre']}
Descripción: {story['descripcion']}
Story Points: {story['story_points']}
Prioridad: {story['priority']}
Estado: {story['status']}
{deps_info}
Criterios: {', '.join(story['criterios'])}
""".strip())

        return "\n\n".join(formatted)

    async def _generate_plan_with_ai(
        self,
        project_config: Dict[str, Any],
        stories_data: str,
        total_stories: int,
        total_story_points: int,
        estimated_sprints: int,
        num_releases: int = 1
    ) -> Dict[str, Any]:
        """Genera el plan de release usando IA dividido en múltiples releases."""
        # Calcular fechas realistas para el primer sprint
        from datetime import datetime, timedelta
        today = datetime.now()

        # El primer sprint comienza el próximo lunes (o hoy si es lunes)
        days_until_monday = (7 - today.weekday()) % 7
        if days_until_monday == 0:  # Ya es lunes
            first_sprint_start = today
        else:
            first_sprint_start = today + timedelta(days=days_until_monday)

        sprint_duration_weeks = project_config["sprint_duration"]
        first_sprint_end = first_sprint_start + timedelta(weeks=sprint_duration_weeks, days=-1)  # -1 para incluir el último día

        sprint_start_date = first_sprint_start.strftime("%Y-%m-%d")
        sprint_end_date = first_sprint_end.strftime("%Y-%m-%d")

        prompt = RELEASE_PLANNING_PROMPT.format(
            num_devs=project_config["num_devs"],
            team_velocity=project_config["team_velocity"],
            sprint_duration=project_config["sprint_duration"],
            team_capacity=project_config.get("team_capacity", "No especificada"),
            release_target_date=project_config["release_target_date"],
            optimistic_scenario=project_config.get("optimistic_scenario", "No especificado"),
            realistic_scenario=project_config.get("realistic_scenario", "No especificado"),
            pessimistic_scenario=project_config.get("pessimistic_scenario", "No especificado"),
            stories_data=stories_data,
            len_stories=total_stories,
            total_story_points=total_story_points,
            estimated_sprints=estimated_sprints,
            num_releases=num_releases,
            sprint_start_date=sprint_start_date,
            sprint_end_date=sprint_end_date
        )

        try:
            model = genai.GenerativeModel(MODEL)
            response = model.generate_content(prompt, request_options={"timeout": 10000})

            # Limpiar la respuesta de bloques de código markdown
            cleaned_response = self._clean_ai_response(response.text.strip())

            # Verificar si la respuesta limpiada es un error
            try:
                error_check = json.loads(cleaned_response)
                if "error" in error_check:
                    self.logger.error(f"Error procesando respuesta IA: {error_check.get('error_details', error_check.get('error', 'Error desconocido'))}")
                    raise HTTPException(
                        status_code=500,
                        detail=f"Error procesando respuesta de IA: {error_check.get('error', 'La IA no devolvió un JSON válido')}"
                    )
            except json.JSONDecodeError:
                pass  # No es un error, continuar

            # Intentar parsear la respuesta como JSON
            try:
                plan_data = json.loads(cleaned_response)
                return plan_data
            except json.JSONDecodeError as e:
                # Log detallado del error
                self.logger.error(f"Error parseando JSON: {e}")
                self.logger.error(f"Respuesta original longitud: {len(response.text)}")
                self.logger.error(f"Respuesta limpiada longitud: {len(cleaned_response)}")

                # Lanzar excepción HTTP en lugar de devolver error técnico
                raise HTTPException(
                    status_code=500,
                    detail="La IA no pudo generar un plan de release válido. Intente nuevamente."
                )

        except Exception as e:
            self.logger.error(f"Error generando plan con IA: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Error generando plan con IA: {str(e)}"
            )

    def _clean_ai_response(self, response_text: str) -> str:
        """
        Limpia la respuesta de la IA eliminando bloques de código markdown.
        Método ultra-robusto para respuestas grandes y casos edge.
        """
        if not response_text or not response_text.strip():
            return json.dumps({"error": "Respuesta vacía de la IA"})

        response_text = response_text.strip()
        self.logger.info(f"🔍 Procesando respuesta IA - Longitud: {len(response_text)}")

        # PRIMERO: Buscar bloques de código markdown - buscar el ÚLTIMO bloque si hay múltiples
        if '```' in response_text:
            self.logger.info("📝 Detectados bloques markdown - procesando...")

            # Buscar todos los bloques ```json o ``` y usar el último
            json_blocks = []
            search_text = response_text.lower()

            # Buscar bloques ```json primero
            start = 0
            while True:
                json_start = search_text.find('```json', start)
                if json_start == -1:
                    break
                json_end = search_text.find('```', json_start + 7)
                if json_end == -1:
                    break
                json_blocks.append((json_start, json_end + 3))
                start = json_end + 3

            # Si no hay bloques ```json, buscar bloques ``` normales
            if not json_blocks:
                start = 0
                while True:
                    block_start = search_text.find('```', start)
                    if block_start == -1:
                        break
                    block_end = search_text.find('```', block_start + 3)
                    if block_end == -1:
                        break
                    json_blocks.append((block_start, block_end + 3))
                    start = block_end + 3

            # Usar el ÚLTIMO bloque encontrado
            if json_blocks:
                start_pos, end_pos = json_blocks[-1]  # Último bloque
                self.logger.info(f"📍 Procesando último bloque markdown - Inicio: {start_pos}, Fin: {end_pos}")

                # Extraer el contenido entre los marcadores
                json_content = response_text[start_pos:end_pos].strip()

                # Remover los marcadores ```json o ```
                if json_content.lower().startswith('```json'):
                    json_content = json_content[7:]
                elif json_content.startswith('```'):
                    json_content = json_content[3:]

                # Remover el marcador final ```
                if json_content.endswith('```'):
                    json_content = json_content[:-3]

                json_content = json_content.strip()

                # Limpiar líneas vacías al inicio y final
                lines = json_content.split('\n')
                # Remover líneas vacías del inicio
                while lines and not lines[0].strip():
                    lines.pop(0)
                # Remover líneas vacías del final
                while lines and not lines[-1].strip():
                    lines.pop()

                json_content = '\n'.join(lines)

                # Limpiar caracteres de control y problemáticos
                import re
                json_content = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', json_content)

                self.logger.info(f"📄 JSON extraído del markdown - Longitud: {len(json_content)}")
                self.logger.info(f"📄 Preview primeros 300 chars: {json_content[:300]}...")

                # Verificar si es JSON válido
                try:
                    parsed_json = json.loads(json_content)
                    self.logger.info("✅ JSON válido extraído del markdown")
                    self.logger.info(f"🔑 Keys principales: {list(parsed_json.keys())}")
                    return json_content
                except json.JSONDecodeError as e:
                    self.logger.warning(f"❌ JSON del markdown no válido: {e}")
                    self.logger.warning(f"📄 Primeros 500 chars del JSON problemático: {json_content[:500]}...")

                    # Intentar arreglar JSON común - trailing commas
                    try:
                        self.logger.info("🔧 Intentando arreglar trailing commas...")
                        # Remover trailing commas antes de }, o ]
                        fixed_json = re.sub(r',(\s*[}\]])', r'\1', json_content)
                        # También remover trailing commas antes de fin de array/objeto
                        fixed_json = re.sub(r',\s*(\]|\})', r'\1', fixed_json)
                        parsed_json = json.loads(fixed_json)
                        self.logger.info("✅ JSON arreglado (trailing commas)")
                        return fixed_json
                    except json.JSONDecodeError as e2:
                        self.logger.warning(f"❌ No se pudo arreglar trailing commas: {e2}")

                    # Intentar arreglar otros errores comunes
                    try:
                        self.logger.info("🔧 Intentando otras reparaciones...")
                        # Remover comas duplicadas
                        fixed_json = re.sub(r',,+', ',', json_content)
                        # Arreglar strings sin cerrar (buscar strings que empiecen con " pero no terminen)
                        fixed_json = re.sub(r'": "[^"]*$', '": "valor"', fixed_json, flags=re.MULTILINE)
                        # Intentar reparar trailing commas de nuevo con el JSON parcialmente arreglado
                        fixed_json = re.sub(r',(\s*[}\]])', r'\1', fixed_json)
                        fixed_json = re.sub(r',\s*(\]|\})', r'\1', fixed_json)
                        parsed_json = json.loads(fixed_json)
                        self.logger.info("✅ JSON reparado con otras técnicas")
                        return fixed_json
                    except json.JSONDecodeError as e3:
                        self.logger.error(f"❌ No se pudo reparar el JSON: {e3}")

                    # Si no se puede arreglar, devolver error detallado
                    return json.dumps({
                        "error": "La IA no devolvió un JSON válido",
                        "error_details": f"JSON extraído del markdown no válido: {str(e)}",
                        "response_length": len(response_text),
                        "json_length": len(json_content),
                        "json_preview": json_content[:300] + "..." if len(json_content) > 300 else json_content,
                        "markdown_blocks_found": len(json_blocks)
                    })

        # SEGUNDO: Si no hay bloques markdown, buscar JSON directo
        self.logger.info("🔍 No se encontraron bloques markdown válidos, buscando JSON directo...")
        start_brace = response_text.find('{')
        end_brace = response_text.rfind('}')

        if start_brace != -1 and end_brace != -1 and end_brace > start_brace:
            potential_json = response_text[start_brace:end_brace + 1]
            self.logger.info(f"📍 JSON directo encontrado - Longitud: {len(potential_json)}")
            try:
                parsed_json = json.loads(potential_json)
                self.logger.info("✅ JSON directo válido encontrado")
                return potential_json
            except json.JSONDecodeError as e:
                self.logger.warning(f"⚠️ JSON directo no válido: {e}")
                self.logger.warning(f"📄 JSON directo problemático (primeros 300): {potential_json[:300]}...")

        # ÚLTIMO RECURSO: devolver error detallado
        self.logger.error("❌ No se pudo extraer JSON válido de la respuesta")
        return json.dumps({
            "error": "La IA no devolvió un JSON válido",
            "error_details": "No se pudo extraer JSON válido de la respuesta",
            "response_length": len(response_text),
            "has_markdown": '```' in response_text,
            "has_json_start": '{' in response_text,
            "response_preview": response_text[:500] + "..." if len(response_text) > 500 else response_text
        })

    async def _regenerate_complete_plan(
        self,
        project_config: Dict[str, Any],
        user_stories: List[Dict[str, Any]],
        partial_plan: Dict[str, Any],
        total_story_points: int,
        estimated_sprints: int
    ) -> Dict[str, Any]:
        """
        Regenera el plan si faltan historias, con instrucciones más estrictas.
        """
        self.logger.info("Regenerando plan de release con instrucciones más estrictas...")

        regeneration_prompt = f"""
        El plan anterior está incompleto. Tienes {len(user_stories)} historias de usuario pero solo incluiste algunas.

        IMPORTANTE: TODA tu respuesta debe estar en ESPAÑOL. No uses inglés en ningún campo, recomendación o descripción.

        RESPONDE ÚNICAMENTE con JSON válido. NO incluyas bloques de código markdown (```json), NO agregues texto adicional antes o después del JSON. La respuesta debe comenzar con {{ y terminar con }}.

        INSTRUCCIONES CRÍTICAS:
        1. DEBES incluir TODAS las {len(user_stories)} historias en los sprints
        2. Calcula exactamente cuántos sprints necesitas: {total_story_points} story points / {project_config["team_velocity"]} velocity
        3. Distribuye TODAS las historias sin excepción
        4. Verifica que la suma de historias en sprints = {len(user_stories)}

        CONFIGURACIÓN DEL PROYECTO:
        - Número de desarrolladores: {project_config["num_devs"]}
        - Velocidad del equipo: {project_config["team_velocity"]} story points por sprint
        - Duración del sprint: {project_config["sprint_duration"]} semanas

        HISTORIAS QUE FALTAN INCLUIR:
        """

        # Identificar historias faltantes
        included_codes = set()
        if "sprints" in partial_plan:
            for sprint in partial_plan["sprints"]:
                for story in sprint.get("stories", []):
                    included_codes.add(story.get("code"))

        missing_stories = []
        for story in user_stories:
            if story["code"] not in included_codes:
                missing_stories.append(story)

        # Agregar historias faltantes al prompt
        for story in missing_stories:
            regeneration_prompt += f"""
            Código: {story['code']}
            Nombre: {story['nombre']}
            Story Points: {story['story_points']}
            Prioridad: {story['priority']}
            """

        regeneration_prompt += f"""

        Plan anterior (completa lo que falta):
        {json.dumps(partial_plan, indent=2)}

        Devuelve el plan COMPLETO con TODAS las historias en ESPAÑOL.
        """

        try:
            model = genai.GenerativeModel(MODEL)
            response = model.generate_content(regeneration_prompt, request_options={"timeout": 10000})

            cleaned_response = self._clean_ai_response(response.text)

            try:
                complete_plan = json.loads(cleaned_response)
                return complete_plan
            except json.JSONDecodeError:
                self.logger.error("La regeneración tampoco devolvió JSON válido")
                return partial_plan

        except Exception as e:
            self.logger.error(f"Error en regeneración: {e}")
            return partial_plan

    def _validate_plan_viability(self, release_plan: Dict[str, Any], project_config: Dict[str, Any], total_story_points: int, estimated_sprints: int) -> Dict[str, Any]:
        """
        Valida si el plan generado por la IA cumple con las restricciones de viabilidad.
        """
        issues = []
        recommendations = []
        adjustments = []
        is_viable = True

        if not release_plan or "sprints" not in release_plan:
            return {
                "is_viable": False,
                "issues": ["Plan de release no generado correctamente"],
                "recommendations": ["Vuelva a generar el plan de release"],
                "adjustments": ["Regenerar plan completo"]
            }

        sprints = release_plan.get("sprints", [])
        team_velocity = project_config["team_velocity"]

        # 1. Verificar que el número de sprints sea razonable
        if len(sprints) > estimated_sprints * 1.5:  # Más del 50% de lo estimado
            issues.append(f"Demasiados sprints generados: {len(sprints)} vs estimados {estimated_sprints}")
            recommendations.append("El plan generado excede significativamente lo estimado")
            adjustments.append("Considerar aumentar la velocidad del equipo o reducir el alcance")
            is_viable = False

        # 2. Verificar distribución de story points por sprint
        for sprint in sprints:
            sprint_sp = sprint.get("story_points_planned", 0)
            if sprint_sp > team_velocity * 1.2:  # Más del 20% sobre la velocidad
                issues.append(f"Sprint {sprint.get('sprint_number', '?')} sobrecargado: {sprint_sp} SP (velocidad: {team_velocity})")
                recommendations.append(f"Reducir carga del sprint {sprint.get('sprint_number', '?')} o aumentar velocidad del equipo")
                is_viable = False

        # 3. Verificar fechas realistas
        from datetime import datetime, timedelta
        sprint_duration_weeks = project_config["sprint_duration"]
        target_date = datetime.fromisoformat(project_config["release_target_date"])

        if sprints:
            last_sprint_end = datetime.fromisoformat(sprints[-1]["end_date"]) if "end_date" in sprints[-1] else None
            if last_sprint_end and last_sprint_end > target_date:
                weeks_over = (last_sprint_end - target_date).days // 7
                issues.append(f"Fecha límite excedida por {weeks_over} semanas")
                recommendations.append(f"El proyecto se extenderá {weeks_over} semanas más allá de la fecha objetivo")
                adjustments.append("Extender fecha límite o aumentar velocidad del equipo")
                is_viable = False

        # 4. Verificar cobertura de story points
        total_planned_sp = sum(sprint.get("story_points_planned", 0) for sprint in sprints)
        coverage_percentage = (total_planned_sp / total_story_points) * 100 if total_story_points > 0 else 0

        if coverage_percentage < 90:  # Menos del 90% de cobertura
            issues.append(f"El plan cubre solo {coverage_percentage:.1f}% de los story points totales")
            recommendations.append("El plan no cubre la mayoría de las historias de usuario")
            adjustments.append("Aumentar velocidad del equipo o reducir alcance del proyecto")
            is_viable = False

        # 5. Análisis específico para proyectos con baja viabilidad
        if estimated_sprints >= 15:  # Proyectos que toman 15+ sprints
            recommendations.append("Proyecto de alta complejidad - considerar dividir en releases más pequeñas")
            if not is_viable:
                adjustments.append("Dividir proyecto en múltiples releases para mejorar manejabilidad")

        return {
            "is_viable": is_viable,
            "issues": issues,
            "recommendations": recommendations,
            "adjustments": adjustments
        }

    def _validate_generated_plan_viability(self, release_plan: Dict[str, Any], project_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Valida si el plan de release GENERADO por la IA cabe en la fecha límite.
        Esta es la validación REAL, no teórica.
        """
        from datetime import datetime, date
        issues = []
        recommendations = []
        risks = []
        is_viable = True

        if not release_plan or "sprints" not in release_plan or not release_plan["sprints"]:
            return {
                "is_viable": False,
                "reason": "Plan no generado correctamente",
                "issues": ["Plan de release no generado"],
                "recommendations": ["Vuelva a generar el plan"],
                "risks": []
            }

        # Obtener la fecha del último sprint
        last_sprint = release_plan["sprints"][-1]
        last_sprint_end = last_sprint.get("end_date", "")

        # Obtener fecha objetivo del proyecto
        target_date_str = project_config.get("release_target_date", "")
        if not target_date_str or not last_sprint_end:
            return {
                "is_viable": True,  # No podemos validar sin fechas
                "reason": "No hay fechas para validar",
                "issues": [],
                "recommendations": [],
                "risks": []
            }

        try:
            # Parsear fechas
            if isinstance(target_date_str, str):
                target_date = datetime.fromisoformat(target_date_str.replace('Z', '+00:00')).date()
            else:
                target_date = target_date_str.date() if hasattr(target_date_str, 'date') else target_date_str

            project_end_date = datetime.fromisoformat(last_sprint_end).date()

            # Comparar fechas
            if project_end_date > target_date:
                is_viable = False
                days_over = (project_end_date - target_date).days
                weeks_over = days_over // 7

                issues.append(f"Proyecto termina {days_over} días ({weeks_over} semanas) después de la fecha límite")
                recommendations.append("Reducir el alcance del proyecto o extender la fecha objetivo")
                recommendations.append("Aumentar la velocidad del equipo")
                recommendations.append("Reorganizar las historias en los sprints")

                risks.append({
                    "level": "CRITICAL",
                    "description": f"Fecha límite excedida por {days_over} días - proyecto destinado al fracaso",
                    "mitigation": "Negociar extensión de fecha límite con stakeholders"
                })

            elif project_end_date == target_date:
                recommendations.append("Proyecto ajustado justo a la fecha límite - considere buffer adicional")
                risks.append({
                    "level": "MEDIUM",
                    "description": "Proyecto termina exactamente en la fecha límite - sin margen de error",
                    "mitigation": "Agregar buffer de al menos 1-2 semanas"
                })

            else:
                # Proyecto termina ANTES de la fecha límite - es viable
                days_early = (target_date - project_end_date).days
                self.logger.info(f"✅ Proyecto viable: termina {days_early} días antes de la fecha límite")

        except (ValueError, TypeError, AttributeError) as e:
            self.logger.warning(f"No se pudo validar fechas del plan: {e}")
            # No fallar si no podemos validar fechas
            is_viable = True

        return {
            "is_viable": is_viable,
            "reason": "; ".join(issues) if issues else "Plan viable",
            "issues": issues,
            "recommendations": recommendations,
            "risks": risks
        }

    def _check_and_fix_duplicate_stories(self, release_plan: Dict[str, Any], user_stories: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Verifica si hay historias duplicadas en el plan y las corrige.
        Cada historia debe aparecer exactamente una vez.
        """
        if not release_plan or "sprints" not in release_plan:
            return {"duplicates_found": False, "duplicates": [], "corrected_plan": release_plan}

        story_codes_in_plan = {}
        duplicates_found = []
        corrected_sprints = []

        # Recopilar todas las apariciones de cada historia
        for sprint in release_plan["sprints"]:
            corrected_stories = []
            for story in sprint.get("stories", []):
                code = story.get("code")
                if not code:
                    continue

                if code in story_codes_in_plan:
                    # Historia duplicada encontrada
                    duplicates_found.append({
                        "code": code,
                        "first_sprint": story_codes_in_plan[code]["sprint_number"],
                        "duplicate_sprint": sprint["sprint_number"]
                    })
                    self.logger.warning(f"Historia duplicada {code}: aparece en sprint {story_codes_in_plan[code]['sprint_number']} y {sprint['sprint_number']}")
                    continue  # Omitir la historia duplicada
                else:
                    # Primera aparición de la historia
                    story_codes_in_plan[code] = {
                        "sprint_number": sprint["sprint_number"],
                        "story": story
                    }
                    corrected_stories.append(story)

            # Actualizar el sprint con las historias corregidas
            corrected_sprint = sprint.copy()
            corrected_sprint["stories"] = corrected_stories

            # Recalcular story_points_planned para el sprint
            total_sp = sum(story.get("story_points", 0) for story in corrected_stories)
            corrected_sprint["story_points_planned"] = total_sp

            # Recalcular capacity_used_percentage (asumiendo velocidad del equipo)
            team_velocity = 30  # Valor por defecto, se puede hacer configurable
            corrected_sprint["capacity_used_percentage"] = min(100, int((total_sp / team_velocity) * 100)) if team_velocity > 0 else 0

            corrected_sprints.append(corrected_sprint)

        # Verificar que todas las historias originales estén incluidas
        all_story_codes = {story["code"] for story in user_stories}
        included_codes = set(story_codes_in_plan.keys())
        missing_codes = all_story_codes - included_codes

        if missing_codes:
            self.logger.warning(f"Historias faltantes después de corrección de duplicados: {missing_codes}")
            # Intentar agregar las historias faltantes al último sprint
            if corrected_sprints:
                last_sprint = corrected_sprints[-1]
                for missing_code in missing_codes:
                    # Buscar la historia original
                    original_story = next((s for s in user_stories if s["code"] == missing_code), None)
                    if original_story:
                        # Convertir al formato del plan
                        plan_story = {
                            "code": original_story["code"],
                            "name": original_story["nombre"],
                            "story_points": original_story["story_points"],
                            "priority": original_story["priority"],
                            "dependencies": []  # Simplificar dependencias por ahora
                        }
                        last_sprint["stories"].append(plan_story)

                        # Recalcular métricas del sprint
                        total_sp = sum(story.get("story_points", 0) for story in last_sprint["stories"])
                        last_sprint["story_points_planned"] = total_sp
                        team_velocity = 30
                        last_sprint["capacity_used_percentage"] = min(100, int((total_sp / team_velocity) * 100)) if team_velocity > 0 else 0

        corrected_plan = release_plan.copy()
        corrected_plan["sprints"] = corrected_sprints
        return {
            "duplicates_found": bool(duplicates_found),
            "duplicates": duplicates_found,
            "corrected_plan": corrected_plan
        }

    def _validate_project_viability(
        self,
        total_story_points: int,
        team_velocity: int,
        project_config: Dict[str, Any],
        estimated_sprints: int
    ) -> Dict[str, Any]:
        """
        Valida si un proyecto es viable para generar un plan de release.
        Considera velocidad del equipo, número de devs, duración de sprints y fecha límite.
        """
        from datetime import datetime, date
        issues = []
        recommendations = []
        risks = []
        is_viable = True

        # Extraer parámetros del proyecto
        num_devs = project_config.get("num_devs", 1)
        sprint_duration_weeks = project_config.get("sprint_duration", 2)
        team_capacity_hours = project_config.get("team_capacity", 0)

        # Cálculo más preciso: semanas totales necesarias
        weeks_needed = estimated_sprints * sprint_duration_weeks

        # Validar fecha límite si está disponible
        target_date_viable = True
        weeks_available = 0

        if "release_target_date" in project_config:
            try:
                # Parsear fecha objetivo (puede venir como string ISO o datetime)
                target_date_str = project_config["release_target_date"]
                if isinstance(target_date_str, str):
                    target_date = datetime.fromisoformat(target_date_str.replace('Z', '+00:00')).date()
                else:
                    # Si viene como datetime de MongoDB
                    target_date = target_date_str.date() if hasattr(target_date_str, 'date') else target_date_str

                today = date.today()
                weeks_available = max(0, (target_date - today).days // 7)

                if weeks_needed > weeks_available:
                    target_date_viable = False
                    is_viable = False
                    issues.append(f"Fecha límite insuficiente: necesita {weeks_needed} semanas, tiene {weeks_available} disponibles")
                    recommendations.append("Extender la fecha objetivo o reducir significativamente el alcance del proyecto")
                    risks.append({
                        "level": "CRITICAL",
                        "description": f"Fecha límite irrealista - proyecto necesita {weeks_needed} semanas pero solo tiene {weeks_available}",
                        "mitigation": "Negociar nueva fecha límite con stakeholders o reducir scope drásticamente"
                    })

            except (ValueError, TypeError, AttributeError) as e:
                self.logger.warning(f"No se pudo validar fecha límite: {e}")

        # Validar capacidad del equipo
        if team_capacity_hours > 0 and num_devs > 0:
            # Calcular capacidad teórica por sprint
            capacity_per_dev_per_week = team_capacity_hours / num_devs / sprint_duration_weeks
            # Estimar story points que el equipo puede completar
            estimated_capacity_sp = int(capacity_per_dev_per_week * num_devs * sprint_duration_weeks * 0.8)  # 80% eficiencia

            if team_velocity > estimated_capacity_sp:
                issues.append(f"Velocidad configurada ({team_velocity} SP/sprint) excede capacidad real estimada ({estimated_capacity_sp} SP/sprint)")
                recommendations.append("Ajustar la velocidad del equipo basada en capacidad real o mejorar la eficiencia")

        # Validar sobrecarga crítica: más del 200% de la capacidad normal
        max_recommended_sprints = 12  # 6 meses máximo recomendado
        if estimated_sprints > max_recommended_sprints:
            is_viable = False
            issues.append(f"Proyecto requiere {estimated_sprints} sprints (excede máximo recomendado de {max_recommended_sprints})")
            recommendations.append("Dividir el proyecto en múltiples releases o aumentar significativamente los recursos")
            risks.append({
                "level": "CRITICAL",
                "description": f"Proyecto extremadamente largo ({weeks_needed} semanas) - alto riesgo de fracaso",
                "mitigation": "Implementar releases incrementales con funcionalidades mínimas viables"
            })

        # Validar sobrecarga moderada: más del 150% de la capacidad normal
        elif estimated_sprints > 8:  # Más de 4 meses
            issues.append(f"Proyecto complejo: requiere {estimated_sprints} sprints ({weeks_needed} semanas)")
            recommendations.append("Considerar aumentar la velocidad del equipo o reducir el alcance")
            risks.append({
                "level": "HIGH",
                "description": f"Proyecto largo - riesgo de fatiga del equipo y cambios en requisitos",
                "mitigation": "Implementar checkpoints regulares y mantener comunicación constante con stakeholders"
            })

        # Validar velocidad del equipo vs capacidad
        if team_velocity < 15 and num_devs >= 3:
            issues.append(f"Velocidad del equipo baja ({team_velocity} SP/sprint) para {num_devs} desarrolladores")
            recommendations.append("Mejorar procesos ágiles, capacitación o revisar estimaciones de historias")
            risks.append({
                "level": "MEDIUM",
                "description": "Velocidad del equipo por debajo de estándares típicos",
                "mitigation": "Invertir en mejora continua y capacitación técnica"
            })

        # Validar ratio story points por dev
        if num_devs > 0:
            sp_per_dev = total_story_points / num_devs
            if sp_per_dev > 200:  # Más de 200 SP por dev = proyecto muy grande
                recommendations.append("Considerar agregar más desarrolladores o dividir el proyecto")
                risks.append({
                    "level": "MEDIUM",
                    "description": f"Carga de trabajo alta ({sp_per_dev:.0f} SP por desarrollador)",
                    "mitigation": "Distribuir trabajo equitativamente y monitorear burnout"
                })

        # Si no hay fecha límite configurada, usar criterio de sprints como fallback
        if "release_target_date" not in project_config and estimated_sprints > 10:
            issues.append(f"Sin fecha límite definida y proyecto requiere {estimated_sprints} sprints")
            recommendations.append("Definir una fecha objetivo realista para el proyecto")

        return {
            "is_viable": is_viable,
            "reason": "; ".join(issues) if issues else "Proyecto viable",
            "issues": issues,
            "recommendations": recommendations,
            "risks": risks,
            "metrics": {
                "weeks_needed": weeks_needed,
                "weeks_available": weeks_available,
                "estimated_sprints": estimated_sprints,
                "team_velocity": team_velocity,
                "num_devs": num_devs,
                "sprint_duration_weeks": sprint_duration_weeks
            }
        }

    def _validate_generated_plan_viability(self, release_plan: Dict[str, Any], project_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Valida si el plan de release GENERADO por la IA cabe en la fecha límite.
        Esta es la validación REAL, no teórica.
        """
        from datetime import datetime, date
        issues = []
        recommendations = []
        risks = []
        is_viable = True

        if not release_plan or "sprints" not in release_plan or not release_plan["sprints"]:
            return {
                "is_viable": False,
                "reason": "Plan no generado correctamente",
                "issues": ["Plan de release no generado"],
                "recommendations": ["Vuelva a generar el plan"],
                "risks": []
            }

        # Obtener la fecha del último sprint
        last_sprint = release_plan["sprints"][-1]
        last_sprint_end = last_sprint.get("end_date", "")

        # Obtener fecha objetivo del proyecto
        target_date_str = project_config.get("release_target_date", "")
        if not target_date_str or not last_sprint_end:
            return {
                "is_viable": True,  # No podemos validar sin fechas
                "reason": "No hay fechas para validar",
                "issues": [],
                "recommendations": [],
                "risks": []
            }

        try:
            # Parsear fechas
            if isinstance(target_date_str, str):
                target_date = datetime.fromisoformat(target_date_str.replace('Z', '+00:00')).date()
            else:
                target_date = target_date_str.date() if hasattr(target_date_str, 'date') else target_date_str

            project_end_date = datetime.fromisoformat(last_sprint_end).date()

            # Comparar fechas
            if project_end_date > target_date:
                is_viable = False
                days_over = (project_end_date - target_date).days
                weeks_over = days_over // 7

                issues.append(f"Proyecto termina {days_over} días ({weeks_over} semanas) después de la fecha límite")
                recommendations.append("Reducir el alcance del proyecto o extender la fecha objetivo")
                recommendations.append("Aumentar la velocidad del equipo")
                recommendations.append("Reorganizar las historias en los sprints")

                risks.append({
                    "level": "CRITICAL",
                    "description": f"Fecha límite excedida por {days_over} días - proyecto destinado al fracaso",
                    "mitigation": "Negociar extensión de fecha límite con stakeholders"
                })

            elif project_end_date == target_date:
                recommendations.append("Proyecto ajustado justo a la fecha límite - considere buffer adicional")
                risks.append({
                    "level": "MEDIUM",
                    "description": "Proyecto termina exactamente en la fecha límite - sin margen de error",
                    "mitigation": "Agregar buffer de al menos 1-2 semanas"
                })

            else:
                # Proyecto termina ANTES de la fecha límite - es viable
                days_early = (target_date - project_end_date).days
                self.logger.info(f"✅ Proyecto viable: termina {days_early} días antes de la fecha límite")

        except (ValueError, TypeError, AttributeError) as e:
            self.logger.warning(f"No se pudo validar fechas del plan: {e}")
            # No fallar si no podemos validar fechas
            is_viable = True

        return {
            "is_viable": is_viable,
            "reason": "; ".join(issues) if issues else "Plan viable",
            "issues": issues,
            "recommendations": recommendations,
            "risks": risks
        }


    def _validate_generated_plan_viability_multi_release(self, release_plan: Dict[str, Any], project_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Valida si el plan de release con MÚLTIPLES RELEASES cabe en la fecha límite.
        """
        from datetime import datetime, date
        issues = []
        recommendations = []
        risks = []
        is_viable = True

        if not release_plan or "releases" not in release_plan or not release_plan["releases"]:
            return {
                "is_viable": False,
                "reason": "Plan no generado correctamente",
                "issues": ["Plan de releases no generado"],
                "recommendations": ["Vuelva a generar el plan"],
                "risks": []
            }

        # Obtener la fecha del último sprint del último release
        last_release = release_plan["releases"][-1]
        if not last_release.get("sprints"):
            return {
                "is_viable": False,
                "reason": "Último release sin sprints",
                "issues": ["Último release no contiene sprints"],
                "recommendations": ["Vuelva a generar el plan"],
                "risks": []
            }

        last_sprint = last_release["sprints"][-1]
        last_sprint_end = last_sprint.get("end_date", "")

        # Obtener fecha objetivo del proyecto
        target_date_str = project_config.get("release_target_date", "")
        if not target_date_str or not last_sprint_end:
            return {
                "is_viable": True,  # No podemos validar sin fechas
                "reason": "No hay fechas para validar",
                "issues": [],
                "recommendations": [],
                "risks": []
            }

        try:
            # Parsear fechas
            if isinstance(target_date_str, str):
                target_date = datetime.fromisoformat(target_date_str.replace('Z', '+00:00')).date()
            else:
                target_date = target_date_str.date() if hasattr(target_date_str, 'date') else target_date_str

            project_end_date = datetime.fromisoformat(last_sprint_end).date()

            # Comparar fechas
            if project_end_date > target_date:
                is_viable = False
                days_over = (project_end_date - target_date).days
                weeks_over = days_over // 7

                issues.append(f"Proyecto termina {days_over} días ({weeks_over} semanas) después de la fecha límite")
                recommendations.append("Reducir el alcance del proyecto o extender la fecha objetivo")
                recommendations.append("Aumentar la velocidad del equipo")
                recommendations.append("Considerar reducir el número de releases")

                risks.append({
                    "level": "CRITICAL",
                    "description": f"Fecha límite excedida por {days_over} días - proyecto destinado al fracaso",
                    "mitigation": "Negociar extensión de fecha límite con stakeholders"
                })

            elif project_end_date == target_date:
                recommendations.append("Proyecto ajustado justo a la fecha límite - considere buffer adicional")
                risks.append({
                    "level": "MEDIUM",
                    "description": "Proyecto termina exactamente en la fecha límite - sin margen de error",
                    "mitigation": "Agregar buffer de al menos 1-2 semanas"
                })

            else:
                # Proyecto termina ANTES de la fecha límite - es viable
                days_early = (target_date - project_end_date).days
                self.logger.info(f" Proyecto viable: termina {days_early} días antes de la fecha límite")

        except (ValueError, TypeError, AttributeError) as e:
            self.logger.warning(f"No se pudo validar fechas del plan: {e}")
            # No fallar si no podemos validar fechas
            is_viable = True

        return {
            "is_viable": is_viable,
            "reason": "; ".join(issues) if issues else "Plan viable",
            "issues": issues,
            "recommendations": recommendations,
            "risks": risks
        }

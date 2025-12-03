from fastapi import APIRouter, HTTPException, Depends
from fastapi_crudrouter_mongodb import CRUDRouter
from pydantic import BaseModel
from typing import List
from datetime import datetime, date
from bson import ObjectId
import logging

from backend.app.db import db
from backend.app.schemas import (
    User, Project, UserStory, DependencyGraph, ProjectConfig
)
from backend.api.schemas.responses import (
    UserOut, ProjectConfigOut, DashboardStatsOut, ProjectStatsOut,
    CalendarEventsOut, CalendarEventOut, EventDetailOut
)
from backend.api.schemas.requests import ProjectConfigCreateIn, ProjectConfigUpdateIn
from backend.api.services.auth_service import AuthService, auth_service
from backend.api.schemas.requests import UserCreateIn

router = APIRouter()

# Custom User router con manejo de contraseñas
user_router = APIRouter(prefix="/users", tags=["Users"])

@user_router.post("/", response_model=UserOut, status_code=201)
async def create_user(
    user_data: UserCreateIn,
    auth_svc: AuthService = Depends(auth_service)
):
    """Crear un nuevo usuario con contraseña."""
    user = await auth_svc.create_user(user_data)
    return UserOut(
        id=str(user.id),
        email=user.email,
        name=user.name,
        role=user.role,
        created_at=user.created_at if user.created_at else datetime.utcnow()
    )

@user_router.get("/", response_model=List[UserOut])
async def get_users():
    """Obtener todos los usuarios sin datos sensibles."""
    users = await db.users.find().to_list(None)
    return [
        UserOut(
            id=str(user["_id"]),
            email=user["email"],
            name=user["name"],
            role=user["role"],
            created_at=user.get("created_at", datetime.utcnow())
        )
        for user in users
    ]

@user_router.get("/{user_id}", response_model=UserOut)
async def get_user(user_id: str):
    """Obtener un usuario por ID sin datos sensibles."""
    from bson import ObjectId
    
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    return UserOut(
        id=str(user["_id"]),
        email=user["email"],
        name=user["name"],
        role=user["role"],
        created_at=user.get("created_at", datetime.utcnow())
    )

# Incluir el router personalizado para usuarios
router.include_router(user_router)

# ── Endpoint para Dashboard Stats (ANTES del CRUDRouter para evitar conflictos) ──────────────

@router.get("/projects/dashboard-stats", response_model=DashboardStatsOut, tags=["Projects"])
async def get_dashboard_stats(user_id: str = None):
    """
    Obtener estadísticas del dashboard para un usuario (o todos si no se especifica).
    
    Retorna:
    - total_projects: Número total de proyectos
    - projects_growth: Texto descriptivo del crecimiento
    - total_active_stories: Total de historias activas
    - pending_refinement: Historias pendientes de refinar (dor < 80)
    - planned_releases: Número de releases planificados
    - next_release_date: Fecha del próximo release más cercano
    - ai_analysis_count: Número de análisis de IA realizados
    - ai_analysis_period: Período del conteo
    """
    try:
        from datetime import timedelta
        
        # Filtro para el usuario (si se proporciona)
        project_filter = {}
        if user_id:
            try:
                project_filter = {"createdBy": ObjectId(user_id)}
            except:
                project_filter = {"createdBy": user_id}
        
        # 1. Total de proyectos
        total_projects = await db.projects.count_documents(project_filter)
        
        # 2. Crecimiento de proyectos (últimos 30 días)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        projects_filter_recent = {**project_filter, "created_at": {"$gte": thirty_days_ago}}
        recent_projects = await db.projects.count_documents(projects_filter_recent)
        
        if recent_projects == 0:
            projects_growth = "Sin crecimiento este mes"
        elif recent_projects == 1:
            projects_growth = "+1 este mes"
        else:
            projects_growth = f"+{recent_projects} este mes"
        
        # 3. Obtener IDs de proyectos para filtrar historias
        projects = await db.projects.find(project_filter).to_list(None)
        project_ids = [p["_id"] for p in projects]
        
        # 4. Total de historias activas (status != "Done" y status != "Archived")
        stories_filter = {
            "project_id": {"$in": project_ids},
            "status": {"$nin": ["Done", "Archived"]}
        }
        total_active_stories = await db.user_stories.count_documents(stories_filter)
        
        # 5. Historias pendientes de refinamiento (dor < 80)
        refinement_filter = {
            "project_id": {"$in": project_ids},
            "dor": {"$lt": 80},
            "status": {"$nin": ["Done", "Archived"]}
        }
        pending_refinement = await db.user_stories.count_documents(refinement_filter)
        
        # 6. Releases planificados y próximo release
        releases_filter = {"project_id": {"$in": project_ids}}
        planned_releases = await db.release_plans.count_documents(releases_filter)
        
        # Buscar el próximo release más cercano
        next_release_date = None
        if planned_releases > 0:
            # Obtener todos los release plans
            release_plans = await db.release_plans.find(releases_filter).to_list(None)
            
            # Buscar la fecha más cercana en el futuro
            now = datetime.utcnow()
            closest_date = None
            
            for plan in release_plans:
                releases = plan.get("releases", [])
                for release in releases:
                    end_date_str = release.get("end_date")
                    if end_date_str:
                        try:
                            # Parsear fecha (puede ser string o datetime)
                            if isinstance(end_date_str, str):
                                end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
                            else:
                                end_date = end_date_str
                            
                            # Si es una fecha futura y es la más cercana
                            if end_date > now:
                                if closest_date is None or end_date < closest_date:
                                    closest_date = end_date
                        except:
                            continue
            
            if closest_date:
                next_release_date = closest_date.strftime("%Y-%m-%d")
        
        # 7. Análisis de IA realizados (últimos 7 días)
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        
        # Contar análisis de PDF imports
        pdf_imports_filter = {
            **project_filter,
            "generated_at": {"$gte": seven_days_ago}
        }
        pdf_imports_count = await db.pdf_imports.count_documents(pdf_imports_filter)
        
        # Contar análisis de release backlog
        release_backlog_filter = {
            "project_id": {"$in": project_ids},
            "generated_at": {"$gte": seven_days_ago}
        }
        release_backlog_count = await db.release_backlogs.count_documents(release_backlog_filter)
        
        # Contar análisis de release planning
        release_planning_filter = {
            "project_id": {"$in": project_ids},
            "generated_at": {"$gte": seven_days_ago}
        }
        release_planning_count = await db.release_plans.count_documents(release_planning_filter)
        
        ai_analysis_count = pdf_imports_count + release_backlog_count + release_planning_count
        ai_analysis_period = "Esta semana"
        
        return DashboardStatsOut(
            total_projects=total_projects,
            projects_growth=projects_growth,
            total_active_stories=total_active_stories,
            pending_refinement=pending_refinement,
            planned_releases=planned_releases,
            next_release_date=next_release_date,
            ai_analysis_count=ai_analysis_count,
            ai_analysis_period=ai_analysis_period
        )
        
    except Exception as e:
        logging.error(f"Error obteniendo estadísticas del dashboard: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

# ── Endpoint para Stats de Proyecto Individual (ANTES del CRUDRouter) ──────────────

@router.get("/projects/{project_id}/stats", response_model=ProjectStatsOut, tags=["Projects"])
async def get_project_stats(project_id: str):
    """
    Obtener estadísticas de un proyecto específico.
    
    Retorna:
    - total_stories: Total de historias de usuario del proyecto
    - in_development: Historias actualmente en desarrollo
    - completed: Historias completadas
    - pending: Historias pendientes/sin iniciar
    - releases_count: Número de releases planificados
    - total_story_points: Story points totales del proyecto
    - completed_story_points: Story points completados
    - progress_percentage: Porcentaje de avance del proyecto
    """
    try:
        # Verificar que el proyecto existe
        project = await db.projects.find_one({"_id": ObjectId(project_id)})
        if not project:
            raise HTTPException(status_code=404, detail="Proyecto no encontrado")
        
        # 1. Obtener todas las historias del proyecto
        stories_filter = {"project_id": ObjectId(project_id)}
        all_stories = await db.user_stories.find(stories_filter).to_list(None)
        
        total_stories = len(all_stories)
        
        # 2. Contar historias por status
        in_development = 0
        completed = 0
        pending = 0
        
        for story in all_stories:
            status = story.get("status", "Ready")
            if status in ["In Progress", "In Development", "Doing"]:
                in_development += 1
            elif status in ["Done", "Completed"]:
                completed += 1
            elif status in ["Ready", "To Do", "Pending", "Backlog"]:
                pending += 1
        
        # 3. Calcular story points
        total_story_points = sum(story.get("story_points", 0) for story in all_stories)
        
        completed_stories = [s for s in all_stories if s.get("status") in ["Done", "Completed"]]
        completed_story_points = sum(story.get("story_points", 0) for story in completed_stories)
        
        # 4. Calcular porcentaje de progreso
        if total_story_points > 0:
            progress_percentage = round((completed_story_points / total_story_points) * 100, 1)
        else:
            progress_percentage = 0.0
        
        # 5. Contar releases planificados (sumar releases dentro de cada plan)
        releases_filter = {"project_id": ObjectId(project_id)}
        release_plans = await db.release_plans.find(releases_filter).to_list(None)
        
        releases_count = 0
        for plan in release_plans:
            # Cada plan puede tener múltiples releases en el array "releases"
            releases_array = plan.get("releases", [])
            releases_count += len(releases_array)
        
        return ProjectStatsOut(
            total_stories=total_stories,
            in_development=in_development,
            completed=completed,
            pending=pending,
            releases_count=releases_count,
            total_story_points=total_story_points,
            completed_story_points=completed_story_points,
            progress_percentage=progress_percentage
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error obteniendo estadísticas del proyecto: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

# ── Endpoint para Eventos del Calendario (ANTES del CRUDRouter) ──────────────

@router.get("/projects/{project_id}/calendar-events", response_model=CalendarEventsOut, tags=["Projects"])
async def get_project_calendar_events(project_id: str, month: int = None, year: int = None):
    """
    Obtener eventos de calendario para un proyecto.
    Genera automáticamente eventos basados en releases y sprints.
    
    Query Parameters:
    - month: Mes (0-11, opcional)
    - year: Año (opcional)
    
    Retorna:
    - events: Eventos para el calendario principal (releases, milestones, sprints)
    - event_details: Detalles de eventos para panel lateral (planning, review, standup, etc.)
    """
    try:
        from datetime import datetime, timedelta
        
        # Verificar que el proyecto existe
        project = await db.projects.find_one({"_id": ObjectId(project_id)})
        if not project:
            raise HTTPException(status_code=404, detail="Proyecto no encontrado")
        
        events = []
        event_details = []
        
        # Obtener release plans del proyecto
        release_plans = await db.release_plans.find({"project_id": ObjectId(project_id)}).to_list(None)
        
        event_id_counter = 1
        detail_id_counter = 1
        
        for plan in release_plans:
            releases = plan.get("releases", [])
            
            for release in releases:
                release_number = release.get("release_number", 1)
                release_title = release.get("title", f"Release {release_number}")
                release_description = release.get("description", "")
                start_date = release.get("start_date")
                end_date = release.get("end_date")
                sprints = release.get("sprints", [])
                
                # Evento principal del release
                if start_date and end_date:
                    release_event = CalendarEventOut(
                        id=f"evt_{event_id_counter}",
                        title=release_title,
                        type="release",
                        start_date=f"{start_date}T00:00:00Z",
                        end_date=f"{end_date}T23:59:59Z",
                        color="#e3f2fd",
                        text_color="#1976d2",
                        release_id=f"rel_{release_number}",
                        sprint_number=None,
                        description=release_description
                    )
                    events.append(release_event)
                    event_id_counter += 1
                    
                    # Evento detalle: Release Review
                    try:
                        end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                        release_review = EventDetailOut(
                            id=f"detail_{detail_id_counter}",
                            title=f"{release_title} - Review",
                            location="Remote",
                            time="10am to 11:30am",
                            date=f"{end_date}T10:00:00Z",
                            color="#b39ddb",
                            event_type="review",
                            sprint_number=None,
                            release_id=f"rel_{release_number}",
                            description=f"Review del {release_title}"
                        )
                        event_details.append(release_review)
                        detail_id_counter += 1
                    except:
                        pass
                
                # Eventos de sprints
                for sprint in sprints:
                    sprint_number = sprint.get("sprint_number", 1)
                    sprint_start = sprint.get("start_date")
                    sprint_end = sprint.get("end_date")
                    
                    if sprint_start and sprint_end:
                        # Evento: Sprint Start
                        sprint_start_event = CalendarEventOut(
                            id=f"evt_{event_id_counter}",
                            title=f"Sprint {sprint_number} - Start",
                            type="sprint_start",
                            start_date=f"{sprint_start}T00:00:00Z",
                            end_date=f"{sprint_start}T23:59:59Z",
                            color="#f3e5f5",
                            text_color="#8e24aa",
                            release_id=f"rel_{release_number}",
                            sprint_number=sprint_number,
                            description=f"Inicio del Sprint {sprint_number}"
                        )
                        events.append(sprint_start_event)
                        event_id_counter += 1
                        
                        # Evento: Sprint End
                        sprint_end_event = CalendarEventOut(
                            id=f"evt_{event_id_counter}",
                            title=f"Sprint {sprint_number} - End",
                            type="sprint_end",
                            start_date=f"{sprint_end}T00:00:00Z",
                            end_date=f"{sprint_end}T23:59:59Z",
                            color="#fce4ec",
                            text_color="#c2185b",
                            release_id=f"rel_{release_number}",
                            sprint_number=sprint_number,
                            description=f"Fin del Sprint {sprint_number}"
                        )
                        events.append(sprint_end_event)
                        event_id_counter += 1
                        
                        # Event Details: Sprint Planning (primer día del sprint)
                        try:
                            sprint_planning = EventDetailOut(
                                id=f"detail_{detail_id_counter}",
                                title=f"Sprint {sprint_number} Planning",
                                location="Remote",
                                time="2pm to 4pm",
                                date=f"{sprint_start}T14:00:00Z",
                                color="#ce93d8",
                                event_type="planning",
                                sprint_number=sprint_number,
                                release_id=f"rel_{release_number}",
                                description=f"Planificación del Sprint {sprint_number}"
                            )
                            event_details.append(sprint_planning)
                            detail_id_counter += 1
                        except:
                            pass
                        
                        # Event Details: Sprint Review (último día del sprint)
                        try:
                            sprint_review = EventDetailOut(
                                id=f"detail_{detail_id_counter}",
                                title=f"Sprint {sprint_number} Review",
                                location="Conference Room A",
                                time="3pm to 4pm",
                                date=f"{sprint_end}T15:00:00Z",
                                color="#b39ddb",
                                event_type="review",
                                sprint_number=sprint_number,
                                release_id=f"rel_{release_number}",
                                description=f"Revisión del Sprint {sprint_number}"
                            )
                            event_details.append(sprint_review)
                            detail_id_counter += 1
                        except:
                            pass
                        
                        # Event Details: Sprint Retrospective (último día del sprint)
                        try:
                            sprint_retro = EventDetailOut(
                                id=f"detail_{detail_id_counter}",
                                title=f"Sprint {sprint_number} Retrospective",
                                location="Remote",
                                time="4pm to 5pm",
                                date=f"{sprint_end}T16:00:00Z",
                                color="#9fa8da",
                                event_type="retrospective",
                                sprint_number=sprint_number,
                                release_id=f"rel_{release_number}",
                                description=f"Retrospectiva del Sprint {sprint_number}"
                            )
                            event_details.append(sprint_retro)
                            detail_id_counter += 1
                        except:
                            pass
                        
                        # Event Details: Daily Standups (durante el sprint)
                        try:
                            start_dt = datetime.fromisoformat(sprint_start.replace('Z', '+00:00'))
                            end_dt = datetime.fromisoformat(sprint_end.replace('Z', '+00:00'))
                            
                            # Agregar standups cada día laboral (lunes a viernes)
                            current_dt = start_dt
                            while current_dt <= end_dt:
                                # Solo días laborales (0=lunes, 4=viernes)
                                if current_dt.weekday() < 5:
                                    standup = EventDetailOut(
                                        id=f"detail_{detail_id_counter}",
                                        title="Daily Standup",
                                        location="Remote",
                                        time="9am to 9:15am",
                                        date=f"{current_dt.strftime('%Y-%m-%d')}T09:00:00Z",
                                        color="#ef9a9a",
                                        event_type="standup",
                                        sprint_number=sprint_number,
                                        release_id=f"rel_{release_number}",
                                        description="Daily team sync"
                                    )
                                    event_details.append(standup)
                                    detail_id_counter += 1
                                
                                current_dt += timedelta(days=1)
                        except:
                            pass
                        
                        # Milestone: Code Freeze (3 días antes del fin del sprint)
                        try:
                            end_dt = datetime.fromisoformat(sprint_end.replace('Z', '+00:00'))
                            code_freeze_dt = end_dt - timedelta(days=3)
                            
                            code_freeze_event = CalendarEventOut(
                                id=f"evt_{event_id_counter}",
                                title=f"Sprint {sprint_number} - Code Freeze",
                                type="milestone",
                                start_date=f"{code_freeze_dt.strftime('%Y-%m-%d')}T00:00:00Z",
                                end_date=f"{code_freeze_dt.strftime('%Y-%m-%d')}T23:59:59Z",
                                color="#ede7f6",
                                text_color="#7e57c2",
                                release_id=f"rel_{release_number}",
                                sprint_number=sprint_number,
                                description="No new features, only bug fixes"
                            )
                            events.append(code_freeze_event)
                            event_id_counter += 1
                        except:
                            pass
        
        # Filtrar por mes/año si se proporcionan
        if month is not None and year is not None:
            filtered_events = []
            for event in events:
                try:
                    event_date = datetime.fromisoformat(event.start_date.replace('Z', '+00:00'))
                    # month es 0-11 en JS, pero datetime usa 1-12
                    if event_date.month == (month + 1) and event_date.year == year:
                        filtered_events.append(event)
                except:
                    pass
            events = filtered_events
            
            filtered_details = []
            for detail in event_details:
                try:
                    detail_date = datetime.fromisoformat(detail.date.replace('Z', '+00:00'))
                    if detail_date.month == (month + 1) and detail_date.year == year:
                        filtered_details.append(detail)
                except:
                    pass
            event_details = filtered_details
        
        return CalendarEventsOut(
            events=events,
            event_details=event_details
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error obteniendo eventos del calendario: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

# Routers para otras entidades (sin cambios)
def _mount(name: str, collection, schema):
    tag = name.replace("_", " ").title()
    router.include_router(
        CRUDRouter(
            model=schema,
            db=db,
            collection_name=name,
            prefix=f"/{name}",
            tags=[tag],
        )
    )

for _name, _coll, _schema in [
    ("projects",          db.projects,          Project),
    ("user_stories",      db.user_stories,      UserStory),
    ("dependencies_graph", db.dependencies_graph, DependencyGraph),
]:
    _mount(_name, _coll, _schema)

__all__ = ["router"]

# Endpoint personalizado que REEMPLAZA al GET /user_stories/ del CRUDRouter
# (Se registra DESPUÉS para tener prioridad sobre el automático)
@router.get("/user_stories/", tags=["User Stories"])
async def get_user_stories(projectId: str = None):
    """Obtener historias de usuario, opcionalmente filtradas por projectId."""
    try:
        logging.info(f"Endpoint /user_stories/ llamado con projectId: {projectId}")
        
        # Verificar que db esté disponible
        if not hasattr(db, 'user_stories'):
            logging.error("db.user_stories no está disponible")
            raise HTTPException(status_code=500, detail="Base de datos no disponible")
        
        filtro = {}
        if projectId:
            logging.info(f"Filtrando historias por projectId: {projectId}")
            try:
                # Intentar convertir a ObjectId, si falla usar como string
                try:
                    object_id = ObjectId(projectId)
                    # Buscar por ambos posibles nombres de campo para compatibilidad
                    filtro = {"$or": [
                        {"projectId": object_id},
                        {"project_id": object_id}
                    ]}
                    logging.info(f"Usando filtro ObjectId: {filtro}")
                except Exception as oid_error:
                    logging.warning(f"projectId no es ObjectId válido ({oid_error}), buscando como string")
                    # Si no es un ObjectId válido, buscar como string en ambos campos
                    filtro = {"$or": [
                        {"projectId": projectId},
                        {"project_id": projectId}
                    ]}
                    logging.info(f"Usando filtro string: {filtro}")
            except Exception as e:
                logging.warning(f"Error al procesar projectId {projectId}: {e}")
                # En caso de error, no filtrar
                filtro = {}
        else:
            logging.info("No se proporcionó projectId, trayendo todas las historias")
        
        logging.info(f"Ejecutando query con filtro: {filtro}")
        historias = await db.user_stories.find(filtro).to_list(None)
        logging.info(f"Encontradas {len(historias)} historias con filtro: {filtro}")
        
        result = []
        for h in historias:
            result.append({
                "id": str(h.get("_id", "")),
                "project_id": str(h.get("projectId", h.get("project_id", ""))),
                "code": h.get("code", ""),
                "epica": h.get("epica", ""),
                "nombre": h.get("nombre", ""),
                "descripcion": h.get("descripcion", ""),
                "criterios": h.get("criterios", []),
                "created_at": h.get("createdAt", h.get("created_at", "")),
                "priority": h.get("priority", "Medium"),
                "story_points": h.get("storyPoints", h.get("story_points", 0)),
                "dor": h.get("dor", 0),
                "status": h.get("status", "Ready"),
                "deps": h.get("deps", 0),
                "ai": h.get("ai", False),
            })
        
        logging.info(f"Retornando {len(result)} historias")
        return result
        
    except HTTPException:
        # Re-lanzar HTTPExceptions sin modificar
        raise
    except Exception as e:
        logging.error(f"Error interno en get_user_stories: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

# Endpoint adicional para Product Backlog
@router.get("/user_stories/product_backlog", tags=["User Stories"])
async def get_user_stories_product_backlog(product_id: str = None):
    # Buscar por ambos formatos de project_id
    filtro = {}
    if product_id:
        filtro = {"$or": [
            {"project_id": product_id},
            {"projectId": product_id}
        ]}
    historias = await db.user_stories.find(filtro).to_list(None)
    result = []
    for h in historias:
        result.append({
            "code": h.get("code", ""),
            "title": h.get("nombre", ""),
            "epica": h.get("epica", ""),
            "priority": h.get("priority", "Medium"),
            "story_points": h.get("story_points", 0),
            "dor": h.get("dor", 0),
            "status": h.get("status", "Ready"),
            "deps": h.get("deps", 0),
            "ai": h.get("ai", False),
            "_id": str(h.get("_id", "")),
            "project_id": h.get("project_id", h.get("projectId", "")),
        })
    return result

# Nuevo endpoint para filtrar US por proyecto
@router.get("/user_stories/by-project/{projectId}", tags=["User Stories"])
async def get_user_stories_by_project(projectId: str):
    """Obtener historias de usuario filtradas por projectId."""
    try:
        logging.info(f"Endpoint /user_stories/by-project/{{projectId}} llamado con projectId: {projectId}")
        
        if not hasattr(db, 'user_stories'):
            logging.error("db.user_stories no está disponible")
            raise HTTPException(status_code=500, detail="Base de datos no disponible")
        
        filtro = {}
        logging.info(f"Filtrando historias por projectId: {projectId}")
        try:
            try:
                object_id = ObjectId(projectId)
                filtro = {"$or": [
                    {"projectId": object_id},
                    {"project_id": object_id}
                ]}
                logging.info(f"Usando filtro ObjectId: {filtro}")
            except Exception as oid_error:
                logging.warning(f"projectId no es ObjectId válido ({oid_error}), buscando como string")
                filtro = {"$or": [
                    {"projectId": projectId},
                    {"project_id": projectId}
                ]}
                logging.info(f"Usando filtro string: {filtro}")
        except Exception as e:
            logging.warning(f"Error al procesar projectId {projectId}: {e}")
            # En caso de error, no filtrar
            filtro = {}
        
        logging.info(f"Ejecutando query con filtro: {filtro}")
        historias = await db.user_stories.find(filtro).to_list(None)
        logging.info(f"Encontradas {len(historias)} historias con filtro: {filtro}")
        
        result = []
        for h in historias:
            result.append({
                "id": str(h.get("_id", "")),
                "project_id": str(h.get("projectId", h.get("project_id", ""))),
                "code": h.get("code", ""),
                "epica": h.get("epica", ""),
                "nombre": h.get("nombre", ""),
                "descripcion": h.get("descripcion", ""),
                "criterios": h.get("criterios", []),
                "created_at": h.get("createdAt", h.get("created_at", "")),
                "priority": h.get("priority", "Medium"),
                "story_points": h.get("storyPoints", h.get("story_points", 0)),
                "dor": h.get("dor", 0),
                "status": h.get("status", "Ready"),
                "deps": h.get("deps", 0),
                "ai": h.get("ai", False),
            })
        
        logging.info(f"Retornando {len(result)} historias")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error interno en get_user_stories_by_project: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

# ── Endpoints para Project Config ──────────────────────────────────────

@router.post("/project_configs/", response_model=ProjectConfigOut, tags=["Project Config"])
async def create_project_config(config_data: ProjectConfigCreateIn):
    """Crear configuración para un proyecto."""
    logging.info("=== INICIANDO CREACIÓN DE CONFIGURACIÓN ===")
    try:
        logging.info(f"Creando configuración para proyecto: {config_data.project_id}")
        logging.info(f"Datos recibidos: {config_data.model_dump()}")

        # Verificar que el proyecto existe
        logging.info("Verificando existencia del proyecto...")
        project = await db.projects.find_one({"_id": ObjectId(config_data.project_id)})
        if not project:
            logging.error(f"Proyecto no encontrado: {config_data.project_id}")
            raise HTTPException(status_code=404, detail="Proyecto no encontrado")
        logging.info(f"Proyecto encontrado: {project.get('name', 'Unknown')}")

        # Verificar que no existe ya una configuración para este proyecto
        logging.info("Verificando configuración existente...")
        existing_config = await db.project_configs.find_one({"project_id": ObjectId(config_data.project_id)})
        if existing_config:
            logging.warning(f"Ya existe configuración para proyecto: {config_data.project_id}")
            raise HTTPException(status_code=400, detail="Ya existe configuración para este proyecto")

        # Crear la configuración
        logging.info("Creando diccionario de configuración...")
        config_dict = config_data.model_dump()
        config_dict["project_id"] = ObjectId(config_dict["project_id"])
        # Convertir date a datetime para MongoDB
        if isinstance(config_dict["release_target_date"], date):
            config_dict["release_target_date"] = datetime.combine(config_dict["release_target_date"], datetime.min.time())
        config_dict["created_at"] = datetime.utcnow()
        config_dict["updated_at"] = datetime.utcnow()

        logging.info(f"Insertando configuración: {config_dict}")
        result = await db.project_configs.insert_one(config_dict)
        created_config = await db.project_configs.find_one({"_id": result.inserted_id})

        logging.info(f"Configuración creada exitosamente: {created_config}")
        response = ProjectConfigOut(
            id=str(created_config["_id"]),
            project_id=str(created_config["project_id"]),
            num_devs=created_config["num_devs"],
            team_velocity=created_config["team_velocity"],
            sprint_duration=created_config["sprint_duration"],
            prioritization_metric=created_config["prioritization_metric"],
            release_target_date=created_config["release_target_date"],  # Ya es datetime, no convertir
            team_capacity=created_config.get("team_capacity"),
            optimistic_scenario=created_config.get("optimistic_scenario"),
            realistic_scenario=created_config.get("realistic_scenario"),
            pessimistic_scenario=created_config.get("pessimistic_scenario"),
            created_at=created_config["created_at"],
            updated_at=created_config["updated_at"]
        )
        logging.info("=== CONFIGURACIÓN CREADA EXITOSAMENTE ===")
        return response

    except HTTPException:
        logging.info("=== HTTP EXCEPTION LANZADA ===")
        raise
    except Exception as e:
        logging.error(f"=== ERROR INTERNO: {e} ===", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

@router.get("/project_configs/{project_id}", response_model=ProjectConfigOut, tags=["Project Config"])
async def get_project_config(project_id: str):
    """Obtener configuración de un proyecto."""
    try:
        config = await db.project_configs.find_one({"project_id": ObjectId(project_id)})
        if not config:
            raise HTTPException(status_code=404, detail="Configuración no encontrada para este proyecto")

        return ProjectConfigOut(
            id=str(config["_id"]),
            project_id=str(config["project_id"]),
            num_devs=config["num_devs"],
            team_velocity=config["team_velocity"],
            sprint_duration=config["sprint_duration"],
            prioritization_metric=config["prioritization_metric"],
            release_target_date=config["release_target_date"],
            team_capacity=config.get("team_capacity"),
            optimistic_scenario=config.get("optimistic_scenario"),
            realistic_scenario=config.get("realistic_scenario"),
            pessimistic_scenario=config.get("pessimistic_scenario"),
            created_at=config["created_at"],
            updated_at=config["updated_at"]
        )

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error obteniendo configuración del proyecto: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

@router.put("/project_configs/{project_id}", response_model=ProjectConfigOut, tags=["Project Config"])
async def update_project_config(project_id: str, config_data: ProjectConfigUpdateIn):
    """Actualizar configuración de un proyecto."""
    try:
        # Verificar que existe la configuración
        existing_config = await db.project_configs.find_one({"project_id": ObjectId(project_id)})
        if not existing_config:
            raise HTTPException(status_code=404, detail="Configuración no encontrada para este proyecto")

        # Preparar los datos de actualización
        update_data = config_data.model_dump(exclude_unset=True)
        # Convertir date a datetime para MongoDB si está presente
        if "release_target_date" in update_data and isinstance(update_data["release_target_date"], date):
            update_data["release_target_date"] = datetime.combine(update_data["release_target_date"], datetime.min.time())
        update_data["updated_at"] = datetime.utcnow()

        # Actualizar
        await db.project_configs.update_one(
            {"project_id": ObjectId(project_id)},
            {"$set": update_data}
        )

        # Obtener la configuración actualizada
        updated_config = await db.project_configs.find_one({"project_id": ObjectId(project_id)})

        return ProjectConfigOut(
            id=str(updated_config["_id"]),
            project_id=str(updated_config["project_id"]),
            num_devs=updated_config["num_devs"],
            team_velocity=updated_config["team_velocity"],
            sprint_duration=updated_config["sprint_duration"],
            prioritization_metric=updated_config["prioritization_metric"],
            release_target_date=updated_config["release_target_date"],
            team_capacity=updated_config.get("team_capacity"),
            optimistic_scenario=updated_config.get("optimistic_scenario"),
            realistic_scenario=updated_config.get("realistic_scenario"),
            pessimistic_scenario=updated_config.get("pessimistic_scenario"),
            created_at=updated_config["created_at"],
            updated_at=updated_config["updated_at"]
        )

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error actualizando configuración del proyecto: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

# backend/app/__init__.py
from .database import app            # FastAPI instance
from .routers  import api_router     # CRUD routes

app.include_router(api_router, prefix="/api")

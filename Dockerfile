# Usar Python 3.11 slim como base
FROM python:3.11-slim

# Establecer directorio de trabajo
WORKDIR /app

# Variables de entorno para Python
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Copiar archivos de requisitos
COPY backend/requirements.txt backend/requirements.txt

# Instalar dependencias
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copiar el código de la aplicación
COPY . .

# Exponer el puerto que usa Cloud Run (8080 por defecto)
ENV PORT=8080

# Comando para ejecutar la aplicación
CMD uvicorn backend.app:app --host 0.0.0.0 --port ${PORT}

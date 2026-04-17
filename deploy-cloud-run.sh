#!/bin/bash

# Script para construir y hacer push de la imagen Docker a Google Container Registry

# Variables
PROJECT_ID="your-gcp-project-id"
IMAGE_NAME="back-release-project"
REGION="us-central1"
SERVICE_NAME="back-release-api"

# Colores para output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 Iniciando deployment a Cloud Run...${NC}"

# 1. Autenticar con GCP (si es necesario)
echo -e "${BLUE}📝 Autenticando con GCP...${NC}"
gcloud auth configure-docker

# 2. Construir la imagen Docker
echo -e "${BLUE}🔨 Construyendo imagen Docker...${NC}"
docker build -t gcr.io/${PROJECT_ID}/${IMAGE_NAME}:latest .

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Error construyendo la imagen${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Imagen construida exitosamente${NC}"

# 3. Push de la imagen a Google Container Registry
echo -e "${BLUE}📤 Subiendo imagen a GCR...${NC}"
docker push gcr.io/${PROJECT_ID}/${IMAGE_NAME}:latest

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Error subiendo la imagen${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Imagen subida exitosamente${NC}"

# 4. Deploy a Cloud Run
echo -e "${BLUE}🚀 Desplegando a Cloud Run...${NC}"
gcloud run deploy ${SERVICE_NAME} \
  --image gcr.io/${PROJECT_ID}/${IMAGE_NAME}:latest \
  --platform managed \
  --region ${REGION} \
  --allow-unauthenticated \
  --port 8080 \
  --memory 1Gi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 10 \
  --timeout 300 \
  --set-env-vars "PYTHON_ENV=production" \
  --set-secrets "MONGODB_URI=mongodb-uri:latest,GEMINI_API_KEY=gemini-api-key:latest"

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Error desplegando a Cloud Run${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Deployment completado exitosamente!${NC}"
echo -e "${BLUE}🌐 Tu API está disponible en Cloud Run${NC}"

# Obtener la URL del servicio
SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} --region ${REGION} --format 'value(status.url)')
echo -e "${GREEN}📍 URL del servicio: ${SERVICE_URL}${NC}"

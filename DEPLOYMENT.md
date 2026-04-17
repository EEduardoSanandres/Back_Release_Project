# Deployment Guide - Google Cloud Run

## Prerequisites

1. **Google Cloud SDK** installed
   ```bash
   # Install gcloud CLI: https://cloud.google.com/sdk/docs/install
   ```

2. **Docker** installed and running
   ```bash
   docker --version
   ```

3. **Google Cloud Project** with billing enabled
   ```bash
   gcloud projects list
   ```

4. **Enable required APIs**
   ```bash
   gcloud services enable run.googleapis.com
   gcloud services enable containerregistry.googleapis.com
   gcloud services enable cloudbuild.googleapis.com
   ```

## Setup Steps

### 1. Configure GCP Project

```bash
# Set your project ID
export PROJECT_ID="your-gcp-project-id"
gcloud config set project $PROJECT_ID

# Set default region
gcloud config set run/region us-central1
```

### 2. Create Secrets in Secret Manager

The application requires environment variables. Store them securely using Google Secret Manager:

```bash
# Enable Secret Manager API
gcloud services enable secretmanager.googleapis.com

# Create secrets (replace with your actual values)
echo -n "mongodb+srv://user:password@cluster.mongodb.net/dbname" | \
  gcloud secrets create mongodb-uri --data-file=-

echo -n "your-gemini-api-key" | \
  gcloud secrets create gemini-api-key --data-file=-

echo -n "your-jwt-secret-key" | \
  gcloud secrets create jwt-secret --data-file=-

# Grant Cloud Run access to secrets
gcloud secrets add-iam-policy-binding mongodb-uri \
  --member=serviceAccount:$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")-compute@developer.gserviceaccount.com \
  --role=roles/secretmanager.secretAccessor

gcloud secrets add-iam-policy-binding gemini-api-key \
  --member=serviceAccount:$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")-compute@developer.gserviceaccount.com \
  --role=roles/secretmanager.secretAccessor

gcloud secrets add-iam-policy-binding jwt-secret \
  --member=serviceAccount:$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")-compute@developer.gserviceaccount.com \
  --role=roles/secretmanager.secretAccessor
```

### 3. Test Docker Image Locally

```bash
# Build the image
docker build -t back-release-project:test .

# Create a local .env file for testing (DO NOT commit this)
cat > .env << EOF
MONGODB_URI=mongodb+srv://user:password@cluster.mongodb.net/dbname
GEMINI_API_KEY=your-gemini-api-key
JWT_SECRET=your-jwt-secret-key
PORT=8080
EOF

# Run locally
docker run -p 8080:8080 --env-file .env back-release-project:test

# Test the API
curl http://localhost:8080/docs
```

### 4. Deploy to Cloud Run

#### Option A: Using the provided script (Linux/Mac)

```bash
# Make the script executable
chmod +x deploy-cloud-run.sh

# Edit the script to set your PROJECT_ID and REGION
nano deploy-cloud-run.sh

# Run the deployment
./deploy-cloud-run.sh
```

#### Option B: Manual deployment (Windows PowerShell)

```powershell
# Set variables
$PROJECT_ID = "your-gcp-project-id"
$IMAGE_NAME = "back-release-project"
$REGION = "us-central1"
$SERVICE_NAME = "back-release-api"

# Authenticate Docker with GCR
gcloud auth configure-docker

# Build and tag the image
docker build -t gcr.io/$PROJECT_ID/$IMAGE_NAME`:latest .

# Push to Google Container Registry
docker push gcr.io/$PROJECT_ID/$IMAGE_NAME`:latest

# Deploy to Cloud Run
gcloud run deploy $SERVICE_NAME `
  --image gcr.io/$PROJECT_ID/$IMAGE_NAME`:latest `
  --platform managed `
  --region $REGION `
  --allow-unauthenticated `
  --port 8080 `
  --memory 1Gi `
  --cpu 1 `
  --min-instances 0 `
  --max-instances 10 `
  --timeout 300 `
  --set-env-vars "PYTHON_ENV=production" `
  --set-secrets "MONGODB_URI=mongodb-uri:latest,GEMINI_API_KEY=gemini-api-key:latest,JWT_SECRET=jwt-secret:latest"
```

#### Option C: Using Cloud Build (recommended for CI/CD)

Create `cloudbuild.yaml`:

```yaml
steps:
  # Build the Docker image
  - name: 'gcr.io/cloud-builders/docker'
    args: ['build', '-t', 'gcr.io/$PROJECT_ID/back-release-project:latest', '.']
  
  # Push the image to Container Registry
  - name: 'gcr.io/cloud-builders/docker'
    args: ['push', 'gcr.io/$PROJECT_ID/back-release-project:latest']
  
  # Deploy to Cloud Run
  - name: 'gcr.io/google.com/cloudsdktool/cloud-sdk'
    entrypoint: gcloud
    args:
      - 'run'
      - 'deploy'
      - 'back-release-api'
      - '--image=gcr.io/$PROJECT_ID/back-release-project:latest'
      - '--region=us-central1'
      - '--platform=managed'
      - '--allow-unauthenticated'
      - '--port=8080'
      - '--memory=1Gi'
      - '--min-instances=0'
      - '--max-instances=10'
      - '--set-secrets=MONGODB_URI=mongodb-uri:latest,GEMINI_API_KEY=gemini-api-key:latest'

images:
  - 'gcr.io/$PROJECT_ID/back-release-project:latest'
```

Then run:

```bash
gcloud builds submit --config cloudbuild.yaml
```

### 5. Verify Deployment

```bash
# Get service URL
gcloud run services describe back-release-api \
  --region us-central1 \
  --format 'value(status.url)'

# Test the API
curl https://YOUR-SERVICE-URL/docs
```

## Environment Variables Reference

The application uses the following environment variables:

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `MONGODB_URI` | Yes | MongoDB connection string | `mongodb+srv://user:pass@cluster.mongodb.net/db` |
| `GEMINI_API_KEY` | Yes | Google Gemini API key | `AIza...` |
| `JWT_SECRET` | Yes | Secret for JWT token signing | `your-secret-key` |
| `PORT` | No | Server port (Cloud Run sets this) | `8080` |
| `PYTHON_ENV` | No | Environment name | `production` |

## Monitoring and Logs

```bash
# View logs
gcloud run services logs read back-release-api \
  --region us-central1 \
  --limit 50

# Follow logs in real-time
gcloud run services logs tail back-release-api \
  --region us-central1

# View service details
gcloud run services describe back-release-api \
  --region us-central1
```

## Updating the Service

```bash
# After making code changes, rebuild and redeploy
docker build -t gcr.io/$PROJECT_ID/back-release-project:latest .
docker push gcr.io/$PROJECT_ID/back-release-project:latest

gcloud run deploy back-release-api \
  --image gcr.io/$PROJECT_ID/back-release-project:latest \
  --region us-central1
```

## Cost Optimization Tips

1. **Set minimum instances to 0** - Scales down when not in use
2. **Use appropriate memory/CPU** - Start with 1Gi/1 CPU, adjust as needed
3. **Set request timeout** - Default 300s is reasonable for AI operations
4. **Enable request concurrency** - Cloud Run default is 80 concurrent requests per instance

## Troubleshooting

### Container fails to start

```bash
# Check logs
gcloud run services logs read back-release-api --region us-central1 --limit 100

# Common issues:
# - Missing environment variables (check secrets)
# - MongoDB connection issues (verify MONGODB_URI)
# - Port mismatch (ensure PORT=8080)
```

### Secret access denied

```bash
# Verify Secret Manager permissions
gcloud secrets get-iam-policy mongodb-uri

# Grant access if needed
gcloud secrets add-iam-policy-binding mongodb-uri \
  --member=serviceAccount:PROJECT_NUMBER-compute@developer.gserviceaccount.com \
  --role=roles/secretmanager.secretAccessor
```

### Health check failures

The application should respond to HTTP requests on `/docs` and `/`. If health checks fail:

1. Check that uvicorn is binding to `0.0.0.0` (not `127.0.0.1`)
2. Verify PORT environment variable is set correctly
3. Check application logs for startup errors

## Additional Resources

- [Cloud Run Documentation](https://cloud.google.com/run/docs)
- [Cloud Run Pricing](https://cloud.google.com/run/pricing)
- [Secret Manager Documentation](https://cloud.google.com/secret-manager/docs)
- [Container Registry Documentation](https://cloud.google.com/container-registry/docs)

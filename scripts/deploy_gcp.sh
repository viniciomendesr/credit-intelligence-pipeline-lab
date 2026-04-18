#!/usr/bin/env bash
# Deploy manual no GCP Cloud Run.
# Rodar uma vez para setup inicial; depois o CI/CD (4.4) automatiza.
# Pré-requisito: gcloud CLI instalado + autenticado (gcloud auth login)

set -euo pipefail  # para imediatamente em qualquer erro

# ── Configuração — ajuste estes valores ──────────────────────────────────────
PROJECT_ID="credit-pipeline-demo"   # gcloud config get-value project
REGION="us-central1"
SERVICE="credit-api"
REPO="credit-api"                   # nome do repositório no Artifact Registry
# ─────────────────────────────────────────────────────────────────────────────

IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/${SERVICE}:latest"

echo "▶ Configurando projeto GCP: ${PROJECT_ID}"
gcloud config set project "${PROJECT_ID}"

echo "▶ Ativando APIs necessárias..."
gcloud services enable run.googleapis.com artifactregistry.googleapis.com

echo "▶ Criando repositório no Artifact Registry (idempotente)..."
gcloud artifacts repositories create "${REPO}" \
  --repository-format=docker \
  --location="${REGION}" \
  --quiet 2>/dev/null || echo "  (repositório já existe — ok)"

echo "▶ Configurando autenticação Docker..."
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

echo "▶ Build da imagem (linux/amd64 para Cloud Run)..."
docker buildx build --platform linux/amd64 -t "${IMAGE}" . --load

echo "▶ Push para o Artifact Registry..."
docker push "${IMAGE}"

echo "▶ Deploy no Cloud Run..."
gcloud run deploy "${SERVICE}" \
  --image "${IMAGE}" \
  --platform managed \
  --region "${REGION}" \
  --allow-unauthenticated \
  --port 8080 \
  --memory 512Mi \
  --quiet

echo ""
echo "✅ Deploy concluído. URL pública:"
gcloud run services describe "${SERVICE}" \
  --region "${REGION}" \
  --format "value(status.url)"

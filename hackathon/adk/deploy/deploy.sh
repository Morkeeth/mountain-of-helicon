#!/usr/bin/env bash
# Deploy measurement-bench agent + brief UI to Cloud Run (scale to zero).
# Requires: gcloud CLI, GOOGLE_CLOUD_PROJECT, Application Default Credentials.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

PROJECT="${GOOGLE_CLOUD_PROJECT:?set GOOGLE_CLOUD_PROJECT}"
REGION="${REGION:-us-central1}"
AGENT_SERVICE="${AGENT_SERVICE:-helicon-measurement-bench}"
BRIEF_SERVICE="${BRIEF_SERVICE:-helicon-brief}"
TOPIC="${PUBSUB_TOPIC:-helicon-measurement-trigger}"
AGENT_IMAGE="gcr.io/${PROJECT}/${AGENT_SERVICE}"
BRIEF_IMAGE="gcr.io/${PROJECT}/${BRIEF_SERVICE}"

echo "==> Project: ${PROJECT}  Region: ${REGION}"

echo "==> Enabling APIs..."
gcloud services enable \
  run.googleapis.com \
  firestore.googleapis.com \
  pubsub.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  --project="${PROJECT}"

echo "==> Firestore (native mode, create if missing)..."
if ! gcloud firestore databases describe --project="${PROJECT}" >/dev/null 2>&1; then
  gcloud firestore databases create \
    --project="${PROJECT}" \
    --location="${REGION}" \
    --type=firestore-native
fi

echo "==> Ensure demo DB exists locally (gitignored — seed before build)..."
if [[ ! -f "${REPO_ROOT}/hackathon/adk/demo/helicon.db" ]]; then
  python3 "${REPO_ROOT}/hackathon/adk/seed_demo_db.py"
fi

echo "==> Build + push agent image..."
gcloud builds submit "${REPO_ROOT}" \
  --project="${PROJECT}" \
  --config="${SCRIPT_DIR}/cloudbuild.agent.yaml" \
  --substitutions="_IMAGE=${AGENT_IMAGE}"

echo "==> Deploy agent (${AGENT_SERVICE})..."
gcloud run deploy "${AGENT_SERVICE}" \
  --project="${PROJECT}" \
  --image="${AGENT_IMAGE}" \
  --region="${REGION}" \
  --platform=managed \
  --allow-unauthenticated \
  --min-instances=0 \
  --max-instances=3 \
  --memory=512Mi \
  --timeout=300 \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=${PROJECT}"

AGENT_URL="$(gcloud run services describe "${AGENT_SERVICE}" \
  --project="${PROJECT}" \
  --region="${REGION}" \
  --format='value(status.url)')"

echo "==> Grant Firestore access to agent service account..."
AGENT_SA="$(gcloud run services describe "${AGENT_SERVICE}" \
  --project="${PROJECT}" \
  --region="${REGION}" \
  --format='value(spec.template.spec.serviceAccountName)')"
if [[ -z "${AGENT_SA}" || "${AGENT_SA}" == "null" ]]; then
  PROJECT_NUMBER="$(gcloud projects describe "${PROJECT}" --format='value(projectNumber)')"
  AGENT_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
fi
gcloud projects add-iam-policy-binding "${PROJECT}" \
  --member="serviceAccount:${AGENT_SA}" \
  --role="roles/datastore.user" \
  --condition=None \
  >/dev/null

echo "==> Pub/Sub topic (${TOPIC})..."
gcloud pubsub topics create "${TOPIC}" --project="${PROJECT}" 2>/dev/null || true

echo "==> Build + push brief image..."
gcloud builds submit "${REPO_ROOT}" \
  --project="${PROJECT}" \
  --config="${SCRIPT_DIR}/cloudbuild.brief.yaml" \
  --substitutions="_IMAGE=${BRIEF_IMAGE}"

echo "==> Deploy brief (${BRIEF_SERVICE})..."
gcloud run deploy "${BRIEF_SERVICE}" \
  --project="${PROJECT}" \
  --image="${BRIEF_IMAGE}" \
  --region="${REGION}" \
  --platform=managed \
  --allow-unauthenticated \
  --min-instances=0 \
  --max-instances=2 \
  --memory=256Mi \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=${PROJECT},AGENT_URL=${AGENT_URL}"

BRIEF_SA="$(gcloud run services describe "${BRIEF_SERVICE}" \
  --project="${PROJECT}" \
  --region="${REGION}" \
  --format='value(spec.template.spec.serviceAccountName)')"
if [[ -z "${BRIEF_SA}" || "${BRIEF_SA}" == "null" ]]; then
  PROJECT_NUMBER="$(gcloud projects describe "${PROJECT}" --format='value(projectNumber)')"
  BRIEF_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
fi
gcloud projects add-iam-policy-binding "${PROJECT}" \
  --member="serviceAccount:${BRIEF_SA}" \
  --role="roles/datastore.user" \
  --condition=None \
  >/dev/null

BRIEF_URL="$(gcloud run services describe "${BRIEF_SERVICE}" \
  --project="${PROJECT}" \
  --region="${REGION}" \
  --format='value(status.url)')"

echo ""
echo "Deploy complete."
echo "  Agent:  ${AGENT_URL}"
echo "  Brief:  ${BRIEF_URL}"
echo "  Topic:  projects/${PROJECT}/topics/${TOPIC}"
echo ""
echo "Trigger a run:"
echo "  bash ${SCRIPT_DIR}/trigger.sh"
echo ""
echo "Append these URLs to hackathon/adk/CLOUD-LOG.md for the demo video."

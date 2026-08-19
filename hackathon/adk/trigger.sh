#!/usr/bin/env bash
# Manual Pub/Sub / Cloud Run trigger (fill PROJECT after deploy).
set -euo pipefail
PROJECT="${GOOGLE_CLOUD_PROJECT:?set GOOGLE_CLOUD_PROJECT}"
REGION="${REGION:-us-central1}"
SERVICE="${SERVICE:-helicon-measurement-bench}"

echo "POST to Cloud Run service ${SERVICE} in ${PROJECT} (${REGION})"
echo "(Replace with gcloud run services describe URL + curl once deployed.)"
echo ""
echo "  gcloud run services describe ${SERVICE} --region ${REGION} --format='value(status.url)'"
echo "  curl -X POST \"\$(gcloud run services describe ${SERVICE} --region ${REGION} --format='value(status.url)')/run\""

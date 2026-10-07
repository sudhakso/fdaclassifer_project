#!/usr/bin/env bash
# Build the FDA predictor with Cloud Build, push to Artifact Registry, then
# optionally register/deploy it on Vertex AI.
#
# Typical Cloud Shell flow (matches trainer image pushes):
#   export PROJECT_ID=striped-sight-489713-a0
#   export REGION=asia-southeast1
#   export IMAGE_TAG=v1.4
#   export MODEL_ARTIFACT_URI=gs://fdaclassifier/registry/model-v1
#   ./deploy/vertex/deploy_predictor.sh
#
# That builds and pushes:
#   ${REGION}-docker.pkg.dev/${PROJECT_ID}/gke-finetune/dberta-finetuned:${IMAGE_TAG}
#
# Required env:
#   PROJECT_ID
#   MODEL_ARTIFACT_URI     gs://fdaclassifier/registry/model-v1
# Optional:
#   REGION                 Artifact Registry / Cloud Build region (default asia-southeast1)
#   VERTEX_REGION          Vertex AI region (default us-central1)
#   AR_REPO                Artifact Registry repo (default gke-finetune)
#   IMAGE_NAME             image name (default dberta-finetuned)
#   IMAGE_TAG              image tag (default v1.4)
#   PREDICTOR_IMAGE        full image URI override (skips REGION/AR_REPO/IMAGE_* assembly)
#   SKIP_DEPLOY            set to 1 to only build/push the image
#   ENDPOINT_NAME          default fda-classifier-endpoint
#   MODEL_DISPLAY_NAME     default deberta-fda-classifier
#   MACHINE_TYPE           default n1-standard-4
#   ACCELERATOR_TYPE       default nvidia-tesla-t4 (empty string to skip GPU)
#   ACCELERATOR_COUNT      default 1
#   MIN_REPLICA_COUNT      default 1
#   MAX_REPLICA_COUNT      default 2
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?set PROJECT_ID}"
MODEL_ARTIFACT_URI="${MODEL_ARTIFACT_URI:?set MODEL_ARTIFACT_URI}"
REGION="${REGION:-asia-southeast1}"
VERTEX_REGION="${VERTEX_REGION:-us-central1}"
AR_REPO="${AR_REPO:-gke-finetune}"
IMAGE_NAME="${IMAGE_NAME:-dberta-finetuned}"
IMAGE_TAG="${IMAGE_TAG:-v1.4}"
PREDICTOR_IMAGE="${PREDICTOR_IMAGE:-${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/${IMAGE_NAME}:${IMAGE_TAG}}"
SKIP_DEPLOY="${SKIP_DEPLOY:-0}"
ENDPOINT_NAME="${ENDPOINT_NAME:-fda-classifier-endpoint}"
MODEL_DISPLAY_NAME="${MODEL_DISPLAY_NAME:-deberta-fda-classifier}"
MACHINE_TYPE="${MACHINE_TYPE:-n1-standard-4}"
ACCELERATOR_TYPE="${ACCELERATOR_TYPE-nvidia-tesla-t4}"
ACCELERATOR_COUNT="${ACCELERATOR_COUNT:-1}"
MIN_REPLICA_COUNT="${MIN_REPLICA_COUNT:-1}"
MAX_REPLICA_COUNT="${MAX_REPLICA_COUNT:-2}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

echo "Building and pushing ${PREDICTOR_IMAGE} via Cloud Build"
gcloud builds submit \
  --project="${PROJECT_ID}" \
  --config=deploy/vertex/cloudbuild.yaml \
  --substitutions="_IMAGE=${PREDICTOR_IMAGE}" \
  .

echo "Image available at ${PREDICTOR_IMAGE}"

if [[ "${SKIP_DEPLOY}" == "1" ]]; then
  exit 0
fi

echo "Uploading Vertex Model ${MODEL_DISPLAY_NAME} in ${VERTEX_REGION}"
MODEL_ID="$(
  gcloud ai models upload \
    --project="${PROJECT_ID}" \
    --region="${VERTEX_REGION}" \
    --display-name="${MODEL_DISPLAY_NAME}" \
    --container-image-uri="${PREDICTOR_IMAGE}" \
    --artifact-uri="${MODEL_ARTIFACT_URI}" \
    --container-health-route=/health \
    --container-predict-route=/predict \
    --container-ports=8080 \
    --format='value(model)'
)"
echo "MODEL_ID=${MODEL_ID}"

ENDPOINT_ID="$(
  gcloud ai endpoints list \
    --project="${PROJECT_ID}" \
    --region="${VERTEX_REGION}" \
    --filter="displayName=${ENDPOINT_NAME}" \
    --format='value(name)' \
    | head -n1
)"
if [[ -z "${ENDPOINT_ID}" ]]; then
  ENDPOINT_ID="$(
    gcloud ai endpoints create \
      --project="${PROJECT_ID}" \
      --region="${VERTEX_REGION}" \
      --display-name="${ENDPOINT_NAME}" \
      --format='value(name)'
  )"
fi
echo "ENDPOINT_ID=${ENDPOINT_ID}"

DEPLOY_ARGS=(
  --project="${PROJECT_ID}"
  --region="${VERTEX_REGION}"
  --model="${MODEL_ID}"
  --display-name="${MODEL_DISPLAY_NAME}-deployment"
  --machine-type="${MACHINE_TYPE}"
  --min-replica-count="${MIN_REPLICA_COUNT}"
  --max-replica-count="${MAX_REPLICA_COUNT}"
  --traffic-split=0=100
)
if [[ -n "${ACCELERATOR_TYPE}" ]]; then
  DEPLOY_ARGS+=(
    --accelerator=type="${ACCELERATOR_TYPE}",count="${ACCELERATOR_COUNT}"
  )
fi

echo "Deploying model to endpoint"
gcloud ai endpoints deploy-model "${ENDPOINT_ID}" "${DEPLOY_ARGS[@]}"

cat <<EOF
Deployed.
  image:    ${PREDICTOR_IMAGE}
  model:    ${MODEL_ID}
  endpoint: ${ENDPOINT_ID}

Smoke predict:
  gcloud ai endpoints predict ${ENDPOINT_ID} \\
    --project=${PROJECT_ID} \\
    --region=${VERTEX_REGION} \\
    --json-request=deploy/vertex/sample_request.json
EOF

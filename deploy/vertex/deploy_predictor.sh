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
#   MODEL_ARTIFACT_URI     gs://fdaclassifier/registry/<RUN_ID>   (deploy only)
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
#
# List models deployed in VERTEX_REGION, or pick one to undeploy:
#   ./deploy/vertex/deploy_predictor.sh list
#   ./deploy/vertex/deploy_predictor.sh undeploy
set -euo pipefail

ACTION="${1:-deploy}"
PROJECT_ID="${PROJECT_ID:?set PROJECT_ID}"
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

# Print one TSV row per deployed model:
# endpoint_resource, endpoint_display, deployed_model_id, display_name, model_resource, deployed_at
list_deployed_rows() {
  gcloud ai endpoints list \
    --project="${PROJECT_ID}" \
    --region="${VERTEX_REGION}" \
    --format='json(name,displayName)' \
  | python3 -c '
import json, subprocess, sys
endpoints = json.load(sys.stdin)
for endpoint in endpoints:
    described = subprocess.check_output([
        "gcloud", "ai", "endpoints", "describe", endpoint["name"],
        "--project", "'"${PROJECT_ID}"'",
        "--region", "'"${VERTEX_REGION}"'",
        "--format", "json(deployedModels)",
    ], text=True)
    payload = json.loads(described)
    for deployed in payload.get("deployedModels") or []:
        created = deployed.get("createTime") or ""
        if created.endswith("Z"):
            created = created[:-1]
        created = created.replace("T", " ")[:16]
        print("\t".join([
            endpoint["name"],
            endpoint.get("displayName") or "",
            str(deployed.get("id") or ""),
            deployed.get("displayName") or "",
            deployed.get("model") or "",
            created,
        ]))
'
}

print_deployed_table() {
  local rows="$1"
  local index=0
  if [[ -z "${rows}" ]]; then
    echo "No deployed models in ${VERTEX_REGION}."
    return 1
  fi
  printf '%-4s %-18s %-28s %-22s %s\n' "#" "DEPLOYED" "ENDPOINT" "DEPLOYED MODEL" "MODEL"
  while IFS=$'\t' read -r endpoint_resource endpoint_display deployed_id display_name model_resource deployed_at; do
    index=$((index + 1))
    printf '%-4s %-18s %-28s %-22s %s\n' "${index}" "${deployed_at}" "${endpoint_display}" "${display_name}" "${model_resource}"
    printf '     endpoint=%s deployed_model_id=%s\n' "${endpoint_resource}" "${deployed_id}"
  done <<< "${rows}"
}

undeploy_chosen() {
  local rows index chosen endpoint_resource deployed_id model_resource
  local -a same_endpoint=() remaining=() split_parts=()
  rows="$(list_deployed_rows)"
  print_deployed_table "${rows}" || return 0
  read -r -p "Number to undeploy (empty cancels): " chosen
  if [[ -z "${chosen}" ]]; then
    echo "Cancelled."
    return 0
  fi
  if [[ ! "${chosen}" =~ ^[0-9]+$ ]]; then
    echo "Enter the row number from the list."
    return 1
  fi
  index=0
  while IFS=$'\t' read -r endpoint_resource _endpoint_display deployed_id _display_name model_resource _deployed_at; do
    index=$((index + 1))
    if [[ "${index}" == "${chosen}" ]]; then
      break
    fi
    endpoint_resource=""
  done <<< "${rows}"
  if [[ -z "${endpoint_resource}" ]]; then
    echo "No row ${chosen}."
    return 1
  fi
  while IFS=$'\t' read -r row_endpoint _row_display row_deployed _row_name _row_model _row_deployed_at; do
    if [[ "${row_endpoint}" == "${endpoint_resource}" ]]; then
      same_endpoint+=("${row_deployed}")
    fi
  done <<< "${rows}"
  for deployed in "${same_endpoint[@]}"; do
    if [[ "${deployed}" != "${deployed_id}" ]]; then
      remaining+=("${deployed}")
    fi
  done
  echo "Undeploying deployed_model_id=${deployed_id} from ${endpoint_resource}"
  local -a undeploy_args=(
    --project="${PROJECT_ID}"
    --region="${VERTEX_REGION}"
    --deployed-model-id="${deployed_id}"
    --quiet
  )
  if [[ "${#remaining[@]}" -gt 0 ]]; then
    local share=$((100 / ${#remaining[@]}))
    local used=0
    local last_index=$((${#remaining[@]} - 1))
    local i
    for i in "${!remaining[@]}"; do
      if [[ "${i}" -eq "${last_index}" ]]; then
        split_parts+=("${remaining[$i]}=$((100 - used))")
      else
        split_parts+=("${remaining[$i]}=${share}")
        used=$((used + share))
      fi
    done
    local joined
    joined="$(IFS=,; echo "${split_parts[*]}")"
    undeploy_args+=(--traffic-split="${joined}")
  fi
  gcloud ai endpoints undeploy-model "${endpoint_resource}" "${undeploy_args[@]}"
  echo "Undeployed ${deployed_id}."
  read -r -p "Also delete the Vertex model resource ${model_resource}? [y/N] " chosen
  if [[ "${chosen}" == "y" || "${chosen}" == "Y" ]]; then
    gcloud ai models delete "${model_resource}" \
      --project="${PROJECT_ID}" \
      --region="${VERTEX_REGION}" \
      --quiet
    echo "Deleted ${model_resource}."
  fi
}

case "${ACTION}" in
  list)
    print_deployed_table "$(list_deployed_rows)" || true
    exit 0
    ;;
  undeploy)
    undeploy_chosen
    exit 0
    ;;
  deploy)
    ;;
  *)
    echo "Usage: $0 [deploy|list|undeploy]" >&2
    exit 2
    ;;
esac

MODEL_ARTIFACT_URI="${MODEL_ARTIFACT_URI:?set MODEL_ARTIFACT_URI}"

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

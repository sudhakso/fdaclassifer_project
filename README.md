# FDA observation severity classifier

Fine-tunes `microsoft/deberta-v3-base` on labelled FDA 483 observations. The model has a classification head for **severity**, **primary_risk_tier**, and **cfr_reference**. Inference also returns **fmea_rationale**, the evidence for that classification. Training runs as a GKE Job on one GPU.

## Dataset

JSON export with one object per inspection under `records`. Each observation's model input is:

`[establishment_type] | Summary: [observation_summary] | Details: [full_details] | Citation: [act_cfr_number] — [short_description] — [long_description]`

`establishment_type` and `observation_summary` come from the inspection. `full_details` comes from the observation. The citation suffix is added only when that observation's `citation` object is present. `description` is not used when `full_details` is present.

Training reads the labelled file, one inspection per record and one or more observations under it:

```json
{
  "records": [
    {
      "establishment_type": "503B Outsourcing Facility",
      "observation_summary": "...",
      "observations": [
        {
          "full_details": "...",
          "severity": "Critical",
          "primary_risk_tier": "Tier 1 — Direct Patient Safety Risks",
          "cfr_reference": "211.192",
          "fmea_rationale": "Failure Mode: ... Cause: ... Impact: ...",
          "citation": {
            "act_cfr_number": "21 CFR 211.63",
            "short_description": "Equipment Design, Size and Location",
            "long_description": "..."
          }
        }
      ]
    }
  ]
}
```

`severity` must be Minor, Major, or Critical. A row also needs `primary_risk_tier`, `cfr_reference`, and `fmea_rationale`. The citation object is optional and is appended to the input text when present. Inference returns the three labels and `fmea_rationale` as the reason.

## Labeling

`data/sample_fda_483_observations.json` is a three-row fixture. The labeling set is built from the original FDA export. Observations without `full_details` are dropped. Citation-only rows are not imported.

```bash
python3 -m fda_classifier.labelstudio prepare \
  --input data/fda_inspection_dataset.json \
  --tasks data/labelstudio/tasks.json \
  --sample data/fda_prelabel_sample.json
```

`--limit 200` takes a round-robin sample across inspections. Omit it to export every narrative.

In Label Studio, create a project, set the labeling config to `labeling/label_config.xml`, and import `data/labelstudio/tasks.json`. Each task shows the training string (establishment, summary, details, and citation when present). The annotator picks Minor, Major, or Critical.

Export the finished project as JSON, then write the training file:

```bash
python3 -m fda_classifier.labelstudio apply \
  --export data/labelstudio/export.json \
  --output data/fda_labeled.json
```

`data/fda_labeled.json` is the records file with `severity` filled in. Point `train.py` at that path.

## Train locally

The container image supplies PyTorch. For a CPU smoke run, install the image dependencies plus a CPU torch build, then:

```bash
python3 train.py \
  --fda-data-path data/sample_fda_483_observations.json \
  --output-gcs-uri /tmp/fda-model \
  --epochs 1 \
  --batch-size 2 \
  --max-steps 1
```

`data/sample_fda_483_observations.json` has one row per class, so it only checks that the job starts. It is not a training set.

## Train on GKE

```bash
docker build -t litewave-fda-trainer:dev .
docker tag litewave-fda-trainer:dev "$TRAINER_IMAGE" && docker push "$TRAINER_IMAGE"

export RUN_ID=fda-$(date +%Y%m%d-%H%M%S)
export TRAINER_IMAGE=your-registry/litewave-fda-trainer:TAG
envsubst < deploy/k8s/fine-tune-job.yaml | kubectl apply -f -
kubectl logs -f "job/fda-train-${RUN_ID}" -n ml-workloads
```

The Job uses the same cluster contract as the Gemma4 trainer: namespace `ml-workloads`, service account `vijeta-finetuning-workload-sa`, L4 node pool, and the `ml-object-store` GCS FUSE volume mounted at `/gcs-mount`. Put the labelled JSON at `dataset/v1/fda_labelled_sample.json` in that bucket. The trainer writes the final model to `registry/model-v1/` on the same mount (`config.json`, weights, tokenizer, `training_summary.json`), not epoch checkpoints.

After the object prefix is in place, call the inference service `/reload` endpoint from outside this job. The training container does not send that webhook.

## Run inference on GKE

Put unlabeled observations at `evaluation/fda_observations.json` in the same bucket. `data/evaluation/fda_observations.json` is a three-observation sample in that shape. The Job reads the trained model from `registry/model-v1/` and writes `evaluation/predictions-${RUN_ID}.json`. Rebuild the trainer image first so it includes the batch scorer. The container entrypoint is still training; this Job overrides it.

```bash
export RUN_ID=fda-$(date +%Y%m%d-%H%M%S)
export TRAINER_IMAGE=your-registry/litewave-fda-trainer:TAG
envsubst < deploy/k8s/infer-job.yaml | kubectl apply -f -
kubectl logs -f "job/fda-infer-${RUN_ID}" -n ml-workloads
```

One L4 is enough. Scoring is one forward pass per batch of 16, then up to 128 greedy steps for the rationale. A few thousand observations finish in minutes. The 12–24Gi memory limit is enough for DeBERTa-v3-base; the 2Gi shared-memory volume counts against that limit.

## Vertex AI endpoint

Register the trained export under `gs://fdaclassifier/registry/model-v1/`, create an endpoint in `us-central1`, then deploy onto one T4 with autoscaling 1–2 replicas.

```bash
# 1. Upload/Register the model in us-central1
gcloud ai models upload \
  --region="us-central1" \
  --display-name="deberta-fda-classifier" \
  --container-image-uri="us-docker.pkg.dev/deeplearning-platform-release/gcr.io/huggingface-pytorch-inference-cu121.2-3.transformers.4-48.ubuntu2204.py311" \
  --artifact-uri="gs://fdaclassifier/registry/model-v1/"

# 2. Create the Endpoint in us-central1
gcloud ai endpoints create \
  --region="us-central1" \
  --display-name="fda-classifier-endpoint"

# 3. Deploy the Model to the Endpoint (replace with the new Model & Endpoint IDs from above)
gcloud ai endpoints deploy-model <NEW_ENDPOINT_ID> \
  --region="us-central1" \
  --model="<NEW_MODEL_ID>" \
  --display-name="deberta-fda-classifier-deployment" \
  --machine-type="n1-standard-4" \
  --accelerator="type=nvidia-tesla-t4,count=1" \
  --min-replica-count=1 \
  --max-replica-count=2
```

The Hugging Face inference image above does **not** load `heads.pt` or the evidence decoder, so predictions collapse. Use the custom predictor container instead. Build and push with Cloud Build the same way as the trainer image:

```bash
export PROJECT_ID=striped-sight-489713-a0
export REGION=asia-southeast1
export IMAGE_TAG=v1.4
export MODEL_ARTIFACT_URI=gs://fdaclassifier/registry/model-v1

# Build Dockerfile.predictor and push to Artifact Registry, then deploy to Vertex.
./deploy/vertex/deploy_predictor.sh

# Image-only (no Vertex upload/deploy):
# SKIP_DEPLOY=1 ./deploy/vertex/deploy_predictor.sh
```

That produces:

`asia-southeast1-docker.pkg.dev/striped-sight-489713-a0/gke-finetune/dberta-finetuned:v1.4`

Equivalent one-liner for the image push alone:

```bash
gcloud builds submit \
  --config=deploy/vertex/cloudbuild.yaml \
  --substitutions=_IMAGE=${REGION}-docker.pkg.dev/${PROJECT_ID}/gke-finetune/dberta-finetuned:${IMAGE_TAG} \
  .
```

Vertex model/endpoint steps in the script use `VERTEX_REGION` (default `us-central1`), separate from the Artifact Registry `REGION`.

## Scale

DeBERTa-v3-base is about 184M parameters. At batch 16 and sequence length 512 it uses well under an L4's 24 GB, so one GPU is the right size for a corpus up to a few hundred thousand observations (on the order of a few hours for four epochs). Dynamic padding is on, so short observations do not pay for a full 512-token batch.

Move off a single JSON download only if the file itself becomes multi-GB: shard to JSONL and stream it. A larger GPU does not help this model; it helps if you switch the base checkpoint to DeBERTa-v3-large.

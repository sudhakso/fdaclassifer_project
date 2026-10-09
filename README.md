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

Each label also comes with a confidence between 0 and 1 (`severity_confidence`, `primary_risk_tier_confidence`, `cfr_reference_confidence`), and severity with the probability of each class (`severity_probabilities`). Training fits one number per label on the held-out rows, saved as `temperatures` in `labels.json`, so that confidence matches how often the model is right on held-out FDA 483 text. It changes no label. A model saved without `temperatures` returns raw probabilities, which run high. Confidence has not been checked on text other than FDA 483 observations.

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

Build the image with Cloud Build from a checkout that holds only the code. Do not build from a
directory that contains a service account key or data files: `gcloud builds submit` uploads the
whole directory.

```bash
export PROJECT_ID=striped-sight-489713-a0
export REGION=asia-southeast1
export TRAINER_IMAGE=${REGION}-docker.pkg.dev/${PROJECT_ID}/gke-finetune/dberta-finetuned:TAG
gcloud builds submit --tag "$TRAINER_IMAGE" .

export RUN_ID=<RUN_ID of the relabel job>
export DATASET_PATH=runs/${RUN_ID}/data/train.json
export EVAL_PATH=runs/${RUN_ID}/data/val.json
envsubst < deploy/k8s/fine-tune-job.yaml | kubectl apply -f -
kubectl logs -f "job/fda-train-${RUN_ID}" -n ml-workloads -c trainer
```

The Job uses the same cluster contract as the Gemma4 trainer: namespace `ml-workloads`, service account `vijeta-finetuning-workload-sa`, L4 node pool, and the `fdaclassifier` bucket mounted at `/gcs-mount` through the `ml-object-store-fda-classifier` claim. `DATASET_PATH` is the labelled JSON's path inside that bucket. The trainer writes the final model to `registry/${RUN_ID}/` on the same mount (`config.json`, weights, tokenizer, `training_summary.json`), so each run keeps its own directory.

The GPU pool is Spot, and a node can be shut down in the middle of a run. To make a run resumable, add `--checkpoint-dir=/gcs-mount/checkpoints/${RUN_ID}` to the Job's `args`. The trainer then saves a checkpoint to the bucket after every epoch, and a restarted pod continues from the newest complete one. The directory is removed after a successful export. `backoffLimit` is 20 because every node shutdown counts as a failed pod.

After the object prefix is in place, call the inference service `/reload` endpoint from outside this job. The training container does not send that webhook.

### Training options

The defaults reproduce the original recipe. Add any of these to the Job's `args`:

| Flag | Default | What it does |
|---|---|---|
| `--epochs` | 4 | Maximum epochs. |
| `--eval-data-path` | none | Labelled file to evaluate on each epoch. Without it, 10% of the training rows are held out. |
| `--selection-metric` | `f1` | Picks the epoch to export: `f1` is severity macro F1, `combined` is its mean with tier and CFR accuracy. |
| `--early-stopping-patience` | 2 | Epochs without improvement before stopping. |
| `--warmup-ratio` | 0 | Share of steps spent warming up the learning rate. |
| `--severity-loss-weight` | 1 | Multiplier on the severity loss. |
| `--label-smoothing` | 0 | Leave at 0. With the severity class weights it pushes every example toward the rare class. |
| `--checkpoint-dir` | none | Where epoch checkpoints go, for resume. |
| `--base-model` | `microsoft/deberta-v3-base` | Any encoder `AutoModel` can load. `answerdotai/ModernBERT-large` has been run. |

The encoder is always loaded as float32. The hub checkpoint for DeBERTa-v3 is stored in float16, current transformers keeps that dtype, and AdamW on float16 weights produces NaN on the first step.

## Run inference on GKE

The Job reads a trained model from `registry/${MODEL_RUN_ID}/`, scores the observations in `INPUT_PATH`, and writes `evaluation/predictions-${RUN_ID}.json`. The input has the same shape as the training file, and labels in it are ignored. `data/evaluation/fda_observations.json` is a small sample in that shape. The container entrypoint is still training; this Job overrides it.

```bash
export RUN_ID=fda-infer-$(date +%Y%m%d-%H%M%S)
export MODEL_RUN_ID=<RUN_ID of the training job>
export INPUT_PATH=runs/${MODEL_RUN_ID}/data/test.json
envsubst < deploy/k8s/infer-job.yaml | kubectl apply -f -
kubectl logs -f "job/fda-infer-${RUN_ID}" -n ml-workloads -c infer
```

One L4 is enough. Scoring is one forward pass per batch of 16, then up to 128 greedy steps for the rationale. A few thousand observations finish in minutes. The 12 to 24Gi memory limit is enough for DeBERTa-v3-base; the 2Gi shared-memory volume counts against that limit.

## Relabelling and scoring

The first labelled set used free-text tiers and CFR references, which gave 108 tier strings and 397 CFR strings. The current labels follow `labeling/severity_rubric.md`: three severities, twelve risk categories, and a CFR section, for drug GMP (21 CFR 210/211) observations only. In the training file the risk category is stored in `primary_risk_tier`.

The scripts expect two inputs: the annotated inspection export, and the earlier labelled file, which carries the FDA citation attached to each observation.

```bash
# 1. Fix the set of observations and a train/test split by firm, and write blind batches to label.
python3 scripts/prepare_relabel_batches.py \
  --s3-dataset data/fda_483_dataset.json \
  --pro-labels data/fda_labelled_sample.json \
  --output-dir data/fda_relabel

# 2. Label each batch in data/fda_relabel/blind/ against the rubric and write
#    data/fda_relabel/labels/batch_NNN.json with one object per observation:
#    id, severity, risk_category, cfr_section, rule, borderline, in_scope, reason.

# 3. Write trainer-ready files for a label set.
python3 scripts/assemble_arm.py \
  --universe data/fda_relabel/universe.json \
  --arm opus --relabels-dir data/fda_relabel/labels \
  --drop-summary --val-ratio 0.1 \
  --output-dir data/fda_arms/opus_nosummary_val

# 4. After training and inference, score the predictions against every reference.
python3 scripts/score_predictions.py \
  --predictions predictions.json \
  --universe data/fda_relabel/universe.json \
  --cfr-classes data/fda_arms/opus_nosummary_val/cfr_classes.json \
  --relabels-dir data/fda_relabel/labels
```

`scripts/build_reference_sample.py` and `scripts/compare_reference_labels.py` draw a small stratified sample and measure how consistent a labeller is with itself and with the existing labels. Use them before relabelling everything.

The same steps run as a CPU Job. It reads the two source files from the bucket, writes blind batches and rubric labels under `/runs/${RUN_ID}/relabel/`, then writes `runs/${RUN_ID}/data/train.json`, `runs/${RUN_ID}/data/val.json`, and `runs/${RUN_ID}/data/test.json`. Rebuild the trainer image first so it includes `scripts/` and `labeling/`.

The Job labels with Claude Opus 5.5 (`--provider=anthropic`). Create a secret `anthropic-api-key` with key `api-key`. To label with Gemini, change the Job to `--provider=gemini` and create `gemini-api-key` the same way.

The Opus labelling is one self-contained file, `labeling/opus_labeler.py`. It needs only the `anthropic` package, `ANTHROPIC_API_KEY`, and the rubric next to it, so another pipeline can copy the `labeling/` folder and call it directly:

```bash
python3 labeling/opus_labeler.py --input observations.json --labels opus_labels.json
```

`--input` is a list of `{"id", "establishment_type", "full_details"}` or the inspection export. `--labels` is the label store:

- **Only new observations are sent.** Anything already in the store keeps its label. The store records the model and a hash of the rubric and refuses to mix in labels from a different one, so use a new file to relabel everything.
- **Restarts are safe.** Requests go through the Message Batches API and the batch id is saved in the store, so a restarted run waits on the same batch. Requests that fail or return invalid labels are sent again, and the run fails if any observation is still unlabelled after three rounds.
- **In the Job**, `LABEL_STORE` is the store file in the bucket, shared by every release.
- **The split does not move.** Firms listed in `labeling/firm_split.json` keep the train or test split used for the 2026-10-07 results. A firm not listed there is placed by a hash of its id, as are validation firms, so adding observations never moves an existing firm. Train rows whose narrative also appears in test are left out.

The relabel Job and the train Job both update `gs://fdaclassifier/runs/${RUN_ID}/manifest.json`. Relabel records the source files and the trainer JSON paths. Training adds the registry path and the eval metrics. Each job only replaces its own fields, so the file still holds both stages when training finishes. The image must include this manifest writer. The running trainer tag does not.

```bash
export INGEST=20261008
export RUN_ID=fda-${INGEST}-$(date +%H%M%S)
export TRAINER_IMAGE=asia-southeast1-docker.pkg.dev/<PROJECT>/gke-finetune/dberta-finetuned:TAG
export S3_DATASET=sources/s3/${INGEST}/fda_483_dataset.json
export PRO_LABELS=sources/pro/${INGEST}/fda_labelled_sample.json
export RELABEL_DIR=runs/${RUN_ID}/relabel
export OUTPUT_DIR=runs/${RUN_ID}/data
export LABEL_STORE=labels/${RUN_ID}_labels.json   # kept across releases

envsubst < deploy/k8s/relabel-job.yaml | kubectl apply -f -
kubectl logs -f "job/fda-relabel-${RUN_ID}  " -n ml-workloads
```

This Job does not request a GPU. A batch usually finishes within an hour and can take up to 24.

Results so far are in `docs/results/2026-10-07-experiments.md`.

## Synthetic batch record findings

FDA 483 observations describe a site. Findings from the review of one executed batch record read differently, so the classifier is also trained on synthetic findings of that kind. `labeling/batch_record_rubric.md` is the addendum to the rubric for them. The pipeline is in `synthetic/`:

```bash
# 1. Sample the facts of each finding. Severity is never part of the facts.
python synthetic/make_seeds.py --count 1500 --seed 11 --prefix f --output data/fda_synthetic/full/seeds.json         # fuller findings
python synthetic/make_sparse_seeds.py --count 820 --seed 31 --output data/fda_synthetic/sparse/seeds.json            # one field on one page
python synthetic/make_check_seeds.py --count 1500 --seed 97 --prefix k --output data/fda_synthetic/checks/seeds.json  # every entry that fails one check

# 2. A writer turns each seed into one finding in several wordings, following
#    writer_instructions.md, sparse_writer_instructions.md or check_writer_instructions.md,
#    and saves findings_*.json next to the seeds.

# 3. Two readers label every finding blind, on different wordings, following labeller_instructions.md.
python synthetic/make_read_batches.py data/fda_synthetic/full data/fda_synthetic/full 100 7
python synthetic/make_check_read_batches.py data/fda_synthetic/checks 100 113

# 4. Keep the findings both readers agree on and merge them into an FDA arm.
python synthetic/build_training_arm.py --fda-arm data/fda_arms/opus_nosummary_val \
    --train-findings data/fda_synthetic/full data/fda_synthetic/sparse data/fda_synthetic/checks \
    --test-findings data/fda_synthetic/trial_v6 --test-source data/fda_synthetic/trial \
    --holdout data/fda_synthetic/checks/holdout_seed_ids.json --output data/fda_arms/opus_plus_synthetic_v2

# 5. Score predictions on the held-out synthetic findings, by kind and wording.
python synthetic/score_synthetic_test.py data/fda_arms/opus_plus_synthetic_v2/synthetic_test.json name=predictions.json
```

All wordings of a finding share one label and one split. Real audit findings are never used for training. The counts and seed values above are examples.

## Decision model experiment

`experiments/decision_model/` fine-tunes a small LLM (Qwen 3.5 2B, LoRA, Unsloth `FastDecisionModel`) on the same data. The model reads the finding together with three questions (severity, risk category, CFR section) whose criteria are the rubric (`questions.py`), and returns a probability for every option. `train_decision.py` trains, calibrates and writes predictions in the shape of `fda_classifier.infer`; `serve.py` answers the same Vertex request contract as the classifier. It has its own image because Unsloth pins an older transformers:

```bash
docker build -t fda-decision:dev experiments/decision_model
docker build -t fda-decision-predictor:dev -f experiments/decision_model/Dockerfile.serve --build-arg BASE=fda-decision:dev experiments/decision_model
```

## Vertex AI endpoint

Register a trained export, for example `gs://fdaclassifier/registry/<RUN_ID>/`, create an endpoint in `us-central1`, then deploy onto one T4 with autoscaling 1 to 2 replicas.

```bash
# 1. Upload/Register the model in us-central1
gcloud ai models upload \
  --region="us-central1" \
  --display-name="deberta-fda-classifier" \
  --container-image-uri="us-docker.pkg.dev/deeplearning-platform-release/gcr.io/huggingface-pytorch-inference-cu121.2-3.transformers.4-48.ubuntu2204.py311" \
  --artifact-uri="gs://fdaclassifier/registry/<RUN_ID>/"

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
export MODEL_ARTIFACT_URI=gs://fdaclassifier/registry/<RUN_ID>

# Build Dockerfile.predictor and push to Artifact Registry, then deploy to Vertex.
./deploy/vertex/deploy_predictor.sh

# Image-only (no Vertex upload/deploy):
# SKIP_DEPLOY=1 ./deploy/vertex/deploy_predictor.sh

# List models deployed in VERTEX_REGION, then pick one to undeploy:
# ./deploy/vertex/deploy_predictor.sh list
# ./deploy/vertex/deploy_predictor.sh undeploy
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

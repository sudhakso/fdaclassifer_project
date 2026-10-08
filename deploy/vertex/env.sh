export PROJECT_ID=$(gcloud config get-value project)
export REGION="asia-southeast1"
export LOCATION="global"
export BUCKET_NAME="${PROJECT_ID}-fdaclassifier"
export ENDPOINT_ID="6350427318313287680"

#export INGEST=20261008 yyyymmdd
#export IMAGE_TAG=v2.1
#
export RUN_ID=fda-${INGEST}-$(date +%H%M%S)
export TRAINER_IMAGE=asia-southeast1-docker.pkg.dev/striped-sight-489713-a0/gke-finetune/dberta-finetuned:${IMAGE_TAG}
export S3_DATASET=sources/s3/${INGEST}/fda_483_dataset.json
export PRO_LABELS=sources/pro/${INGEST}/fda_labelled_sample.json
export RELABEL_DIR=runs/${RUN_ID}/relabel
export OUTPUT_DIR=runs/${RUN_ID}/data
export DATASET_PATH=runs/${RUN_ID}/data/train.json
export EVAL_PATH=runs/${RUN_ID}/data/val.json
# Decision-model experiment image. Separate from the main trainer image because Unsloth pins
# transformers <= 5.17 and brings its own torch build.
#
#   docker build -t fda-decision:dev experiments/decision_model
FROM pytorch/pytorch:2.6.0-cuda12.4-cudnn9-runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/tmp/hf \
    TOKENIZERS_PARALLELISM=false

RUN apt-get update && apt-get install -y --no-install-recommends git build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "unsloth==2026.10.3" "unsloth_zoo==2026.10.3"

WORKDIR /app
COPY questions.py train_decision.py ./

ENTRYPOINT ["python3", "train_decision.py"]

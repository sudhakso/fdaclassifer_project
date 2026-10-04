# GPU trainer image. The FDA JSON and the exported weights stay on GCS;
# this image is code and libraries only.
#
#   docker build -t litewave-fda-trainer:dev .
#   docker tag litewave-fda-trainer:dev $TRAINER_IMAGE && docker push $TRAINER_IMAGE

FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/tmp/training_cache/hf \
    TOKENIZERS_PARALLELISM=false \
    PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

COPY fda_classifier ./fda_classifier
COPY train.py .

RUN mkdir -p /tmp/training_cache

ENTRYPOINT ["python3", "train.py"]

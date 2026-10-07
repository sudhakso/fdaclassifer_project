"""Vertex AI custom-prediction FastAPI app.

Vertex injects ``AIP_HTTP_PORT``, ``AIP_HEALTH_ROUTE``, ``AIP_PREDICT_ROUTE``,
and ``AIP_STORAGE_URI``. The container listens on those routes and answers the
standard ``{"instances": [...]}`` / ``{"predictions": [...]}`` contract.

Unlike the stock Hugging Face inference image, this loads ``heads.pt`` and the
evidence decoder from the training export, so severity / tier / CFR / rationale
come from the fine-tuned multi-head model.
"""

from __future__ import annotations

import logging
import os
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from fda_classifier.data import instance_to_text
from fda_classifier.gcs import parse_gcs_uri
from fda_classifier.infer import load_model, predict_batch

logger = logging.getLogger(__name__)

DEFAULT_HEALTH_ROUTE = "/health"
DEFAULT_PREDICT_ROUTE = "/predict"
DEFAULT_PORT = "8080"


class Predictor:
    """Holds one loaded model for the process lifetime."""

    def __init__(self) -> None:
        self.model = None
        self.tokenizer = None
        self.labels: dict | None = None
        self.model_dir: str | None = None
        self.max_length = int(os.environ.get("MAX_LENGTH", "512"))
        self.batch_size = int(os.environ.get("BATCH_SIZE", "16"))

    @property
    def ready(self) -> bool:
        return self.model is not None and self.tokenizer is not None and self.labels is not None

    def load(self, model_dir: str | None = None) -> None:
        directory = resolve_model_dir(model_dir)
        logger.info("Loading model from %s", directory)
        required = ("labels.json", "heads.pt")
        missing = [name for name in required if not (Path(directory) / name).is_file()]
        if missing:
            raise FileNotFoundError(
                f"model dir {directory} is missing {missing}; "
                "the Vertex artifact URI must point at the training export"
            )
        self.model, self.tokenizer, self.labels = load_model(directory)
        self.model_dir = directory
        logger.info(
            "Model ready device=%s severity=%s tiers=%s cfr=%s",
            next(self.model.parameters()).device,
            len(self.labels["severity"]),
            len(self.labels["primary_risk_tier"]),
            len(self.labels["cfr_reference"]),
        )

    def predict_instances(self, instances: list[Any], parameters: dict | None = None) -> list[dict[str, str]]:
        if not self.ready:
            raise RuntimeError("model is not loaded")
        texts = [instance_to_text(instance) for instance in instances]
        params = parameters or {}
        max_length = int(params.get("max_length", self.max_length))
        batch_size = int(params.get("batch_size", self.batch_size))
        return predict_batch(
            texts,
            self.model,
            self.tokenizer,
            self.labels,
            max_length=max_length,
            batch_size=batch_size,
        )


def resolve_model_dir(model_dir: str | None = None) -> str:
    """Pick the model directory Vertex or the operator mounted for this process.

    Vertex sets ``AIP_STORAGE_URI`` to the mounted artifact path at runtime.
    Prefer that over the image default ``MODEL_DIR=/model`` used for local runs.
    """
    candidate = (
        model_dir
        or os.environ.get("AIP_STORAGE_URI")
        or os.environ.get("MODEL_DIR")
        or "/model"
    )
    if candidate.startswith("gs://"):
        return _stage_gcs_model(candidate)
    path = Path(candidate)
    if not path.is_dir():
        raise FileNotFoundError(f"model directory not found: {candidate}")
    return str(path)


def _stage_gcs_model(gcs_uri: str) -> str:
    """Download a model prefix from GCS into a local cache directory."""
    bucket_name, prefix = parse_gcs_uri(gcs_uri.rstrip("/"))
    local_dir = Path(os.environ.get("MODEL_CACHE_DIR", "/tmp/model"))
    if local_dir.exists():
        shutil.rmtree(local_dir)
    local_dir.mkdir(parents=True, exist_ok=True)

    from google.cloud import storage

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blobs = [blob for blob in bucket.list_blobs(prefix=prefix) if not blob.name.endswith("/")]
    if not blobs:
        raise FileNotFoundError(f"no objects under {gcs_uri}")
    for blob in blobs:
        relative = blob.name[len(prefix):].lstrip("/")
        if not relative:
            continue
        destination = local_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        blob.download_to_filename(destination)
        logger.info("Downloaded gs://%s/%s", bucket_name, blob.name)
    return str(local_dir)


def create_app(predictor: Predictor | None = None, load_on_startup: bool = True) -> FastAPI:
    state = predictor or Predictor()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if load_on_startup:
            state.load()
        yield

    app = FastAPI(title="FDA 483 predictor", version="1.0.0", lifespan=lifespan)
    app.state.predictor = state

    health_route = os.environ.get("AIP_HEALTH_ROUTE", DEFAULT_HEALTH_ROUTE)
    predict_route = os.environ.get("AIP_PREDICT_ROUTE", DEFAULT_PREDICT_ROUTE)

    @app.get(health_route)
    async def health():
        if not state.ready:
            return JSONResponse(status_code=503, content={"status": "not ready"})
        return {"status": "ok", "model_dir": state.model_dir}

    @app.get("/healthz")
    async def healthz():
        return await health()

    @app.get("/readyz")
    async def readyz():
        return await health()

    @app.post(predict_route)
    async def predict(request: Request):
        if not state.ready:
            return JSONResponse(status_code=503, content={"error": "model is not loaded"})
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(status_code=400, content={"error": "request body must be JSON"})
        if not isinstance(body, dict):
            return JSONResponse(status_code=400, content={"error": "request body must be an object"})
        instances = body.get("instances")
        if not isinstance(instances, list) or not instances:
            return JSONResponse(status_code=400, content={"error": "instances must be a non-empty list"})
        parameters = body.get("parameters")
        if parameters is not None and not isinstance(parameters, dict):
            return JSONResponse(status_code=400, content={"error": "parameters must be an object"})
        try:
            predictions = state.predict_instances(instances, parameters)
        except ValueError as exc:
            return JSONResponse(status_code=400, content={"error": str(exc)})
        except Exception:
            logger.exception("prediction failed")
            return JSONResponse(status_code=500, content={"error": "prediction failed"})
        return {"predictions": predictions}

    return app


app = create_app(load_on_startup=os.environ.get("LOAD_MODEL_ON_STARTUP", "1") not in {"0", "false", "False"})


def main() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("AIP_HTTP_PORT", os.environ.get("PORT", DEFAULT_PORT)))
    # One worker keeps a single GPU-resident model. Scale with Vertex replicas.
    uvicorn.run(app, host=host, port=port, workers=1, log_level="info")


if __name__ == "__main__":
    main()

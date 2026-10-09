"""Vertex AI prediction server for the decision model.

Same contract as fda_classifier/serving/app.py: POST {"instances": [{"establishment_type", "full_details"}]}
returns {"predictions": [{severity, primary_risk_tier, cfr_reference, the three *_confidence fields,
severity_probabilities}]}. The model directory is the training export (LoRA adapters, decision head and
questions.json); Vertex passes its location in AIP_STORAGE_URI.
"""
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from unsloth import FastDecisionModel  # isort: skip, must load before transformers
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
HEADS = ("severity", "primary_risk_tier", "cfr_reference")
state = {}


def model_dir() -> str:
    location = os.environ.get("AIP_STORAGE_URI") or os.environ.get("MODEL_DIR") or "/model"
    if not location.startswith("gs://"):
        return location
    from google.cloud import storage

    bucket_name, _, prefix = location[len("gs://"):].rstrip("/").partition("/")
    local = Path("/tmp/model")
    for blob in storage.Client().bucket(bucket_name).list_blobs(prefix=prefix):
        relative = blob.name[len(prefix):].lstrip("/")
        if relative and not blob.name.endswith("/"):
            (local / relative).parent.mkdir(parents=True, exist_ok=True)
            blob.download_to_filename(local / relative)
    return str(local)


@asynccontextmanager
async def lifespan(_: FastAPI):
    folder = model_dir()
    model, tokenizer = FastDecisionModel.from_pretrained(folder, load_in_4bit=True)
    FastDecisionModel.for_inference(model)
    state.update(model=model, tokenizer=tokenizer, questions=json.loads((Path(folder) / "questions.json").read_text(encoding="utf-8")))
    logger.info("decision model ready from %s", folder)
    yield


app = FastAPI(title="FDA decision model", lifespan=lifespan)


@app.get(os.environ.get("AIP_HEALTH_ROUTE", "/health"))
async def health():
    return {"status": "ok"} if state else JSONResponse(status_code=503, content={"status": "not ready"})


@app.post(os.environ.get("AIP_PREDICT_ROUTE", "/predict"))
async def predict(request: Request):
    body = await request.json()
    instances = body.get("instances") if isinstance(body, dict) else None
    if not isinstance(instances, list) or not instances:
        return JSONResponse(status_code=400, content={"error": "instances must be a non-empty list"})
    predictions = []
    for instance in instances:
        if isinstance(instance, str):
            instance = {"full_details": instance}
        details = instance.get("full_details") or instance.get("text")
        if not details:
            return JSONResponse(status_code=400, content={"error": "instance needs full_details or text"})
        text = f"Establishment type: {instance.get('establishment_type') or 'not stated'}\n\n{details}"
        answers = FastDecisionModel.predict(state["model"], state["tokenizer"], text, state["questions"])
        prediction = {"fmea_rationale": "not used"}
        for head in HEADS:
            prediction[head] = answers[head]["answer"]
            prediction[f"{head}_confidence"] = round(max(answers[head]["probabilities"].values()), 6)
        prediction["severity_probabilities"] = answers["severity"]["probabilities"]
        predictions.append(prediction)
    return {"predictions": predictions}


if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("AIP_HTTP_PORT", "8080")), workers=1)

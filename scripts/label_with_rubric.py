"""Score blind relabel batches with the written rubric.

Each blind batch is establishment type plus narrative only. The model must
return the closed label set in labeling/severity_rubric.md.

Two labellers:
  label_batches            Gemini, one call per blind batch. Completed batch
                           files are skipped, so a restarted Job continues.
  label_batches_anthropic  Claude through the Message Batches API. Only rows
                           with no label yet are sent, and the batch id is
                           saved so a restarted Job waits on the same batch.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

CATEGORIES = (
    "contamination and mix-ups",
    "quality control failure",
    "critical process parameter deviation",
    "process not followed",
    "personnel hygiene",
    "equipment and environment hygiene",
    "document control and traceability",
    "inadequate investigation and capa",
    "labeling and packaging",
    "stability and storage",
    "supplier and raw material quality",
    "electronic data integrity",
)
SEVERITIES = ("Minor", "Major", "Critical")
_CATEGORY_KEYS = {name.lower(): name for name in CATEGORIES}
INSTRUCTIONS = (
    "You label FDA Form 483 observations. Follow the rubric exactly. "
    "Return JSON {\"labels\": [...]} with one object per input row, same ids, in the same order. "
    "severity is Minor, Major, or Critical. risk_category is one of the rubric category names. "
    "cfr_section is one section such as 211.113, with no paragraph letters. "
    "Also set rule, borderline, in_scope, and a one-sentence reason.\n\n"
)
LABEL_SET_FILE = "label_set.json"
_LABEL_FIELDS = {
    "id": {"type": "string"},
    "severity": {"type": "string", "enum": list(SEVERITIES)},
    "risk_category": {"type": "string", "enum": list(CATEGORIES)},
    "cfr_section": {"type": "string"},
    "rule": {"type": "string"},
    "borderline": {"type": "boolean"},
    "in_scope": {"type": "boolean"},
    "reason": {"type": "string"},
}
LABELS_SCHEMA = {
    "type": "object",
    "properties": {
        "labels": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": _LABEL_FIELDS,
                "required": list(_LABEL_FIELDS),
                "additionalProperties": False,
            },
        },
    },
    "required": ["labels"],
    "additionalProperties": False,
}


def normalize_label(raw: dict, expected_id: str) -> dict:
    """Coerce one model object onto the rubric's closed sets."""
    severity = str(raw.get("severity") or "").strip().capitalize()
    if severity not in SEVERITIES:
        raise ValueError(f"{expected_id}: severity {severity!r} is not one of {SEVERITIES}")
    category_key = str(raw.get("risk_category") or "").strip().lower()
    category = _CATEGORY_KEYS.get(category_key)
    if category is None:
        raise ValueError(f"{expected_id}: risk_category {raw.get('risk_category')!r} is not in the rubric")
    section = str(raw.get("cfr_section") or "").strip().lstrip("§")
    return {
        "id": expected_id,
        "severity": severity,
        "risk_category": category,
        "cfr_section": section,
        "rule": str(raw.get("rule") or "").strip(),
        "borderline": bool(raw.get("borderline")),
        "in_scope": bool(raw.get("in_scope", True)),
        "reason": str(raw.get("reason") or "").strip(),
    }


def batch_is_complete(blind_path: Path, labels_path: Path) -> bool:
    if not labels_path.is_file():
        return False
    blind = json.loads(blind_path.read_text(encoding="utf-8"))
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    return {row["id"] for row in labels} == {row["id"] for row in blind}


def label_batches(
    blind_dir: Path,
    labels_dir: Path,
    rubric_path: Path,
    model: str,
    api_key: str | None = None,
    pause_seconds: float = 1.0,
) -> int:
    from google import genai
    from google.genai import types

    rubric = rubric_path.read_text(encoding="utf-8")
    client = genai.Client(api_key=api_key or os.environ.get("GEMINI_API_KEY"))
    config = types.GenerateContentConfig(
        system_instruction=INSTRUCTIONS + rubric,
        temperature=0.1,
        response_mime_type="application/json",
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    labels_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    batches = sorted(blind_dir.glob("batch_*.json"))
    for index, blind_path in enumerate(batches, start=1):
        labels_path = labels_dir / blind_path.name
        if batch_is_complete(blind_path, labels_path):
            print(f"skip {blind_path.name} (already labelled)")
            continue
        blind = json.loads(blind_path.read_text(encoding="utf-8"))
        print(f"labelling {blind_path.name} ({index}/{len(batches)}, {len(blind)} observations)")
        response = client.models.generate_content(
            model=model,
            contents=json.dumps(blind, ensure_ascii=False),
            config=config,
        )
        payload = json.loads(response.text)
        raw_rows = payload["labels"] if isinstance(payload, dict) else payload
        by_id = {str(row.get("id")): row for row in raw_rows}
        missing = [row["id"] for row in blind if row["id"] not in by_id]
        if missing:
            raise SystemExit(f"{blind_path.name} response missed ids: {missing[:5]}")
        labels = [normalize_label(by_id[row["id"]], row["id"]) for row in blind]
        temporary = labels_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(labels, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(labels_path)
        written += 1
        if pause_seconds and index < len(batches):
            time.sleep(pause_seconds)
    return written


def _read_labels(labels_dir: Path) -> dict[str, dict]:
    labels: dict[str, dict] = {}
    for path in sorted(labels_dir.glob("batch_*.json")):
        for row in json.loads(path.read_text(encoding="utf-8")):
            labels[row["id"]] = row
    return labels


def _read_label_set(labels_dir: Path) -> dict | None:
    path = labels_dir / LABEL_SET_FILE
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def label_batches_anthropic(
    blind_dir: Path,
    labels_dir: Path,
    rubric_path: Path,
    model: str = "claude-opus-5-5",
    reuse_dir: Path | None = None,
    rows_per_request: int = 20,
    poll_seconds: float = 60.0,
    max_rounds: int = 3,
) -> int:
    """Label every blind row that has no label yet. Returns the number of rows newly labelled.

    A label set is one model plus one rubric text, recorded in label_set.json
    next to the labels. Labels from ``reuse_dir`` (an earlier release) are
    carried over only when its label set matches, so unchanged observations
    keep their labels and a changed rubric relabels everything. Rows that come
    back failed, refused, or invalid are sent again, up to ``max_rounds``.
    """
    import anthropic

    rubric = rubric_path.read_text(encoding="utf-8")
    identity = {"model": model, "rubric_sha256": hashlib.sha256(rubric.encode("utf-8")).hexdigest()}
    labels_dir.mkdir(parents=True, exist_ok=True)
    state = _read_label_set(labels_dir)
    known = _read_labels(labels_dir)
    if state is None and known:
        raise SystemExit(f"{labels_dir} holds labels but no {LABEL_SET_FILE}, so their model and rubric are unknown. Use an empty work directory.")
    if state is not None and {key: state.get(key) for key in identity} != identity:
        raise SystemExit(f"{labels_dir} was labelled with a different model or rubric. Use a new work directory.")
    state = state or dict(identity)

    if reuse_dir is not None:
        previous = _read_label_set(reuse_dir)
        if previous is not None and {key: previous.get(key) for key in identity} == identity:
            known = {**_read_labels(reuse_dir), **known}
            print(f"reusing labels from {reuse_dir}")
        else:
            print(f"not reusing {reuse_dir}: no {LABEL_SET_FILE} there, or a different model or rubric")

    blind = {path.name: json.loads(path.read_text(encoding="utf-8")) for path in sorted(blind_dir.glob("batch_*.json"))}
    rows = [row for batch in blind.values() for row in batch]
    wanted = {row["id"] for row in rows}
    already = len(wanted & set(known))
    print(f"{len(rows)} observations, {already} already labelled")

    def save() -> None:
        for name, batch in blind.items():
            labels = [known[row["id"]] for row in batch if row["id"] in known]
            temporary = labels_dir / f"{name}.tmp"
            temporary.write_text(json.dumps(labels, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            temporary.replace(labels_dir / name)
        (labels_dir / LABEL_SET_FILE).write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    client = anthropic.Anthropic()
    system = [{"type": "text", "text": INSTRUCTIONS + rubric, "cache_control": {"type": "ephemeral"}}]
    for _ in range(max_rounds):
        if not state.get("message_batch_id"):
            pending = [row for row in rows if row["id"] not in known]
            if not pending:
                break
            chunks = [pending[start:start + rows_per_request] for start in range(0, len(pending), rows_per_request)]
            batch = client.messages.batches.create(requests=[
                {
                    "custom_id": f"rows-{index:05d}",
                    "params": {
                        "model": model,
                        "max_tokens": 16000,
                        "system": system,
                        "messages": [{"role": "user", "content": json.dumps(chunk, ensure_ascii=False)}],
                        "output_config": {"format": {"type": "json_schema", "schema": LABELS_SCHEMA}},
                    },
                }
                for index, chunk in enumerate(chunks)
            ])
            state["message_batch_id"] = batch.id
            save()
            print(f"submitted batch {batch.id}: {len(pending)} observations in {len(chunks)} requests")

        batch_id = state["message_batch_id"]
        while (batch := client.messages.batches.retrieve(batch_id)).processing_status != "ended":
            print(f"batch {batch_id}: {batch.request_counts.processing} requests still processing")
            time.sleep(poll_seconds)
        for result in client.messages.batches.results(batch_id):
            if result.result.type != "succeeded":
                print(f"{result.custom_id}: {result.result.type}, will resend")
                continue
            message = result.result.message
            if message.stop_reason != "end_turn":
                print(f"{result.custom_id}: stopped with {message.stop_reason}, will resend")
                continue
            payload = json.loads(next(block.text for block in message.content if block.type == "text"))
            for raw in payload["labels"]:
                row_id = str(raw.get("id"))
                if row_id not in wanted:
                    continue
                try:
                    known[row_id] = normalize_label(raw, row_id)
                except ValueError as error:
                    print(f"rejected: {error}")
        state["message_batch_id"] = None
        save()

    save()
    missing = sorted(wanted - set(known))
    if missing:
        raise SystemExit(f"{len(missing)} observations still have no label after {max_rounds} rounds, for example {missing[:5]}")
    return len(wanted) - already

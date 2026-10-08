"""Label FDA 483 observations with Claude Opus and the written rubric.

Self-contained. It needs the ``anthropic`` package, ANTHROPIC_API_KEY, and
severity_rubric.md (read from next to this file unless --rubric is given).

Command line:

    python labeling/opus_labeler.py --input observations.json --labels opus_labels.json

From Python:

    from opus_labeler import label_observations, load_observations
    labels = label_observations(load_observations("observations.json"), "opus_labels.json")

Input is a list of {"id", "establishment_type", "full_details"}, or the
inspection export {"records": [{"record_id", "establishment_type",
"observations": [{"observation_number", "full_details"}]}]}, where the id
becomes "<record_id>-<observation_number>".

The labels file is the label store. Run this again with more observations and
only the ones that are not in the store are sent, so existing labels never
change. The store records the model and a hash of the rubric, and refuses to
mix labels made with a different model or rubric: use a new labels file to
relabel everything.

Requests go through the Message Batches API. The batch id is saved in the
store, so a restarted run waits on the same batch instead of paying twice.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_RUBRIC = Path(__file__).resolve().parent / "severity_rubric.md"
SEVERITIES = ("Minor", "Major", "Critical")
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
INSTRUCTIONS = (
    "You label FDA Form 483 observations. Follow the rubric exactly. "
    "Return one label per input row, with the same ids, in the same order. "
    "cfr_section is one section such as 211.113, with no paragraph letters. "
    "reason is one sentence.\n\n"
)
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
_SCHEMA = {
    "type": "object",
    "properties": {
        "labels": {
            "type": "array",
            "items": {"type": "object", "properties": _LABEL_FIELDS, "required": list(_LABEL_FIELDS), "additionalProperties": False},
        },
    },
    "required": ["labels"],
    "additionalProperties": False,
}


def load_observations(path: str | Path) -> list[dict]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    return [
        {
            "id": f"{record['record_id']}-{observation['observation_number']}",
            "establishment_type": record.get("establishment_type") or "",
            "full_details": observation["full_details"],
        }
        for record in payload["records"]
        for observation in record.get("observations") or []
    ]


def _clean(raw: dict) -> dict:
    severity = str(raw.get("severity") or "").strip().capitalize()
    category = str(raw.get("risk_category") or "").strip().lower()
    if severity not in SEVERITIES or category not in CATEGORIES:
        raise ValueError(f"{raw.get('id')}: severity {severity!r} or category {category!r} is not in the rubric")
    return {
        "id": str(raw["id"]),
        "severity": severity,
        "risk_category": category,
        "cfr_section": str(raw.get("cfr_section") or "").strip().lstrip("§"),
        "rule": str(raw.get("rule") or "").strip(),
        "borderline": bool(raw.get("borderline")),
        "in_scope": bool(raw.get("in_scope", True)),
        "reason": str(raw.get("reason") or "").strip(),
    }


def label_observations(
    observations: list[dict],
    labels_path: str | Path,
    rubric_path: str | Path = DEFAULT_RUBRIC,
    model: str = DEFAULT_MODEL,
    rows_per_request: int = 20,
    poll_seconds: float = 60.0,
    max_rounds: int = 3,
) -> list[dict]:
    """Return one label per observation, in input order, labelling only what the store lacks.

    Requests that fail, are refused, or return labels outside the rubric are
    sent again, up to ``max_rounds``. Raises SystemExit if any observation is
    still unlabelled after that.
    """
    import anthropic

    labels_path = Path(labels_path)
    rubric = Path(rubric_path).read_text(encoding="utf-8")
    identity = {"model": model, "rubric_sha256": hashlib.sha256(rubric.encode("utf-8")).hexdigest()}
    store = json.loads(labels_path.read_text(encoding="utf-8")) if labels_path.is_file() else {**identity, "labels": []}
    if {key: store.get(key) for key in identity} != identity:
        raise SystemExit(f"{labels_path} was labelled with a different model or rubric. Use a new labels file to relabel everything.")
    known = {label["id"]: label for label in store["labels"]}
    rows = [{"id": str(row["id"]), "establishment_type": row.get("establishment_type") or "", "full_details": row["full_details"]} for row in observations]
    wanted = {row["id"] for row in rows}
    print(f"{len(rows)} observations, {len(wanted & set(known))} already labelled")

    def save() -> None:
        store["labels"] = list(known.values())
        labels_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = labels_path.with_name(labels_path.name + ".tmp")
        temporary.write_text(json.dumps(store, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        temporary.replace(labels_path)

    client = anthropic.Anthropic()
    system = [{"type": "text", "text": INSTRUCTIONS + rubric, "cache_control": {"type": "ephemeral"}}]
    for _ in range(max_rounds):
        if not store.get("message_batch_id"):
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
                        "output_config": {"format": {"type": "json_schema", "schema": _SCHEMA}},
                    },
                }
                for index, chunk in enumerate(chunks)
            ])
            store["message_batch_id"] = batch.id
            save()
            print(f"submitted batch {batch.id}: {len(pending)} observations in {len(chunks)} requests")

        batch_id = store["message_batch_id"]
        while (batch := client.messages.batches.retrieve(batch_id)).processing_status != "ended":
            print(f"batch {batch_id}: {batch.request_counts.processing} requests still processing")
            time.sleep(poll_seconds)
        for result in client.messages.batches.results(batch_id):
            if result.result.type != "succeeded" or result.result.message.stop_reason != "end_turn":
                print(f"{result.custom_id}: not completed, will resend")
                continue
            text = next(block.text for block in result.result.message.content if block.type == "text")
            for raw in json.loads(text)["labels"]:
                try:
                    label = _clean(raw)
                except (KeyError, ValueError) as error:
                    print(f"rejected: {error}")
                    continue
                if label["id"] in wanted:
                    known[label["id"]] = label
        store["message_batch_id"] = None
        save()

    missing = sorted(wanted - set(known))
    if missing:
        raise SystemExit(f"{len(missing)} observations still have no label after {max_rounds} rounds, for example {missing[:5]}")
    return [known[row["id"]] for row in rows]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", required=True, type=Path, help="Observations to label")
    parser.add_argument("--labels", required=True, type=Path, help="Label store, created if missing and updated in place")
    parser.add_argument("--rubric", type=Path, default=DEFAULT_RUBRIC)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--rows-per-request", type=int, default=20)
    args = parser.parse_args()
    labels = label_observations(load_observations(args.input), args.labels, args.rubric, args.model, args.rows_per_request)
    print(f"{len(labels)} labels in {args.labels}")


if __name__ == "__main__":
    main()

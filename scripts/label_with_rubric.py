"""Score blind relabel batches with the written rubric.

Each blind batch is establishment type plus narrative only. The model must
return the closed label set in labeling/severity_rubric.md. Completed batch
files are skipped, so a restarted Job continues.
"""

from __future__ import annotations

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
        system_instruction=(
            "You label FDA Form 483 observations. Follow the rubric exactly. "
            "Return JSON {\"labels\": [...]} with one object per input row, same ids, in the same order. "
            "severity is Minor, Major, or Critical. risk_category is one of the rubric category names. "
            "cfr_section is one section such as 211.113, with no paragraph letters. "
            "Also set rule, borderline, in_scope, and a one-sentence reason.\n\n"
            + rubric
        ),
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

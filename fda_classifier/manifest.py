"""Merge fields into a run manifest without dropping what the other job wrote."""

from __future__ import annotations

import json
from pathlib import Path


def update_manifest(path: str | Path, updates: dict) -> None:
    """Create or update a JSON object. Keys in ``updates`` replace existing keys."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    current: dict = {}
    if destination.is_file():
        current = json.loads(destination.read_text(encoding="utf-8"))
        if not isinstance(current, dict):
            raise ValueError(f"{destination} is not a JSON object")
    current.update(updates)
    temporary = destination.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
    temporary.replace(destination)

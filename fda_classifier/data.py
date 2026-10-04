"""Flatten nested FDA 483 JSON into labeled observation texts."""

from __future__ import annotations

import random
import re
from collections import Counter, defaultdict

from fda_classifier import LABELS

LABEL2ID = {label: index for index, label in enumerate(LABELS)}
ID2LABEL = {index: label for label, index in LABEL2ID.items()}

# full_details is the observation narrative. Older fixtures may only have a short text field.
_DETAIL_KEYS = ("full_details", "observation_text", "text", "observation", "description")
_LABEL_KEYS = ("severity", "label")
_CHILD_KEYS = ("records", "inspections", "observations", "observation", "items", "result")


def normalize_label(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip().lower()
    for label in LABELS:
        if cleaned == label.lower():
            return label
    return None


def flatten_observations(payload: object) -> tuple[list[dict[str, str]], int]:
    """Return (examples, skipped_unlabeled).

    Accepts a list of observations, ``{"observations": [...]}``,
    ``{"inspections": [{"observations": [...]}]}``, or the inspection export
    ``{"records": [{"observations": [...]}]}``. Each example's text is

    ``{establishment_type} | Summary: {observation_summary} | Details: {full_details}``

    with establishment type and the inspection summary taken from the parent record.
    When the observation has a ``citation`` object, the CFR number and its
    short and long descriptions are appended as `` | Citation: ...``.
    """
    examples: list[dict[str, str]] = []
    skipped = 0

    def visit(node: object, parent: dict) -> None:
        nonlocal skipped
        if isinstance(node, list):
            for item in node:
                visit(item, parent)
            return
        if not isinstance(node, dict):
            return

        children: list[object] = []
        for key in _CHILD_KEYS:
            child = node.get(key)
            if isinstance(child, list):
                children.extend(child)
        if children:
            context = {**parent, **_context(node)}
            for child in children:
                visit(child, context)
            return

        details = _first(node, _DETAIL_KEYS)
        label = normalize_label(_first(node, _LABEL_KEYS))
        if not details:
            return
        if label is None:
            skipped += 1
            return
        examples.append({"text": build_input_text(node, parent, str(details)), "label": label})

    visit(payload, {})
    return examples, skipped


def stratified_split(
    examples: list[dict[str, str]],
    eval_ratio: float,
    seed: int,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Hold out ``eval_ratio`` of each class, keeping at least one train row."""
    if not 0.0 <= eval_ratio < 1.0:
        raise ValueError("eval_ratio must be in [0, 1)")

    by_label: dict[str, list[dict[str, str]]] = defaultdict(list)
    for example in examples:
        by_label[example["label"]].append(example)

    rng = random.Random(seed)
    train: list[dict[str, str]] = []
    evaluation: list[dict[str, str]] = []
    for rows in by_label.values():
        shuffled = rows[:]
        rng.shuffle(shuffled)
        if len(shuffled) < 2 or eval_ratio <= 0:
            train.extend(shuffled)
            continue
        holdout = min(len(shuffled) - 1, max(1, int(round(len(shuffled) * eval_ratio))))
        evaluation.extend(shuffled[:holdout])
        train.extend(shuffled[holdout:])

    rng.shuffle(train)
    rng.shuffle(evaluation)
    return train, evaluation


# Gemini writes the same tier with small wording differences. Collapse those
# before the tier head sees them.
_TIER_ALIASES = {
    "tier 1 - patient safety risks": "Tier 1 — Direct Patient Safety Risks",
    "tier 1 - direct patient safety risks": "Tier 1 — Direct Patient Safety Risks",
    "tier 1 - patient safety due to contamination & mixing": "Tier 1 — Patient safety due to contamination & mixing",
    "tier 1 - quality control failures": "Tier 1 — Quality control failures",
    "tier 2 - critical process risks": "Tier 2 — Critical Process Risks",
    "tier 3 - hygiene & environment": "Tier 3 — Hygiene & Environment",
    "tier 3 - personnel hygiene": "Tier 3 — Personnel hygiene",
    "tier 3 - equipment & environment hygiene": "Tier 3 — Equipment & environment hygiene",
    "tier 4 - documentation & compliance": "Tier 4 — Documentation & Compliance",
    "tier 4 - detected issues closed without proper closure/prevention": (
        "Tier 4 — Detected issues closed without proper closure/prevention"
    ),
    "additional fda-relevant risks": "Additional FDA-Relevant Risks",
    "additional fda-relevant risks - labeling & packaging errors": (
        "Additional FDA-Relevant Risks - Labeling & packaging errors"
    ),
    "additional fda-relevant risks - stability & storage failures": (
        "Additional FDA-Relevant Risks - Stability & storage failures"
    ),
    "additional fda-relevant risks - supplier/raw material quality lapses": (
        "Additional FDA-Relevant Risks - Supplier/raw material quality lapses"
    ),
    "additional fda-relevant risks - electronic data integrity risks": (
        "Additional FDA-Relevant Risks - Electronic data integrity risks"
    ),
    "additional tier - supplier/raw material quality lapses": (
        "Additional FDA-Relevant Risks - Supplier/raw material quality lapses"
    ),
    "additional tier - supplier quality lapses": (
        "Additional FDA-Relevant Risks - Supplier/raw material quality lapses"
    ),
    "additional tier - electronic data integrity risks": (
        "Additional FDA-Relevant Risks - Electronic data integrity risks"
    ),
    "additional tier - stability & storage failures": (
        "Additional FDA-Relevant Risks - Stability & storage failures"
    ),
    "additional tier - labeling & packaging errors": (
        "Additional FDA-Relevant Risks - Labeling & packaging errors"
    ),
}

_CFR_PART = re.compile(r"part\s+(\d+)", re.IGNORECASE)
_CFR_SECTION = re.compile(r"(\d{3}\.\d+(?:\([a-z0-9]+\))?)", re.IGNORECASE)


def normalize_tier(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    key = value.strip().lower().replace("—", "-").replace("–", "-")
    key = re.sub(r"\s+", " ", key)
    return _TIER_ALIASES.get(key, value.strip())


def normalize_cfr(value: object) -> str | None:
    """Collapse '21 CFR §211.192' and 'CFR §211.192' onto '211.192'."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.replace("§", " ")
    found: list[str] = []
    for match in re.finditer(r"part\s+\d+|\d{3}\.\d+(?:\([a-z0-9]+\))?", text, flags=re.IGNORECASE):
        token = match.group(0)
        part = _CFR_PART.fullmatch(token)
        if part:
            canon = f"Part {part.group(1)}"
        else:
            canon = _CFR_SECTION.fullmatch(token).group(1)
        if canon not in found:
            found.append(canon)
    if not found:
        return value.strip()
    return " / ".join(found)


def load_inference_rows(payload: object) -> list[dict]:
    """Read unlabeled observations in the same shape as the training file.

    Labels are ignored. Each row keeps the identifiers needed to join the
    prediction back to the source observation, plus the encoder text.
    """
    rows: list[dict] = []
    for record, observation in _iter_labelled_rows(payload):
        details = _first(observation, _DETAIL_KEYS)
        if not details:
            continue
        rows.append({
            "record_id": record.get("record_id"),
            "fei_number": record.get("fei_number"),
            "firm_name": record.get("firm_name"),
            "observation_number": observation.get("observation_number"),
            "text": build_input_text(observation, record, str(details)),
        })
    return rows


def load_training_examples(payload: object) -> tuple[list[dict[str, str]], int]:
    """Read the labelled inspection file into one example per observation.

    Each example keeps the encoder text plus the three classification targets
    (severity, primary_risk_tier, cfr_reference) and the FMEA rationale the
    model must give as evidence at inference. Rows missing any of those are skipped.
    """
    examples: list[dict[str, str]] = []
    skipped = 0
    for record, observation in _iter_labelled_rows(payload):
        details = _first(observation, _DETAIL_KEYS)
        severity = normalize_label(_first(observation, _LABEL_KEYS))
        tier = normalize_tier(observation.get("primary_risk_tier"))
        cfr = normalize_cfr(observation.get("cfr_reference"))
        rationale = observation.get("fmea_rationale")
        rationale = rationale.strip() if isinstance(rationale, str) else ""
        if not details or severity is None or tier is None or cfr is None or not rationale:
            skipped += 1
            continue
        examples.append({
            "text": build_input_text(observation, record, str(details)),
            "label": severity,
            "severity": severity,
            "primary_risk_tier": tier,
            "cfr_reference": cfr,
            "fmea_rationale": rationale,
        })
    return examples, skipped


def _iter_labelled_rows(payload: object):
    if isinstance(payload, dict) and isinstance(payload.get("records"), list):
        records = payload["records"]
    elif isinstance(payload, dict) and isinstance(payload.get("observations"), list):
        records = [payload]
    elif isinstance(payload, list):
        records = payload
    else:
        return
    for record in records:
        if not isinstance(record, dict):
            continue
        observations = record.get("observations")
        if isinstance(observations, list):
            for observation in observations:
                if isinstance(observation, dict):
                    yield record, observation
            continue
        yield {}, record


def class_weights(labels: list[str]) -> list[float]:
    """Inverse-frequency weights ordered by label id. Zero if a class is absent."""
    counts = Counter(LABEL2ID[label] for label in labels)
    total = len(labels)
    classes = len(LABELS)
    return [
        (total / (classes * counts[index])) if counts[index] else 0.0
        for index in range(classes)
    ]


def _first(row: dict, keys: tuple[str, ...]) -> object | None:
    for key in keys:
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _context(row: dict) -> dict[str, str]:
    context: dict[str, str] = {}
    for key in ("establishment_type", "observation_summary"):
        value = _first(row, (key,))
        if value:
            context[key] = str(value)
    return context


def build_input_text(row: dict, parent: dict, details: str) -> str:
    """Build the encoder input for one observation.

    ``[Establishment Type] | Summary: [observation_summary] | Details: [full_details]``

    A present citation is appended: `` | Citation: [act_cfr_number] — [short] — [long]``.
    """
    establishment = _first(row, ("establishment_type",)) or parent.get("establishment_type") or ""
    summary = _first(row, ("observation_summary",)) or parent.get("observation_summary") or ""
    text = f"{establishment} | Summary: {summary} | Details: {details.strip()}"
    citation = _citation_text(row)
    if citation:
        text = f"{text} | Citation: {citation}"
    return text


def _citation_text(row: dict) -> str:
    """CFR citation text from the observation, or empty when the join is missing."""
    raw = row.get("citation", row.get("cfr_citation"))
    if isinstance(raw, str):
        return raw.strip()
    if not isinstance(raw, dict):
        return ""
    parts: list[str] = []
    for key in ("act_cfr_number", "short_description", "long_description"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    return " — ".join(parts)

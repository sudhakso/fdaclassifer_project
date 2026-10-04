import json
import os
import argparse
import time
from typing import List, Optional
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

# gemini-2.5-pro returns 404 for new API keys. The API names this as the replacement.
DEFAULT_MODEL = "gemini-3.1-pro-preview"
# One request for all 13,759 observations exceeds the 1,048,576-token input cap.
# 40 observations stays well under that cap and under a 65k-token JSON response.
DEFAULT_BATCH_SIZE = 40
DEFAULT_MAX_INPUT_CHARS = 400_000

# ---------------------------------------------------------------------------
# 1. Define Output Schema via Pydantic for Structured JSON Outputs
# ---------------------------------------------------------------------------

class ObservationScore(BaseModel):
    record_id: str = Field(description="The unique record ID of the FDA 483 entry.")
    observation_number: int = Field(description="The specific observation number evaluated.")
    primary_risk_tier: str = Field(
        description="The assigned risk category/tier (e.g., Tier 1 — Patient Safety Risks, Additional Tier — Supplier Quality Lapses)."
    )
    severity: str = Field(
        description="Assigned severity rating: Critical, Major, or Minor."
    )
    cfr_reference: Optional[str] = Field(
        description="Relevant 21 CFR Part 211 section or Part 11/Part 820 if applicable."
    )
    fmea_rationale: str = Field(
        description="Detailed FMEA explanation of failure mode, potential cause, and impact on product quality or patient safety."
    )

class BatchScoringResponse(BaseModel):
    evaluations: List[ObservationScore]


# ---------------------------------------------------------------------------
# 2. System Prompt Incorporating CFR 211 Tiers & FMEA Methodology
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an expert FDA Regulatory Compliance & CGMP Quality Risk Assessment Auditor.
Your task is to analyze FDA Form 483 observations, evaluate their failure modes using FMEA principles, and score their severity based on the following Tiered Risk Framework:

🏆 ORDERED RISK CATEGORIES (FDA CFR Part 211 Aligned)

Tier 1 — Direct Patient Safety Risks
1. Patient safety due to contamination & mixing (CFR §211.113)
2. Quality control failures → poor/ineffective/low-potency drug (CFR §211.165)

Tier 2 — Critical Process Risks
3. Deviation of critical process parameters (reaction temp, pH, drying errors) (CFR §211.100)
4. Process not followed effectively → inconsistency in drug produce (CFR §211.22)

Tier 3 — Hygiene & Environment
5. Personnel hygiene (CFR §211.28)
6. Equipment & environment hygiene (CFR §211.67)

Tier 4 — Documentation & Compliance
7. Improper document controls affecting traceability (CFR §211.180–211.194)
8. Detected issues closed without proper closure/prevention (CFR §211.192)

➕ Additional FDA-Relevant Risks
- Labeling & packaging errors (CFR §211.130)
- Stability & storage failures (CFR §211.166)
- Supplier/raw material quality lapses (CFR §211.84)
- Electronic data integrity risks (CFR Part 11 / §211.194)

SEVERITY SCORING GUIDELINES:
- Critical: Direct risk of patient harm, sterility/microbial breach in injectables, uninvestigated/released OOS failures, major data integrity issues, or cross-contamination.
- Major: Significant CGMP non-compliance, incomplete process/analytical validation, uncalibrated critical instruments, unhandled complaints, or poor environmental monitoring without proven batch contamination.
- Minor: Administrative gaps, non-critical labeling errors, or minor facility issues with no direct batch/safety impact.

Evaluate each observation in the input JSON, map it to a Primary Risk Tier, derive an FMEA rationale, and assign a Severity rating.
"""

# ---------------------------------------------------------------------------
# 3. Core Processing Function
# ---------------------------------------------------------------------------

_CITATION_DROP_KEYS = ("inspection_id", "citation_id")


def _citation_for_label(citation: object) -> dict | None:
    if not isinstance(citation, dict) or not citation:
        return None
    kept = {key: value for key, value in citation.items() if key not in _CITATION_DROP_KEYS}
    return kept or None


def observation_key(row: dict) -> tuple[str, str]:
    return (str(row.get("record_id", "")), str(row.get("observation_number", "")))


def iter_batches(items: list[dict], batch_size: int, max_input_chars: int):
    """Yield groups that stay within the count cap and the character budget."""
    batch: list[dict] = []
    batch_chars = 0
    for item in items:
        item_chars = len(json.dumps(item, ensure_ascii=False)) + 1
        over_budget = batch and (len(batch) >= batch_size or batch_chars + item_chars > max_input_chars)
        if over_budget:
            yield batch
            batch = []
            batch_chars = 0
        batch.append(item)
        batch_chars += item_chars
    if batch:
        yield batch


def load_scores(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        return list(payload)
    if payload.get("records"):
        rows = []
        for record in payload["records"]:
            for observation in record.get("observations") or []:
                rows.append({
                    "record_id": record.get("record_id"),
                    "observation_number": observation.get("observation_number"),
                    "primary_risk_tier": observation.get("primary_risk_tier"),
                    "severity": observation.get("severity"),
                    "cfr_reference": observation.get("cfr_reference"),
                    "fmea_rationale": observation.get("fmea_rationale"),
                })
        return rows
    return list(payload.get("evaluations") or [])


def assemble_labelled_records(evaluations: list[dict], sources: dict[tuple[str, str], dict]) -> dict:
    """Group scores under their inspection, keeping the source narrative and citation."""
    grouped: dict[str, dict] = {}
    order: list[str] = []
    for evaluation in evaluations:
        key = observation_key(evaluation)
        source = sources.get(key, {})
        record_id = str(evaluation.get("record_id") or source.get("record_id") or "")
        if record_id not in grouped:
            order.append(record_id)
            grouped[record_id] = {
                "record_id": record_id,
                "establishment_type": source.get("establishment_type") or "",
                "observation_summary": source.get("observation_summary") or "",
                "observations": [],
            }
        observation = {
            "observation_number": evaluation.get("observation_number", source.get("observation_number")),
            "full_details": source.get("full_details") or "",
            "primary_risk_tier": evaluation.get("primary_risk_tier"),
            "severity": evaluation.get("severity"),
            "cfr_reference": evaluation.get("cfr_reference"),
            "fmea_rationale": evaluation.get("fmea_rationale"),
        }
        citation = _citation_for_label(source.get("citation"))
        if citation:
            observation["citation"] = citation
        grouped[record_id]["observations"].append(observation)
    return {"records": [grouped[record_id] for record_id in order]}


def write_scores(path: str, evaluations: list[dict], sources: dict[tuple[str, str], dict]) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(assemble_labelled_records(evaluations, sources), handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def score_fda_dataset(
    json_file_path: str,
    output_file_path: str,
    api_key: Optional[str] = None,
    model: str = DEFAULT_MODEL,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_input_chars: int = DEFAULT_MAX_INPUT_CHARS,
    pause_seconds: float = 1.0,
):
    # Initialize the Google GenAI Client
    client = genai.Client(api_key=api_key or os.environ.get("GEMINI_API_KEY"))

    with open(json_file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Handle either raw FDA export structure or flat records list
    records = data.get("records", data if isinstance(data, list) else [])

    # Flatten JSON to extract individual observation payloads
    eval_inputs = []
    for record in records:
        record_id = record.get("record_id", "N/A")
        firm_name = record.get("firm_name", "Unknown Firm")
        establishment_type = record.get("establishment_type", "")
        summary = record.get("observation_summary", "")

        for obs in record.get("observations", []):
            citation = obs.get("citation") if isinstance(obs.get("citation"), dict) else None
            eval_inputs.append({
                "record_id": record_id,
                "firm_name": firm_name,
                "establishment_type": establishment_type,
                "observation_number": obs.get("observation_number"),
                "description": obs.get("description", ""),
                "full_details": obs.get("full_details", ""),
                "observation_summary": summary,
                "citation": citation,
            })

    sources = {observation_key(row): row for row in eval_inputs}
    completed = load_scores(output_file_path)
    done = {observation_key(row) for row in completed}
    # Citation stays in the saved file. It is not sent to the model.
    pending = [
        {key: value for key, value in row.items() if key != "citation"}
        for row in eval_inputs
        if observation_key(row) not in done
    ]
    batches = list(iter_batches(pending, batch_size, max_input_chars))
    print(
        f"Loaded {len(eval_inputs)} observations. "
        f"{len(done)} already scored. {len(pending)} left in {len(batches)} batches."
    )

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        temperature=0.1,  # Low temperature for deterministic, consistent scoring
        response_mime_type="application/json",
        response_schema=BatchScoringResponse,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )

    for index, batch in enumerate(batches, start=1):
        print(f"Calling {model} for batch {index}/{len(batches)} ({len(batch)} observations)...")
        prompt = (
            "Evaluate and score every FDA 483 observation in this JSON array. "
            "Return one evaluation per input row.\n\n"
            + json.dumps(batch, ensure_ascii=False)
        )
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=config,
        )
        parsed_output = json.loads(response.text)
        completed.extend(parsed_output["evaluations"])
        write_scores(output_file_path, completed, sources)
        print(f"Saved {len(completed)} scores to {output_file_path}")
        if pause_seconds and index < len(batches):
            time.sleep(pause_seconds)

    print(f"Scoring complete. Output saved to: {output_file_path}")


# ---------------------------------------------------------------------------
# 4. Command-Line Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Score FDA 483 observations with Gemini using FMEA and 21 CFR 211 tiers.")
    parser.add_argument("--input", required=True, help="Path to raw FDA 483 JSON file.")
    parser.add_argument("--output", default="scored_fda_observations.json", help="Path to save scored JSON output.")
    parser.add_argument("--api-key", help="Google Gemini API key (optional if GEMINI_API_KEY env var is set).")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Gemini model id.")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Max observations per request.")
    parser.add_argument(
        "--max-input-chars",
        type=int,
        default=DEFAULT_MAX_INPUT_CHARS,
        help="Split a batch early when its JSON exceeds this many characters.",
    )
    parser.add_argument("--pause-seconds", type=float, default=1.0, help="Delay between requests.")

    args = parser.parse_args()
    score_fda_dataset(
        args.input,
        args.output,
        args.api_key,
        args.model,
        args.batch_size,
        args.max_input_chars,
        args.pause_seconds,
    )

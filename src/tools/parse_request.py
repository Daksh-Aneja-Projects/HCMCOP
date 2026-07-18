"""Tool: parse_hiring_request.

Extracts structured hiring details from an ambiguous natural-language request.
The extraction itself is performed by Qwen Cloud (JSON mode) — this is the one
tool whose *implementation* also calls the LLM, because turning free text into
structured fields is exactly what the model is good at.
"""

from __future__ import annotations

import json
from typing import Any

from ..utils.qwen_client import chat_completion

# Fields we consider critical. If any are missing, the orchestrator should ask
# the user for clarification instead of fabricating a value.
CRITICAL_FIELDS = ["role", "location"]

_SYSTEM_PROMPT = """You are an HR intake parser. Extract structured hiring \
details from a recruiter's free-text request and return STRICT JSON only.

Return exactly this shape:
{
  "role": string or null,            // normalized job title, e.g. "Senior Backend Developer"
  "level": string or null,           // seniority, e.g. "Senior (IC3)", "Mid", "Staff"
  "department": string or null,
  "location": {                       // null if no location at all is given
    "city": string or null,
    "state": string or null,         // infer the state/region if well-known (e.g. Bangalore -> Karnataka)
    "country": string or null
  } or null,
  "start_date": string or null,      // ISO YYYY-MM-DD. Resolve relative dates against the provided "today".
  "employment_type": string,         // default "Full-time"
  "missing_fields": [string],        // list field names that are null/unknown and matter
  "assumptions_made": [string],      // human-readable notes about any inference you made
  "confidence": number               // 0.0 - 1.0 overall extraction confidence
}

Rules:
- Do NOT invent a role or a country if the text does not support it; use null and list it in missing_fields.
- Resolve relative dates ("next month", "in 2 weeks") to a concrete ISO date using the provided today's date.
- If a city clearly implies a state/country, fill them in and note it in assumptions_made.
- Output JSON only. No markdown, no commentary."""


def parse_hiring_request(raw_request: str, today: str | None = None) -> dict[str, Any]:
    """Parse an ambiguous hiring request into structured fields.

    Args:
        raw_request: The recruiter's free-text hiring request.
        today: ISO date string used to resolve relative dates. Optional.

    Returns:
        A dict matching the schema in the system prompt, always including
        ``role``, ``location``, ``missing_fields``, ``assumptions_made`` and
        ``confidence`` keys (with safe defaults on parse failure).
    """
    user_content = raw_request.strip()
    if today:
        user_content = f"Today's date is {today}.\n\nHiring request:\n{user_content}"

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    response = chat_completion(messages=messages, temperature=0.1)

    content = response.choices[0].message.content or "{}"
    parsed = _safe_json(content)

    return _normalize_parsed(parsed)


def _safe_json(content: str) -> dict[str, Any]:
    content = content.strip()
    # Strip accidental markdown code fences.
    if content.startswith("```"):
        content = content.strip("`")
        # remove a leading "json" language tag if present
        if content.lstrip().lower().startswith("json"):
            content = content.lstrip()[4:]
    try:
        return json.loads(content)
    except (json.JSONDecodeError, TypeError):
        # Last-ditch: try to locate the first {...} block.
        start, end = content.find("{"), content.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(content[start : end + 1])
            except json.JSONDecodeError:
                pass
    return {}


def _normalize_parsed(parsed: dict[str, Any]) -> dict[str, Any]:
    """Guarantee the output shape regardless of what the model returned."""
    result: dict[str, Any] = {
        "role": parsed.get("role"),
        "level": parsed.get("level"),
        "department": parsed.get("department"),
        "location": parsed.get("location"),
        "start_date": parsed.get("start_date"),
        "employment_type": parsed.get("employment_type") or "Full-time",
        "missing_fields": list(parsed.get("missing_fields") or []),
        "assumptions_made": list(parsed.get("assumptions_made") or []),
        "confidence": _clamp_confidence(parsed.get("confidence")),
    }

    # Recompute missing_fields defensively so the orchestrator can trust it.
    computed_missing = _compute_missing(result)
    # Union of model-reported and computed, de-duplicated, order-stable.
    seen: set[str] = set()
    merged: list[str] = []
    for f in list(result["missing_fields"]) + computed_missing:
        if f not in seen:
            seen.add(f)
            merged.append(f)
    result["missing_fields"] = merged
    result["needs_clarification"] = any(f in CRITICAL_FIELDS for f in merged)
    return result


def _compute_missing(result: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if not result.get("role"):
        missing.append("role")
    loc = result.get("location") or {}
    if not loc or not (loc.get("country") or loc.get("city")):
        missing.append("location")
    if not result.get("level"):
        missing.append("level")
    if not result.get("start_date"):
        missing.append("start_date")
    if not result.get("department"):
        missing.append("department")
    return missing


def _clamp_confidence(value: Any) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, v))

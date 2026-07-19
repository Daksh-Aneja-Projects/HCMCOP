"""Tool: multimodal JD / resume image parsing via a Qwen vision model.

Recruiters frequently receive a job description or resume as a screenshot,
scanned PDF page, or photo rather than clean text. This tool sends such an
image to a Qwen vision-language model (``qwen-vl-max`` by default) through the
OpenAI-compatible client and extracts the *same* structured hiring fields as
the text parser (:mod:`src.tools.parse_request`), so downstream tooling can
treat image and text intake identically.

The image is passed as a base64 ``data:`` URI in the standard chat-completions
``image_url`` content-part format. Filesystem paths, raw bytes and pre-built
data / http(s) URIs are all accepted.
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any

from ..utils.qwen_client import get_client

VISION_MODEL = os.getenv("QWEN_VISION_MODEL", "qwen-vl-max")

_SYSTEM_PROMPT = """You are an HR document parser with vision. You are given an \
image of a job description or resume. Extract structured hiring details and \
return STRICT JSON only.

Return exactly this shape:
{
  "role": string or null,            // normalized job title, e.g. "Senior Backend Developer"
  "level": string or null,           // seniority, e.g. "Senior (IC3)", "Mid", "Staff"
  "department": string or null,
  "location": {                       // null if no location at all is shown
    "city": string or null,
    "state": string or null,         // infer the state/region if well-known (e.g. Bangalore -> Karnataka)
    "country": string or null
  } or null,
  "start_date": string or null,      // ISO YYYY-MM-DD if a concrete date is shown, else null
  "employment_type": string,         // default "Full-time"
  "raw_text": string                 // the full text you read from the image
}

Rules:
- Do NOT invent a role or country the image does not support; use null instead.
- Transcribe the visible text faithfully into raw_text.
- Output JSON only. No markdown, no commentary."""


def parse_jd_image(image_source: str | bytes, mime: str = "image/png") -> dict[str, Any]:
    """Extract structured hiring fields from an image of a JD or resume.

    Args:
        image_source: One of:
            * a filesystem path to an image file (``str``),
            * raw image bytes (``bytes``),
            * an existing ``data:`` URI or ``http(s)://`` URL (``str``).
        mime: MIME type used when building a data URI from a path or bytes.

    Returns:
        A dict with keys ``role``, ``level``, ``department``, ``location``
        (``{city, state, country}``), ``start_date``, ``employment_type`` and
        ``raw_text``. On any error a ``{"error": ..., "raw_text": ""}`` dict is
        returned instead so callers never see an exception.
    """
    try:
        image_url = _to_image_url(image_source, mime)
    except Exception as exc:  # noqa: BLE001 - surface as structured error
        return {"error": f"could not read image source: {exc}", "raw_text": ""}

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Extract the hiring fields as JSON."},
                {"type": "image_url", "image_url": {"url": image_url}},
            ],
        },
    ]

    try:
        client = get_client()
        resp = client.chat.completions.create(
            model=VISION_MODEL,
            messages=messages,
            temperature=0.1,
        )
        content = resp.choices[0].message.content or "{}"
    except Exception as exc:  # noqa: BLE001 - network/auth/model errors
        return {"error": f"vision model call failed: {exc}", "raw_text": ""}

    parsed = _safe_json(content)
    if not parsed:
        return {"error": "could not parse model output as JSON", "raw_text": content.strip()}
    return _normalize(parsed)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_image_url(image_source: str | bytes, mime: str) -> str:
    """Coerce a path / bytes / URI into an ``image_url`` string for the API."""
    if isinstance(image_source, bytes):
        b64 = base64.b64encode(image_source).decode("ascii")
        return f"data:{mime};base64,{b64}"

    if isinstance(image_source, str):
        s = image_source.strip()
        # Already a usable URL — pass straight through.
        if s.startswith(("data:", "http://", "https://")):
            return s
        # Otherwise treat it as a filesystem path.
        with open(s, "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode("ascii")
        return f"data:{mime};base64,{b64}"

    raise TypeError(f"unsupported image_source type: {type(image_source).__name__}")


def _safe_json(content: str) -> dict[str, Any]:
    """Parse model output into a dict, tolerant of code fences and prose."""
    content = content.strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content.lstrip().lower().startswith("json"):
            content = content.lstrip()[4:]
    try:
        parsed = json.loads(content)
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        start, end = content.find("{"), content.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                parsed = json.loads(content[start : end + 1])
                return parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                pass
    return {}


def _normalize(parsed: dict[str, Any]) -> dict[str, Any]:
    """Guarantee the output shape regardless of what the model returned."""
    location = parsed.get("location")
    if isinstance(location, dict):
        location = {
            "city": location.get("city"),
            "state": location.get("state"),
            "country": location.get("country"),
        }
    else:
        location = None

    return {
        "role": parsed.get("role"),
        "level": parsed.get("level"),
        "department": parsed.get("department"),
        "location": location,
        "start_date": parsed.get("start_date"),
        "employment_type": parsed.get("employment_type") or "Full-time",
        "raw_text": parsed.get("raw_text") or "",
    }

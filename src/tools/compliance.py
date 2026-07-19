"""Tool: check_geo_compliance.

Thin adapter over the hardcoded compliance knowledge base. Deterministic — no
LLM call, no external API.
"""

from __future__ import annotations

from typing import Any

from ..knowledge.compliance_data import get_compliance


def check_geo_compliance(
    country: str,
    state: str | None = None,
    employment_type: str = "Full-time",
) -> dict[str, Any]:
    """Return statutory/HR compliance requirements for a geography.

    Args:
        country: Country name (aliases like "US"/"UK" are accepted).
        state: State/region within the country, if applicable.
        employment_type: e.g. "Full-time", "Contract".
    """
    if not country:
        return {
            "error": "country is required to check compliance",
            "risk_flags": ["No country provided; cannot determine compliance requirements."],
        }

    result = get_compliance(country=country, state=state, employment_type=employment_type)

    # For geographies not in the hardcoded KB, augment the fallback with the most
    # semantically-similar known geography via the RAG retriever (offline-safe:
    # degrades to keyword matching when embeddings are unavailable).
    if not result.get("statutory_compliance") and result.get("risk_flags"):
        try:
            from ..knowledge.retriever import semantic_compliance

            hits = semantic_compliance(f"{country} {state or ''} employment compliance", k=1)
            if hits:
                result["kb_reference"] = {
                    "closest_geography": hits[0]["metadata"],
                    "context": hits[0]["text"],
                    "score": round(hits[0]["score"], 3),
                }
        except Exception:
            pass  # retrieval is best-effort augmentation

    return result

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
    return get_compliance(country=country, state=state, employment_type=employment_type)

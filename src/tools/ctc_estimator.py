"""Tool: estimate_ctc_band.

Adapter over the hardcoded salary knowledge base. Supports an optional
``max_ctc`` constraint so the rejection/revision flow can cap the band when a
user says e.g. "cap at 30L".
"""

from __future__ import annotations

from typing import Any

from ..knowledge.salary_bands import estimate_band


def estimate_ctc_band(
    role: str,
    level: str,
    location: dict[str, Any],
    max_ctc: float | None = None,
) -> dict[str, Any]:
    """Return an indicative CTC band for a role/level/location.

    Args:
        role: Job title, e.g. "Senior Backend Developer".
        level: Seniority level, e.g. "Senior (IC3)".
        location: ``{"city", "state", "country"}`` (country is required).
        max_ctc: Optional hard cap. When provided, the band is clamped so the
            high (and, if needed, mid) do not exceed the cap. Used by the
            revision flow.
    """
    band = estimate_band(role=role or "", level=level or "", location=location or {})

    if max_ctc is not None:
        band = _apply_cap(band, float(max_ctc))

    return band


def _apply_cap(band: dict[str, Any], cap: float) -> dict[str, Any]:
    cap_int = int(cap)
    original_high = band["band_high"]
    band = dict(band)
    band["cap_applied"] = cap_int

    if band["band_high"] > cap_int:
        band["band_high"] = cap_int
    if band["band_mid"] > cap_int:
        band["band_mid"] = cap_int
    if band["band_low"] > cap_int:
        band["band_low"] = cap_int

    # Keep the ordering sane after clamping.
    band["band_low"] = min(band["band_low"], band["band_mid"], band["band_high"])
    band["band_mid"] = min(max(band["band_low"], band["band_mid"]), band["band_high"])

    note = (
        f" A cap of {cap_int:,} {band['currency']} was applied "
        f"(original high was {original_high:,})."
    )
    band["notes"] = band.get("notes", "") + note
    return band

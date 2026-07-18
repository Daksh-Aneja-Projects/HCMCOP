"""Hardcoded market salary knowledge base.

Provides indicative annual CTC bands by role family, seniority level and
location. Values are illustrative market ranges for the hackathon demo — not
live compensation data. No external API is called.

Currency is inferred from the location's country.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Currency + a rough multiplier to scale a global base band into local money.
# Bands below are expressed in the *base* unit and scaled per-country so we do
# not have to hand-maintain a full matrix for every role x location.
# ---------------------------------------------------------------------------

_CURRENCY_BY_COUNTRY = {
    "India": "INR",
    "USA": "USD",
    "UK": "GBP",
    "Singapore": "SGD",
}

# Base annual CTC bands (in USD) by role family and level.
# Structure: role_family -> level_key -> (low, mid, high)
_BASE_BANDS_USD: dict[str, dict[str, tuple[int, int, int]]] = {
    "backend_developer": {
        "junior": (55000, 70000, 85000),
        "mid": (85000, 105000, 125000),
        "senior": (125000, 150000, 180000),
        "staff": (170000, 205000, 250000),
        "principal": (230000, 275000, 330000),
    },
    "frontend_developer": {
        "junior": (52000, 66000, 80000),
        "mid": (80000, 100000, 120000),
        "senior": (118000, 143000, 170000),
        "staff": (160000, 195000, 235000),
        "principal": (215000, 260000, 310000),
    },
    "fullstack_developer": {
        "junior": (55000, 70000, 85000),
        "mid": (85000, 106000, 128000),
        "senior": (124000, 150000, 180000),
        "staff": (168000, 205000, 248000),
        "principal": (228000, 272000, 325000),
    },
    "data_scientist": {
        "junior": (60000, 75000, 92000),
        "mid": (92000, 115000, 138000),
        "senior": (135000, 165000, 198000),
        "staff": (180000, 220000, 265000),
        "principal": (240000, 290000, 350000),
    },
    "product_manager": {
        "junior": (65000, 82000, 100000),
        "mid": (100000, 125000, 150000),
        "senior": (145000, 178000, 215000),
        "staff": (195000, 235000, 285000),
        "principal": (260000, 315000, 380000),
    },
    "designer": {
        "junior": (50000, 63000, 78000),
        "mid": (78000, 97000, 118000),
        "senior": (115000, 140000, 168000),
        "staff": (155000, 188000, 225000),
        "principal": (205000, 248000, 298000),
    },
    "devops_engineer": {
        "junior": (58000, 72000, 88000),
        "mid": (88000, 110000, 132000),
        "senior": (128000, 156000, 188000),
        "staff": (172000, 210000, 252000),
        "principal": (232000, 280000, 335000),
    },
    "generic": {
        "junior": (45000, 58000, 72000),
        "mid": (72000, 90000, 110000),
        "senior": (105000, 130000, 158000),
        "staff": (150000, 182000, 220000),
        "principal": (200000, 245000, 295000),
    },
}

# Purchasing-power / market scaler applied to the USD base, plus currency FX,
# folded into one number that converts base-USD -> local currency amount.
# (Deliberately simple for a self-contained demo.)
_LOCAL_SCALER: dict[str, float] = {
    "India": 20.0,     # ~ compresses USD base then expresses in INR
    "USA": 1.0,
    "UK": 0.62,        # GBP amount
    "Singapore": 1.15,  # SGD amount
}

_LOCATION_NOTES = {
    "India": "Based on market data for Tier-1 Indian metros. CTC is total cost to company.",
    "USA": "Based on US tech market data. Figure is base + typical cash; equity excluded.",
    "UK": "Based on UK market data. Figure is gross annual salary.",
    "Singapore": "Based on Singapore market data. Figure is annual gross incl. AWS where customary.",
}

# CTC composition breakdown by country (percentages of total CTC).
_BREAKDOWN_BY_COUNTRY: dict[str, dict[str, int]] = {
    "India": {
        "base_salary_pct": 50,
        "hra_pct": 20,
        "special_allowance_pct": 15,
        "pf_employer_pct": 12,
        "other_pct": 3,
    },
    "USA": {
        "base_salary_pct": 88,
        "bonus_target_pct": 10,
        "employer_401k_match_pct": 2,
    },
    "UK": {
        "base_salary_pct": 90,
        "pension_employer_pct": 5,
        "bonus_target_pct": 5,
    },
    "Singapore": {
        "base_salary_pct": 82,
        "cpf_employer_pct": 13,
        "aws_bonus_pct": 5,
    },
}


def _normalize(text: str | None) -> str:
    return (text or "").strip().lower()


def _resolve_role_family(role: str) -> str:
    r = _normalize(role)
    checks = [
        ("backend_developer", ["backend", "back-end", "back end", "server"]),
        ("frontend_developer", ["frontend", "front-end", "front end", "ui engineer"]),
        ("fullstack_developer", ["fullstack", "full-stack", "full stack"]),
        ("data_scientist", ["data scientist", "machine learning", "ml engineer", "data science", "ai engineer"]),
        ("product_manager", ["product manager", "product owner", "pm", "product lead"]),
        ("designer", ["designer", "ux", "ui/ux", "product design"]),
        ("devops_engineer", ["devops", "sre", "site reliability", "platform engineer", "infrastructure"]),
    ]
    for family, needles in checks:
        if any(n in r for n in needles):
            return family
    return "generic"


def _resolve_level(level: str) -> str:
    lvl = _normalize(level)
    if any(k in lvl for k in ["principal", "ic6", "ic7", "director", "vp"]):
        return "principal"
    if any(k in lvl for k in ["staff", "ic5", "lead", "manager"]):
        return "staff"
    if any(k in lvl for k in ["senior", "sr", "ic3", "ic4"]):
        return "senior"
    if any(k in lvl for k in ["junior", "jr", "entry", "graduate", "associate", "ic1"]):
        return "junior"
    return "mid"


def estimate_band(role: str, level: str, location: dict[str, Any]) -> dict[str, Any]:
    """Return an indicative CTC band for a role/level/location.

    ``location`` is expected to look like
    ``{"city": ..., "state": ..., "country": ...}`` but only ``country`` is
    strictly required.
    """
    country = (location or {}).get("country") or "USA"
    country_norm = _resolve_country(country)

    family = _resolve_role_family(role)
    level_key = _resolve_level(level)
    low_usd, mid_usd, high_usd = _BASE_BANDS_USD[family][level_key]

    scaler = _LOCAL_SCALER.get(country_norm, 1.0)
    currency = _CURRENCY_BY_COUNTRY.get(country_norm, "USD")

    def scale(v: int) -> int:
        return _round_band(v * scaler, currency)

    band_low, band_mid, band_high = scale(low_usd), scale(mid_usd), scale(high_usd)

    city = (location or {}).get("city")
    loc_label = f"{city}, {country_norm}" if city else country_norm

    return {
        "role": role,
        "level": level,
        "location": loc_label,
        "currency": currency,
        "band_low": band_low,
        "band_mid": band_mid,
        "band_high": band_high,
        "breakdown": _BREAKDOWN_BY_COUNTRY.get(country_norm, _BREAKDOWN_BY_COUNTRY["USA"]),
        "notes": (
            f"{_LOCATION_NOTES.get(country_norm, 'Indicative market band.')} "
            f"Role family: {family.replace('_', ' ')}, level: {level_key}."
        ),
        "is_indicative": True,
    }


def _resolve_country(country: str) -> str:
    c = _normalize(country)
    aliases = {
        "india": "India", "in": "India",
        "usa": "USA", "us": "USA", "united states": "USA", "america": "USA",
        "uk": "UK", "united kingdom": "UK", "england": "UK", "great britain": "UK",
        "singapore": "Singapore", "sg": "Singapore",
    }
    return aliases.get(c, "USA")


def _round_band(value: float, currency: str) -> int:
    """Round to a clean, human-readable band figure."""
    if currency == "INR":
        # Round to nearest 50,000 INR.
        return int(round(value / 50000.0) * 50000)
    # Round to nearest 1,000 for other currencies.
    return int(round(value / 1000.0) * 1000)

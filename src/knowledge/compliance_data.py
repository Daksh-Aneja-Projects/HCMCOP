"""Hardcoded geographic compliance knowledge base.

This module is the single source of truth for statutory/HR compliance
requirements by geography. No external API calls are made — the hackathon
brief requires a self-contained knowledge base.

Coverage:
  * India   -> Karnataka, Maharashtra, Delhi
  * USA     -> California, Texas, New York
  * UK      -> (national)
  * Singapore -> (national)
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Country-level defaults. State-level rules (below) are merged on top of these.
# ---------------------------------------------------------------------------

_COUNTRY_BASE: dict[str, dict[str, Any]] = {
    "India": {
        "country": "India",
        "notice_period_norm": "60-90 days",
        "probation_period": "6 months standard",
        "mandatory_benefits": [
            "Provident Fund (PF) - 12% employer contribution",
            "Gratuity (after 5 years of service)",
            "ESI (if gross wage <= INR 21,000/month)",
            "Professional Tax (state dependent)",
        ],
        "required_documents": [
            "PAN Card",
            "Aadhaar Card",
            "Bank account details (cancelled cheque)",
            "Previous employer relieving letter",
            "Educational certificates",
        ],
        "statutory_compliance": [
            "PF registration (EPFO)",
            "ESI registration (ESIC)",
            "Professional Tax registration",
        ],
        "risk_flags": [],
    },
    "USA": {
        "country": "USA",
        "notice_period_norm": "At-will employment (no statutory notice)",
        "probation_period": "90 days introductory period (customary, not statutory)",
        "mandatory_benefits": [
            "Social Security & Medicare (FICA)",
            "Federal & state unemployment insurance",
            "Workers' compensation insurance",
        ],
        "required_documents": [
            "Form I-9 (employment eligibility verification)",
            "Form W-4 (federal tax withholding)",
            "Social Security Number",
            "Direct deposit / bank details",
        ],
        "statutory_compliance": [
            "E-Verify (where mandated)",
            "New hire reporting to state directory",
            "EEO compliance",
        ],
        "risk_flags": [
            "At-will employment: confirm no implied contract language in offer",
        ],
    },
    "UK": {
        "country": "UK",
        "notice_period_norm": "1 week (0.5-2 yrs), then +1 week/yr up to 12 weeks statutory minimum",
        "probation_period": "3-6 months typical",
        "mandatory_benefits": [
            "Workplace pension auto-enrolment (min 3% employer)",
            "Statutory Sick Pay (SSP)",
            "Statutory holiday: 28 days incl. bank holidays (pro-rata)",
            "Employer National Insurance contributions",
        ],
        "required_documents": [
            "Right to Work check (passport / share code)",
            "National Insurance (NI) number",
            "P45 from previous employer (or P46 / starter checklist)",
            "Bank details",
        ],
        "statutory_compliance": [
            "Right to Work verification (Home Office)",
            "HMRC PAYE registration & RTI reporting",
            "Pension auto-enrolment via TPR",
            "Written statement of particulars on day one",
        ],
        "risk_flags": [
            "Right to Work check must be completed BEFORE the first working day",
        ],
    },
    "Singapore": {
        "country": "Singapore",
        "notice_period_norm": "1 day to 4 weeks depending on length of service (Employment Act)",
        "probation_period": "3-6 months typical",
        "mandatory_benefits": [
            "CPF contributions (employer up to 17% for citizens/PRs)",
            "Statutory annual leave (min 7 days, rising with service)",
            "Paid sick leave (up to 14 days outpatient)",
        ],
        "required_documents": [
            "NRIC (citizens/PRs) or valid work pass (EP/S Pass)",
            "Bank details",
            "Educational & professional certificates",
        ],
        "statutory_compliance": [
            "CPF registration & monthly contributions (citizens/PRs)",
            "Work pass application via MOM (foreign nationals)",
            "IRAS tax reporting (Form IR8A)",
            "Key Employment Terms (KET) issued within 14 days",
        ],
        "risk_flags": [
            "Foreign hires require a valid work pass (EP/S Pass) before starting",
        ],
    },
}

# ---------------------------------------------------------------------------
# State/region overlays. Only fields that differ from the country base are set.
# ---------------------------------------------------------------------------

_STATE_OVERLAYS: dict[tuple[str, str], dict[str, Any]] = {
    ("India", "Karnataka"): {
        "state": "Karnataka",
        "statutory_compliance": [
            "Shops & Establishments Act (Karnataka) registration",
            "PF registration (EPFO)",
            "ESI registration (ESIC)",
            "Karnataka Professional Tax",
        ],
    },
    ("India", "Maharashtra"): {
        "state": "Maharashtra",
        "statutory_compliance": [
            "Shops & Establishments Act (Maharashtra) registration",
            "PF registration (EPFO)",
            "ESI registration (ESIC)",
            "Maharashtra Professional Tax",
            "Maharashtra Labour Welfare Fund",
        ],
    },
    ("India", "Delhi"): {
        "state": "Delhi",
        "statutory_compliance": [
            "Delhi Shops & Establishments Act registration",
            "PF registration (EPFO)",
            "ESI registration (ESIC)",
        ],
        "mandatory_benefits": [
            "Provident Fund (PF) - 12% employer contribution",
            "Gratuity (after 5 years of service)",
            "ESI (if gross wage <= INR 21,000/month)",
            # Delhi does not levy Professional Tax.
        ],
    },
    ("USA", "California"): {
        "state": "California",
        "risk_flags": [
            "At-will employment: confirm no implied contract language in offer",
            "CA meal/rest break rules apply to non-exempt employees",
            "CA pay transparency: salary range required in job postings",
            "Non-compete clauses are unenforceable in California",
        ],
        "statutory_compliance": [
            "E-Verify (where mandated)",
            "CA new hire reporting (EDD)",
            "CA Wage Theft Prevention Act notice",
            "State Disability Insurance (SDI) withholding",
        ],
    },
    ("USA", "Texas"): {
        "state": "Texas",
        "statutory_compliance": [
            "E-Verify (where mandated)",
            "TX new hire reporting (Attorney General)",
            "EEO compliance",
        ],
    },
    ("USA", "New York"): {
        "state": "New York",
        "risk_flags": [
            "At-will employment: confirm no implied contract language in offer",
            "NY pay transparency: salary range required in job postings",
        ],
        "statutory_compliance": [
            "E-Verify (where mandated)",
            "NY new hire reporting",
            "NY Wage Theft Prevention Act notice at hire",
            "NY Paid Family Leave enrolment",
        ],
    },
}


def _normalize(text: str | None) -> str:
    return (text or "").strip().lower()


def get_compliance(country: str, state: str | None, employment_type: str) -> dict[str, Any]:
    """Return compliance requirements for a geography.

    Matching is case-insensitive and tolerant of a few common aliases. When a
    country is not in the knowledge base, a clearly-labelled generic fallback
    is returned with a risk flag so the caller never silently gets wrong data.
    """
    country_key = _resolve_country(country)

    if country_key is None:
        return _unknown_geo_fallback(country, state, employment_type)

    result: dict[str, Any] = {
        k: (list(v) if isinstance(v, list) else v)
        for k, v in _COUNTRY_BASE[country_key].items()
    }
    result["state"] = state or None
    result["employment_type"] = employment_type

    state_key = _resolve_state(country_key, state)
    if state_key is not None:
        for key, value in _STATE_OVERLAYS[state_key].items():
            result[key] = list(value) if isinstance(value, list) else value

    # Part-time / contract nuance surfaced as an advisory flag.
    if _normalize(employment_type) in {"contract", "contractor", "freelance"}:
        result.setdefault("risk_flags", [])
        result["risk_flags"] = list(result["risk_flags"]) + [
            "Contractor engagement: verify worker-classification rules to avoid misclassification liability",
        ]

    return result


def _resolve_country(country: str) -> str | None:
    c = _normalize(country)
    aliases = {
        "india": "India",
        "in": "India",
        "usa": "USA",
        "us": "USA",
        "united states": "USA",
        "united states of america": "USA",
        "america": "USA",
        "uk": "UK",
        "united kingdom": "UK",
        "great britain": "UK",
        "england": "UK",
        "singapore": "Singapore",
        "sg": "Singapore",
    }
    return aliases.get(c)


def _resolve_state(country_key: str, state: str | None) -> tuple[str, str] | None:
    if not state:
        return None
    s = _normalize(state)
    for (ck, sk) in _STATE_OVERLAYS:
        if ck == country_key and _normalize(sk) == s:
            return (ck, sk)
    return None


def _unknown_geo_fallback(country: str, state: str | None, employment_type: str) -> dict[str, Any]:
    return {
        "country": country,
        "state": state or None,
        "employment_type": employment_type,
        "notice_period_norm": "Unknown - confirm with local counsel",
        "probation_period": "Unknown - confirm with local counsel",
        "mandatory_benefits": [],
        "required_documents": [
            "Government-issued ID",
            "Bank details",
            "Proof of right to work",
        ],
        "statutory_compliance": [],
        "risk_flags": [
            f"No compliance knowledge base entry for '{country}'. "
            "Manual legal review required before proceeding.",
        ],
    }


SUPPORTED_GEOGRAPHIES: dict[str, list[str]] = {
    "India": ["Karnataka", "Maharashtra", "Delhi"],
    "USA": ["California", "Texas", "New York"],
    "UK": [],
    "Singapore": [],
}

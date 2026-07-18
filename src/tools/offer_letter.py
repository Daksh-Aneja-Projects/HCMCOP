"""Tool: generate_offer_letter.

Produces a complete, structured offer-letter draft from the parsed request,
compliance findings and CTC band. Deterministic template-fill (no LLM call) so
the output is stable and reviewable; the orchestrator's LLM decides *when* to
call it.
"""

from __future__ import annotations

from typing import Any


def _fmt_money(amount: Any, currency: str) -> str:
    try:
        return f"{currency} {int(amount):,}"
    except (TypeError, ValueError):
        return f"{currency} {amount}"


def generate_offer_letter(
    parsed_request: dict[str, Any],
    compliance: dict[str, Any],
    ctc: dict[str, Any],
    candidate_name: str | None = None,
    reporting_to: str | None = None,
) -> dict[str, Any]:
    """Generate a structured offer letter draft.

    Args:
        parsed_request: Output of ``parse_hiring_request``.
        compliance: Output of ``check_geo_compliance``.
        ctc: Output of ``estimate_ctc_band``.
        candidate_name: Optional; a placeholder is used when omitted.
        reporting_to: Optional reporting manager.

    Returns:
        A dict with ``letter_content`` (markdown), ``key_terms``,
        ``requires_human_review`` and ``review_reason``.
    """
    parsed_request = parsed_request or {}
    compliance = compliance or {}
    ctc = ctc or {}

    name = candidate_name or "[Candidate Name]"
    designation = parsed_request.get("role") or "[Role]"
    currency = ctc.get("currency", "")
    ctc_mid = ctc.get("band_mid")
    ctc_display = _fmt_money(ctc_mid, currency) if ctc_mid is not None else "[CTC]"

    probation = compliance.get("probation_period", "[Probation period]")
    notice = compliance.get("notice_period_norm", "[Notice period]")
    start_date = parsed_request.get("start_date") or "[Start date]"
    location = _location_label(parsed_request.get("location"))
    manager = reporting_to or "[Reporting Manager]"
    employment_type = parsed_request.get("employment_type", "Full-time")

    benefits = compliance.get("mandatory_benefits") or []
    benefits_block = (
        "\n".join(f"- {b}" for b in benefits)
        if benefits
        else "- As per company policy and applicable law"
    )

    documents = compliance.get("required_documents") or []
    docs_block = (
        "\n".join(f"- {d}" for d in documents)
        if documents
        else "- Standard onboarding documents"
    )

    letter_content = f"""Dear {name},

We are delighted to extend an offer of employment for the position of \
**{designation}** at our organization. We were impressed by your background and \
believe you will be a valuable addition to the team.

**Position Details**
- Designation: {designation}
- Employment type: {employment_type}
- Location: {location}
- Reporting to: {manager}
- Proposed start date: {start_date}

**Compensation**
- Total annual CTC: {ctc_display}
- The detailed compensation structure is enclosed as Annexure A.

**Terms of Employment**
- Probation period: {probation}
- Notice period: {notice}

**Statutory Benefits & Deductions**
{benefits_block}

**Documents Required for Onboarding**
{docs_block}

This offer is contingent upon successful completion of background verification \
and submission of the documents listed above. Please sign and return a copy of \
this letter to confirm your acceptance.

We look forward to welcoming you aboard.

Warm regards,
Human Resources
"""

    key_terms = {
        "designation": designation,
        "ctc": ctc_mid,
        "currency": currency,
        "probation": probation,
        "notice_period": notice,
        "start_date": start_date,
        "location": location,
        "reporting_to": manager,
        "employment_type": employment_type,
    }

    review_reasons = []
    if ctc_mid is None:
        review_reasons.append("CTC could not be determined")
    if reporting_to is None:
        review_reasons.append("reporting manager not confirmed")
    if candidate_name is None:
        review_reasons.append("candidate name is a placeholder")
    if compliance.get("risk_flags"):
        review_reasons.append("compliance risk flags present")

    return {
        "letter_content": letter_content,
        "key_terms": key_terms,
        "requires_human_review": True,
        "review_reason": (
            "; ".join(review_reasons) or "Standard human review before sending"
        ),
    }


def _location_label(location: Any) -> str:
    if not isinstance(location, dict):
        return "[Location]"
    parts = [location.get("city"), location.get("state"), location.get("country")]
    label = ", ".join(p for p in parts if p)
    return label or "[Location]"

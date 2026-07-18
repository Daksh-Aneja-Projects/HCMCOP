"""Tool: create_onboarding_checklist.

Builds a sequenced onboarding checklist with owners and deadlines expressed
relative to the start date (e.g. "D-30"). Deterministic. When compliance data
is available, geography-specific statutory tasks (PF/ESI, Right to Work, CPF,
I-9, etc.) are woven in.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any


# Base checklist applied for every hire. (task, owner, day_offset)
_BASE_TASKS: list[tuple[str, str, int]] = [
    ("Send offer letter", "HR", -30),
    ("Collect signed offer & documents", "HR Ops", -25),
    ("Background verification initiation", "HR Ops", -21),
    ("Provision email & system accounts", "IT", -7),
    ("IT asset provisioning (laptop, peripherals)", "IT", -7),
    ("Set up payroll record", "Payroll", -5),
    ("Day 1 orientation scheduled", "HR", -1),
    ("Buddy assignment", "Hiring Manager", -1),
    ("Day 1 welcome & workspace ready", "HR", 0),
]


def _statutory_tasks(compliance: dict[str, Any]) -> list[tuple[str, str, int]]:
    """Derive geography-specific statutory onboarding tasks."""
    country = (compliance or {}).get("country", "")
    tasks: list[tuple[str, str, int]] = []

    if country == "India":
        tasks.append(("PF/ESI registration & UAN generation", "Payroll", -5))
        tasks.append(("Professional Tax enrolment", "Payroll", -5))
    elif country == "USA":
        tasks.append(("Complete Form I-9 & E-Verify", "HR Ops", 0))
        tasks.append(("Collect Form W-4 & state withholding", "Payroll", -3))
        tasks.append(("State new-hire reporting", "HR Ops", 3))
    elif country == "UK":
        tasks.append(("Right to Work check", "HR Ops", -7))
        tasks.append(("HMRC PAYE / starter checklist", "Payroll", -3))
        tasks.append(("Pension auto-enrolment", "Payroll", 5))
    elif country == "Singapore":
        tasks.append(("Verify work pass / NRIC", "HR Ops", -7))
        tasks.append(("CPF registration", "Payroll", -3))
        tasks.append(("Issue Key Employment Terms (KET)", "HR", 0))

    return tasks


def create_onboarding_checklist(
    parsed_request: dict[str, Any],
    compliance: dict[str, Any],
    start_date: str | None = None,
) -> dict[str, Any]:
    """Return a sequenced onboarding checklist.

    Args:
        parsed_request: Output of ``parse_hiring_request``.
        compliance: Output of ``check_geo_compliance`` (used for statutory tasks).
        start_date: ISO start date. Falls back to ``parsed_request['start_date']``.

    Returns:
        dict with ``checklist`` (list of task dicts), ``total_tasks`` and
        ``critical_path_days``.
    """
    start_date = start_date or (parsed_request or {}).get("start_date")
    start_dt = _parse_date(start_date)

    all_tasks = list(_BASE_TASKS) + _statutory_tasks(compliance or {})
    # Sort by day offset so the checklist reads chronologically.
    all_tasks.sort(key=lambda t: t[2])

    checklist: list[dict[str, Any]] = []
    for task, owner, offset in all_tasks:
        entry: dict[str, Any] = {
            "task": task,
            "owner": owner,
            "deadline": _offset_label(offset),
            "status": "pending",
        }
        if start_dt is not None:
            entry["due_date"] = (start_dt + timedelta(days=offset)).isoformat()
        checklist.append(entry)

    offsets = [t[2] for t in all_tasks]
    earliest = min(offsets) if offsets else 0
    latest = max(offsets) if offsets else 0

    return {
        "checklist": checklist,
        "total_tasks": len(checklist),
        "critical_path_days": abs(earliest),
        "span_days": latest - earliest,
    }


def _offset_label(offset: int) -> str:
    if offset == 0:
        return "D-Day"
    if offset < 0:
        return f"D{offset}"  # e.g. -30 -> "D-30"
    return f"D+{offset}"


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None

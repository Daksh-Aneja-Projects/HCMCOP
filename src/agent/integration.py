"""Integration orchestrator — macro-scale workforce integration (M&A).

Drives the multi-agent council: it parses the macro request, runs the specialist
agents, builds the contradiction graph, decomposes the work into
dependency-ordered phases, and PAUSES to escalate each conflict to a human with
both positions, a risk assessment and resolution options.

Like the hiring orchestrator, this is a resumable state machine so it survives
Streamlit's re-runs: ``start()`` builds the report and stops at unresolved
conflicts; ``resolve_conflict()`` records a human decision and re-evaluates.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ..utils.qwen_client import PRIMARY_MODEL, is_configured, structured_completion
from .council import Conflict, CouncilReport, build_report, decompose_phases


class IStatus(str, Enum):
    IDLE = "idle"
    AWAITING_RESOLUTION = "awaiting_resolution"
    COMPLETE = "complete"
    ERROR = "error"


INTEGRATION_PHASES = [
    "Council Convened",
    "Positions Gathered",
    "Conflicts Detected",
    "Human Resolution",
    "Integration Plan",
    "Complete",
]

_KNOWN_COUNTRIES = [
    "Germany", "France", "United Kingdom", "UK", "United States", "USA", "India",
    "Singapore", "Netherlands", "Spain", "Italy", "Ireland", "Poland", "Japan", "China",
]


@dataclass
class IntegrationState:
    status: IStatus = IStatus.IDLE
    phase: str = INTEGRATION_PHASES[0]
    report: CouncilReport | None = None
    error: str | None = None


class IntegrationOrchestrator:
    def __init__(self) -> None:
        self.state = IntegrationState()
        self._raw = ""

    # -- lifecycle ----------------------------------------------------------

    def start(self, raw_request: str) -> IntegrationState:
        self._raw = raw_request
        try:
            context = parse_integration_context(raw_request)
            report = build_report(context)
            self.state.report = report
            self.state.phase = "Conflicts Detected"
            self._advance()
        except Exception as exc:
            self.state.status = IStatus.ERROR
            self.state.error = f"{type(exc).__name__}: {exc}"
        return self.state

    def resolve_conflict(self, conflict_id: str, option_id: str, note: str = "") -> IntegrationState:
        """Record a human resolution for one conflict, then re-evaluate."""
        report = self.state.report
        if not report:
            return self.state
        for c in report.conflicts:
            if c.id == conflict_id:
                chosen = next((o.option for o in c.options if o.id == option_id), option_id)
                c.resolution = chosen + (f" — {note}" if note else "")
                break
        # Recompute phase blockers now that a conflict is resolved.
        report.phases = decompose_phases(report.context, report.positions, report.conflicts)
        self._advance()
        return self.state

    def _advance(self) -> None:
        report = self.state.report
        if not report:
            return
        unresolved = [c for c in report.conflicts if c.resolution is None]
        if unresolved:
            self.state.status = IStatus.AWAITING_RESOLUTION
            self.state.phase = "Human Resolution"
        else:
            self.state.status = IStatus.COMPLETE
            self.state.phase = "Complete"

    # -- export -------------------------------------------------------------

    def build_package(self) -> dict[str, Any]:
        report = self.state.report
        if not report:
            return {}
        return {
            "request": self._raw,
            "context": report.context,
            "council_positions": [p.__dict__ for p in report.positions],
            "contradiction_graph": [c.__dict__ for c in report.conflicts],
            "integration_plan": [p.__dict__ for p in report.phases],
            "all_conflicts_resolved": all(c.resolution for c in report.conflicts),
        }


# ---------------------------------------------------------------------------
# Context parsing (structured output + deterministic fallback)
# ---------------------------------------------------------------------------

_CTX_PROMPT = """Extract the M&A workforce-integration parameters from the request. \
Return JSON: {"acquirer": str|null, "target_company": str|null, "country": str|null, \
"headcount": int|null, "timeline": str|null, "parent_policies": [str]}. \
parent_policies = standing parent-company mandates implied or stated (e.g. \
"centralized HRIS on US infrastructure", "at-will employment"). JSON only."""


def parse_integration_context(raw: str) -> dict[str, Any]:
    ctx = _regex_context(raw)
    if is_configured():
        try:
            data = _safe_json(structured_completion(
                [{"role": "system", "content": _CTX_PROMPT},
                 {"role": "user", "content": raw}],
                model=PRIMARY_MODEL, temperature=0.1))
            for k in ("acquirer", "target_company", "country", "headcount", "timeline"):
                if data.get(k):
                    ctx[k] = data[k]
            if data.get("parent_policies"):
                ctx["parent_policies"] = list(
                    dict.fromkeys(ctx["parent_policies"] + list(data["parent_policies"])))
        except Exception:
            pass
    return ctx


def _regex_context(raw: str) -> dict[str, Any]:
    text = raw or ""
    headcount = None
    m = re.search(r"(\d{2,5})\s*(?:-|\s)?(?:person|people|employee|headcount|staff)", text, re.I)
    if m:
        headcount = int(m.group(1))
    country = next((c for c in _KNOWN_COUNTRIES if re.search(rf"\b{re.escape(c)}\b", text, re.I)), None)
    if country in ("Germany",) or re.search(r"\bgerman\b", text, re.I):
        country = "Germany"
    timeline = None
    tm = re.search(r"\b(Q[1-4](?:\s*20\d{2})?|by\s+\w+(?:\s+20\d{2})?|20\d{2})\b", text, re.I)
    if tm:
        timeline = tm.group(1)
    return {
        "acquirer": "Parent company",
        "target_company": "Target company",
        "country": country or "target country",
        "headcount": headcount,
        "timeline": timeline or "Q1",
        "parent_policies": [
            "Centralized HRIS with employee records on US infrastructure",
            "At-will employment standard",
        ],
        "raw_request": text,
    }


def _safe_json(content: str) -> dict[str, Any]:
    content = (content or "").strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content[:4].lower() == "json":
            content = content[4:]
    import json
    try:
        return json.loads(content.strip())
    except (json.JSONDecodeError, TypeError):
        a, b = content.find("{"), content.rfind("}")
        if a != -1 and b > a:
            try:
                return json.loads(content[a : b + 1])
            except json.JSONDecodeError:
                pass
    return {}

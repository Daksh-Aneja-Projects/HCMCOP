"""Compliance-Critic agent.

A second, specialised agent (distinct system prompt + its own Qwen call) that
adversarially reviews the drafted offer against the statutory compliance facts
and CTC band. It runs BEFORE the human-in-the-loop gate so obvious compliance
violations are caught and revised automatically — a reflection/critique loop
rather than a single linear pass.

It is surfaced to the orchestrator as the ``review_compliance`` tool, so the
lead agent invokes the critic via function calling (multi-agent-via-tools).
"""

from __future__ import annotations

import json
from typing import Any

from ..utils.qwen_client import PRIMARY_MODEL, structured_completion

_CRITIC_SYSTEM = """You are a meticulous HR Compliance Reviewer agent. You audit \
a drafted job offer against the statutory compliance facts and salary band that \
were computed for the role's geography.

You will receive JSON with: parsed_request, compliance, ctc, and offer_key_terms.

Return STRICT JSON only, in this shape:
{
  "passed": boolean,               // false if any medium/high issue exists
  "severity": "none"|"low"|"medium"|"high",
  "issues": [                      // concrete, each tied to a provided fact
    {"issue": string, "why": string, "fix": string}
  ],
  "recommendations": [string]      // optional non-blocking improvements
}

Audit rules — base findings ONLY on the provided facts, never invent law:
- Probation/notice period in the offer must match compliance norms.
- If compliance.risk_flags contains a pre-start requirement (e.g. Right to Work \
before day one, work pass, background checks), the offer/onboarding must account \
for it — flag if unaddressed.
- The offer CTC should sit within the ctc band_low..band_high; flag if outside.
- Mandatory benefits/statutory items for the geography should be reflected.
- Placeholder fields (e.g. [Candidate Name], unfilled reporting manager) are \
low severity, not blocking.
Output JSON only."""


def review_compliance(
    parsed_request: dict[str, Any],
    compliance: dict[str, Any],
    ctc: dict[str, Any],
    offer: dict[str, Any],
    focus: str | None = None,
) -> dict[str, Any]:
    """Run the compliance critic. Returns a structured verdict dict.

    Deterministic guardrails run first (they never hallucinate); the LLM critic
    then adds nuanced findings. Results are merged.
    """
    deterministic = _rule_based_findings(parsed_request, compliance, ctc, offer)

    payload = {
        "parsed_request": parsed_request,
        "compliance": compliance,
        "ctc": ctc,
        "offer_key_terms": (offer or {}).get("key_terms", {}),
    }
    if focus:
        payload["reviewer_focus"] = focus

    messages = [
        {"role": "system", "content": _CRITIC_SYSTEM},
        {"role": "user", "content": json.dumps(payload, default=str)},
    ]

    llm_verdict: dict[str, Any]
    try:
        raw = structured_completion(messages=messages, model=PRIMARY_MODEL, temperature=0.1)
        llm_verdict = _safe_json(raw)
    except Exception as exc:  # never block the pipeline on a critic failure
        llm_verdict = {"issues": [], "recommendations": [f"Critic unavailable: {exc}"]}

    return _merge_verdicts(deterministic, llm_verdict)


# ---------------------------------------------------------------------------
# Deterministic guardrails (fact-checked, no LLM)
# ---------------------------------------------------------------------------

def _rule_based_findings(
    parsed: dict[str, Any], compliance: dict[str, Any], ctc: dict[str, Any], offer: dict[str, Any]
) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    key_terms = (offer or {}).get("key_terms", {})

    # CTC within band.
    ctc_val = key_terms.get("ctc")
    low, high = ctc.get("band_low"), ctc.get("band_high")
    if isinstance(ctc_val, (int, float)) and isinstance(low, (int, float)) and isinstance(high, (int, float)):
        if ctc_val < low:
            issues.append({
                "issue": "Offered CTC below market band",
                "why": f"Offer {ctc_val:,} is under band low {low:,} {ctc.get('currency','')}",
                "fix": "Raise the offer toward band_mid or justify the discount.",
            })
        elif ctc_val > high:
            issues.append({
                "issue": "Offered CTC above market band",
                "why": f"Offer {ctc_val:,} exceeds band high {high:,} {ctc.get('currency','')}",
                "fix": "Confirm budget approval or cap the CTC.",
            })

    # Pre-start risk flags must be surfaced for the reviewer.
    for flag in compliance.get("risk_flags", []) or []:
        low_flag = flag.lower()
        if any(k in low_flag for k in ["before", "prior", "pre-", "work pass", "right to work"]):
            issues.append({
                "issue": "Pre-start statutory requirement",
                "why": flag,
                "fix": "Ensure the onboarding checklist front-loads this before day one.",
            })

    return {"issues": issues}


def _merge_verdicts(deterministic: dict[str, Any], llm: dict[str, Any]) -> dict[str, Any]:
    issues = list(deterministic.get("issues", [])) + list(llm.get("issues", []) or [])
    # De-dup by (issue, why).
    seen, merged = set(), []
    for it in issues:
        if not isinstance(it, dict):
            continue
        key = (it.get("issue", ""), it.get("why", ""))
        if key not in seen:
            seen.add(key)
            merged.append(it)

    severity = _worst_severity(merged, llm.get("severity"))
    passed = severity in ("none", "low")
    return {
        "passed": passed,
        "severity": severity,
        "issues": merged,
        "recommendations": list(llm.get("recommendations", []) or []),
        "reviewed_by": "compliance-critic",
    }


def _worst_severity(issues: list[dict[str, Any]], llm_severity: str | None) -> str:
    order = {"none": 0, "low": 1, "medium": 2, "high": 3}
    worst = order.get((llm_severity or "none").lower(), 0)
    for it in issues:
        text = f"{it.get('issue','')} {it.get('why','')}".lower()
        if any(k in text for k in ["below", "above", "pre-start", "before day one", "right to work", "work pass"]):
            worst = max(worst, 2)  # material issues are at least medium
    return {0: "none", 1: "low", 2: "medium", 3: "high"}[worst]


def _safe_json(content: str) -> dict[str, Any]:
    content = (content or "").strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content[:4].lower() == "json":
            content = content[4:]
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

"""HCM Autopilot Agent — Streamlit UI.

Enterprise workflow-automation agent that turns an ambiguous hiring request into
a complete, compliant onboarding package, with a human-in-the-loop approval
checkpoint. All reasoning flows through Qwen Cloud function calling.
"""

from __future__ import annotations

import json
import uuid
from datetime import date

import streamlit as st

from src.agent.orchestrator import PHASES, Orchestrator, Status
from src.ui.theme import (
    GLOBAL_CSS,
    brand_html,
    card_head,
    hero_html,
    icon,
    status_html,
    stepper_html,
)
from src.utils.audit import recent_events
from src.utils.oss_client import is_oss_configured, publish_package
from src.utils.qwen_client import METRICS, is_configured

st.set_page_config(
    page_title="HCM Autopilot Agent",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

def _init_state() -> None:
    st.session_state.setdefault("orchestrator", None)
    st.session_state.setdefault("chat", [])
    st.session_state.setdefault("session_id", uuid.uuid4().hex[:12])
    st.session_state.setdefault("reviewer", "")


def _reset() -> None:
    for key in ("orchestrator", "chat", "session_id"):
        st.session_state.pop(key, None)
    _init_state()


def _add_chat(role: str, content: str) -> None:
    st.session_state.chat.append((role, content))


def _html(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def _render_sidebar(active_phase: str) -> None:
    with st.sidebar:
        _html(brand_html())
        _html('<hr class="hcm-sep"/>')
        _html('<div class="hcm-side-title">Workflow</div>')
        _html(stepper_html(PHASES, active_phase))
        _html('<hr class="hcm-sep"/>')

        if is_configured():
            _html(status_html(True, "Qwen Cloud connected"))
        else:
            _html(status_html(False, "API key missing — set .env"))

        # Reviewer identity for the human-in-the-loop audit trail.
        st.session_state.reviewer = st.text_input(
            "Reviewer (for audit trail)",
            value=st.session_state.get("reviewer", ""),
            placeholder="you@company.com",
        )

        # Live observability: tokens / cost / latency across Qwen Cloud calls.
        m = METRICS.summary()
        if m["calls"]:
            _html('<hr class="hcm-sep"/>')
            _html('<div class="hcm-side-title">Session metrics</div>')
            c1, c2 = st.columns(2)
            c1.metric("Qwen calls", m["calls"])
            c2.metric("Tokens", f"{m['total_tokens']:,}")
            c1.metric("Latency", f"{m['total_latency_ms']/1000:.1f}s")
            c2.metric("Est. cost", f"${m['est_cost_usd']:.4f}")

        _html('<hr class="hcm-sep"/>')
        if st.button("Start new request", use_container_width=True):
            _reset()
            st.rerun()


# ---------------------------------------------------------------------------
# Artifact cards
# ---------------------------------------------------------------------------

def _loc_str(loc: dict | None) -> str:
    if not isinstance(loc, dict):
        return "—"
    return ", ".join(v for v in [loc.get("city"), loc.get("state"), loc.get("country")] if v) or "—"


def _render_steps(orch: Orchestrator) -> None:
    if not orch.state.steps:
        return
    _html(card_head("robot", "Agent reasoning & tool calls",
                    f"{len(orch.state.steps)} steps executed via Qwen function calling"))
    for i, step in enumerate(orch.state.steps, start=1):
        ico = "approval" if step.tool == "flag_for_approval" else "sparkle"
        label = step.tool.replace("_", " ")
        with st.expander(f"Step {i} · {label}", expanded=False):
            if step.reasoning:
                st.markdown(f"**Rationale:** {step.reasoning}")
            if step.arguments:
                st.caption("Arguments")
                st.json(step.arguments)
            st.caption("Result")
            st.json(step.result)


def _render_artifacts(orch: Orchestrator) -> None:
    art = orch.state.artifacts

    if "parsed_request" in art:
        parsed = art["parsed_request"]
        _html(card_head("parse", "Parsed hiring request",
                        f"confidence {parsed.get('confidence', 0):.0%}"))
        c1, c2, c3 = st.columns(3)
        c1.metric("Role", parsed.get("role") or "—")
        c2.metric("Level", parsed.get("level") or "—")
        c3.metric("Location", _loc_str(parsed.get("location")))
        if parsed.get("assumptions_made"):
            for a in parsed["assumptions_made"]:
                _html(f'<span class="hcm-pill">{icon("sparkle",13)} {a}</span>')
        with st.expander("Full parse output", expanded=False):
            st.json(parsed)

    if "compliance" in art:
        comp = art["compliance"]
        geo = comp.get("country", "")
        if comp.get("state"):
            geo += f" · {comp['state']}"
        _html(card_head("compliance", "Compliance summary", geo, tone="good"))
        c1, c2 = st.columns(2)
        c1.metric("Notice period", comp.get("notice_period_norm", "—"))
        c2.metric("Probation", comp.get("probation_period", "—"))
        for flag in comp.get("risk_flags", []):
            _html(f'<span class="hcm-pill warn">{icon("alert",13)} {flag}</span>')
        with st.expander("Benefits, documents & statutory filings", expanded=False):
            st.json(comp)

    if "ctc" in art:
        ctc = art["ctc"]
        cur = ctc.get("currency", "")
        _html(card_head("ctc", "CTC band estimate", ctc.get("notes", ""), tone=""))
        c1, c2, c3 = st.columns(3)
        c1.metric("Low", f"{cur} {ctc.get('band_low', 0):,}")
        c2.metric("Mid", f"{cur} {ctc.get('band_mid', 0):,}")
        c3.metric("High", f"{cur} {ctc.get('band_high', 0):,}")
        with st.expander("Compensation breakdown", expanded=False):
            st.json(ctc)

    if "offer_letter" in art:
        offer = art["offer_letter"]
        _html(card_head("offer", "Offer letter draft",
                        offer.get("review_reason", ""), tone="warn"))
        with st.container(border=True):
            st.markdown(offer.get("letter_content", ""))

    if "compliance_review" in art:
        rev = art["compliance_review"]
        passed = rev.get("passed", True)
        sev = rev.get("severity", "none")
        tone = "good" if passed else "warn"
        _html(card_head("shield", "Compliance-Critic review",
                        f"verdict: {'PASSED' if passed else 'ISSUES'} · severity {sev}",
                        tone=tone))
        if passed and not rev.get("issues"):
            _html(f'<span class="hcm-pill good">{icon("check",13)} No compliance issues found</span>')
        for it in rev.get("issues", []):
            _html(
                f'<span class="hcm-pill warn">{icon("alert",13)} {it.get("issue","")}</span>'
            )
        if rev.get("issues") or rev.get("recommendations"):
            with st.expander("Critic findings", expanded=not passed):
                st.json(rev)

    if "checklist" in art:
        chk = art["checklist"]
        _html(card_head("checklist", "Onboarding checklist & timeline",
                        f"{chk.get('total_tasks', 0)} tasks · critical path "
                        f"{chk.get('critical_path_days', 0)} days", tone="good"))
        _html(_timeline_html(chk.get("checklist", [])))
        with st.expander("Checklist table", expanded=False):
            st.dataframe(chk.get("checklist", []), use_container_width=True, hide_index=True)


def _timeline_html(checklist: list[dict]) -> str:
    """Render the onboarding checklist as a vertical timeline."""
    owner_tone = {
        "HR": "#6366f1", "HR Ops": "#8b5cf6", "IT": "#22d3ee", "Payroll": "#34d399",
        "Hiring Manager": "#fbbf24",
    }
    rows = []
    for t in checklist:
        color = owner_tone.get(t.get("owner", ""), "#8a95ad")
        due = t.get("due_date", "")
        rows.append(
            '<div class="hcm-step">'
            '<span class="rail"></span>'
            f'<span class="hcm-node" style="border-color:{color};color:{color};">'
            f'<b style="font-size:.62rem;">{t.get("deadline","")}</b></span>'
            '<div style="display:flex;flex-direction:column;">'
            f'<span class="lbl" style="color:#e6ebf5;font-weight:600;">{t.get("task","")}</span>'
            f'<span style="font-size:.72rem;color:{color};">{t.get("owner","")}'
            + (f' · {due}' if due else "") + "</span></div></div>"
        )
    return '<div class="hcm-stepper" style="margin:.4rem 0;">' + "".join(rows) + "</div>"


# ---------------------------------------------------------------------------
# Approval gate
# ---------------------------------------------------------------------------

def _render_approval(orch: Orchestrator) -> None:
    summary = orch.state.approval_summary or {}
    band = summary.get("ctc_band") or {}
    ctc_val = (
        f"{band.get('currency', '')} {band.get('mid', 0):,}" if band.get("mid") else "—"
    )
    _html(
        '<div class="hcm-gate"><div class="g-head">'
        f'{icon("approval",20)} Human approval required</div>'
        '<p style="color:#c9cfe0;margin:.4rem 0 0;font-size:.92rem;">'
        "Review the summary below. The agent will not generate the final package "
        "until you approve.</p></div>"
    )

    with st.container(border=True):
        _html(card_head("pin", "Checkpoint summary"))
        c1, c2 = st.columns(2)
        with c1:
            _html(f'<div class="hcm-kv"><span class="k">Role</span><span class="v">{summary.get("role") or "—"}</span></div>')
            _html(f'<div class="hcm-kv"><span class="k">Location</span><span class="v">{_loc_str(summary.get("location"))}</span></div>')
        with c2:
            _html(f'<div class="hcm-kv"><span class="k">CTC (mid)</span><span class="v">{ctc_val}</span></div>')
            _html(f'<div class="hcm-kv"><span class="k">Start date</span><span class="v">{summary.get("start_date") or "—"}</span></div>')
        for f in summary.get("compliance_risk_flags", []):
            _html(f'<span class="hcm-pill warn">{icon("alert",13)} {f}</span>')

    st.write("")
    col_a, col_b = st.columns([1, 1])
    with col_a:
        if st.button("Approve & generate checklist", type="primary", use_container_width=True):
            _add_chat("user", "Approved — proceed to generate the onboarding checklist.")
            with st.spinner("Generating onboarding package…"):
                orch.submit_approval(
                    "approved",
                    reviewer=st.session_state.get("reviewer") or None,
                    session_id=st.session_state.get("session_id"),
                )
            _after_run(orch)
            st.rerun()
    with col_b:
        with st.form("revise_form", clear_on_submit=True):
            notes = st.text_input(
                "Revision notes", placeholder="e.g. CTC too high, cap at 30L",
                label_visibility="collapsed",
            )
            if st.form_submit_button("Request revision", use_container_width=True) and notes.strip():
                _add_chat("user", f"Revise: {notes.strip()}")
                with st.spinner("Re-running the affected steps…"):
                    orch.submit_approval("revise", notes.strip())
                _after_run(orch)
                st.rerun()


# ---------------------------------------------------------------------------
# Final package / download
# ---------------------------------------------------------------------------

def _render_download(orch: Orchestrator) -> None:
    package = orch.build_package()
    _html(
        '<div class="hcm-gate" style="border-color:rgba(52,211,153,.4);'
        'background:linear-gradient(180deg,rgba(52,211,153,.10),rgba(52,211,153,.03));">'
        '<div class="g-head" style="color:#34d399;">'
        f'{icon("complete",20)} Onboarding package complete</div>'
        '<p style="color:#c9cfe0;margin:.4rem 0 0;font-size:.92rem;">'
        "Export the full package — offer letter, compliance summary, CTC breakdown "
        "and onboarding checklist.</p></div>"
    )
    c1, c2, c3 = st.columns(3)
    c1.download_button(
        "Download JSON",
        data=json.dumps(package, indent=2, default=str).encode("utf-8"),
        file_name="onboarding_package.json", mime="application/json",
        use_container_width=True,
    )
    c2.download_button(
        "Download Markdown",
        data=_package_to_markdown(package).encode("utf-8"),
        file_name="onboarding_package.md", mime="text/markdown",
        use_container_width=True,
    )
    with c3:
        if st.button("Publish to Alibaba Cloud OSS", use_container_width=True,
                     disabled=not is_oss_configured(),
                     help=None if is_oss_configured()
                     else "Set ALIBABA_CLOUD_ACCESS_KEY_ID/SECRET and OSS_BUCKET to enable"):
            res = publish_package(package)
            if res.get("published"):
                st.success(f"Published: {res['uri']}")
            else:
                st.warning(res.get("reason", "OSS publish failed"))

    # Audit trail for this session (reviewer, decision, timestamp).
    events = recent_events(limit=20, session_id=st.session_state.get("session_id"))
    if events:
        with st.expander("Audit trail", expanded=False):
            st.dataframe(
                [{"time": e["ts"], "event": e["event_type"], "actor": e["actor"]} for e in events],
                use_container_width=True, hide_index=True,
            )


def _package_to_markdown(package: dict) -> str:
    parsed = (package.get("hiring_request") or {}).get("parsed") or {}
    comp = package.get("compliance_summary") or {}
    ctc = package.get("ctc_breakdown") or {}
    offer = package.get("offer_letter") or {}
    chk = package.get("onboarding_checklist") or {}

    lines = ["# Onboarding Package", ""]
    lines += ["## Hiring Request", "```json", json.dumps(parsed, indent=2), "```", ""]
    lines += ["## Compliance Summary", "```json", json.dumps(comp, indent=2), "```", ""]
    lines += ["## CTC Breakdown", "```json", json.dumps(ctc, indent=2), "```", ""]
    lines += ["## Offer Letter", "", offer.get("letter_content", ""), ""]
    lines += ["## Onboarding Checklist", "", "| Task | Owner | Deadline | Status |",
              "|---|---|---|---|"]
    for t in chk.get("checklist", []):
        lines.append(
            f"| {t.get('task','')} | {t.get('owner','')} | "
            f"{t.get('deadline','')} | {t.get('status','')} |"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    _init_state()
    orch: Orchestrator | None = st.session_state.orchestrator
    active_phase = orch.state.phase if orch else PHASES[0]
    _render_sidebar(active_phase)

    _html(hero_html(
        "Autonomous hiring operations",
        "HCM Autopilot Agent",
        "Turn an ambiguous hiring request into a complete, compliant onboarding "
        "package — decomposed, reasoned, and executed with a human approval gate.",
    ))

    for role, content in st.session_state.chat:
        with st.chat_message(role):
            st.markdown(content)

    # Intake state
    if orch is None:
        with st.chat_message("assistant"):
            st.markdown(
                "Describe the role you want to hire — even vaguely. For example: "
                "*“We need a senior backend dev in Bangalore, starting next month.”*"
            )
        prompt = st.chat_input("Enter your hiring request…")
        if prompt:
            if not is_configured():
                st.error("QWEN_CLOUD_API_KEY is not set. Add it to your .env first.")
                st.stop()
            orch = Orchestrator(today=date.today().isoformat())
            st.session_state.orchestrator = orch
            _add_chat("user", prompt)
            with st.spinner("Agent is decomposing the request…"):
                orch.start(prompt)
            _after_run(orch)
            st.rerun()
        return

    _render_steps(orch)
    _render_artifacts(orch)

    status = orch.state.status
    if status == Status.ERROR:
        st.error(f"Agent error: {orch.state.error}")
    elif status == Status.AWAITING_APPROVAL:
        _render_approval(orch)
    elif status == Status.AWAITING_CLARIFICATION:
        with st.chat_message("assistant"):
            st.markdown(orch.state.assistant_message or "Could you share a bit more detail?")
        prompt = st.chat_input("Your reply…")
        if prompt:
            _add_chat("user", prompt)
            with st.spinner("Agent is working…"):
                orch.submit_clarification(prompt)
            _after_run(orch)
            st.rerun()
    elif status == Status.COMPLETE:
        if orch.state.assistant_message:
            with st.chat_message("assistant"):
                st.markdown(orch.state.assistant_message)
        _render_download(orch)


def _after_run(orch: Orchestrator) -> None:
    msg = orch.state.assistant_message
    if msg and orch.state.status in (Status.AWAITING_CLARIFICATION, Status.COMPLETE):
        _add_chat("assistant", msg)


if __name__ == "__main__":
    main()

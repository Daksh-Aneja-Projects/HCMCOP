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

from src.agent.council import contradiction_graph_dot
from src.agent.integration import IntegrationOrchestrator, IStatus
from src.agent.orchestrator import Orchestrator, Status
from src.agent.workflows import get_by_label, workflow_labels
from src.ui.theme import (
    GLOBAL_CSS,
    brand_html,
    card_head,
    hero_html,
    icon,
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
    st.session_state.setdefault("integration", None)
    st.session_state.setdefault("chat", [])
    st.session_state.setdefault("session_id", uuid.uuid4().hex[:12])
    st.session_state.setdefault("reviewer", "")
    st.session_state.setdefault("mode", "Single Hire")


def _reset() -> None:
    for key in ("orchestrator", "integration", "chat", "session_id"):
        st.session_state.pop(key, None)
    _init_state()


def _add_chat(role: str, content: str) -> None:
    st.session_state.chat.append((role, content))


def _html(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def _render_sidebar() -> None:
    with st.sidebar:
        _html(brand_html())
        _html('<hr class="hcm-sep"/>')

        # Mode selector — driven by the workflow registry.
        labels = workflow_labels()
        current = st.session_state.get("mode", labels[0])
        st.session_state.mode = st.radio(
            "Workflow mode", labels,
            index=labels.index(current) if current in labels else 0,
            label_visibility="collapsed",
        )
        wf = get_by_label(st.session_state.mode)

        _html('<hr class="hcm-sep"/>')
        _html('<div class="hcm-side-title">Workflow</div>')
        if wf.key == "ma_integration":
            ig: IntegrationOrchestrator | None = st.session_state.integration
            active = ig.state.phase if ig else wf.phases[0]
        else:
            orch: Orchestrator | None = st.session_state.orchestrator
            active = orch.state.phase if orch else wf.phases[0]
        _html(stepper_html(wf.phases, active))
        # Live observability: tokens / cost / latency across Qwen Cloud calls.
        m = METRICS.summary()
        if m["calls"]:
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


def _pills(items: list, cls: str = "", ico: str = "sparkle") -> str:
    """Render a list of strings as inline-flowing pills within one block."""
    if not items:
        return ""
    chips = "".join(
        f'<span class="hcm-pill {cls}">{icon(ico, 13)} {x}</span>' for x in items
    )
    return f'<div class="hcm-pillrow">{chips}</div>'


def _render_artifacts(orch: Orchestrator) -> None:
    art = orch.state.artifacts

    if "parsed_request" in art:
        parsed = art["parsed_request"]
        with st.container(border=True):
            _html(card_head("parse", "Parsed hiring request",
                            f"confidence {parsed.get('confidence', 0):.0%}"))
            c1, c2, c3 = st.columns(3)
            c1.metric("Role", parsed.get("role") or "—")
            c2.metric("Level", parsed.get("level") or "—")
            c3.metric("Location", _loc_str(parsed.get("location")))
            _html(_pills(parsed.get("assumptions_made", []), "", "sparkle"))
            with st.expander("Full parse output", expanded=False):
                st.json(parsed)

    if "compliance" in art:
        comp = art["compliance"]
        geo = comp.get("country", "")
        if comp.get("state"):
            geo += f" · {comp['state']}"
        with st.container(border=True):
            _html(card_head("compliance", "Compliance summary", geo, tone="good"))
            c1, c2 = st.columns(2)
            c1.metric("Notice period", comp.get("notice_period_norm", "—"))
            c2.metric("Probation", comp.get("probation_period", "—"))
            _html(_pills(comp.get("risk_flags", []), "warn", "alert"))
            with st.expander("Benefits, documents & statutory filings", expanded=False):
                st.json(comp)

    if "ctc" in art:
        ctc = art["ctc"]
        cur = ctc.get("currency", "")
        with st.container(border=True):
            _html(card_head("ctc", "CTC band estimate", ctc.get("notes", "")))
            c1, c2, c3 = st.columns(3)
            c1.metric("Low", f"{cur} {ctc.get('band_low', 0):,}")
            c2.metric("Mid", f"{cur} {ctc.get('band_mid', 0):,}")
            c3.metric("High", f"{cur} {ctc.get('band_high', 0):,}")
            with st.expander("Compensation breakdown", expanded=False):
                st.json(ctc)

    if "offer_letter" in art:
        offer = art["offer_letter"]
        with st.container(border=True):
            _html(card_head("offer", "Offer letter draft",
                            offer.get("review_reason", ""), tone="warn"))
            st.markdown(offer.get("letter_content", ""))

    if "compliance_review" in art:
        rev = art["compliance_review"]
        passed = rev.get("passed", True)
        sev = rev.get("severity", "none")
        with st.container(border=True):
            _html(card_head("shield", "Compliance-Critic review",
                            f"verdict: {'PASSED' if passed else 'ISSUES'} · severity {sev}",
                            tone="good" if passed else "warn"))
            if passed and not rev.get("issues"):
                _html(_pills(["No compliance issues found"], "good", "check"))
            else:
                _html(_pills([it.get("issue", "") for it in rev.get("issues", [])], "warn", "alert"))
            if rev.get("issues") or rev.get("recommendations"):
                with st.expander("Critic findings", expanded=not passed):
                    st.json(rev)

    if "checklist" in art:
        chk = art["checklist"]
        with st.container(border=True):
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
        _html(_pills(summary.get("compliance_risk_flags", []), "warn", "alert"))

    # Reviewer identity is captured here (recorded in the audit trail on decision).
    st.session_state.reviewer = st.text_input(
        "Your name or email (recorded in the audit trail)",
        value=st.session_state.get("reviewer", ""),
        placeholder="you@company.com",
    )

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
    _render_sidebar()
    wf = get_by_label(st.session_state.mode)
    if wf.key == "ma_integration":
        _run_integration(wf)
    else:
        _run_hiring(wf)


def _run_hiring(wf) -> None:
    orch: Orchestrator | None = st.session_state.orchestrator
    _html(hero_html(wf.hero_eyebrow, wf.hero_title, wf.hero_subtitle))

    for role, content in st.session_state.chat:
        with st.chat_message(role):
            st.markdown(content)

    if orch is None:
        with st.chat_message("assistant"):
            st.markdown(wf.intake_hint)
        prompt = st.chat_input(wf.intake_placeholder)
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


# ---------------------------------------------------------------------------
# Workforce Integration (M&A) — multi-agent council with conflict resolution
# ---------------------------------------------------------------------------

_AGENT_COLOR = {"Policy": "#8b5cf6", "Compensation": "#22d3ee",
                "Compliance": "#fb7185", "Orchestrator": "#6366f1"}
_SEV_TONE = {"low": "", "medium": "warn", "high": "warn", "critical": "warn", "none": "good"}


def _run_integration(wf) -> None:
    ig: IntegrationOrchestrator | None = st.session_state.integration
    _html(hero_html(wf.hero_eyebrow, wf.hero_title, wf.hero_subtitle))

    if ig is None:
        with st.chat_message("assistant"):
            st.markdown(wf.intake_hint)
        prompt = st.chat_input(wf.intake_placeholder)
        if prompt:
            if not is_configured():
                st.warning("Running offline — the council will use its deterministic "
                           "domain layer. Add QWEN_CLOUD_API_KEY for full agent reasoning.")
            ig = IntegrationOrchestrator()
            st.session_state.integration = ig
            with st.spinner("Convening the agent council…"):
                ig.start(prompt)
            st.rerun()
        return

    report = ig.state.report
    if ig.state.status == IStatus.ERROR or report is None:
        st.error(f"Council error: {ig.state.error}")
        return

    _render_context(report.context)
    _render_positions(report.positions)
    _render_graph(report)
    _render_conflicts(ig)
    _render_plan(report)

    if ig.state.status == IStatus.COMPLETE:
        _render_integration_download(ig)


def _render_context(ctx: dict) -> None:
    with st.container(border=True):
        _html(card_head("robot", "Integration brief",
                        "decomposed by the Orchestrator agent"))
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Country", ctx.get("country", "—"))
        c2.metric("Headcount", ctx.get("headcount") or "—")
        c3.metric("Timeline", ctx.get("timeline", "—"))
        c4.metric("Agents", "3 + Orchestrator")
        _html(_pills(ctx.get("parent_policies", []), "", "pin"))


def _render_positions(positions: list) -> None:
    with st.container(border=True):
        _html(card_head("compliance", "Agent positions",
                        f"{len(positions)} positions from independent specialists"))
        by_agent: dict[str, list] = {}
        for p in positions:
            by_agent.setdefault(p.agent, []).append(p)
        cols = st.columns(len(by_agent) or 1)
        for col, (agent, items) in zip(cols, by_agent.items()):
            color = _AGENT_COLOR.get(agent, "#5f6b85")
            with col:
                cards = "".join(
                    '<div class="hcm-agentcard">'
                    f'<div class="a-head"><span class="a-badge" style="background:{color};">'
                    f'{agent}</span><span class="hcm-pill {_SEV_TONE.get(p.severity,"")}">'
                    f'{p.stance} · {p.severity}</span></div>'
                    f'<div class="a-stmt">{p.statement}</div>'
                    f'<div class="a-why">{p.rationale}</div></div>'
                    for p in items
                )
                _html(cards)


def _render_graph(report) -> None:
    with st.container(border=True):
        n_conf = len(report.conflicts)
        resolved = sum(1 for c in report.conflicts if c.resolution)
        _html(card_head("alert", "Contradiction graph",
                        f"{n_conf} conflicts · {resolved} resolved",
                        tone="good" if resolved == n_conf else "warn"))
        try:
            st.graphviz_chart(contradiction_graph_dot(report), use_container_width=True)
        except Exception:
            st.caption("Graph unavailable in this environment.")


def _render_conflicts(ig: IntegrationOrchestrator) -> None:
    report = ig.state.report
    open_conflicts = [c for c in report.conflicts if c.resolution is None]
    if open_conflicts:
        _html(
            '<div class="hcm-gate"><div class="g-head">'
            f'{icon("approval",20)} {len(open_conflicts)} conflict(s) need human resolution'
            '</div><p style="color:#c9cfe0;margin:.4rem 0 0;font-size:.92rem;">'
            "The Orchestrator escalated these because the agents cannot both be "
            "satisfied. Review each and choose a resolution.</p></div>"
        )

    idx = {p.id: p for p in report.positions}
    for c in report.conflicts:
        resolved = c.resolution is not None
        cls = "hcm-conflict resolved" if resolved else "hcm-conflict"
        a, b = (idx.get(c.between[0]), idx.get(c.between[1])) if len(c.between) == 2 else (None, None)
        head = (
            f'<div class="{cls}"><div class="a-head">'
            f'<span class="hcm-pill {"good" if resolved else "warn"}">'
            f'{icon("check",13) if resolved else icon("alert",13)} {c.id} · risk {c.risk}</span>'
            f'<b style="color:#e6ebf5;">{c.summary}</b></div>'
        )
        vs = ""
        if a and b:
            vs = (
                '<div class="hcm-vs">'
                f'<div class="side"><div class="who" style="color:{_AGENT_COLOR.get(a.agent)};">'
                f'{a.agent} ({a.id})</div><div class="txt">{a.statement}</div></div>'
                '<div class="clash">✕</div>'
                f'<div class="side"><div class="who" style="color:{_AGENT_COLOR.get(b.agent)};">'
                f'{b.agent} ({b.id})</div><div class="txt">{b.statement}</div></div></div>'
            )
        risk = f'<div class="a-why"><b>Risk:</b> {c.risk_assessment}</div></div>'
        _html(head + vs + risk)

        if resolved:
            _html(_pills([f"Resolved: {c.resolution}"], "good", "check"))
        else:
            labels = [f"{o.id}{' ★' if o.recommended else ''} — {o.option}" for o in c.options]
            choice = st.radio(
                f"Resolution for {c.id}", labels, key=f"opt_{c.id}",
                index=next((i for i, o in enumerate(c.options) if o.recommended), 0),
            )
            note = st.text_input("Note (optional)", key=f"note_{c.id}",
                                 placeholder="rationale for the audit trail")
            if st.button(f"Resolve {c.id}", key=f"res_{c.id}", type="primary"):
                opt_id = c.options[labels.index(choice)].id
                ig.resolve_conflict(c.id, opt_id, note)
                st.rerun()


def _render_plan(report) -> None:
    with st.container(border=True):
        blocked = sum(1 for p in report.phases if p.blocked_by)
        _html(card_head("checklist", "Dependency-phased integration plan",
                        f"{len(report.phases)} phases · {blocked} currently blocked",
                        tone="good" if blocked == 0 else "warn"))
        rows = []
        for ph in report.phases:
            state_color = "#fb7185" if ph.blocked_by else ("#22d3ee" if ph.parallelizable else "#8b5cf6")
            tag = ("blocked by " + ", ".join(ph.blocked_by)) if ph.blocked_by else (
                "parallel" if ph.parallelizable else "sequential")
            deps = (" · depends on " + ", ".join(ph.depends_on)) if ph.depends_on else ""
            rows.append(
                '<div class="hcm-step"><span class="rail"></span>'
                f'<span class="hcm-node" style="border-color:{state_color};color:{state_color};">'
                f'<b style="font-size:.6rem;">{ph.id}</b></span>'
                '<div style="display:flex;flex-direction:column;">'
                f'<span class="lbl" style="color:#e6ebf5;font-weight:600;">{ph.name}</span>'
                f'<span style="font-size:.72rem;color:{state_color};">{ph.window} · {ph.owner} · {tag}{deps}</span>'
                '</div></div>'
            )
        _html('<div class="hcm-stepper" style="margin:.4rem 0;">' + "".join(rows) + "</div>")


def _render_integration_download(ig: IntegrationOrchestrator) -> None:
    package = ig.build_package()
    _html(
        '<div class="hcm-gate" style="border-color:rgba(52,211,153,.4);'
        'background:linear-gradient(180deg,rgba(52,211,153,.10),rgba(52,211,153,.03));">'
        '<div class="g-head" style="color:#34d399;">'
        f'{icon("complete",20)} All conflicts resolved — integration plan ready</div>'
        '<p style="color:#c9cfe0;margin:.4rem 0 0;font-size:.92rem;">'
        "Export the full council report: positions, contradiction graph, resolutions "
        "and the dependency-phased plan.</p></div>"
    )
    c1, c2 = st.columns(2)
    c1.download_button(
        "Download council report (JSON)",
        data=json.dumps(package, indent=2, default=str).encode("utf-8"),
        file_name="integration_report.json", mime="application/json",
        use_container_width=True,
    )
    with c2:
        if st.button("Publish to Alibaba Cloud OSS", use_container_width=True,
                     disabled=not is_oss_configured(),
                     help=None if is_oss_configured() else "Set OSS_* env vars to enable"):
            res = publish_package(package)
            st.success(f"Published: {res['uri']}") if res.get("published") \
                else st.warning(res.get("reason", "OSS publish failed"))


if __name__ == "__main__":
    main()

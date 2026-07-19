"""Workflow registry.

The agent supports multiple Autopilot workflows. Rather than hard-coding each
one into the UI, every workflow is registered here as a ``WorkflowDef`` carrying
its label, phases, hero copy and intake prompt. The Streamlit layer renders the
mode selector, the phase stepper and the intake from this registry, so adding a
new workflow is one entry here plus a runner — not edits scattered across the UI.
"""

from __future__ import annotations

from dataclasses import dataclass

from .integration import INTEGRATION_PHASES
from .orchestrator import PHASES as HIRING_PHASES


@dataclass(frozen=True)
class WorkflowDef:
    key: str                 # stable id used for routing
    label: str               # sidebar selector label
    phases: list[str]        # phase-stepper labels
    hero_eyebrow: str
    hero_title: str
    hero_subtitle: str
    intake_placeholder: str
    intake_hint: str         # assistant example shown before the first message
    offline_ok: bool = False  # can run without a live key (deterministic layer)


SINGLE_HIRE = WorkflowDef(
    key="single_hire",
    label="Single Hire",
    phases=HIRING_PHASES,
    hero_eyebrow="Autonomous hiring operations",
    hero_title="HCM Autopilot Agent",
    hero_subtitle=(
        "Turn an ambiguous hiring request into a complete, compliant onboarding "
        "package — decomposed, reasoned, and executed with a human approval gate."
    ),
    intake_placeholder="Enter your hiring request…",
    intake_hint=(
        "Describe the role you want to hire — even vaguely. For example: "
        "*“We need a senior backend dev in Bangalore, starting next month.”*"
    ),
    offline_ok=False,
)

MA_INTEGRATION = WorkflowDef(
    key="ma_integration",
    label="Workforce Integration (M&A)",
    phases=INTEGRATION_PHASES,
    hero_eyebrow="Multi-agent workforce integration",
    hero_title="HCM Autopilot · Council",
    hero_subtitle=(
        "Specialist agents reason independently, disagree, and resolve conflicts "
        "visibly — with a human-in-the-loop on every escalation."
    ),
    intake_placeholder="Describe the integration task…",
    intake_hint=(
        "Describe a macro workforce-integration task. For example: "
        "*“We're acquiring a 200-person company in Germany. Integrate their "
        "workforce by Q1.”*"
    ),
    offline_ok=True,
)

# Registry — order defines the sidebar selector order.
WORKFLOWS: list[WorkflowDef] = [SINGLE_HIRE, MA_INTEGRATION]


def workflow_labels() -> list[str]:
    return [w.label for w in WORKFLOWS]


def get_by_label(label: str) -> WorkflowDef:
    for w in WORKFLOWS:
        if w.label == label:
            return w
    return WORKFLOWS[0]

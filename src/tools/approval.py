"""Tool: flag_for_approval — the human-in-the-loop gate.

This tool does NOT auto-approve. When the orchestrator invokes it, execution
PAUSES: the tool returns a ``status: "awaiting_approval"`` payload that the
Streamlit layer renders as an approval checkpoint with Approve / Revise
controls. The user's explicit decision is fed back into the orchestrator on the
next turn.

Keeping this as a real tool (rather than pure UI logic) means the pause point
is part of the agent's reasoning trace and shows up in the function-calling
transcript.
"""

from __future__ import annotations

from typing import Any


def flag_for_approval(summary: dict[str, Any]) -> dict[str, Any]:
    """Raise a human-in-the-loop approval checkpoint.

    Args:
        summary: A structured summary of everything produced so far (parsed
            request, compliance, CTC, offer letter key terms) that the human
            reviewer needs in order to decide.

    Returns:
        A payload flagged ``awaiting_approval``. The agent must stop and wait;
        it must not proceed to generate the final package until the human
        responds via the UI.
    """
    return {
        "status": "awaiting_approval",
        "requires_human_input": True,
        "message": (
            "Human approval required before generating the final onboarding "
            "package. Review the summary and choose Approve or Revise."
        ),
        "summary": summary or {},
        "decision": None,  # populated by the UI: "approved" | "revise"
    }

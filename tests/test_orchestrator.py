"""Tests for the orchestrator agent loop.

The Qwen Cloud client is mocked so these tests run offline and deterministically
while still exercising the real function-calling control flow, artifact
collection, human-in-the-loop pause, and the revise/re-run path.
"""

import json
from unittest.mock import patch

import pytest

from src.agent.orchestrator import Orchestrator, Status, available_tool_names


# ---------------------------------------------------------------------------
# Lightweight fakes mimicking the OpenAI SDK response shape.
# ---------------------------------------------------------------------------

class _Func:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments


class _ToolCall:
    def __init__(self, call_id, name, arguments):
        self.id = call_id
        self.type = "function"
        self.function = _Func(name, arguments)


class _Message:
    def __init__(self, content="", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class _Choice:
    def __init__(self, message):
        self.message = message


class _Response:
    def __init__(self, message):
        self.choices = [_Choice(message)]


def _tool_msg(call_id, name, args: dict):
    return _Response(_Message(tool_calls=[_ToolCall(call_id, name, json.dumps(args))]))


def _text_msg(text):
    return _Response(_Message(content=text))


PARSED_COMPLETE = {
    "role": "Senior Backend Developer",
    "level": "Senior (IC3)",
    "department": "Engineering",
    "location": {"city": "Bangalore", "state": "Karnataka", "country": "India"},
    "start_date": "2026-08-15",
    "employment_type": "Full-time",
    "missing_fields": [],
    "assumptions_made": [],
    "confidence": 0.9,
}

PARSED_AMBIGUOUS = {
    "role": None,
    "level": None,
    "department": None,
    "location": None,
    "start_date": None,
    "employment_type": "Full-time",
    "missing_fields": ["role", "location"],
    "assumptions_made": [],
    "confidence": 0.3,
}


def _parse_json(parsed: dict) -> str:
    """Fake return for the parser's structured_completion call (a JSON string)."""
    return json.dumps(parsed)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_available_tools_exposes_all_six():
    names = available_tool_names()
    for expected in (
        "parse_hiring_request",
        "check_geo_compliance",
        "estimate_ctc_band",
        "generate_offer_letter",
        "create_onboarding_checklist",
        "flag_for_approval",
    ):
        assert expected in names


def test_full_pipeline_pauses_at_approval_then_completes():
    orch_turns = [
        _tool_msg("c1", "parse_hiring_request", {"raw_request": "hire senior backend dev Bangalore"}),
        _tool_msg("c2", "check_geo_compliance", {"country": "India", "state": "Karnataka"}),
        _tool_msg("c3", "estimate_ctc_band", {
            "role": "Senior Backend Developer", "level": "Senior (IC3)",
            "location": {"city": "Bangalore", "country": "India"},
        }),
        _tool_msg("c4", "generate_offer_letter", {}),
        _tool_msg("c5", "flag_for_approval", {"note": "confirm CTC"}),
        # After approval:
        _tool_msg("c6", "create_onboarding_checklist", {}),
        _text_msg("All done — the onboarding package is ready."),
    ]

    with patch("src.agent.orchestrator.chat_completion", side_effect=orch_turns), \
         patch("src.tools.parse_request.structured_completion", return_value=_parse_json(PARSED_COMPLETE)):
        orch = Orchestrator(today="2026-07-19")
        state = orch.start("Hire a senior backend dev in Bangalore, start Aug 15, Engineering.")

        # Must pause at the human-in-the-loop gate, NOT auto-complete.
        assert state.status == Status.AWAITING_APPROVAL
        assert state.approval_summary is not None
        assert "parsed_request" in state.artifacts
        assert "compliance" in state.artifacts
        assert "ctc" in state.artifacts
        assert "offer_letter" in state.artifacts
        # Checklist must NOT exist before approval.
        assert "checklist" not in state.artifacts

        # Approve and resume.
        state = orch.submit_approval("approved")
        assert state.status == Status.COMPLETE
        assert "checklist" in state.artifacts

        package = orch.build_package()
        assert package["approved"] is True
        assert package["onboarding_checklist"]["total_tasks"] >= 6


def test_ambiguous_request_asks_for_clarification():
    orch_turns = [
        _tool_msg("c1", "parse_hiring_request", {"raw_request": "we need someone for the backend team"}),
        _text_msg("Could you tell me the seniority level and the location for this role?"),
    ]
    with patch("src.agent.orchestrator.chat_completion", side_effect=orch_turns), \
         patch("src.tools.parse_request.structured_completion", return_value=_parse_json(PARSED_AMBIGUOUS)):
        orch = Orchestrator(today="2026-07-19")
        state = orch.start("We need someone for the backend team")

        assert state.status == Status.AWAITING_CLARIFICATION
        assert "location" in state.assistant_message.lower() or "level" in state.assistant_message.lower()
        # Parser flagged the missing critical fields.
        assert state.artifacts["parsed_request"]["needs_clarification"] is True


def test_revise_flow_reruns_ctc_with_cap():
    orch_turns = [
        _tool_msg("c1", "parse_hiring_request", {"raw_request": "hire senior backend dev Bangalore"}),
        _tool_msg("c2", "check_geo_compliance", {"country": "India", "state": "Karnataka"}),
        _tool_msg("c3", "estimate_ctc_band", {
            "role": "Senior Backend Developer", "level": "Senior",
            "location": {"city": "Bangalore", "country": "India"},
        }),
        _tool_msg("c4", "generate_offer_letter", {}),
        _tool_msg("c5", "flag_for_approval", {}),
        # After "revise: cap at 30L" -> re-run CTC with cap, re-draft, re-flag.
        _tool_msg("c6", "estimate_ctc_band", {
            "role": "Senior Backend Developer", "level": "Senior",
            "location": {"city": "Bangalore", "country": "India"}, "max_ctc": 3000000,
        }),
        _tool_msg("c7", "generate_offer_letter", {}),
        _tool_msg("c8", "flag_for_approval", {}),
        # Then approve.
        _tool_msg("c9", "create_onboarding_checklist", {}),
        _text_msg("Revised and ready."),
    ]
    with patch("src.agent.orchestrator.chat_completion", side_effect=orch_turns), \
         patch("src.tools.parse_request.structured_completion", return_value=_parse_json(PARSED_COMPLETE)):
        orch = Orchestrator(today="2026-07-19")
        state = orch.start("Hire a senior backend dev in Bangalore.")
        assert state.status == Status.AWAITING_APPROVAL

        # Reject with a revision note -> should pause again at approval.
        state = orch.submit_approval("revise", "CTC too high, cap at 30L")
        assert state.status == Status.AWAITING_APPROVAL
        # CTC must now reflect the cap.
        assert state.artifacts["ctc"].get("cap_applied") == 3000000
        assert state.artifacts["ctc"]["band_high"] <= 3000000

        # Now approve.
        state = orch.submit_approval("approved")
        assert state.status == Status.COMPLETE
        assert orch.build_package()["approved"] is True


def test_error_status_on_llm_failure():
    with patch("src.agent.orchestrator.chat_completion", side_effect=RuntimeError("boom")):
        orch = Orchestrator()
        state = orch.start("anything")
        assert state.status == Status.ERROR
        assert "boom" in (state.error or "")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

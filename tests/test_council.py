"""Tests for the multi-agent council + integration orchestrator (offline).

These run without an API key, exercising the deterministic domain layer that
guarantees the signature M&A conflicts surface and the resolution flow works.
"""

import src.utils.qwen_client as qc
from src.agent.council import build_report, contradiction_graph_dot, detect_conflicts
from src.agent.integration import (
    IntegrationOrchestrator,
    IStatus,
    parse_integration_context,
)

GERMAN_MA = "We're acquiring a 200-person company in Germany. Integrate their workforce by Q1."


def _offline(monkeypatch):
    # Force is_configured() False so only the deterministic layer runs.
    monkeypatch.setattr(qc, "QWEN_BASE_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1")
    monkeypatch.delenv("QWEN_CLOUD_API_KEY", raising=False)


def test_context_parsing_extracts_country_headcount(monkeypatch):
    _offline(monkeypatch)
    ctx = parse_integration_context(GERMAN_MA)
    assert ctx["country"] == "Germany"
    assert ctx["headcount"] == 200
    assert ctx["parent_policies"]  # parent mandates present (drives the conflict)


def test_council_surfaces_positions_from_multiple_agents(monkeypatch):
    _offline(monkeypatch)
    report = build_report(parse_integration_context(GERMAN_MA))
    agents = {p.agent for p in report.positions}
    # Positions come from more than one specialist agent.
    assert len(agents) >= 2
    assert any("gdpr" in p.tags for p in report.positions)


def test_headline_conflict_detected(monkeypatch):
    _offline(monkeypatch)
    report = build_report(parse_integration_context(GERMAN_MA))
    assert report.conflicts, "expected at least one contradiction"
    # The GDPR data-transfer vs centralized-US-HRIS clash must appear.
    tagsets = []
    idx = {p.id: p for p in report.positions}
    for c in report.conflicts:
        tags = set()
        for pid in c.between:
            tags |= set(idx[pid].tags)
        tagsets.append(tags)
    assert any({"gdpr", "data_transfer"} & t and {"centralized_hris", "us_data"} & t for t in tagsets)
    # Each conflict offers resolution options.
    assert all(c.options for c in report.conflicts)


def test_resolution_flow_completes(monkeypatch):
    _offline(monkeypatch)
    orch = IntegrationOrchestrator()
    state = orch.start(GERMAN_MA)
    assert state.status == IStatus.AWAITING_RESOLUTION
    # Resolve every conflict → status becomes COMPLETE.
    for c in list(state.report.conflicts):
        orch.resolve_conflict(c.id, c.options[0].id, note="ok")
    assert orch.state.status == IStatus.COMPLETE
    pkg = orch.build_package()
    assert pkg["all_conflicts_resolved"] is True
    assert pkg["integration_plan"]


def test_graph_dot_is_valid(monkeypatch):
    _offline(monkeypatch)
    report = build_report(parse_integration_context(GERMAN_MA))
    dot = contradiction_graph_dot(report)
    assert dot.startswith("digraph")
    assert "->" in dot  # has at least one conflict edge

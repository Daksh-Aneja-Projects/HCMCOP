"""Tests for the Compliance-Critic agent (deterministic guardrails + merge)."""

import json
from unittest.mock import patch

from src.agent.critic import review_compliance


PARSED = {"role": "Senior Backend Developer",
          "location": {"city": "London", "country": "UK"}, "start_date": "2026-09-01"}
CTC = {"currency": "GBP", "band_low": 90000, "band_mid": 110000, "band_high": 130000}


def _mock_llm(verdict: dict):
    return patch("src.agent.critic.structured_completion", return_value=json.dumps(verdict))


def test_ctc_above_band_flags_medium_and_fails():
    offer = {"key_terms": {"ctc": 200000}}  # above band_high 130000
    with _mock_llm({"passed": True, "severity": "none", "issues": [], "recommendations": []}):
        verdict = review_compliance(PARSED, {"country": "UK", "risk_flags": []}, CTC, offer)
    assert verdict["passed"] is False
    assert verdict["severity"] in ("medium", "high")
    assert any("above" in i["issue"].lower() or "above" in i["why"].lower()
               for i in verdict["issues"])


def test_pre_start_risk_flag_is_surfaced():
    offer = {"key_terms": {"ctc": 110000}}  # in band
    compliance = {"country": "UK",
                  "risk_flags": ["Right to Work check must be completed BEFORE the first working day"]}
    with _mock_llm({"passed": True, "severity": "none", "issues": [], "recommendations": []}):
        verdict = review_compliance(PARSED, compliance, CTC, offer)
    assert verdict["passed"] is False
    assert any("right to work" in (i["issue"] + i["why"]).lower() for i in verdict["issues"])


def test_clean_offer_passes():
    offer = {"key_terms": {"ctc": 110000}}
    with _mock_llm({"passed": True, "severity": "none", "issues": [], "recommendations": ["Fill reporting manager"]}):
        verdict = review_compliance(PARSED, {"country": "UK", "risk_flags": []}, CTC, offer)
    assert verdict["passed"] is True
    assert verdict["severity"] == "none"
    assert verdict["reviewed_by"] == "compliance-critic"


def test_critic_survives_llm_failure():
    offer = {"key_terms": {"ctc": 110000}}
    with patch("src.agent.critic.structured_completion", side_effect=RuntimeError("boom")):
        verdict = review_compliance(PARSED, {"country": "UK", "risk_flags": []}, CTC, offer)
    # Should not raise; deterministic verdict still returned.
    assert "passed" in verdict

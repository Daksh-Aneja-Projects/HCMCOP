"""Tests for the deterministic tool functions (CTC, offer letter, onboarding)."""

from src.tools.ctc_estimator import estimate_ctc_band
from src.tools.offer_letter import generate_offer_letter
from src.tools.onboarding import create_onboarding_checklist


BANGALORE = {"city": "Bangalore", "state": "Karnataka", "country": "India"}
LONDON = {"city": "London", "state": None, "country": "UK"}


def test_ctc_band_ordering_and_currency():
    band = estimate_ctc_band("Senior Backend Developer", "Senior (IC3)", BANGALORE)
    assert band["currency"] == "INR"
    assert band["band_low"] < band["band_mid"] < band["band_high"]
    assert "India" in band["location"]


def test_ctc_uk_uses_gbp():
    band = estimate_ctc_band("Product Manager", "Senior", LONDON)
    assert band["currency"] == "GBP"


def test_ctc_cap_clamps_the_band():
    uncapped = estimate_ctc_band("Senior Backend Developer", "Senior", BANGALORE)
    cap = 3_000_000  # 30L
    capped = estimate_ctc_band("Senior Backend Developer", "Senior", BANGALORE, max_ctc=cap)
    assert capped["band_high"] <= cap
    assert capped["cap_applied"] == cap
    # Capping should not raise the high beyond the original.
    assert capped["band_high"] <= uncapped["band_high"]


def test_seniority_scales_pay_upward():
    junior = estimate_ctc_band("Backend Developer", "Junior", BANGALORE)["band_mid"]
    senior = estimate_ctc_band("Backend Developer", "Senior", BANGALORE)["band_mid"]
    assert senior > junior


def test_offer_letter_contains_key_terms_and_flags_review():
    parsed = {
        "role": "Senior Backend Developer",
        "location": BANGALORE,
        "start_date": "2026-08-15",
        "employment_type": "Full-time",
    }
    compliance = {
        "probation_period": "6 months standard",
        "notice_period_norm": "60-90 days",
        "mandatory_benefits": ["PF (12%)"],
        "required_documents": ["PAN Card"],
        "risk_flags": [],
    }
    ctc = {"currency": "INR", "band_mid": 3_500_000}
    offer = generate_offer_letter(parsed, compliance, ctc)

    assert "Senior Backend Developer" in offer["letter_content"]
    assert offer["key_terms"]["ctc"] == 3_500_000
    assert offer["key_terms"]["probation"] == "6 months standard"
    # Human review must always be required.
    assert offer["requires_human_review"] is True


def test_onboarding_checklist_sequenced_with_statutory_tasks():
    parsed = {"start_date": "2026-08-15"}
    compliance = {"country": "India"}
    result = create_onboarding_checklist(parsed, compliance, "2026-08-15")

    checklist = result["checklist"]
    assert result["total_tasks"] == len(checklist)
    assert result["total_tasks"] >= 6
    # India-specific statutory task should be present.
    assert any("PF/ESI" in t["task"] for t in checklist)
    # Every task has an owner, deadline label and status.
    for t in checklist:
        assert t["owner"] and t["deadline"] and t["status"] == "pending"
    # Due dates computed relative to start date.
    assert all("due_date" in t for t in checklist)


def test_onboarding_uk_adds_right_to_work_task():
    result = create_onboarding_checklist({"start_date": "2026-09-01"}, {"country": "UK"}, "2026-09-01")
    assert any("Right to Work" in t["task"] for t in result["checklist"])

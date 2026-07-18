"""Tests for the geographic compliance knowledge base."""

from src.tools.compliance import check_geo_compliance
from src.knowledge.compliance_data import SUPPORTED_GEOGRAPHIES


def test_india_karnataka_has_pf_and_shops_act():
    result = check_geo_compliance("India", "Karnataka", "Full-time")
    assert result["country"] == "India"
    assert result["state"] == "Karnataka"
    assert any("PF" in b or "Provident" in b for b in result["mandatory_benefits"])
    assert any("Shops & Establishments" in s for s in result["statutory_compliance"])


def test_uk_requires_right_to_work_and_pension():
    result = check_geo_compliance("UK", None, "Full-time")
    assert result["country"] == "UK"
    docs = " ".join(result["required_documents"])
    assert "Right to Work" in docs
    assert any("pension" in b.lower() for b in result["mandatory_benefits"])
    # Right to Work must be flagged as a pre-start risk.
    assert any("Right to Work" in f for f in result["risk_flags"])


def test_singapore_cpf_and_work_pass():
    result = check_geo_compliance("Singapore", None, "Full-time")
    assert result["country"] == "Singapore"
    assert any("CPF" in b for b in result["mandatory_benefits"])
    assert any("work pass" in f.lower() for f in result["risk_flags"])


def test_usa_california_overlays_national_rules():
    result = check_geo_compliance("US", "California", "Full-time")
    assert result["country"] == "USA"
    assert result["state"] == "California"
    # California-specific flag (non-compete) should be present.
    assert any("compete" in f.lower() for f in result["risk_flags"])


def test_country_alias_resolution():
    # "US" alias should resolve to USA.
    assert check_geo_compliance("US", None, "Full-time")["country"] == "USA"
    # "united kingdom" should resolve to UK.
    assert check_geo_compliance("united kingdom", None, "Full-time")["country"] == "UK"


def test_unknown_country_returns_safe_fallback_with_flag():
    result = check_geo_compliance("Atlantis", None, "Full-time")
    assert result["risk_flags"], "unknown geography must raise a manual-review flag"
    assert any("Atlantis" in f for f in result["risk_flags"])


def test_contract_type_adds_misclassification_flag():
    result = check_geo_compliance("India", "Karnataka", "Contract")
    assert any("misclassification" in f.lower() for f in result["risk_flags"])


def test_all_four_core_geographies_supported():
    for country in ("India", "USA", "UK", "Singapore"):
        assert country in SUPPORTED_GEOGRAPHIES

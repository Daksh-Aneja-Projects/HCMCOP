"""Offline tests for the compliance RAG retriever.

These tests exercise the keyword-fallback path only — they run with no Qwen
Cloud API key configured, so ``VectorStore`` must degrade to keyword scoring
without any network calls. Embedding-mode behaviour needs a live endpoint and
is intentionally not tested here.
"""

import os

import pytest

from src.knowledge import retriever
from src.knowledge.retriever import (
    VectorStore,
    build_compliance_index,
    reset_compliance_index,
    semantic_compliance,
)
from src.utils import qwen_client


@pytest.fixture(autouse=True)
def offline_env(monkeypatch):
    """Force the fully-offline path: no API key, local endpoint check false."""
    monkeypatch.delenv("QWEN_CLOUD_API_KEY", raising=False)
    monkeypatch.setattr(qwen_client, "QWEN_BASE_URL", qwen_client.DEFAULT_CLOUD_URL)
    qwen_client.reset_client()
    reset_compliance_index()
    assert not qwen_client.is_configured(), "test must run without a live client"
    yield
    reset_compliance_index()


def test_index_builds_in_keyword_mode_when_not_configured():
    store = build_compliance_index()
    assert isinstance(store, VectorStore)
    assert store.mode == "keyword"
    assert store.vectors is None
    # One doc per country plus one per state overlay.
    assert len(store) >= 4


def test_search_returns_relevant_geography():
    store = build_compliance_index()
    results = store.search("India Karnataka provident fund shops act", k=3)
    assert results, "expected at least one keyword match"
    top = results[0]
    assert top["metadata"]["country"] == "India"
    assert top["metadata"]["state"] == "Karnataka"
    assert top["score"] > 0.0
    # Results must be sorted by descending score.
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)


def test_semantic_compliance_wrapper_finds_singapore_cpf():
    results = semantic_compliance("Singapore CPF work pass foreign hire", k=1)
    assert len(results) == 1
    assert results[0]["metadata"]["country"] == "Singapore"
    assert "CPF" in results[0]["text"]


def test_empty_query_is_safe():
    store = build_compliance_index()
    # No tokens to match on — must not crash and must return well-formed dicts.
    results = store.search("", k=2)
    assert len(results) == 2
    assert all(r["score"] == 0.0 for r in results)

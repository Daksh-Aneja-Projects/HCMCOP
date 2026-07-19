"""Lightweight RAG vector store over the compliance knowledge base.

This is a deliberately small, dependency-light retriever (numpy only) that lets
the agent answer semantic "what applies in <geography>?" questions — including
for geographies not hardcoded in :mod:`src.knowledge.compliance_data`.

Design goals:
  * Real embeddings when Qwen Cloud is configured (``text-embedding-v4`` via the
    OpenAI-compatible endpoint), ranked by cosine similarity.
  * Offline-safe: if the client is not configured OR ``embed()`` raises, the
    store transparently degrades to a keyword-overlap score. No crash, ever.
    The active strategy is exposed on :attr:`VectorStore.mode`
    (``"embeddings"`` | ``"keyword"``).

The index is built once, lazily, and cached at module level so repeated
``semantic_compliance()`` calls do not re-embed the corpus.
"""

from __future__ import annotations

import re
from typing import Any

import numpy as np

from ..utils import qwen_client
from .compliance_data import _COUNTRY_BASE, _STATE_OVERLAYS, get_compliance

# ---------------------------------------------------------------------------
# Vector store
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> set[str]:
    """Lowercase word/number tokens used by the keyword-fallback scorer."""
    return set(_TOKEN_RE.findall(text.lower()))


class VectorStore:
    """A tiny in-memory vector store with graceful keyword fallback.

    Attributes:
        texts: The raw documents added to the store.
        metadatas: Per-document metadata dicts (parallel to ``texts``).
        vectors: An ``(n_docs, dim)`` numpy array of embeddings, or ``None``
            when running in keyword mode.
        mode: ``"embeddings"`` if documents were embedded via Qwen Cloud,
            otherwise ``"keyword"``.
    """

    def __init__(self, dimensions: int = 1024) -> None:
        self.dimensions = dimensions
        self.texts: list[str] = []
        self.metadatas: list[dict[str, Any]] = []
        self.vectors: np.ndarray | None = None
        self._token_sets: list[set[str]] = []
        self.mode: str = "keyword"

    # -- ingestion ----------------------------------------------------------

    def add(self, texts: list[str], metadatas: list[dict[str, Any]]) -> None:
        """Add documents to the store, embedding them when possible.

        Args:
            texts: Documents to index.
            metadatas: One metadata dict per document (same length as ``texts``).

        Raises:
            ValueError: If ``texts`` and ``metadatas`` differ in length.
        """
        if len(texts) != len(metadatas):
            raise ValueError("texts and metadatas must have the same length")
        if not texts:
            return

        self.texts.extend(texts)
        self.metadatas.extend(metadatas)
        self._token_sets.extend(_tokenize(t) for t in texts)

        new_vectors = self._try_embed(texts)
        if new_vectors is None:
            # Keyword mode — drop any partial vector state so search() is
            # unambiguous about which strategy to use.
            self.mode = "keyword"
            self.vectors = None
            return

        self.mode = "embeddings"
        block = np.asarray(new_vectors, dtype=np.float32)
        self.vectors = block if self.vectors is None else np.vstack([self.vectors, block])

    def _try_embed(self, texts: list[str]) -> list[list[float]] | None:
        """Embed ``texts`` via Qwen Cloud, or return ``None`` to force fallback."""
        if not qwen_client.is_configured():
            return None
        try:
            return qwen_client.embed(texts, dimensions=self.dimensions)
        except Exception:
            # Network error, auth failure, rate limit — degrade, never crash.
            return None

    # -- retrieval ----------------------------------------------------------

    def search(self, query: str, k: int = 3) -> list[dict[str, Any]]:
        """Return the top-``k`` documents most relevant to ``query``.

        Args:
            query: Free-text query.
            k: Maximum number of results to return.

        Returns:
            A list of ``{"text", "score", "metadata"}`` dicts sorted by
            descending score. Uses cosine similarity in embeddings mode and a
            normalized keyword-overlap score in keyword mode.
        """
        if not self.texts:
            return []

        if self.mode == "embeddings" and self.vectors is not None:
            scores = self._embedding_scores(query)
        else:
            scores = self._keyword_scores(query)

        order = np.argsort(scores)[::-1][: max(k, 0)]
        return [
            {
                "text": self.texts[i],
                "score": float(scores[i]),
                "metadata": self.metadatas[i],
            }
            for i in order
        ]

    def _embedding_scores(self, query: str) -> np.ndarray:
        """Cosine similarity between ``query`` and every stored vector."""
        try:
            q = qwen_client.embed([query], dimensions=self.dimensions)[0]
        except Exception:
            # Query-time failure: fall back to keyword scoring for this call.
            return self._keyword_scores(query)

        qv = np.asarray(q, dtype=np.float32)
        assert self.vectors is not None
        mat = self.vectors
        denom = (np.linalg.norm(mat, axis=1) * np.linalg.norm(qv)) + 1e-8
        return (mat @ qv) / denom

    def _keyword_scores(self, query: str) -> np.ndarray:
        """Jaccard-style token overlap between ``query`` and each document."""
        q_tokens = _tokenize(query)
        if not q_tokens:
            return np.zeros(len(self.texts), dtype=np.float32)
        scores = np.empty(len(self.texts), dtype=np.float32)
        for i, doc_tokens in enumerate(self._token_sets):
            if not doc_tokens:
                scores[i] = 0.0
                continue
            overlap = len(q_tokens & doc_tokens)
            union = len(q_tokens | doc_tokens)
            scores[i] = overlap / union if union else 0.0
        return scores

    def __len__(self) -> int:
        return len(self.texts)


# ---------------------------------------------------------------------------
# Compliance index
# ---------------------------------------------------------------------------

_compliance_index: VectorStore | None = None


def _summarize_compliance(record: dict[str, Any]) -> str:
    """Render a compliance record as a compact, embeddable text document."""
    country = record.get("country", "Unknown")
    state = record.get("state")
    geo = f"{country}" + (f" / {state}" if state else "")
    parts = [
        f"Geography: {geo}.",
        f"Notice period: {record.get('notice_period_norm', 'n/a')}.",
        f"Probation: {record.get('probation_period', 'n/a')}.",
    ]
    benefits = record.get("mandatory_benefits") or []
    if benefits:
        parts.append("Mandatory benefits: " + "; ".join(benefits) + ".")
    docs = record.get("required_documents") or []
    if docs:
        parts.append("Required documents: " + "; ".join(docs) + ".")
    statutory = record.get("statutory_compliance") or []
    if statutory:
        parts.append("Statutory compliance: " + "; ".join(statutory) + ".")
    flags = record.get("risk_flags") or []
    if flags:
        parts.append("Risk flags: " + "; ".join(flags) + ".")
    return " ".join(parts)


def build_compliance_index() -> VectorStore:
    """Build a :class:`VectorStore` over the compliance knowledge base.

    Emits one document per country and one per state overlay, each summarizing
    notice period, benefits, required documents, statutory items and risk flags.
    The result is cached at module level so subsequent calls are free.
    """
    global _compliance_index
    if _compliance_index is not None:
        return _compliance_index

    texts: list[str] = []
    metadatas: list[dict[str, Any]] = []

    # One document per country (national-level view).
    for country in _COUNTRY_BASE:
        record = get_compliance(country, None, "Full-time")
        texts.append(_summarize_compliance(record))
        metadatas.append({"country": country, "state": None, "scope": "country"})

    # One document per state/region overlay (more specific view).
    for (country, state) in _STATE_OVERLAYS:
        record = get_compliance(country, state, "Full-time")
        texts.append(_summarize_compliance(record))
        metadatas.append({"country": country, "state": state, "scope": "state"})

    store = VectorStore()
    store.add(texts, metadatas)
    _compliance_index = store
    return store


def reset_compliance_index() -> None:
    """Drop the cached index (used by tests after changing configuration)."""
    global _compliance_index
    _compliance_index = None


def semantic_compliance(query: str, k: int = 1) -> list[dict[str, Any]]:
    """Semantically retrieve the most relevant compliance document(s).

    Convenience wrapper over the cached compliance index. Useful for answering
    "what applies in <geography>?" — including for geographies that are not in
    the hardcoded lookup table, by returning the nearest known jurisdiction.

    Args:
        query: Free-text geography/compliance question.
        k: Number of documents to return.

    Returns:
        A list of ``{"text", "score", "metadata"}`` dicts (see
        :meth:`VectorStore.search`).
    """
    return build_compliance_index().search(query, k=k)


if __name__ == "__main__":  # pragma: no cover - manual smoke test
    # Offline smoke: builds the index and runs a keyword-mode search.
    index = build_compliance_index()
    print(f"Index built with {len(index)} documents in '{index.mode}' mode.")
    hits = index.search("India Karnataka provident fund shops act", k=2)
    for rank, hit in enumerate(hits, start=1):
        meta = hit["metadata"]
        geo = meta["country"] + (f"/{meta['state']}" if meta["state"] else "")
        print(f"{rank}. [{geo}] score={hit['score']:.3f}")
        print(f"   {hit['text'][:120]}...")

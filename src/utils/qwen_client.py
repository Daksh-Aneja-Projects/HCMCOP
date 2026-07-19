"""Wrapper around the Qwen Cloud API (OpenAI-compatible endpoint).

All LLM reasoning in this project flows through here. We use the official
OpenAI Python SDK pointed at DashScope's compatible-mode base URL (DashScope is
Alibaba Cloud's Model Studio service), per the hackathon constraints:

    Base URL : https://dashscope-intl.aliyuncs.com/compatible-mode/v1
    Models   : qwen-plus (reasoning), qwen-turbo/qwen-flash (fast/cheap)
    Embeds   : text-embedding-v4
    Auth     : env var QWEN_CLOUD_API_KEY (never hardcoded)

Capabilities exposed:
  * chat_completion            — tool/function calling (+ parallel tool calls)
  * stream_chat                — streaming deltas with usage
  * structured_completion      — JSON-mode structured output (json_object)
  * embed                      — text-embedding-v4 vectors (for RAG)
  * metrics                    — per-call token/latency accounting
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Iterator

from dotenv import load_dotenv
from openai import OpenAI

# Load .env once at import time so both the Streamlit app and the tests pick
# up configuration without each caller having to remember to.
load_dotenv()

# Production default is Qwen Cloud. For local testing you can override the base
# URL (e.g. an Ollama OpenAI-compatible endpoint) and model names via env vars.
DEFAULT_CLOUD_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
QWEN_BASE_URL = os.getenv("QWEN_BASE_URL", DEFAULT_CLOUD_URL)
PRIMARY_MODEL = os.getenv("QWEN_PRIMARY_MODEL", "qwen-plus")
FALLBACK_MODEL = os.getenv("QWEN_FALLBACK_MODEL", "qwen-turbo")
FAST_MODEL = os.getenv("QWEN_FAST_MODEL", "qwen-turbo")
EMBED_MODEL = os.getenv("QWEN_EMBED_MODEL", "text-embedding-v4")


class QwenConfigError(RuntimeError):
    """Raised when the Qwen Cloud client cannot be configured."""


# ---------------------------------------------------------------------------
# Per-call metrics (token / cost / latency accounting for observability).
# ---------------------------------------------------------------------------

# Indicative per-1K-token USD pricing for cost estimation in the UI. These are
# approximate and only used for a relative "cost" badge, not billing.
_PRICE_PER_1K = {
    "qwen-plus": (0.0008, 0.002),
    "qwen-max": (0.0024, 0.0096),
    "qwen-turbo": (0.0003, 0.0006),
    "qwen-flash": (0.00015, 0.0006),
}


@dataclass
class CallMetrics:
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0
    ok: bool = True

    @property
    def est_cost_usd(self) -> float:
        rate_in, rate_out = _PRICE_PER_1K.get(self.model, (0.0, 0.0))
        return (self.prompt_tokens / 1000 * rate_in) + (
            self.completion_tokens / 1000 * rate_out
        )


@dataclass
class MetricsCollector:
    calls: list[CallMetrics] = field(default_factory=list)

    def record(self, m: CallMetrics) -> None:
        self.calls.append(m)

    @property
    def total_tokens(self) -> int:
        return sum(c.total_tokens for c in self.calls)

    @property
    def total_latency_ms(self) -> float:
        return sum(c.latency_ms for c in self.calls)

    @property
    def total_cost_usd(self) -> float:
        return sum(c.est_cost_usd for c in self.calls)

    def summary(self) -> dict[str, Any]:
        return {
            "calls": len(self.calls),
            "total_tokens": self.total_tokens,
            "total_latency_ms": round(self.total_latency_ms, 1),
            "est_cost_usd": round(self.total_cost_usd, 5),
        }


# Global collector; the Streamlit app reads this for the cost/latency badges.
METRICS = MetricsCollector()


def _usage_to_metrics(model: str, usage: Any, latency_ms: float, ok: bool = True) -> CallMetrics:
    pt = getattr(usage, "prompt_tokens", 0) or 0
    ct = getattr(usage, "completion_tokens", 0) or 0
    tt = getattr(usage, "total_tokens", 0) or (pt + ct)
    return CallMetrics(model=model, prompt_tokens=pt, completion_tokens=ct,
                       total_tokens=tt, latency_ms=latency_ms, ok=ok)


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

_client: OpenAI | None = None


def get_client() -> OpenAI:
    """Return a lazily-constructed, cached OpenAI SDK client for Qwen Cloud."""
    global _client
    if _client is not None:
        return _client

    api_key = os.getenv("QWEN_CLOUD_API_KEY")
    if not api_key:
        # A local OpenAI-compatible endpoint (e.g. Ollama) needs no real key.
        if _is_local_endpoint():
            api_key = "local"
        else:
            raise QwenConfigError(
                "QWEN_CLOUD_API_KEY is not set. Copy .env.example to .env and add "
                "your Qwen Cloud (DashScope) API key (or set QWEN_BASE_URL to a "
                "local endpoint for testing)."
            )

    _client = OpenAI(api_key=api_key, base_url=QWEN_BASE_URL)
    return _client


def reset_client() -> None:
    """Drop the cached client (e.g. after env changes in tests)."""
    global _client
    _client = None


def _is_local_endpoint() -> bool:
    return QWEN_BASE_URL != DEFAULT_CLOUD_URL and (
        "localhost" in QWEN_BASE_URL or "127.0.0.1" in QWEN_BASE_URL
    )


def is_configured() -> bool:
    """True if the client can be built (real key set, or a local endpoint)."""
    return bool(os.getenv("QWEN_CLOUD_API_KEY")) or _is_local_endpoint()


# ---------------------------------------------------------------------------
# Chat completion (function calling + parallel tool calls + metrics)
# ---------------------------------------------------------------------------

def chat_completion(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str = "auto",
    model: str = PRIMARY_MODEL,
    temperature: float = 0.2,
    parallel_tool_calls: bool = False,
    use_fallback_on_error: bool = True,
) -> Any:
    """Call Qwen chat completions with optional function-calling tools.

    Returns the raw OpenAI SDK response object. Records a CallMetrics entry.
    On error with the primary model, retries once with the fallback model.
    """
    client = get_client()

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = tool_choice
        if parallel_tool_calls:
            # Supported by Qwen; harmless to omit for models that ignore it.
            kwargs["parallel_tool_calls"] = True

    start = time.perf_counter()
    try:
        resp = client.chat.completions.create(**kwargs)
        METRICS.record(_usage_to_metrics(
            model, getattr(resp, "usage", None), (time.perf_counter() - start) * 1000))
        return resp
    except Exception:
        if use_fallback_on_error and model != FALLBACK_MODEL:
            kwargs["model"] = FALLBACK_MODEL
            kwargs.pop("parallel_tool_calls", None)
            start = time.perf_counter()
            resp = client.chat.completions.create(**kwargs)
            METRICS.record(_usage_to_metrics(
                FALLBACK_MODEL, getattr(resp, "usage", None),
                (time.perf_counter() - start) * 1000))
            return resp
        METRICS.record(CallMetrics(model=model, ok=False))
        raise


# ---------------------------------------------------------------------------
# Streaming
# ---------------------------------------------------------------------------

def stream_chat(
    messages: list[dict[str, Any]],
    model: str = PRIMARY_MODEL,
    temperature: float = 0.3,
) -> Iterator[str]:
    """Yield content deltas from a streamed completion (no tools).

    Uses ``stream_options={"include_usage": True}`` so the final chunk carries
    usage, which we fold into METRICS. Text-only — used for the UI's live
    narration/summary, not the tool-calling loop.
    """
    client = get_client()
    start = time.perf_counter()
    usage = None
    try:
        stream = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            stream=True,
            stream_options={"include_usage": True},
        )
        for chunk in stream:
            if getattr(chunk, "usage", None):
                usage = chunk.usage
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            piece = getattr(delta, "content", None)
            if piece:
                yield piece
    finally:
        METRICS.record(_usage_to_metrics(
            model, usage, (time.perf_counter() - start) * 1000))


# ---------------------------------------------------------------------------
# Structured output (JSON mode)
# ---------------------------------------------------------------------------

def structured_completion(
    messages: list[dict[str, Any]],
    model: str = PRIMARY_MODEL,
    temperature: float = 0.1,
) -> str:
    """Return raw JSON string using DashScope's json_object response format.

    IMPORTANT (DashScope quirk): the word "json" MUST appear somewhere in the
    messages or the API rejects the request. We inject a nudge into the first
    system message when absent. Falls back to a plain call if the endpoint
    rejects ``response_format`` (e.g. some local models).
    """
    msgs = _ensure_json_hint(messages)
    client = get_client()
    start = time.perf_counter()

    def _call(use_rf: bool) -> Any:
        kw: dict[str, Any] = {"model": model, "messages": msgs, "temperature": temperature}
        if use_rf:
            kw["response_format"] = {"type": "json_object"}
        return client.chat.completions.create(**kw)

    try:
        resp = _call(use_rf=True)
    except Exception:
        # Endpoint may not support response_format (local models); retry plain.
        resp = _call(use_rf=False)

    METRICS.record(_usage_to_metrics(
        model, getattr(resp, "usage", None), (time.perf_counter() - start) * 1000))
    return resp.choices[0].message.content or "{}"


def _ensure_json_hint(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    joined = " ".join(str(m.get("content", "")) for m in messages).lower()
    if "json" in joined:
        return messages
    patched = [dict(m) for m in messages]
    for m in patched:
        if m.get("role") == "system":
            m["content"] = f"{m.get('content', '')}\n\nRespond in JSON."
            return patched
    # No system message — prepend one.
    return [{"role": "system", "content": "Respond in JSON."}] + patched


# ---------------------------------------------------------------------------
# Embeddings (for RAG / semantic retrieval)
# ---------------------------------------------------------------------------

def embed(texts: list[str], dimensions: int = 1024, model: str = EMBED_MODEL) -> list[list[float]]:
    """Return embedding vectors for a batch of texts (batch <= 10 per API).

    Uses the OpenAI-compatible ``dimensions`` parameter on text-embedding-v4.
    """
    client = get_client()
    vectors: list[list[float]] = []
    # DashScope caps batch at 10 texts/request.
    for i in range(0, len(texts), 10):
        batch = texts[i : i + 10]
        start = time.perf_counter()
        resp = client.embeddings.create(model=model, input=batch, dimensions=dimensions)
        METRICS.record(_usage_to_metrics(
            model, getattr(resp, "usage", None), (time.perf_counter() - start) * 1000))
        vectors.extend(d.embedding for d in resp.data)
    return vectors

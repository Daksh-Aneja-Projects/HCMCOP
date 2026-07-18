"""Thin wrapper around the Qwen Cloud API (OpenAI-compatible endpoint).

All LLM reasoning in this project flows through here. We use the official
OpenAI Python SDK pointed at DashScope's compatible-mode base URL, per the
hackathon hard constraints:

    Base URL : https://dashscope-intl.aliyuncs.com/compatible-mode/v1
    Models   : qwen-plus (primary), qwen-turbo (fallback for simple tasks)
    Auth     : env var QWEN_CLOUD_API_KEY (never hardcoded)
"""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

# Load .env once at import time so both the Streamlit app and the tests pick
# up QWEN_CLOUD_API_KEY without each caller having to remember to.
load_dotenv()

# Production default is Qwen Cloud. For local testing you can override the base
# URL (e.g. an Ollama OpenAI-compatible endpoint) and model names via env vars,
# without touching code.
DEFAULT_CLOUD_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
QWEN_BASE_URL = os.getenv("QWEN_BASE_URL", DEFAULT_CLOUD_URL)
PRIMARY_MODEL = os.getenv("QWEN_PRIMARY_MODEL", "qwen-plus")
FALLBACK_MODEL = os.getenv("QWEN_FALLBACK_MODEL", "qwen-turbo")


class QwenConfigError(RuntimeError):
    """Raised when the Qwen Cloud client cannot be configured."""


_client: OpenAI | None = None


def get_client() -> OpenAI:
    """Return a lazily-constructed, cached OpenAI SDK client for Qwen Cloud.

    Raises:
        QwenConfigError: if QWEN_CLOUD_API_KEY is not set.
    """
    global _client
    if _client is not None:
        return _client

    api_key = os.getenv("QWEN_CLOUD_API_KEY")
    if not api_key:
        # A local OpenAI-compatible endpoint (e.g. Ollama) needs no real key;
        # the SDK only requires a non-empty string. Only the real Qwen Cloud
        # endpoint truly requires a key.
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


def _is_local_endpoint() -> bool:
    return QWEN_BASE_URL != DEFAULT_CLOUD_URL and (
        "localhost" in QWEN_BASE_URL or "127.0.0.1" in QWEN_BASE_URL
    )


def is_configured() -> bool:
    """True if the client can be built (real key set, or a local endpoint)."""
    return bool(os.getenv("QWEN_CLOUD_API_KEY")) or _is_local_endpoint()


def chat_completion(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str = "auto",
    model: str = PRIMARY_MODEL,
    temperature: float = 0.2,
    use_fallback_on_error: bool = True,
) -> Any:
    """Call Qwen Cloud chat completions with optional function-calling tools.

    Returns the raw OpenAI SDK response object so callers can inspect
    ``choices[0].message`` for either ``content`` or ``tool_calls``.

    If the primary model errors and ``use_fallback_on_error`` is set, we retry
    once with the lighter ``qwen-turbo`` model.
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

    try:
        return client.chat.completions.create(**kwargs)
    except Exception:
        if use_fallback_on_error and model != FALLBACK_MODEL:
            kwargs["model"] = FALLBACK_MODEL
            return client.chat.completions.create(**kwargs)
        raise

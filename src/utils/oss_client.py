"""Alibaba Cloud OSS (Object Storage Service) export.

Publishes the finished onboarding package to an OSS bucket — a second,
unambiguous Alibaba Cloud service alongside DashScope (Qwen Cloud), and the
durable audit artifact for an enterprise workflow.

Configuration (env, never hardcoded):
    ALIBABA_CLOUD_ACCESS_KEY_ID
    ALIBABA_CLOUD_ACCESS_KEY_SECRET
    OSS_BUCKET
    OSS_ENDPOINT   (e.g. https://oss-ap-southeast-1.aliyuncs.com)

If OSS is not configured (or the ``oss2`` SDK is absent), ``publish_package``
degrades gracefully and returns ``{"published": False, "reason": ...}`` so the
app never crashes when the optional integration is unset.
"""

from __future__ import annotations

import json
import os
from typing import Any


def is_oss_configured() -> bool:
    return all(
        os.getenv(k)
        for k in ("ALIBABA_CLOUD_ACCESS_KEY_ID", "ALIBABA_CLOUD_ACCESS_KEY_SECRET", "OSS_BUCKET")
    )


def _endpoint() -> str:
    return os.getenv("OSS_ENDPOINT", "https://oss-ap-southeast-1.aliyuncs.com")


def publish_package(package: dict[str, Any], key: str | None = None) -> dict[str, Any]:
    """Upload the onboarding package JSON to Alibaba Cloud OSS.

    Returns a result dict:
        {"published": True, "uri": "oss://bucket/key", "request_id": ..., "status": 200}
    or, when OSS is unavailable:
        {"published": False, "reason": "..."}
    """
    if not is_oss_configured():
        return {"published": False, "reason": "OSS not configured (set ALIBABA_CLOUD_* + OSS_BUCKET)."}

    try:
        import oss2  # imported lazily so the app runs without the optional dep
    except ImportError:
        return {"published": False, "reason": "oss2 SDK not installed (pip install oss2)."}

    key = key or _default_key(package)
    bucket_name = os.environ["OSS_BUCKET"]

    try:
        auth = oss2.Auth(
            os.environ["ALIBABA_CLOUD_ACCESS_KEY_ID"],
            os.environ["ALIBABA_CLOUD_ACCESS_KEY_SECRET"],
        )
        bucket = oss2.Bucket(auth, _endpoint(), bucket_name)
        body = json.dumps(package, indent=2, default=str).encode("utf-8")
        result = bucket.put_object(key, body)  # <-- Alibaba Cloud OSS API call
        return {
            "published": True,
            "uri": f"oss://{bucket_name}/{key}",
            "request_id": getattr(result, "request_id", None),
            "status": getattr(result, "status", None),
        }
    except Exception as exc:  # surface a friendly reason, never crash the UI
        return {"published": False, "reason": f"{type(exc).__name__}: {exc}"}


def _default_key(package: dict[str, Any]) -> str:
    parsed = (package.get("hiring_request") or {}).get("parsed") or {}
    role = (parsed.get("role") or "role").lower().replace(" ", "-")
    return f"onboarding-packages/{role}.json"

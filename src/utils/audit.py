"""Lightweight, append-only audit trail (SQLite).

Enterprise HCM workflows need an auditable record of *who* approved *what* and
*when*. This captures approval decisions (reviewer identity, timestamp, decision,
notes) and completed packages in a local SQLite database — a production-readiness
signal beyond ephemeral Streamlit session state.

Storage is a single file (default ``data/audit.db``); the directory is created
on demand. In an Alibaba Cloud deployment this can be pointed at an ApsaraDB /
Tablestore-backed path, but SQLite keeps the demo self-contained.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any

_DB_PATH = os.getenv("AUDIT_DB_PATH", os.path.join("data", "audit.db"))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            session_id TEXT,
            event_type TEXT NOT NULL,
            actor TEXT,
            payload TEXT
        )
        """
    )
    return conn


def record_event(
    session_id: str, event_type: str, actor: str | None = None, payload: Any = None
) -> int:
    """Append an audit event. Returns the row id. Never raises to the caller."""
    try:
        conn = _connect()
        with conn:
            cur = conn.execute(
                "INSERT INTO audit_events (ts, session_id, event_type, actor, payload) "
                "VALUES (?, ?, ?, ?, ?)",
                (_now_iso(), session_id, event_type, actor, json.dumps(payload, default=str)),
            )
        conn.close()
        return int(cur.lastrowid)
    except Exception:
        return -1


def record_approval(
    session_id: str, reviewer: str | None, decision: str, notes: str, summary: dict[str, Any]
) -> int:
    """Record a human approval/revision decision at the HITL gate."""
    return record_event(
        session_id=session_id,
        event_type=f"approval:{decision}",
        actor=reviewer or "unknown",
        payload={"decision": decision, "notes": notes, "summary": summary},
    )


def recent_events(limit: int = 50, session_id: str | None = None) -> list[dict[str, Any]]:
    """Return recent audit events (newest first) for a UI audit panel."""
    try:
        conn = _connect()
        if session_id:
            rows = conn.execute(
                "SELECT ts, session_id, event_type, actor, payload FROM audit_events "
                "WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT ts, session_id, event_type, actor, payload FROM audit_events "
                "ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        conn.close()
    except Exception:
        return []

    out = []
    for ts, sid, etype, actor, payload in rows:
        try:
            parsed = json.loads(payload) if payload else None
        except json.JSONDecodeError:
            parsed = payload
        out.append({"ts": ts, "session_id": sid, "event_type": etype,
                    "actor": actor, "payload": parsed})
    return out

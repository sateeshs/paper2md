"""Push SAT tutor session results to Supabase.

Mirrors supabase_push.py patterns — uses SERVICE_ROLE_KEY, NullPool, _s() null-byte strip.
"""

from __future__ import annotations

import os

_supabase_client = None


def _s(value: str | None) -> str | None:
    """Strip null bytes — PostgreSQL rejects \\u0000 in text columns."""
    if value is None:
        return None
    return value.replace("\x00", "")


def _get_client():
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client

    try:
        from supabase import create_client  # type: ignore
    except ImportError:
        raise RuntimeError("supabase package not installed. Run: pip install supabase")

    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()

    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set."
        )

    _supabase_client = create_client(url, key)
    return _supabase_client


def mark_sat_processing(session_id: str) -> None:
    """Update sat_sessions status to 'processing'."""
    client = _get_client()
    client.table("sat_sessions").update(
        {"status": "processing"}
    ).eq("id", session_id).execute()


def push_sat_session(session_id: str, result: dict) -> None:
    """Write all 7 response fields + status=complete to sat_sessions."""
    client = _get_client()
    client.table("sat_sessions").update({
        "status":           "complete",
        "explanation":      _s(result.get("explanation")),
        "step_by_step":     _s(result.get("step_by_step")),
        "key_concepts":     _s(result.get("key_concepts")),
        "hints":            _s(result.get("hints")),
        "common_mistakes":  _s(result.get("common_mistakes")),
        "sat_strategy":     _s(result.get("sat_strategy")),
        "answer":           _s(result.get("answer")),
        "agent_model":      _s(result.get("agent_model")),
        "error_msg":        None,
    }).eq("id", session_id).execute()


def mark_sat_error(session_id: str, error_msg: str) -> None:
    """Update sat_sessions status to 'error'."""
    try:
        client = _get_client()
        client.table("sat_sessions").update({
            "status":    "error",
            "error_msg": _s(error_msg[:2000]),
        }).eq("id", session_id).execute()
    except Exception:
        pass  # Best-effort

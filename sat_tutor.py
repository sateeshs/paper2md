#!/usr/bin/env python3
"""SAT Tutor CLI — called by GitHub Actions with --session-id.

Usage:
    python sat_tutor.py --session-id <UUID>

Environment:
    SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY — DB access
    PAPER2MD_LLM_PROVIDER, OPENROUTER_API_KEY, etc. — LLM provider
"""

from __future__ import annotations

import argparse
import sys

from lib.dspy_config import configure_dspy
from lib.dspy_modules import SATTutorModule
from lib.sat_push import mark_sat_error, mark_sat_processing, push_sat_session


def _fetch_session(session_id: str) -> dict:
    """Return the sat_sessions row for this session_id."""
    from lib.sat_push import _get_client
    client = _get_client()
    resp = (
        client.table("sat_sessions")
        .select("id, question, subject, user_context, status")
        .eq("id", session_id)
        .single()
        .execute()
    )
    if not resp.data:
        raise RuntimeError(f"Session {session_id} not found in sat_sessions.")
    return resp.data


def run(session_id: str) -> None:
    session = _fetch_session(session_id)

    if session["status"] not in ("pending", "error"):
        print(f"[INFO] Session {session_id} already has status={session['status']}, skipping.")
        return

    print(f"[INFO] Processing SAT session {session_id} (subject={session['subject']})")
    mark_sat_processing(session_id)

    try:
        configure_dspy()
        module = SATTutorModule()
        result = module.forward(
            question=session["question"],
            subject=session["subject"],
            user_context=session.get("user_context") or "",
        )
        push_sat_session(session_id, result)
        print(f"[OK] Session {session_id} complete.")
    except Exception as e:
        error_msg = str(e)
        print(f"[ERROR] Session {session_id} failed: {error_msg}", file=sys.stderr)
        mark_sat_error(session_id, error_msg)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="SAT Tutor agent — processes one session")
    parser.add_argument("--session-id", required=True, help="UUID of the sat_sessions row")
    args = parser.parse_args()
    run(args.session_id)


if __name__ == "__main__":
    main()

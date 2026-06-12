"""Push processed papers to Supabase.

Connection strategy:
  - Transaction Mode via port 6543 (Supabase pooler)
  - NullPool: no persistent connections from a CLI process
  - SERVICE_ROLE_KEY bypasses RLS — write access

Upsert is idempotent:
  - papers:      ON CONFLICT (arxiv_id) DO UPDATE
  - sections:    DELETE + bulk INSERT (clean re-run)
  - math_blocks: bulk INSERT after sections

Required env vars:
  SUPABASE_URL              https://xxxx.supabase.co
  SUPABASE_SERVICE_ROLE_KEY service_role key (never expose to frontend)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from lib.models import MathBlock, Paper, Section

# Lazy import — only needed when --push-supabase is used
_supabase_client = None


def _s(value: str | None) -> str | None:
    """Strip null bytes from a string — PostgreSQL rejects \\u0000 in text columns."""
    if value is None:
        return None
    return value.replace("\x00", "")


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

def _get_client():
    """Return a cached Supabase client (initialised once per process)."""
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client

    try:
        from supabase import create_client  # type: ignore
    except ImportError:
        raise RuntimeError(
            "supabase package not installed. Run: pip install supabase"
        )

    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()

    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set "
            "when using --push-supabase."
        )

    _supabase_client = create_client(url, key)
    return _supabase_client


# ---------------------------------------------------------------------------
# Status helpers
# ---------------------------------------------------------------------------

def get_paper_status(arxiv_id: str) -> str | None:
    """Return the status of a paper in Supabase, or None if not found."""
    try:
        client = _get_client()
        resp = (
            client.table("papers")
            .select("status")
            .eq("arxiv_id", arxiv_id)
            .maybe_single()
            .execute()
        )
        if resp.data:
            return resp.data.get("status")
        return None
    except Exception:
        return None


def mark_processing(arxiv_id: str, title: str = "") -> None:
    """Update existing paper row status to 'processing'. Preserves existing title."""
    client = _get_client()
    update: dict = {"status": "processing", "source_type": "arxiv_latex"}
    # Only set title if explicitly provided — don't overwrite a real title with arxiv_id
    if title and title != arxiv_id:
        update["title"] = title
    client.table("papers").update(update).eq("arxiv_id", arxiv_id).execute()


def mark_error(arxiv_id: str, error_msg: str) -> None:
    """Update paper status to 'error'."""
    try:
        client = _get_client()
        client.table("papers").update(
            {"status": "error", "error_msg": error_msg[:2000]}
        ).eq("arxiv_id", arxiv_id).execute()
    except Exception:
        pass  # Best-effort


def fetch_pending_arxiv_ids() -> list[str]:
    """Return all arxiv_ids with status='pending' from Supabase."""
    try:
        client = _get_client()
        resp = (
            client.table("papers")
            .select("arxiv_id")
            .eq("status", "pending")
            .execute()
        )
        return [row["arxiv_id"] for row in (resp.data or []) if row.get("arxiv_id")]
    except Exception as e:
        raise RuntimeError(f"Failed to fetch pending papers: {e}") from e


# ---------------------------------------------------------------------------
# Main push
# ---------------------------------------------------------------------------

def push_paper(paper: Paper) -> None:
    """
    Upsert a fully-processed Paper (with sections + math_blocks) to Supabase.

    Steps:
      1. Upsert papers row
      2. Delete existing sections for this paper (clean re-run)
      3. Bulk insert sections (100 rows/batch)
      4. Bulk insert math_blocks (100 rows/batch)
      5. Update paper status = 'complete'

    Raises: RuntimeError on any fatal DB error.
    """
    client = _get_client()

    # ── 1. Upsert paper ────────────────────────────────────────────────────
    paper_row: dict[str, Any] = {
        "title":       _s(paper.title),
        "source_type": paper.source_type,
        "status":      "processing",
    }
    if paper.arxiv_id:
        paper_row["arxiv_id"] = paper.arxiv_id
    if paper.pdf_path:
        paper_row["pdf_filename"] = paper.pdf_path.name

    upsert_resp = (
        client.table("papers")
        .upsert(paper_row, on_conflict="arxiv_id")
        .execute()
    )
    paper_id: str = upsert_resp.data[0]["id"]

    # ── 2. Delete existing sections (idempotent re-run) ────────────────────
    client.table("sections").delete().eq("paper_id", paper_id).execute()

    # ── 3. Insert sections ─────────────────────────────────────────────────
    section_id_map: dict[int, str] = {}  # order_idx → DB id

    section_rows = [
        {
            "paper_id":   paper_id,
            "order_idx":  s.order_idx,
            "title":      _s(s.title),
            "plain_text": _s(s.plain_text),
            "raw_latex":  _s(s.raw_latex),
            "has_math":   len(s.math_blocks) > 0,
        }
        for s in paper.sections
    ]

    for batch in _batches(section_rows, 100):
        resp = client.table("sections").insert(batch).execute()
        for row in resp.data:
            section_id_map[row["order_idx"]] = row["id"]

    # ── 4. Insert math_blocks ──────────────────────────────────────────────
    math_rows: list[dict[str, Any]] = []
    for section in paper.sections:
        section_db_id = section_id_map.get(section.order_idx)
        if not section_db_id:
            continue
        for block in section.math_blocks:
            math_rows.append({
                "section_id":        section_db_id,
                "order_idx":         block.order_idx,
                "env_type":          block.env_type,
                "latex_expr":        _s(block.latex_expr),
                "context_before":    _s(block.context_before),
                "context_after":     _s(block.context_after),
                "explanation":       _s(block.explanation),
                "explanation_model": _s(block.explanation_model),
            })

    for batch in _batches(math_rows, 100):
        client.table("math_blocks").insert(batch).execute()

    # ── 5. Mark complete ───────────────────────────────────────────────────
    client.table("papers").update(
        {"status": "complete", "error_msg": None}
    ).eq("id", paper_id).execute()


# ---------------------------------------------------------------------------
# Failed push journal (offline fallback)
# ---------------------------------------------------------------------------

_FAILED_PUSH_FILE = Path.home() / ".paper2md" / "failed_push.json"


def save_failed_push(paper: Paper, error: str) -> None:
    """Persist a failed push to a local journal for retry later."""
    _FAILED_PUSH_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "arxiv_id":    paper.arxiv_id,
        "title":       paper.title,
        "source_type": paper.source_type,
        "error":       error,
    }
    existing: list[dict] = []
    if _FAILED_PUSH_FILE.exists():
        try:
            existing = json.loads(_FAILED_PUSH_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    existing.append(entry)
    _FAILED_PUSH_FILE.write_text(json.dumps(existing, indent=2))


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _batches(items: list, size: int):
    """Yield successive fixed-size batches from a list."""
    for i in range(0, len(items), size):
        yield items[i: i + size]

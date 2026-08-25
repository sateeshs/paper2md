#!/usr/bin/env python3
"""
Fill in missing math explanations for blocks already in Supabase.

Fetches all math_blocks where explanation IS NULL (or --force refills all),
runs MathExplainer on each, and UPDATEs the rows in-place.
Sections and paper IDs are never deleted or re-inserted.

Usage:
  python explain_math_only.py                                    # unexplained blocks only
  python explain_math_only.py --arxiv-id 2606.06447              # single paper
  python explain_math_only.py --section-id <uuid>                # single section (page)
  python explain_math_only.py --max-blocks 100                   # override cap
  python explain_math_only.py --force                            # re-explain all blocks
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv(Path(__file__).parent / ".env")


# Module-level guard to ensure configure_dspy() is called exactly once per process
_dspy_configured: bool = False


def _ensure_dspy() -> None:
    """Ensure DSPy is configured exactly once per process."""
    global _dspy_configured
    if not _dspy_configured:
        from lib.dspy_config import configure_dspy
        configure_dspy()
        _dspy_configured = True


def _get_client():
    from supabase import create_client  # type: ignore
    url = os.environ["SUPABASE_URL"].strip()
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"].strip()
    return create_client(url, key)


def _fetch_section(client, section_id: str) -> dict | None:
    """Resolve a section row with nested paper data. Returns None if unknown."""
    resp = (
        client.table("sections")
        .select("id, title, paper_id, papers(id, arxiv_id, title)")
        .eq("id", section_id).maybeSingle().execute()
    )
    if not resp.data:
        tqdm.write(f"[WARN] Section {section_id} not found in DB.")
    return resp.data


def _fetch_paper(client, arxiv_id: str) -> tuple[dict | None, list[str]]:
    """Resolve a paper row + its section IDs. Returns (None, []) if unknown."""
    resp = (
        client.table("papers").select("id, arxiv_id, title")
        .eq("arxiv_id", arxiv_id).maybeSingle().execute()
    )
    paper = resp.data
    if not paper:
        tqdm.write(f"[WARN] Paper {arxiv_id} not found in DB.")
        return None, []
    secs = client.table("sections").select("id, title, paper_id").eq("paper_id", paper["id"]).execute()
    section_ids = [s["id"] for s in (secs.data or [])]
    if not section_ids:
        tqdm.write(f"[WARN] No sections found for {arxiv_id}.")
    return paper, section_ids


def fetch_unexplained_blocks(
    client,
    arxiv_id: str | None,
    section_id: str | None,
    force: bool,
) -> list[dict]:
    """
    Return rows joined across math_blocks → sections → papers.
    Each row has the fields MathExplainer needs.

    If section_id is given, only blocks for that single section are returned.
    """
    # Resolve section IDs for the given arxiv_id first (nested filter
    # in the Supabase Python client doesn't work as an inner-join filter).
    section_ids: list[str] | None = None
    paper_meta: dict | None = None

    if section_id:
        # Single section mode — resolve paper via section
        sec = _fetch_section(client, section_id)
        if not sec:
            return []
        section_ids = [section_id]
        paper_meta = sec.get("papers")
        tqdm.write(f"[INFO] Section: {sec.get('title', '?')} (paper: {(paper_meta or {}).get('title', '?')})")
    elif arxiv_id:
        paper_meta, section_ids = _fetch_paper(client, arxiv_id)
        if not paper_meta:
            return []

    # Build base query
    query = (
        client.table("math_blocks")
        .select(
            "id, order_idx, env_type, latex_expr, context_before, context_after, explanation,"
            "sections(id, title, paper_id, papers(id, arxiv_id, title))"
        )
    )

    if not force:
        query = query.is_("explanation", "null")

    if section_ids is not None:
        query = query.in_("section_id", section_ids)

    resp = query.execute()
    rows = resp.data or []

    # Attach paper_meta to rows where join might be null (single-paper mode)
    if arxiv_id and paper_meta:
        for r in rows:
            if r.get("sections") and not r["sections"].get("papers"):
                r["sections"]["papers"] = paper_meta

    # Filter out rows where the join didn't resolve
    rows = [r for r in rows if r.get("sections") and r["sections"].get("papers")]

    return rows


def _format_exc(e: Exception) -> str:
    """Format exception for logging."""
    msg = str(e).strip()
    if msg:
        return f"{type(e).__name__}: {msg}"
    return type(e).__name__


def run(
    arxiv_id: str | None,
    max_blocks: int,
    force: bool,
    min_expr_len: int,
    paper_type: str,
    max_blocks_per_section: int | None = None,
    section_id: str | None = None,
) -> int:
    from lib.dspy_modules import MathExplainer
    from lib.models import MathBlock

    _ensure_dspy()
    explainer = MathExplainer()
    client = _get_client()

    tqdm.write("[INFO] Fetching unexplained math blocks from Supabase…")
    rows = fetch_unexplained_blocks(client, arxiv_id, section_id, force)

    if not rows:
        tqdm.write("[INFO] No unexplained blocks found.")
        return 0

    from lib.math_block_selection import prioritize_and_cap
    from lib.paper_type import infer_paper_type
    before = len(rows)
    rows = prioritize_and_cap(rows, max_blocks=max_blocks, max_blocks_per_section=max_blocks_per_section)
    tqdm.write(f"[INFO] Selected {len(rows)} of {before} candidate block(s)")

    # Infer document type per paper from its section titles; the --paper-type
    # CLI value remains the fallback for rows whose paper can't be resolved.
    titles_by_paper: dict[str, list[str]] = {}
    for r in rows:
        sec = r.get("sections") or {}
        pid = ((sec.get("papers") or {}).get("arxiv_id")) or "?"
        titles_by_paper.setdefault(pid, []).append(sec.get("title") or "")
    type_by_paper = {pid: infer_paper_type(titles) for pid, titles in titles_by_paper.items()}
    tqdm.write(f"[INFO] paper types: {type_by_paper}")

    updated = skipped = failed = 0

    for row in tqdm(rows, desc="Explaining math", unit="block"):
        section = row.get("sections") or {}
        paper = section.get("papers") or {}

        paper_title = paper.get("title") or "Unknown Paper"
        section_title = section.get("title") or "Unknown Section"

        # Build a MathBlock for the explainer
        block = MathBlock(
            order_idx=row["order_idx"],
            env_type=row["env_type"],
            latex_expr=row["latex_expr"],
            context_before=row.get("context_before") or "",
            context_after=row.get("context_after") or "",
            paper_type=type_by_paper.get(paper.get("arxiv_id") or "?", paper_type),
        )

        # Skip trivially short inline expressions
        if block.env_type == "inline" and len(block.latex_expr.strip()) < min_expr_len:
            skipped += 1
            continue

        explained = explainer.explain_block(block, paper_title, section_title)

        if not explained.explanation:
            # explain_block failed silently
            failed += 1
            continue

        # UPDATE in-place — never touch sections or papers rows
        try:
            client.table("math_blocks").update({
                "explanation":       explained.explanation,
                "explanation_model": explained.explanation_model,
            }).eq("id", row["id"]).execute()
            updated += 1
        except Exception as e:
            failed += 1
            tqdm.write(f"[ERROR] update failed for block {row['id']}: {_format_exc(e)}")

    tqdm.write(
        f"[INFO] Done — updated: {updated}, skipped (trivial): {skipped}, failed: {failed}"
    )
    return 1 if failed else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Fill missing math explanations in Supabase")
    ap.add_argument("--arxiv-id", metavar="ID", help="Limit to one paper")
    ap.add_argument("--section-id", metavar="UUID",
                    help="Limit to a single section (Supabase section UUID)")
    ap.add_argument("--max-blocks", type=int,
                    default=int(os.environ.get("PAPER2MD_MAX_MATH_BLOCKS", 200)),
                    help="Global cap on blocks to explain (default: 200)")
    ap.add_argument("--max-blocks-per-section", type=int, default=None,
                    help="Max blocks per section before global cap; ensures all sections covered")
    ap.add_argument("--force", action="store_true",
                    help="Re-explain blocks that already have explanations")
    ap.add_argument("--min-expr-len", type=int, default=6,
                    help="Skip inline exprs shorter than this (default: 6)")
    ap.add_argument("--paper-type",
                    choices=["research_paper", "textbook", "lecture_notes"],
                    default="research_paper",
                    help="Document type for explanation framing (default: research_paper)")
    args = ap.parse_args()

    if args.force and not (args.arxiv_id or args.section_id):
        ap.error("--force requires --arxiv-id or --section-id (it would rewrite every block)")

    return run(
        arxiv_id=args.arxiv_id,
        max_blocks=args.max_blocks,
        force=args.force,
        min_expr_len=args.min_expr_len,
        paper_type=args.paper_type,
        max_blocks_per_section=args.max_blocks_per_section,
        section_id=args.section_id,
    )


if __name__ == "__main__":
    raise SystemExit(main())

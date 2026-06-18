#!/usr/bin/env python3
"""
Fill in missing math explanations for blocks already in Supabase.

Fetches all math_blocks where explanation IS NULL (or --force refills all),
runs MathExplainer on each, and UPDATEs the rows in-place.
Sections and paper IDs are never deleted or re-inserted.

Usage:
  python explain_math_only.py                       # unexplained blocks only
  python explain_math_only.py --arxiv-id 2606.06447 # single paper
  python explain_math_only.py --max-blocks 100      # override cap
  python explain_math_only.py --force               # re-explain all blocks
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv(Path(__file__).parent / ".env")


def _get_client():
    from supabase import create_client  # type: ignore
    url = os.environ["SUPABASE_URL"].strip()
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"].strip()
    return create_client(url, key)


def fetch_unexplained_blocks(
    client,
    arxiv_id: str | None,
    force: bool,
) -> list[dict]:
    """
    Return rows joined across math_blocks → sections → papers.
    Each row has the fields MathExplainer needs.
    """
    # Resolve section IDs for the given arxiv_id first (nested filter
    # in the Supabase Python client doesn't work as an inner-join filter).
    section_ids: list[str] | None = None
    paper_meta: dict | None = None
    if arxiv_id:
        paper_resp = client.table("papers").select("id, arxiv_id, title").eq("arxiv_id", arxiv_id).single().execute()
        if not paper_resp.data:
            tqdm.write(f"[WARN] Paper {arxiv_id} not found in DB.")
            return []
        paper_meta = paper_resp.data
        secs_resp = client.table("sections").select("id, title, paper_id").eq("paper_id", paper_meta["id"]).execute()
        section_ids = [s["id"] for s in (secs_resp.data or [])]
        if not section_ids:
            tqdm.write(f"[WARN] No sections found for {arxiv_id}.")
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


def run(
    arxiv_id: str | None,
    max_blocks: int,
    force: bool,
    min_expr_len: int,
    paper_type: str,
) -> None:
    from lib.dspy_config import configure_dspy
    from lib.dspy_modules import MathExplainer
    from lib.models import MathBlock

    configure_dspy()
    explainer = MathExplainer()
    client = _get_client()

    tqdm.write("[INFO] Fetching unexplained math blocks from Supabase…")
    rows = fetch_unexplained_blocks(client, arxiv_id, force)

    if not rows:
        tqdm.write("[INFO] No unexplained blocks found.")
        return

    # Prioritise named envs (equation/align) over inline
    def priority(r: dict) -> int:
        return 0 if r["env_type"] != "inline" else 1

    rows.sort(key=priority)

    # Apply cap
    if len(rows) > max_blocks:
        tqdm.write(f"[INFO] {len(rows)} blocks found — capping at {max_blocks}")
        rows = rows[:max_blocks]

    tqdm.write(f"[INFO] Will explain {len(rows)} block(s)")

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
            paper_type=paper_type,
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
        client.table("math_blocks").update({
            "explanation":       explained.explanation,
            "explanation_model": explained.explanation_model,
        }).eq("id", row["id"]).execute()

        updated += 1

    tqdm.write(
        f"[INFO] Done — updated: {updated}, skipped (trivial): {skipped}, failed: {failed}"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Fill missing math explanations in Supabase")
    ap.add_argument("--arxiv-id", metavar="ID", help="Limit to one paper")
    ap.add_argument("--max-blocks", type=int,
                    default=int(os.environ.get("PAPER2MD_MAX_MATH_BLOCKS", 80)),
                    help="Cap on blocks to explain (default: 80)")
    ap.add_argument("--force", action="store_true",
                    help="Re-explain blocks that already have explanations")
    ap.add_argument("--min-expr-len", type=int, default=6,
                    help="Skip inline exprs shorter than this (default: 6)")
    ap.add_argument("--paper-type",
                    choices=["research_paper", "textbook", "lecture_notes"],
                    default="research_paper",
                    help="Document type for explanation framing (default: research_paper)")
    args = ap.parse_args()

    run(
        arxiv_id=args.arxiv_id,
        max_blocks=args.max_blocks,
        force=args.force,
        min_expr_len=args.min_expr_len,
        paper_type=args.paper_type,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

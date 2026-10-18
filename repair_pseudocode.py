#!/usr/bin/env python3
"""
Re-derive `algorithm_blocks.pseudocode_text` from the raw LaTeX already stored.

Rows written before `_pseudocode_to_text()` protected math spans had every
symbol stripped by the generic command remover: `$\\hat{\\theta}_0 \\leftarrow 0$`
reached the page as `$ _0  0$`, and the environment name leaked in as a literal
`algorithmic[1]` line.

`raw_pseudocode` holds the untouched original, so the repair is a pure local
recompute — no ArXiv download, no LLM call. Only `pseudocode_text` is written;
block IDs, captions and existing explanations are preserved.

Usage:
  python repair_pseudocode.py                       # every paper
  python repair_pseudocode.py --arxiv-id 2412.05265
  python repair_pseudocode.py --arxiv-id 2412.05265 --dry-run
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv(Path(__file__).parent / ".env")

BLOCK_SELECT = "id, order_idx, caption, raw_pseudocode, pseudocode_text, section_id"
# Captions were stripped by the same bug — "$\\epsilon$-greedy" was stored as
# "$$-greedy" — and are re-derived from the same raw source.


def _get_client():
    from supabase import create_client  # type: ignore

    url = os.environ["SUPABASE_URL"].strip()
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"].strip()
    return create_client(url, key)


def _section_ids(client, arxiv_id: str | None) -> list[str] | None:
    """Section IDs for one paper, or None meaning 'every section'."""
    if not arxiv_id:
        return None
    paper = (
        client.table("papers").select("id, arxiv_id")
        .eq("arxiv_id", arxiv_id).maybe_single().execute()
    ).data
    if not paper:
        tqdm.write(f"[ERROR] No paper with arxiv_id {arxiv_id}")
        return []
    secs = client.table("sections").select("id").eq("paper_id", paper["id"]).execute()
    return [s["id"] for s in (secs.data or [])]


def _fetch_blocks(client, section_ids: list[str] | None) -> list[dict]:
    """Algorithm blocks to consider, in chunks Supabase's `in` filter accepts."""
    if section_ids is None:
        return client.table("algorithm_blocks").select(BLOCK_SELECT).execute().data or []

    rows: list[dict] = []
    for start in range(0, len(section_ids), 100):
        chunk = section_ids[start:start + 100]
        resp = (
            client.table("algorithm_blocks").select(BLOCK_SELECT)
            .in_("section_id", chunk).execute()
        )
        rows.extend(resp.data or [])
    return rows


def run(arxiv_id: str | None, *, dry_run: bool) -> int:
    # Private but stable — the same import style repair_macros.py uses.
    from lib.latex_parse import (  # type: ignore
        _extract_algorithm_caption,
        _pseudocode_to_text,
    )

    client = _get_client()
    section_ids = _section_ids(client, arxiv_id)
    if section_ids == []:
        return 1

    blocks = _fetch_blocks(client, section_ids)
    if not blocks:
        tqdm.write("[INFO] No algorithm blocks found.")
        return 0

    updated = unchanged = skipped = 0
    for block in tqdm(blocks, desc="algorithm blocks", unit="blk"):
        raw = block.get("raw_pseudocode") or ""
        if not raw.strip():
            skipped += 1
            continue
        rebuilt = _pseudocode_to_text(raw)
        if not rebuilt.strip():
            # Never replace something readable with nothing.
            skipped += 1
            continue
        changes: dict[str, str] = {}
        if rebuilt != (block.get("pseudocode_text") or ""):
            changes["pseudocode_text"] = rebuilt

        caption = _extract_algorithm_caption(raw)
        if caption and caption != (block.get("caption") or ""):
            changes["caption"] = caption

        if not changes:
            unchanged += 1
            continue
        if not dry_run:
            client.table("algorithm_blocks").update(changes).eq(
                "id", block["id"]
            ).execute()
        updated += 1

    verb = "would update" if dry_run else "updated"
    tqdm.write(
        f"[INFO] Done — {verb} {updated} block(s); "
        f"{unchanged} already current, {skipped} skipped (no usable source)"
    )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Re-derive pseudocode_text from stored raw_pseudocode"
    )
    ap.add_argument("--arxiv-id", metavar="ID", default=None,
                    help="Limit to one paper (default: every paper)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Report what would change, write nothing")
    args = ap.parse_args()
    return run(args.arxiv_id, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())

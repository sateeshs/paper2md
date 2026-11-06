#!/usr/bin/env python3
"""
Fill papers.authors and papers.affiliations for papers processed before search
covered them (migration 009). New papers get both from summarize_papers.py.

This script:
  1. Fetches papers with an arxiv_id from Supabase
  2. Authors (+ any submitter-entered affiliations): arXiv Atom API, 50 ids per request
  3. Affiliations: downloads each LaTeX source and runs extract_affiliations()
  4. UPDATEs only authors / affiliations — status, sections, math are untouched

Usage:
  python backfill_paper_metadata.py                        # papers missing either field
  python backfill_paper_metadata.py --arxiv-id 2603.04735  # one paper
  python backfill_paper_metadata.py --authors-only         # skip source downloads
  python backfill_paper_metadata.py --force --dry-run      # recompute all, write nothing
"""
from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv(Path(__file__).parent / ".env")

# Pause between arXiv API batches (source downloads pace themselves).
_API_BATCH_PAUSE_S = 3


def _get_client():
    from supabase import create_client  # type: ignore
    url = os.environ["SUPABASE_URL"].strip()
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"].strip()
    return create_client(url, key)


def fetch_papers(client, arxiv_id: str | None, force: bool) -> list[dict]:
    query = client.table("papers").select("arxiv_id, authors, affiliations").not_.is_("arxiv_id", "null")
    if arxiv_id:
        query = query.eq("arxiv_id", arxiv_id)
    rows = query.execute().data or []
    if force or arxiv_id:
        return rows
    return [r for r in rows if not r.get("authors") or not r.get("affiliations")]


def fetch_api_metadata(ids: list[str]) -> dict:
    """arXiv API metadata (authors + any submitter-entered affiliations) by id."""
    from lib.arxiv_metadata import MAX_IDS_PER_REQUEST, fetch_arxiv_metadata

    meta: dict = {}
    for start in range(0, len(ids), MAX_IDS_PER_REQUEST):
        batch = ids[start:start + MAX_IDS_PER_REQUEST]
        try:
            meta.update(fetch_arxiv_metadata(batch))
        except Exception as e:  # noqa: BLE001 — one failed batch must not stop the rest
            tqdm.write(f"[WARN] arXiv API batch at {start} failed: {e}")
            continue
        time.sleep(_API_BATCH_PAUSE_S)
    return meta


def fetch_affiliations(arxiv_id: str) -> tuple[str, ...]:
    from lib.arxiv_source import fetch_arxiv_latex_full
    from lib.latex_affiliations import extract_affiliations

    result = fetch_arxiv_latex_full(arxiv_id)
    full = result[1] if result else None
    return extract_affiliations(full or "")


def main() -> int:
    ap = argparse.ArgumentParser(description="Backfill papers.authors and papers.affiliations")
    ap.add_argument("--arxiv-id", metavar="ID", help="Limit to one paper")
    ap.add_argument("--authors-only", action="store_true", help="Skip LaTeX downloads")
    ap.add_argument("--force", action="store_true", help="Recompute papers that already have both")
    ap.add_argument("--dry-run", action="store_true", help="Print what would change, write nothing")
    args = ap.parse_args()

    client = _get_client()
    rows = fetch_papers(client, args.arxiv_id, args.force)
    print(f"{len(rows)} paper(s) to backfill")
    from lib.latex_affiliations import merge_affiliations

    api = fetch_api_metadata([r["arxiv_id"] for r in rows])

    updated = failed = 0
    for row in tqdm(rows, desc="Papers"):
        aid = row["arxiv_id"]
        meta = api.get(aid)
        update: dict = {}
        if meta and meta.authors:
            update["authors"] = list(meta.authors)
        latex_affils: tuple[str, ...] = ()
        if not args.authors_only:
            try:
                latex_affils = fetch_affiliations(aid)
            except Exception as e:  # noqa: BLE001 — keep going; report at the end
                tqdm.write(f"[WARN] {aid}: source download failed: {e}")
                failed += 1
        affils = merge_affiliations(latex_affils, meta.affiliations if meta else ())
        if affils:
            update["affiliations"] = list(affils)
        if not update:
            continue
        tqdm.write(f"{aid}: {len(update.get('authors', []))} authors, "
                   f"affiliations={update.get('affiliations', [])[:3]}")
        if not args.dry_run:
            client.table("papers").update(update).eq("arxiv_id", aid).execute()
        updated += 1

    print(f"Done: {updated} updated, {failed} source download(s) failed"
          + (" (dry run — nothing written)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

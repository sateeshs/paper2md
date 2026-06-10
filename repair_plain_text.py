#!/usr/bin/env python3
"""
Re-generate plain_text for sections from their stored raw_latex.

Sections processed before the pylatexenc inline-math fix have garbled
text like "q_ (e d)" instead of "$q_\\phi(e \\mid d)$".

This script:
  1. Fetches sections where raw_latex IS NOT NULL from Supabase
  2. Re-runs _latex_to_text() on raw_latex (with the fixed code)
  3. UPDATEs only plain_text — no sections or math_blocks are touched

Usage:
  python repair_plain_text.py                        # all sections
  python repair_plain_text.py --arxiv-id 2606.06447  # one paper
"""

from __future__ import annotations

import argparse
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


def fetch_sections(client, arxiv_id: str | None) -> list[dict]:
    query = (
        client.table("sections")
        .select("id, raw_latex, papers(arxiv_id)")
        .not_.is_("raw_latex", "null")
    )
    if arxiv_id:
        query = query.eq("papers.arxiv_id", arxiv_id)
    resp = query.execute()
    rows = resp.data or []
    if arxiv_id:
        rows = [r for r in rows if r.get("papers")]
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="Repair plain_text from raw_latex in Supabase")
    ap.add_argument("--arxiv-id", metavar="ID", help="Limit to one paper")
    args = ap.parse_args()

    from lib.latex_parse import _latex_to_text  # type: ignore  # private but stable

    client = _get_client()

    tqdm.write("[INFO] Fetching sections with raw_latex…")
    sections = fetch_sections(client, args.arxiv_id)

    if not sections:
        tqdm.write("[INFO] No sections found.")
        return 0

    tqdm.write(f"[INFO] Re-generating plain_text for {len(sections)} section(s)…")
    updated = failed = 0

    for row in tqdm(sections, desc="Repairing sections", unit="section"):
        raw_latex = row.get("raw_latex") or ""
        if not raw_latex.strip():
            continue
        try:
            new_plain_text = _latex_to_text(raw_latex)
            client.table("sections").update(
                {"plain_text": new_plain_text}
            ).eq("id", row["id"]).execute()
            updated += 1
        except Exception as e:
            tqdm.write(f"[WARN] Section {row['id']}: {e}")
            failed += 1

    tqdm.write(f"[INFO] Done — updated: {updated}, failed: {failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

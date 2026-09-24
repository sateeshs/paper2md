#!/usr/bin/env python3
"""
Re-expand the paper's own LaTeX macros in rows that were written without them.

Papers define most of their shorthands (\\xb, \\mylangle, …) in the preamble.
Rows processed before `parse_latex_sections()` took a `preamble` argument stored
those control sequences verbatim, so KaTeX prints them as literal text instead
of the symbol they stand for.

This script re-downloads the ArXiv source, reads the definitions out of its
preamble, and expands them in place. It UPDATEs `sections.raw_latex`,
`sections.plain_text` and `math_blocks.latex_expr` plus its
context windows only — section IDs (and so
existing URLs), math-block IDs and their LLM explanations are preserved.

Usage:
  python repair_macros.py --arxiv-id 2510.03989
  python repair_macros.py --arxiv-id 2510.03989 --dry-run
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv(Path(__file__).parent / ".env")

SECTION_SELECT = "id, order_idx, title, raw_latex"
MATH_SELECT = "id, order_idx, latex_expr, context_before, context_after"
# Fields on math_blocks that hold LaTeX and therefore need the same expansion.
MATH_LATEX_FIELDS = ("latex_expr", "context_before", "context_after")
ALGO_SELECT = "id, order_idx, raw_pseudocode, pseudocode_text, context_before, context_after"
# Algorithm pseudocode carries the paper's macros too — a stale "$\\vw$" is an
# undefined control sequence in KaTeX exactly like a stale "$\\policy$".
ALGO_LATEX_FIELDS = ("raw_pseudocode", "pseudocode_text", "context_before", "context_after")


def _get_client():
    from supabase import create_client  # type: ignore

    url = os.environ["SUPABASE_URL"].strip()
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"].strip()
    return create_client(url, key)


def _fetch_preamble(arxiv_id: str) -> str:
    """Return the preamble of the paper's ArXiv source, or '' if unavailable."""
    from lib.arxiv_source import fetch_arxiv_latex_full, split_preamble

    result = fetch_arxiv_latex_full(arxiv_id)
    if not result:
        return ""
    _body, full_source = result
    return split_preamble(full_source or "")


def _repair_paper(client, paper: dict, *, dry_run: bool) -> tuple[int, int, int]:
    """Expand macros for one paper.

    Returns (sections_updated, math_blocks_updated, algorithm_blocks_updated).
    """
    from lib.latex_macros import expand_custom_macros
    from lib.latex_parse import _latex_to_text  # type: ignore  # private but stable

    arxiv_id = paper["arxiv_id"]
    preamble = _fetch_preamble(arxiv_id)
    if not preamble.strip():
        tqdm.write(f"[WARN] {arxiv_id}: no preamble available — skipping")
        return 0, 0, 0

    sections = (
        client.table("sections")
        .select(SECTION_SELECT)
        .eq("paper_id", paper["id"])
        .order("order_idx")
        .execute()
        .data
        or []
    )

    sections_updated = blocks_updated = algos_updated = 0

    for section in sections:
        raw_latex = section.get("raw_latex") or ""
        expanded = expand_custom_macros(raw_latex, preamble) if raw_latex.strip() else ""
        if expanded and expanded != raw_latex:
            if not dry_run:
                client.table("sections").update(
                    {"raw_latex": expanded, "plain_text": _latex_to_text(expanded)}
                ).eq("id", section["id"]).execute()
            sections_updated += 1

        blocks = (
            client.table("math_blocks")
            .select(MATH_SELECT)
            .eq("section_id", section["id"])
            .order("order_idx")
            .execute()
            .data
            or []
        )
        for block in blocks:
            changes = {}
            for field in MATH_LATEX_FIELDS:
                value = block.get(field) or ""
                if not value.strip():
                    continue
                expanded_value = expand_custom_macros(value, preamble)
                if expanded_value and expanded_value != value:
                    changes[field] = expanded_value
            if not changes:
                continue
            if not dry_run:
                client.table("math_blocks").update(changes).eq("id", block["id"]).execute()
            blocks_updated += 1

        algos = (
            client.table("algorithm_blocks")
            .select(ALGO_SELECT)
            .eq("section_id", section["id"])
            .order("order_idx")
            .execute()
            .data
            or []
        )
        for algo in algos:
            changes = {}
            for field in ALGO_LATEX_FIELDS:
                value = algo.get(field) or ""
                if not value.strip():
                    continue
                expanded_value = expand_custom_macros(value, preamble)
                if expanded_value and expanded_value != value:
                    changes[field] = expanded_value
            if not changes:
                continue
            if not dry_run:
                client.table("algorithm_blocks").update(changes).eq(
                    "id", algo["id"]
                ).execute()
            algos_updated += 1

        tqdm.write(
            f"[INFO] {arxiv_id} §{section['order_idx']} {section['title']}: "
            f"{len(blocks)} blocks, {len(algos)} algorithms"
        )

    return sections_updated, blocks_updated, algos_updated


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Re-expand preamble macros in stored sections and math blocks"
    )
    ap.add_argument("--arxiv-id", metavar="ID", required=True, help="Paper to repair")
    ap.add_argument(
        "--dry-run", action="store_true", help="Report what would change, write nothing"
    )
    args = ap.parse_args()

    client = _get_client()
    papers = (
        client.table("papers")
        .select("id, arxiv_id, title")
        .eq("arxiv_id", args.arxiv_id)
        .execute()
        .data
        or []
    )
    if not papers:
        tqdm.write(f"[ERROR] No paper with arxiv_id {args.arxiv_id}")
        return 1

    total_sections = total_blocks = total_algos = 0
    for paper in papers:
        sections, blocks, algos = _repair_paper(client, paper, dry_run=args.dry_run)
        total_sections += sections
        total_blocks += blocks
        total_algos += algos

    verb = "would update" if args.dry_run else "updated"
    tqdm.write(
        f"[INFO] Done — {verb} {total_sections} section(s), "
        f"{total_blocks} math block(s), {total_algos} algorithm block(s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

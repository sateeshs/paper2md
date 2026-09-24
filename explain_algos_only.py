#!/usr/bin/env python3
"""
Generate explanations for algorithm blocks already in Supabase.

The mirror of `explain_math_only.py`, for `algorithm_blocks`. It UPDATEs rows
in place — no section or block is deleted, so existing URLs and math
explanations are untouched.

Papers processed before AlgorithmExplainer existed have pseudocode but a null
`explanation`, which is why the "Show explanation" toggle never appears for
them.

Run `repair_pseudocode.py` first on older papers: the explainer is fed
`pseudocode_text`, and rows written before math spans were protected contain
gutted source ("$ _0  0$") that no model can explain well.

Usage:
  python explain_algos_only.py                          # every unexplained block
  python explain_algos_only.py --arxiv-id 2412.05265
  python explain_algos_only.py --arxiv-id 2412.05265 --force
  python explain_algos_only.py --section-id <uuid> --dry-run
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv(Path(__file__).parent / ".env")

BLOCK_SELECT = (
    "id, order_idx, caption, raw_pseudocode, pseudocode_text, "
    "context_before, context_after, explanation, "
    "sections(id, title, paper_id, papers(id, arxiv_id, title))"
)

# Module-level guard so configure_dspy() runs exactly once per process.
_dspy_configured: bool = False


def _ensure_dspy() -> None:
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


def _resolve_section_ids(
    client, arxiv_id: str | None, section_id: str | None
) -> tuple[list[str] | None, bool]:
    """Return (section_ids, ok). None means 'every section'."""
    if section_id:
        return [section_id], True

    if not arxiv_id:
        return None, True

    paper = (
        client.table("papers").select("id, arxiv_id, title")
        .eq("arxiv_id", arxiv_id).maybe_single().execute()
    ).data
    if not paper:
        tqdm.write(f"[ERROR] No paper with arxiv_id {arxiv_id}")
        return None, False

    secs = client.table("sections").select("id").eq("paper_id", paper["id"]).execute()
    ids = [s["id"] for s in (secs.data or [])]
    if not ids:
        tqdm.write(f"[WARN] No sections found for {arxiv_id}.")
    return ids, True


def fetch_unexplained_blocks(
    client, arxiv_id: str | None, section_id: str | None, force: bool
) -> list[dict]:
    """Rows joined across algorithm_blocks → sections → papers."""
    section_ids, ok = _resolve_section_ids(client, arxiv_id, section_id)
    if not ok:
        return []

    def _query(ids: list[str] | None) -> list[dict]:
        q = client.table("algorithm_blocks").select(BLOCK_SELECT)
        if not force:
            q = q.is_("explanation", "null")
        if ids is not None:
            q = q.in_("section_id", ids)
        return q.execute().data or []

    if section_ids is None:
        rows = _query(None)
    else:
        # Supabase caps the `in` list length — page through in chunks.
        rows = []
        for start in range(0, len(section_ids), 100):
            rows.extend(_query(section_ids[start:start + 100]))

    # Drop rows whose join did not resolve — the explainer needs both titles.
    return [r for r in rows if r.get("sections") and r["sections"].get("papers")]


def _format_exc(e: Exception) -> str:
    msg = str(e).strip()
    return f"{type(e).__name__}: {msg}" if msg else type(e).__name__


def run(
    arxiv_id: str | None,
    section_id: str | None,
    max_blocks: int,
    force: bool,
    dry_run: bool,
) -> int:
    from lib.dspy_modules import AlgorithmExplainer
    from lib.models import AlgorithmBlock

    client = _get_client()

    tqdm.write("[INFO] Fetching unexplained algorithm blocks from Supabase…")
    rows = fetch_unexplained_blocks(client, arxiv_id, section_id, force)
    if not rows:
        tqdm.write("[INFO] No unexplained algorithm blocks found.")
        return 0

    if len(rows) > max_blocks:
        tqdm.write(f"[INFO] Capping {len(rows)} candidate(s) to {max_blocks}")
        rows = rows[:max_blocks]

    if dry_run:
        for row in rows:
            section = row["sections"]
            tqdm.write(
                f"[DRY] {section['papers'].get('arxiv_id')} "
                f"§{section.get('title')} — {row.get('caption') or 'Unnamed Algorithm'}"
            )
        tqdm.write(f"[INFO] Done — would explain {len(rows)} block(s)")
        return 0

    _ensure_dspy()
    explainer = AlgorithmExplainer()

    explained = failed = 0
    for row in tqdm(rows, desc="algorithm blocks", unit="blk"):
        section = row["sections"]
        paper = section["papers"]
        block = AlgorithmBlock(
            order_idx=row.get("order_idx") or 0,
            caption=row.get("caption"),
            raw_pseudocode=row.get("raw_pseudocode") or "",
            pseudocode_text=row.get("pseudocode_text"),
            context_before=row.get("context_before"),
            context_after=row.get("context_after"),
        )
        try:
            result = explainer.explain_block(
                block,
                paper_title=paper.get("title") or paper.get("arxiv_id") or "",
                section_title=section.get("title") or "",
            )
        except Exception as e:
            tqdm.write(f"[WARN] block {row['id']}: {_format_exc(e)}")
            failed += 1
            continue

        if not result.explanation:
            # explain_block swallows provider errors and returns the block as-is.
            failed += 1
            continue

        client.table("algorithm_blocks").update({
            "explanation": result.explanation,
            "explanation_model": result.explanation_model,
        }).eq("id", row["id"]).execute()
        explained += 1

    tqdm.write(f"[INFO] Done — explained {explained} block(s), {failed} failed")
    return 0 if explained or not failed else 1


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Generate explanations for algorithm blocks already in Supabase"
    )
    ap.add_argument("--arxiv-id", metavar="ID", default=None, help="Limit to one paper")
    ap.add_argument("--section-id", metavar="UUID", default=None,
                    help="Limit to a single section (Supabase section UUID)")
    ap.add_argument("--max-blocks", type=int,
                    default=int(os.environ.get("PAPER2MD_MAX_ALGORITHM_BLOCKS", 10)),
                    help="Cap blocks explained in one run (default: 10)")
    ap.add_argument("--force", action="store_true",
                    help="Re-explain blocks that already have an explanation")
    ap.add_argument("--dry-run", action="store_true",
                    help="List what would be explained, call no model")
    args = ap.parse_args()
    return run(args.arxiv_id, args.section_id, args.max_blocks, args.force, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())

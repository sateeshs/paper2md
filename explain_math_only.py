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
  python explain_math_only.py --ask-key                          # type the API key at runtime
  python explain_math_only.py --dry-run --max-blocks 3           # preview, write nothing

With --ask-key the key is entered at a hidden prompt, held in memory for this
process only, and never written to .env or any server.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from tqdm import tqdm

from lib.explanation_quality import find_defect
from lib.key_prompt import (
    PROVIDER_KEYS,
    KeyPromptError,
    ensure_provider_key,
    read_key_from_stdin,
)

load_dotenv(Path(__file__).parent / ".env")


# How often one-per-provider mode looks for providers whose quota came back,
# even while every lane is still busy with a block.
REFILL_INTERVAL_S = 60

# Exit status when every provider's daily quota is used up — distinct from 1
# (some blocks failed) so a scheduler can wait for the reset and rerun.
EXIT_QUOTA_EXHAUSTED = 3

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
        .eq("id", section_id).maybe_single().execute()
    )
    if not resp.data:
        tqdm.write(f"[WARN] Section {section_id} not found in DB.")
    return resp.data


def _fetch_paper(client, arxiv_id: str) -> tuple[dict | None, list[str]]:
    """Resolve a paper row + its section IDs. Returns (None, []) if unknown."""
    resp = (
        client.table("papers").select("id, arxiv_id, title")
        .eq("arxiv_id", arxiv_id).maybe_single().execute()
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
            "sections(id, title, level, paper_id, papers(id, arxiv_id, title))"
        )
    )

    if not force:
        query = query.is_("explanation", "null")

    if section_ids is not None:
        query = query.in_("section_id", section_ids)

    # PostgREST caps a response at 1000 rows. Without paging, a --force run
    # (which has no "explanation is null" filter to shrink the set) refetches
    # the same first 1000 rows every time and can never reach the rest.
    rows = _fetch_all(query)

    # Attach paper_meta to rows where join might be null (single-paper mode)
    if arxiv_id and paper_meta:
        for r in rows:
            if r.get("sections") and not r["sections"].get("papers"):
                r["sections"]["papers"] = paper_meta

    # Filter out rows where the join didn't resolve
    rows = [r for r in rows if r.get("sections") and r["sections"].get("papers")]

    return rows


_PAGE_SIZE = 1000


def _fetch_all(query) -> list[dict]:
    """Page through a PostgREST query until every matching row is retrieved."""
    rows: list[dict] = []
    offset = 0
    while True:
        page = query.range(offset, offset + _PAGE_SIZE - 1).execute().data or []
        rows.extend(page)
        if len(page) < _PAGE_SIZE:
            return rows
        offset += _PAGE_SIZE


def _paper_section_levels(client, paper_uuid: str | None) -> set[int]:
    """Outline levels present anywhere in a paper, for document-type inference.

    Queried separately from the selected blocks: a capped run may not include
    any chapter-level section, which would make a book look like an article.
    """
    if not paper_uuid:
        return set()
    try:
        resp = (
            client.table("sections")
            .select("level")
            .eq("paper_id", paper_uuid)
            .not_.is_("level", "null")
            .execute()
        )
        return {r["level"] for r in (resp.data or []) if r.get("level") is not None}
    except Exception:
        return set()


def _format_exc(e: Exception) -> str:
    """Format exception for logging."""
    msg = str(e).strip()
    if msg:
        return f"{type(e).__name__}: {msg}"
    return type(e).__name__


def _block_for_row(
    row: dict, type_by_paper: dict[str, str], paper_type: str | None
) -> tuple["MathBlock", str, str]:
    """Build the MathBlock plus paper/section titles the explainer needs."""
    from lib.models import MathBlock

    section = row.get("sections") or {}
    paper = section.get("papers") or {}
    block = MathBlock(
        order_idx=row["order_idx"],
        env_type=row["env_type"],
        latex_expr=row["latex_expr"],
        context_before=row.get("context_before") or "",
        context_after=row.get("context_after") or "",
        paper_type=type_by_paper.get(
            paper.get("arxiv_id") or "?", paper_type or "research_paper"
        ),
    )
    return block, paper.get("title") or "Unknown Paper", section.get("title") or "Unknown Section"


def _record(row: dict, block, explained, section_title: str, client, dry_run: bool) -> bool:
    """Validate one explanation and write it. Returns True if it was (or would be) written."""
    if not explained.explanation:
        return False  # explain_block failed silently

    # Weak or overloaded models return placeholders and repetition loops
    # that parse as valid JSON. Writing those is worse than writing
    # nothing: the block looks explained and never gets retried.
    defect = find_defect(explained.explanation)
    if defect:
        tqdm.write(f"[REJECT] block {row['id']}: {defect}")
        return False

    if dry_run:
        # Verify the provider and the output before writing to the live DB.
        preview = json.loads(explained.explanation)
        tqdm.write(
            f"\n[DRY RUN] {section_title} — {block.env_type} block {block.order_idx}\n"
            f"  expr: {block.latex_expr.strip()[:90]}\n"
            f"  what_it_computes: {str(preview.get('what_it_computes'))[:220]}\n"
            f"  model: {explained.explanation_model}"
        )
        return True

    # UPDATE in-place — never touch sections or papers rows
    try:
        client.table("math_blocks").update({
            "explanation":       explained.explanation,
            "explanation_model": explained.explanation_model,
        }).eq("id", row["id"]).execute()
        return True
    except Exception as e:
        tqdm.write(f"[ERROR] update failed for block {row['id']}: {_format_exc(e)}")
        return False


def _complete_if_explaining(client, arxiv_id: str) -> None:
    """Flip a paper readable-while-explaining ("explaining") to "complete".

    Called once a pass has worked through every remaining block. Blocks that
    stayed unexplained (trivial, or rejected every time) do not hold it back.
    """
    client.table("papers").update({"status": "complete"}).eq(
        "arxiv_id", arxiv_id
    ).eq("status", "explaining").execute()


def _explain_rows(
    rows: list[dict],
    explainer,
    client,
    type_by_paper: dict[str, str],
    paper_type: str | None,
    min_expr_len: int,
    dry_run: bool,
    workers: int,
) -> dict:
    """Explain rows on `workers` threads; validate and write on this thread.

    At most `workers` blocks are in flight, so when every provider is spent
    the run stops after the calls already started — those are still written.
    """
    from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

    from lib.dspy_config import ProvidersExhaustedError

    counts = {"updated": 0, "skipped": 0, "failed": 0, "exhausted": False}
    pending = iter(rows)
    in_flight: dict = {}

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool, \
            tqdm(total=len(rows), desc="Explaining math", unit="block") as bar:

        def submit_next() -> bool:
            for row in pending:
                block, paper_title, section_title = _block_for_row(row, type_by_paper, paper_type)
                # Skip trivially short inline expressions
                if block.env_type == "inline" and len(block.latex_expr.strip()) < min_expr_len:
                    counts["skipped"] += 1
                    bar.update()
                    continue
                future = pool.submit(explainer.explain_block, block, paper_title, section_title)
                in_flight[future] = (row, block, section_title)
                return True
            return False

        for _ in range(max(1, workers)):
            if not submit_next():
                break

        while in_flight:
            done, _ = wait(in_flight, return_when=FIRST_COMPLETED)
            for future in done:
                row, block, section_title = in_flight.pop(future)
                bar.update()
                try:
                    explained = future.result()
                except ProvidersExhaustedError as e:
                    # Every remaining block would fail the same way; stop so a rerun
                    # after the quota resets picks up exactly where this left off.
                    if not counts["exhausted"]:
                        tqdm.write(f"[STOP] {e} — retry after the quotas reset")
                    counts["exhausted"] = True
                    continue
                written = _record(row, block, explained, section_title, client, dry_run)
                counts["updated" if written else "failed"] += 1
                if not counts["exhausted"]:
                    submit_next()
    return counts


def _explain_on(explainer, provider: str, block, paper_title: str, section_title: str):
    """Explain one block on one provider (runs on a worker thread)."""
    from lib.dspy_modules import pinned_provider

    with pinned_provider(provider):
        return explainer.explain_block(block, paper_title, section_title)


def _explain_rows_per_provider(
    rows: list[dict],
    explainer,
    client,
    type_by_paper: dict[str, str],
    paper_type: str | None,
    min_expr_len: int,
    dry_run: bool,
) -> dict:
    """Give every provider with quota left exactly one block at a time.

    All free quotas are spent concurrently instead of one after another. A
    provider that runs out puts its block back for another provider; the run
    stops once no provider is left and blocks remain.
    """
    from collections import deque
    from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

    from lib.dspy_config import PROVIDER_CONFIG, ProviderQuotaError, live_providers

    counts = {"updated": 0, "skipped": 0, "failed": 0, "exhausted": False}
    queue = deque(rows)
    in_flight: dict = {}

    with ThreadPoolExecutor(max_workers=len(PROVIDER_CONFIG)) as pool, \
            tqdm(total=len(rows), desc="Explaining math", unit="block") as bar:

        def next_block():
            while queue:
                row = queue.popleft()
                block, paper_title, section_title = _block_for_row(row, type_by_paper, paper_type)
                if block.env_type == "inline" and len(block.latex_expr.strip()) < min_expr_len:
                    counts["skipped"] += 1
                    bar.update()
                    continue
                return row, block, paper_title, section_title
            return None

        def fill() -> None:
            busy = {provider for provider, *_ in in_flight.values()}
            for provider in live_providers():
                if provider in busy:
                    continue
                item = next_block()
                if item is None:
                    return
                row, block, paper_title, section_title = item
                future = pool.submit(_explain_on, explainer, provider, block, paper_title, section_title)
                in_flight[future] = (provider, row, block, section_title)

        tqdm.write(f"[INFO] one block at a time on each of: {', '.join(live_providers()) or 'none'}")
        fill()
        while in_flight:
            done, _ = wait(in_flight, timeout=REFILL_INTERVAL_S, return_when=FIRST_COMPLETED)
            for future in done:
                provider, row, block, section_title = in_flight.pop(future)
                try:
                    explained = future.result()
                except ProviderQuotaError:
                    tqdm.write(f"[INFO] {provider} quota spent — its block goes to another provider")
                    queue.appendleft(row)
                    continue
                bar.update()
                written = _record(row, block, explained, section_title, client, dry_run)
                counts["updated" if written else "failed"] += 1
            fill()

        if next_block() is not None:
            tqdm.write("[STOP] Every provider's quota is spent — retry after the quotas reset")
            counts["exhausted"] = True
    return counts


def run(
    arxiv_id: str | None,
    max_blocks: int,
    force: bool,
    min_expr_len: int,
    paper_type: str | None,
    max_blocks_per_section: int | None = None,
    section_id: str | None = None,
    dry_run: bool = False,
    workers: int = 1,
    one_per_provider: bool = False,
) -> int:
    from lib.dspy_modules import MathExplainer

    from lib.dspy_config import ProvidersExhaustedError

    try:
        _ensure_dspy()
    except ProvidersExhaustedError as e:
        tqdm.write(f"[STOP] {e} — retry after the quotas reset")
        return EXIT_QUOTA_EXHAUSTED
    explainer = MathExplainer()
    client = _get_client()

    tqdm.write("[INFO] Fetching unexplained math blocks from Supabase…")
    rows = fetch_unexplained_blocks(client, arxiv_id, section_id, force)

    if not rows:
        tqdm.write("[INFO] No unexplained blocks found.")
        if arxiv_id and not dry_run:
            _complete_if_explaining(client, arxiv_id)
        return 0

    from lib.math_block_selection import prioritize_and_cap
    from lib.paper_type import infer_paper_type
    before = len(rows)
    rows = prioritize_and_cap(rows, max_blocks=max_blocks, max_blocks_per_section=max_blocks_per_section)
    tqdm.write(f"[INFO] Selected {len(rows)} of {before} candidate block(s)")

    # An explicit --paper-type wins; the heuristic only fills in when the user
    # did not say. Inferring over a stated choice silently ignored the flag.
    titles_by_paper: dict[str, list[str]] = {}
    paper_uuid_by_arxiv: dict[str, str] = {}
    for r in rows:
        sec = r.get("sections") or {}
        pid = ((sec.get("papers") or {}).get("arxiv_id")) or "?"
        titles_by_paper.setdefault(pid, []).append(sec.get("title") or "")
        if sec.get("paper_id"):
            paper_uuid_by_arxiv.setdefault(pid, sec["paper_id"])

    if paper_type is not None:
        type_by_paper = {pid: paper_type for pid in titles_by_paper}
        tqdm.write(f"[INFO] paper type: {paper_type} (from --paper-type)")
    else:
        # Levels must come from the paper's full outline, not just the blocks
        # selected here — a capped run may not include any chapter-level row.
        type_by_paper = {
            pid: infer_paper_type(
                titles,
                section_levels=_paper_section_levels(client, paper_uuid_by_arxiv.get(pid)),
            )
            for pid, titles in titles_by_paper.items()
        }
        tqdm.write(f"[INFO] paper types (inferred): {type_by_paper}")

    if one_per_provider:
        counts = _explain_rows_per_provider(
            rows, explainer, client, type_by_paper, paper_type, min_expr_len, dry_run
        )
    else:
        counts = _explain_rows(
            rows, explainer, client, type_by_paper, paper_type, min_expr_len, dry_run, workers
        )
    updated, skipped, failed = counts["updated"], counts["skipped"], counts["failed"]
    exhausted = counts["exhausted"]
    if arxiv_id and not dry_run and not exhausted and len(rows) == before:
        _complete_if_explaining(client, arxiv_id)

    verb = "would update" if dry_run else "updated"
    tqdm.write(
        f"[INFO] Done — {verb}: {updated}, skipped (trivial): {skipped}, failed: {failed}"
        + ("  (no rows were written)" if dry_run else "")
    )
    if exhausted:
        return EXIT_QUOTA_EXHAUSTED
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
    ap.add_argument("--workers", type=int, default=1, metavar="N",
                    help="Explain N blocks concurrently (default 1). Calls stay "
                         "spaced to each provider's rpm across all workers.")
    ap.add_argument("--one-per-provider", action="store_true",
                    help="Give every free provider with quota left one block at a "
                         "time, so all quotas are spent concurrently (ignores --workers)")
    ap.add_argument("--min-expr-len", type=int, default=6,
                    help="Skip inline exprs shorter than this (default: 6)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Generate explanations and print them without writing to "
                         "Supabase; use this to check a key and output quality first")
    ap.add_argument("--key-stdin", action="store_true",
                    help="Read the API key from stdin (for contexts with no terminal, "
                         "e.g. piping from a password manager)")
    ap.add_argument("--ask-key", action="store_true",
                    help="Prompt for the LLM API key at runtime instead of reading it "
                         "from the environment; the key is never stored")
    ap.add_argument("--provider", choices=sorted(PROVIDER_KEYS),
                    help="LLM provider to use (default: PAPER2MD_LLM_PROVIDER, or gemini)")
    ap.add_argument("--paper-type",
                    choices=["research_paper", "textbook", "lecture_notes"],
                    default=None,
                    help="Document type for explanation framing. Overrides the "
                         "heuristic; omit it to infer from the paper's structure.")
    args = ap.parse_args()

    if args.force and not (args.arxiv_id or args.section_id):
        ap.error("--force requires --arxiv-id or --section-id (it would rewrite every block)")

    provider = args.provider or os.environ.get("PAPER2MD_LLM_PROVIDER", "gemini").strip().lower()
    if args.provider:
        # An explicit --provider must also steer configure_dspy's selection order.
        os.environ["PAPER2MD_LLM_PROVIDER"] = provider
    if args.key_stdin:
        try:
            read_key_from_stdin(provider)
        except KeyPromptError as e:
            ap.error(str(e))
    elif args.ask_key:
        try:
            ensure_provider_key(provider, ask=True)
        except KeyPromptError as e:
            ap.error(str(e))

    return run(
        arxiv_id=args.arxiv_id,
        max_blocks=args.max_blocks,
        force=args.force,
        min_expr_len=args.min_expr_len,
        paper_type=args.paper_type,
        max_blocks_per_section=args.max_blocks_per_section,
        section_id=args.section_id,
        dry_run=args.dry_run,
        workers=args.workers,
        one_per_provider=args.one_per_provider,
    )


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
Summarize PDFs or ArXiv papers into structured markdown with math explanations.

Behavior:
- PDF mode:   extracts text from local PDFs, generates LLM summaries.
- ArXiv mode: fetches LaTeX source, extracts sections + math, explains math.
- All results can be pushed to Supabase (--push-supabase).
- Caches extracted text in .paper2md/ to skip re-extraction of unchanged PDFs.

Usage:
  python summarize_papers.py                                 # PDF dir mode
  python summarize_papers.py --arxiv-id 2301.07984           # single ArXiv paper
  python summarize_papers.py --arxiv-list ids.txt            # batch ArXiv IDs
  python summarize_papers.py --process-pending               # pick up from Supabase queue
  python summarize_papers.py --arxiv-id 2301.07984 --push-supabase

Required env vars (at least one LLM provider):
  GEMINI_API_KEY        preferred (1500 req/day free)
  GROQ_API_KEY          fallback  (1000 req/day free)
  OPENROUTER_API_KEY    fallback  (50 req/day free)
  OPENAI_API_KEY        legacy / paid

Optional env vars:
  PAPER2MD_LLM_PROVIDER   primary provider: gemini|groq|openrouter|openai
  SUPABASE_URL            required for --push-supabase
  SUPABASE_SERVICE_ROLE_KEY  required for --push-supabase
  PAPER2MD_MAX_MATH_BLOCKS   cap math blocks per paper (default: 50)
  PAPER2MD_DEBUG_TRACE    set to 1 for full tracebacks
"""

from __future__ import annotations

import argparse
import dataclasses
import os
import re
import traceback
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from tqdm import tqdm

from lib.models import Paper
from lib.pdf_extract import extract_paper_from_pdf
from lib.content_analysis import extract_structured_content
from lib.cache import PaperCache, compute_pdf_hash

# Load environment variables from root .env if it exists
load_dotenv(Path(__file__).parent / ".env")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _truthy_env(name: str) -> bool:
    v = os.environ.get(name, "").strip().lower()
    return v not in {"", "0", "false", "no", "off"}


def _format_exc(e: Exception) -> str:
    msg = str(e).strip()
    if msg:
        return f"{type(e).__name__}: {msg}"
    return type(e).__name__


def _report_error(stage: str, label: str, e: Exception) -> None:
    tqdm.write(f"[ERROR] {stage} failed for {label}: {_format_exc(e)}")
    if _truthy_env("PAPER2MD_DEBUG_TRACE"):
        tqdm.write(traceback.format_exc())


def _get_summarizer():
    """Lazy-load DSPy summarizer (configures provider on first call)."""
    from lib.dspy_config import configure_dspy
    from lib.dspy_modules import PaperSummarizer
    configure_dspy()
    return PaperSummarizer()


def _get_explainer():
    """Lazy-load DSPy math explainer."""
    from lib.dspy_modules import MathExplainer
    return MathExplainer()


def _get_algorithm_explainer():
    """Lazy-load DSPy algorithm explainer."""
    from lib.dspy_modules import AlgorithmExplainer
    return AlgorithmExplainer()


# ---------------------------------------------------------------------------
# PDF pipeline (existing behaviour, unchanged)
# ---------------------------------------------------------------------------

def load_papers(
    papers_dir: Path,
    max_pages: int | None = None,
    cache: PaperCache | None = None,
) -> list[Paper]:
    """Extract title + text from all PDFs in directory."""
    pdfs = sorted(papers_dir.glob("*.pdf"))
    papers: list[Paper] = []
    failures = cached_count = new_extractions = 0

    for pdf in tqdm(pdfs, desc="Extracting PDFs"):
        if cache:
            cached = cache.get_cached(pdf)
            if cached:
                papers.append(cached)
                cached_count += 1
                continue
        try:
            paper = extract_paper_from_pdf(pdf, max_pages=max_pages)
            if cache:
                pdf_hash = compute_pdf_hash(pdf)
                cache.store(paper, pdf_hash)
                new_extractions += 1
        except Exception as e:
            failures += 1
            _report_error("extract", pdf.name, e)
            continue

        if len(paper.text) < 500:
            tqdm.write(
                f"[WARN] Very little text in {pdf.name} "
                f"(chars={len(paper.text)}). May be scanned."
            )
        papers.append(paper)

    if cache and new_extractions:
        cache.save()
        tqdm.write(f"[INFO] Cached text for {new_extractions} newly extracted papers")
    if cached_count:
        tqdm.write(f"[INFO] Using cached text for {cached_count} unchanged papers")
    if failures:
        tqdm.write(f"[WARN] Extraction failures: {failures}/{len(pdfs)} PDFs")

    return papers


def generate_summaries(papers: list[Paper]) -> list[Paper]:
    """Generate LLM summaries for all papers (DSPy PaperSummarizer)."""
    summarizer = _get_summarizer()
    summarized: list[Paper] = []
    failures = 0

    for paper in tqdm(papers, desc="Summarising"):
        if not paper.text:
            summarized.append(paper)
            continue
        try:
            result = summarizer(paper)
            summarized.append(result)
        except Exception as e:
            failures += 1
            _report_error("summarise", paper.pdf_path.name if paper.pdf_path else paper.title, e)
            summarized.append(paper)

    if failures:
        tqdm.write(f"[WARN] Summarisation failures: {failures}/{len(papers)}")
    return summarized


def build_markdown(papers: list[Paper]) -> str:
    """Build final markdown document from papers (existing format, unchanged)."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines: list[str] = []

    lines += ["# Papers Summary", "", f"_Generated: {now}_", ""]
    lines += ["## Index", ""]
    for p in papers:
        anchor = re.sub(r"[^a-z0-9]+", "-", p.title.lower()).strip("-")
        lines.append(f"- [{p.title}](#{anchor})")
    lines += ["", "---", ""]

    for p in papers:
        lines.append(f"## {p.title}")
        lines.append("")
        if p.pdf_path:
            lines.append(f"- **Source PDF**: `{p.pdf_path.as_posix()}`")
        if p.arxiv_id:
            lines.append(f"- **ArXiv**: https://arxiv.org/abs/{p.arxiv_id}")

        content = extract_structured_content(p.text)
        if content.doi:
            lines.append(f"- **DOI**: `https://doi.org/{content.doi}`")
        lines.append("")

        if p.summary_md:
            lines.append(p.summary_md.strip())
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------
# ArXiv pipeline
# ---------------------------------------------------------------------------

def process_arxiv_id(
    arxiv_id: str,
    no_math_explain: bool = False,
    max_math_blocks: int | None = None,
    max_blocks_per_section: int | None = None,
    no_algo_explain: bool = False,
    push_supabase: bool = False,
    force: bool = False,
) -> Paper | None:
    """
    Full pipeline for a single ArXiv paper.

    Returns the processed Paper, or None on fatal error.
    """
    from lib.arxiv_source import fetch_arxiv_latex_full
    from lib.latex_parse import parse_latex_sections

    label = f"arXiv:{arxiv_id}"

    # Check Supabase cache
    if push_supabase:
        from lib.supabase_push import get_paper_status, mark_processing, mark_error
        status = get_paper_status(arxiv_id)
        if status == "complete" and not force:
            tqdm.write(f"[INFO] {label} already complete in Supabase — skipping (use --force to re-process)")
            return None
        mark_processing(arxiv_id)

    # Fetch LaTeX source
    tqdm.write(f"[INFO] Fetching LaTeX source for {label}")
    try:
        latex_result = fetch_arxiv_latex_full(arxiv_id)
    except Exception as e:
        _report_error("fetch", label, e)
        if push_supabase:
            mark_error(arxiv_id, _format_exc(e))
        return None

    latex = latex_result[0] if latex_result else None
    full_latex_source = latex_result[1] if latex_result else None

    # Extract citations from bibliography (cheap — pure regex, no LLM)
    citations = ()
    if full_latex_source:
        try:
            from lib.citation_extract import extract_citations
            citations = extract_citations(full_latex_source)
            arxiv_count = sum(1 for c in citations if c.arxiv_id)
            tqdm.write(f"[INFO] {label}: {len(citations)} citations ({arxiv_count} with ArXiv IDs)")
        except Exception as e:
            _report_error("citation_extract", label, e)

    source_type = "arxiv_latex"
    sections = ()

    if latex:
        # Parse sections and math blocks from LaTeX
        try:
            sections = parse_latex_sections(latex)
            tqdm.write(
                f"[INFO] {label}: {len(sections)} sections, "
                f"{sum(len(s.math_blocks) for s in sections)} math blocks"
            )
        except Exception as e:
            _report_error("latex_parse", label, e)
            sections = ()
    else:
        # Fall back to direct PDF download (no API call — avoids rate limits)
        tqdm.write(f"[WARN] {label}: no LaTeX source — falling back to PDF")
        try:
            import tempfile
            import time
            import httpx
            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"
            tqdm.write(f"[INFO] {label}: downloading PDF from {pdf_url}")
            time.sleep(3)  # polite delay
            resp = httpx.get(pdf_url, follow_redirects=True, timeout=120)
            resp.raise_for_status()
            with tempfile.TemporaryDirectory() as tmp:
                pdf_path = Path(tmp) / f"{arxiv_id}.pdf"
                pdf_path.write_bytes(resp.content)
                paper_pdf = extract_paper_from_pdf(pdf_path)
                paper = paper_pdf
                source_type = "pdf"
        except Exception as e:
            _report_error("pdf_fallback", label, e)
            if push_supabase:
                mark_error(arxiv_id, _format_exc(e))
            return None

    # Build Paper object from LaTeX path
    if latex:
        # For arXiv papers prefer the API title (authoritative, avoids template placeholders).
        # Fall back to LaTeX \title{} extraction if the API call fails.
        title = _arxiv_api_title(arxiv_id) or _title_from_latex(latex, arxiv_id, full_source=full_latex_source)
        full_text = "\n\n".join(s.plain_text for s in sections)
        paper = Paper(
            title=title,
            text=full_text,
            arxiv_id=arxiv_id,
            source_type=source_type,
            sections=sections,
            citations=citations,
        )
    else:
        # PDF fallback — split plain text into sections heuristically
        pdf_sections = _split_pdf_into_sections(paper.text)
        tqdm.write(f"[INFO] {label}: {len(pdf_sections)} section(s) split from PDF text")
        paper = Paper(
            title=paper.title,
            text=paper.text,
            pdf_path=paper.pdf_path,
            arxiv_id=arxiv_id,
            source_type=source_type,
            sections=pdf_sections,
        )

    # Summarise
    try:
        summarizer = _get_summarizer()
        paper = summarizer(paper)
    except Exception as e:
        _report_error("summarise", label, e)

    # Explain math
    if not no_math_explain and paper.sections:
        try:
            explainer = _get_explainer()
            cap = max_math_blocks or int(os.environ.get("PAPER2MD_MAX_MATH_BLOCKS", 50))
            paper = explainer(paper, max_blocks=cap, max_blocks_per_section=max_blocks_per_section)
        except Exception as e:
            _report_error("math_explain", label, e)

    # Explain algorithm blocks
    if not no_algo_explain and paper.sections:
        algo_count = sum(len(s.algorithm_blocks) for s in paper.sections)
        if algo_count > 0:
            tqdm.write(f"[INFO] {label}: {algo_count} algorithm block(s) found — explaining")
            try:
                algo_explainer = _get_algorithm_explainer()
                paper = algo_explainer(paper)
            except Exception as e:
                _report_error("algo_explain", label, e)

    # Push to Supabase
    if push_supabase:
        try:
            from lib.supabase_push import push_paper
            push_paper(paper)
            tqdm.write(f"[INFO] {label}: pushed to Supabase")
        except Exception as e:
            _report_error("supabase_push", label, e)
            from lib.supabase_push import save_failed_push, mark_error
            save_failed_push(paper, _format_exc(e))
            mark_error(arxiv_id, _format_exc(e))

    return paper


def _split_pdf_into_sections(text: str) -> "tuple[Section, ...]":
    """Heuristically split plain PDF text into Section objects.

    Strategy:
    1. Skip the table-of-contents zone at the document start (lines that look
       like "Title ......... N" or "Title  N").
    2. Split only on top-level headings — single-number or keyword-prefixed:
         "1 Introduction", "12. Nash Equilibrium", "Chapter 3 Games"
       Subsection headings like "1.2 Background" are intentionally excluded so
       each section captures a full chapter's worth of content.
    3. Merge any section body shorter than MIN_BODY chars into the previous one.

    Falls back to a single "Content" section if no chapter headings are found.
    """
    from lib.models import Section

    # Matches top-level chapter headings only (NOT subsections like "1.2 Title")
    _CHAPTER_RE = re.compile(
        r"^(?:"
        # Single integer heading: "1 Title" or "12. Title"
        # The negative lookahead (?!\.\d) ensures we don't match "1.2 Title"
        r"(?:\d+(?!\.\d)\.?\s+[A-Z][^\n]{2,80})"
        r"|"
        # Keyword prefix: "Chapter 3 Games", "Part II", "Appendix A"
        r"(?:(?:Chapter|Part|Appendix)\s+[\dA-Z]+(?:\s+[A-Z][^\n]{0,70})?)"
        r")$",
        re.MULTILINE,
    )

    # TOC line: text followed by dots/spaces and a page number, e.g.
    # "1.2 Background .............. 42"  or  "Nash Equilibrium  12"
    _TOC_LINE_RE = re.compile(r"[.\s]{4,}\d+\s*$")

    MIN_BODY = 300  # chars — skip near-empty sections (TOC artefacts)

    # ── 1. Detect and skip the TOC zone ──────────────────────────────────────
    lines = text.splitlines()
    toc_end_line = 0
    consecutive_toc = 0
    for i, line in enumerate(lines):
        if _TOC_LINE_RE.search(line.strip()):
            consecutive_toc += 1
            if consecutive_toc >= 3:
                toc_end_line = i + 1  # keep extending as long as TOC runs
        else:
            if consecutive_toc >= 3:
                break  # first non-TOC line after a real TOC block
            consecutive_toc = 0

    # Reconstruct text starting after the TOC zone
    body_text = "\n".join(lines[toc_end_line:])

    # ── 2. Find chapter headings ──────────────────────────────────────────────
    heading_positions: list[tuple[int, str]] = []
    char_offset = 0
    for line in body_text.splitlines():
        stripped = line.strip()
        if stripped and _CHAPTER_RE.match(stripped):
            heading_positions.append((char_offset, stripped))
        char_offset += len(line) + 1

    if len(heading_positions) < 2:
        return (Section(order_idx=0, title="Content", plain_text=body_text.strip()),)

    # ── 3. Build sections from heading boundaries ─────────────────────────────
    sections: list[Section] = []
    for i, (pos, title) in enumerate(heading_positions):
        next_pos = (
            heading_positions[i + 1][0] if i + 1 < len(heading_positions) else len(body_text)
        )
        content = body_text[pos:next_pos].strip()
        # Strip the heading line itself from the body
        nl = content.find("\n")
        content = content[nl:].strip() if nl != -1 else ""

        if len(content) < MIN_BODY:
            # Merge short sections (likely TOC echoes) into the previous one
            if sections:
                prev = sections[-1]
                sections[-1] = dataclasses.replace(
                    prev, plain_text=prev.plain_text + "\n\n" + content
                )
            continue
        sections.append(Section(order_idx=len(sections), title=title, plain_text=content))

    if not sections:
        return (Section(order_idx=0, title="Content", plain_text=body_text.strip()),)

    return tuple(sections)


def _arxiv_api_title(arxiv_id: str) -> str | None:
    """Fetch the canonical title from the ArXiv Atom API. Returns None on failure."""
    try:
        import urllib.request
        import xml.etree.ElementTree as ET
        url = f"https://export.arxiv.org/api/query?id_list={arxiv_id}"
        with urllib.request.urlopen(url, timeout=10) as r:
            root = ET.fromstring(r.read().decode())
        ns = {"a": "http://www.w3.org/2005/Atom"}
        entry = root.find("a:entry", ns)
        if entry is not None:
            t = entry.find("a:title", ns)
            if t is not None and t.text:
                return re.sub(r"\s+", " ", t.text.strip()).strip()
    except Exception:
        pass
    return None


def _title_from_latex(latex: str, fallback: str, full_source: str | None = None) -> str:
    """Extract paper title from LaTeX source.

    Tries common title commands (\\title, \\icmltitle, \\Title) in order.
    Handles one level of nested braces (e.g. \\title{\\textbf{...}}).
    Falls back to ArXiv API if arxiv_id is available, then to `fallback`.
    """
    # Title commands to try, in priority order
    _TITLE_CMDS = (r"\\title", r"\\icmltitle", r"\\Title")
    # Pattern for content with one level of nested braces
    _brace_content = r"((?:[^{}]|\{[^{}]*\})+)"

    for src in filter(None, [full_source, latex]):
        for cmd in _TITLE_CMDS:
            m = re.search(cmd + r"\s*\{" + _brace_content + r"\}", src)
            if m:
                raw = m.group(1)
                # Strip LaTeX commands and line-break markers, keep text args
                title = re.sub(r"\\\\", " ", raw)           # \\ line breaks → space
                title = re.sub(r"\\[a-zA-Z]+\s*", "", title)
                title = re.sub(r"[{}]", "", title)
                title = re.sub(r"\s+", " ", title).strip()
                if title and len(title) > 3:
                    return title

    return fallback


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Summarize papers + explain math. Supports PDF dirs and ArXiv IDs."
    )

    # ── Input sources ──────────────────────────────────────────────────────
    src = ap.add_argument_group("Input sources (mutually exclusive with --arxiv-*)")
    src.add_argument("--papers-dir", default="papers",
                     help="Directory containing PDFs (default: papers)")
    src.add_argument("--arxiv-id", metavar="ID",
                     help="Single ArXiv paper ID, e.g. 2301.07984")
    src.add_argument("--arxiv-list", metavar="FILE",
                     help="File of ArXiv IDs, one per line")
    src.add_argument("--process-pending", action="store_true",
                     help="Fetch and process all status=pending papers from Supabase")

    # ── Output ─────────────────────────────────────────────────────────────
    ap.add_argument("--out", default="output/PAPERS_SUMMARY.md",
                    help="Output markdown path (default: output/PAPERS_SUMMARY.md)")

    # ── PDF options ────────────────────────────────────────────────────────
    ap.add_argument("--max-pages", type=int, default=0,
                    help="Limit pages per PDF (0 = all)")
    ap.add_argument("--no-cache", action="store_true",
                    help="Disable text extraction cache")
    ap.add_argument("--clear-cache", action="store_true",
                    help="Clear cache before running")

    # ── ArXiv / math options ───────────────────────────────────────────────
    ap.add_argument("--no-math-explain", action="store_true",
                    help="Skip math explanation step (faster)")
    ap.add_argument("--max-math-blocks", type=int, default=None,
                    help="Global cap on math blocks explained per paper (default: PAPER2MD_MAX_MATH_BLOCKS env or 50)")
    ap.add_argument("--max-blocks-per-section", type=int, default=None,
                    help="Max math blocks explained per section; ensures coverage across all sections in large papers")
    ap.add_argument("--no-algo-explain", action="store_true",
                    help="Skip algorithm explanation step")

    # ── Supabase ───────────────────────────────────────────────────────────
    ap.add_argument("--push-supabase", action="store_true",
                    help="Push results to Supabase after processing")
    ap.add_argument("--force", action="store_true",
                    help="Re-process even if paper is already complete in Supabase")

    args = ap.parse_args()

    # ── ArXiv modes ────────────────────────────────────────────────────────
    arxiv_ids: list[str] = []

    if args.arxiv_id:
        arxiv_ids = [args.arxiv_id.strip()]

    elif args.arxiv_list:
        list_path = Path(args.arxiv_list)
        if not list_path.exists():
            raise SystemExit(f"arxiv list file not found: {list_path}")
        arxiv_ids = [
            line.strip()
            for line in list_path.read_text().splitlines()
            if line.strip() and not line.startswith("#")
        ]

    elif args.process_pending:
        from lib.supabase_push import fetch_pending_arxiv_ids
        arxiv_ids = fetch_pending_arxiv_ids()
        if not arxiv_ids:
            print("[INFO] No pending papers in Supabase queue.")
            return 0
        print(f"[INFO] {len(arxiv_ids)} pending paper(s) to process")

    if arxiv_ids:
        processed = 0
        for arxiv_id in tqdm(arxiv_ids, desc="ArXiv papers"):
            paper = process_arxiv_id(
                arxiv_id=arxiv_id,
                no_math_explain=args.no_math_explain,
                max_math_blocks=args.max_math_blocks,
                max_blocks_per_section=args.max_blocks_per_section,
                no_algo_explain=args.no_algo_explain,
                push_supabase=args.push_supabase,
                force=args.force,
            )
            if paper:
                processed += 1
        print(f"[INFO] Processed {processed}/{len(arxiv_ids)} ArXiv papers")
        return 0

    # ── PDF mode (original behaviour) ─────────────────────────────────────
    papers_dir = Path(args.papers_dir)
    out_path = Path(args.out)
    max_pages = None if args.max_pages == 0 else args.max_pages

    if not papers_dir.exists():
        raise SystemExit(f"papers dir not found: {papers_dir}")

    cache = None if args.no_cache else PaperCache()
    if cache and args.clear_cache:
        cache.clear()
        cache.save()
        print("[INFO] Cache cleared")

    papers = load_papers(papers_dir, max_pages=max_pages, cache=cache)
    papers = generate_summaries(papers)

    if args.push_supabase:
        from lib.supabase_push import push_paper
        for paper in tqdm(papers, desc="Pushing to Supabase"):
            try:
                push_paper(paper)
            except Exception as e:
                _report_error("supabase_push", paper.title, e)

    md = build_markdown(papers)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")
    print(f"Wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

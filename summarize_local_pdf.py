#!/usr/bin/env python3
"""
Process a local PDF file: extract text, generate a structured summary, and
optionally explain math blocks. Writes output to .md files — no Supabase needed.

Usage:
  python summarize_local_pdf.py --pdf paper.pdf
  python summarize_local_pdf.py --pdf paper.pdf --out results/ --no-math
  python summarize_local_pdf.py --pdf paper.pdf --paper-type textbook --max-blocks 30
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")


# ---------------------------------------------------------------------------
# Inline math extraction from plain text
# ---------------------------------------------------------------------------

_DISPLAY_MATH_RE = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)
_INLINE_MATH_RE  = re.compile(r"\$([^$\n]{2,80}?)\$")


def _extract_math_blocks_from_text(
    text: str,
    paper_type: str = "research_paper",
) -> "list[MathBlock]":
    """Best-effort: find $...$ and $$...$$ patterns in plain PDF text."""
    from lib.models import MathBlock

    blocks: list[MathBlock] = []
    seen: set[str] = set()

    # Display math first ($$...$$)
    for m in _DISPLAY_MATH_RE.finditer(text):
        expr = m.group(1).strip()
        if not expr or expr in seen:
            continue
        seen.add(expr)
        start, end = m.start(), m.end()
        blocks.append(
            MathBlock(
                order_idx=len(blocks),
                env_type="display",
                latex_expr=expr,
                context_before=text[max(0, start - 300): start].strip(),
                context_after=text[end: end + 300].strip(),
                paper_type=paper_type,
            )
        )

    # Inline math ($...$) — skip positions already captured by display
    display_spans = {m.span() for m in _DISPLAY_MATH_RE.finditer(text)}
    for m in _INLINE_MATH_RE.finditer(text):
        # skip if inside a display span
        if any(ds <= m.start() and m.end() <= de for ds, de in display_spans):
            continue
        expr = m.group(1).strip()
        if not expr or expr in seen or len(expr) < 3:
            continue
        seen.add(expr)
        start, end = m.start(), m.end()
        blocks.append(
            MathBlock(
                order_idx=len(blocks),
                env_type="inline",
                latex_expr=expr,
                context_before=text[max(0, start - 200): start].strip(),
                context_after=text[end: end + 200].strip(),
                paper_type=paper_type,
            )
        )

    return blocks


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

def _render_summary_md(paper: "Paper") -> str:
    """Render summary_md JSON (as stored in Paper) to a readable markdown string."""
    if not paper.summary_md:
        return "_No summary generated._\n"

    raw = paper.summary_md
    # summary_md may already be a string or a dict
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return raw  # already plain text / markdown
    else:
        data = raw  # type: ignore[assignment]

    parts = [f"# {paper.title}\n"]
    for key, label in [
        ("tldr",        "TL;DR"),
        ("problem",     "Problem"),
        ("approach",    "Approach"),
        ("results",     "Results"),
        ("takeaways",   "Practical Takeaways"),
        ("limitations", "Limitations / Open Questions"),
    ]:
        val = data.get(key, "")
        if val:
            parts.append(f"### {label}\n{val}")

    return "\n\n".join(parts) + "\n"


def _render_math_md(paper: "Paper", blocks: "list[MathBlock]") -> str:
    """Render explained math blocks to a readable markdown string."""
    lines = [f"# Math Explanations — {paper.title}\n"]
    explained = [b for b in blocks if b.explanation]

    if not explained:
        lines.append("_No math explanations generated._\n")
        return "\n".join(lines)

    for b in explained:
        lines.append(f"---\n\n## Block {b.order_idx + 1} (`{b.env_type}`)\n")
        lines.append(f"**Expression:** `{b.latex_expr}`\n")
        if b.context_before:
            lines.append(f"**Context before:** {b.context_before[-200:]}\n")

        try:
            data = json.loads(b.explanation)
        except (json.JSONDecodeError, TypeError):
            lines.append(f"{b.explanation}\n")
            continue

        for key, label in [
            ("what_it_computes",        "What it computes"),
            ("symbol_meanings",         "Symbols"),
            ("derivation",              "Derivation"),
            ("intuition",               "Intuition"),
            ("proof_role",              "Role in proof"),
            ("prerequisites",           "Prerequisites"),
            ("mathematical_significance","Why it matters"),
        ]:
            val = data.get(key, "")
            if val:
                lines.append(f"**{label}:** {val}\n")

        if b.explanation_model:
            lines.append(f"_Model: {b.explanation_model}_\n")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _safe_dirname(title: str) -> str:
    """Turn a paper title into a filesystem-safe directory name."""
    name = re.sub(r'[^\w\s-]', '', title).strip()
    name = re.sub(r'[\s]+', '_', name)
    return name[:80] or "paper"


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  Wrote {path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

_SUPPORTED_EXTS = {".pdf", ".epub"}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summarise a local PDF or EPUB and save .md files (no Supabase)."
    )
    # --input is the canonical flag; --pdf is kept as a backward-compat alias
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--input", metavar="FILE", help="Path to a .pdf or .epub file")
    input_group.add_argument("--pdf", metavar="FILE", help="Alias for --input (PDF only)")
    parser.add_argument(
        "--out", default="output",
        help="Output directory (default: output/). A subdirectory per paper is created."
    )
    parser.add_argument(
        "--no-math", action="store_true",
        help="Skip math extraction and explanation (faster, fewer LLM calls)"
    )
    parser.add_argument(
        "--paper-type", default="research_paper",
        choices=["research_paper", "textbook", "lecture_notes"],
        help="Type of document — shapes the math explanation style"
    )
    parser.add_argument(
        "--max-blocks", type=int, default=20,
        help="Max math blocks to explain (default: 20)"
    )
    parser.add_argument(
        "--max-pages", type=int, default=None,
        help="Max PDF pages to extract (default: all, capped at 300). Ignored for epub."
    )
    args = parser.parse_args()

    raw_path = args.input or args.pdf
    input_path = Path(raw_path).expanduser().resolve()
    if not input_path.exists():
        print(f"[ERROR] File not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    ext = input_path.suffix.lower()
    if ext not in _SUPPORTED_EXTS:
        print(
            f"[ERROR] Unsupported file type '{ext}'. Supported: {', '.join(sorted(_SUPPORTED_EXTS))}",
            file=sys.stderr,
        )
        sys.exit(1)

    # ── 1. Configure DSPy ──────────────────────────────────────────────────
    print("[1/4] Configuring LLM provider…")
    from lib.dspy_config import configure_dspy
    provider = configure_dspy()
    print(f"      Using provider: {provider}")

    # ── 2. Extract text ────────────────────────────────────────────────────
    print(f"[2/4] Extracting text from {input_path.name}…")
    if ext == ".epub":
        from lib.epub_extract import extract_paper_from_epub
        paper = extract_paper_from_epub(input_path)
    else:
        from lib.pdf_extract import extract_paper_from_pdf
        max_pages = args.max_pages or 300
        paper = extract_paper_from_pdf(str(input_path), max_pages=max_pages)
    print(f"      Title : {paper.title}")
    print(f"      Text  : {len(paper.text or '')} chars")

    if not paper.text:
        hint = "is it a scanned image?" if ext == ".pdf" else "does it contain readable HTML chapters?"
        print(f"[ERROR] No text extracted — {hint}", file=sys.stderr)
        sys.exit(1)

    # ── 3. Summarise ───────────────────────────────────────────────────────
    print("[3/4] Generating paper summary…")
    from lib.dspy_modules import PaperSummarizer
    summarizer = PaperSummarizer()
    paper = summarizer.forward(paper)

    # ── 4. Math explanation ────────────────────────────────────────────────
    math_blocks: list = []
    if not args.no_math:
        print("[4/4] Extracting and explaining math blocks…")
        math_blocks = _extract_math_blocks_from_text(paper.text, paper_type=args.paper_type)
        print(f"      Found {len(math_blocks)} candidate blocks (cap: {args.max_blocks})")

        if math_blocks:
            from lib.dspy_modules import MathExplainer
            from lib.models import MathBlock
            explainer = MathExplainer()
            capped = math_blocks[: args.max_blocks]
            explained: list[MathBlock] = []
            for block in capped:
                result = explainer.explain_block(block, paper.title, "")
                explained.append(result)
            math_blocks = explained
            n_explained = sum(1 for b in math_blocks if b.explanation)
            print(f"      Explained {n_explained}/{len(math_blocks)} blocks")
        else:
            print("      No $...$ math patterns found in extracted text.")
    else:
        print("[4/4] Math explanation skipped (--no-math).")

    # ── 5. Write output ────────────────────────────────────────────────────
    out_root = Path(args.out) / _safe_dirname(paper.title)
    print(f"\nWriting output to {out_root}/")

    _write(out_root / "summary.md", _render_summary_md(paper))

    if not args.no_math:
        _write(out_root / "math.md", _render_math_md(paper, math_blocks))

    print("\nDone.")


if __name__ == "__main__":
    main()

"""
Vision-based math extraction for PDF-sourced papers.

For each section, renders its PDF pages as images and sends them to a
free vision LLM via OpenRouter to extract mathematical expressions as LaTeX.
Returns sections with math_blocks populated.

Requires: pymupdf (pip install pymupdf)
Env var:  OPENROUTER_API_KEY
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
import dataclasses
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from lib.models import MathBlock, Section

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

VISION_MODEL = "google/gemma-4-31b-it:free"
FALLBACK_MODEL = "nvidia/nemotron-nano-12b-v2-vl:free"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Render scale — 2× zoom gives ~150 DPI for a letter page (good for math)
RENDER_SCALE = 2.0

# Rate-limit guard: free tier ~10 req/min → sleep between section calls
SLEEP_BETWEEN_SECTIONS = 7  # seconds

# Max pages rendered per section (keeps API payload manageable)
MAX_PAGES_PER_SECTION = 5

_PROMPT = """\
Look at this PDF page image and extract every mathematical expression you can see.

For each expression return:
- latex: the LaTeX code (use standard LaTeX commands like \\frac, \\sum, \\sigma, etc.)
- env_type: "display" if it is a standalone equation on its own line, "inline" if inside a sentence
- context_before: up to 60 characters of plain text immediately before the expression
- context_after: up to 60 characters of plain text immediately after the expression

Return ONLY a valid JSON array. Example:
[
  {"latex": "u_i(s_i, s_{-i})", "env_type": "inline",
   "context_before": "The utility function", "context_after": "is maximized when"},
  {"latex": "\\\\max_{s \\\\in S} \\\\sum_{j} p_j \\\\cdot u(s, j)",
   "env_type": "display", "context_before": "Player i solves", "context_after": "subject to"}
]

If no math is present return [].
Do NOT include markdown fences or any text outside the JSON array.\
"""


# ---------------------------------------------------------------------------
# OpenRouter call
# ---------------------------------------------------------------------------

def _call_vision(image_b64_list: list[str], model: str = VISION_MODEL) -> str:
    """Send page images to OpenRouter vision model. Returns raw text response."""
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY not set")

    content: list[dict] = []
    for b64 in image_b64_list:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{b64}"},
        })
    content.append({"type": "text", "text": _PROMPT})

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0.0,
        "max_tokens": 2048,
    }

    resp = httpx.post(
        OPENROUTER_URL,
        json=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://paper2md.vercel.app",
            "X-Title": "paper2md",
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def _parse_math_response(raw: str) -> list[dict]:
    """Extract JSON array from LLM response, tolerating markdown fences."""
    raw = raw.strip()
    # Strip ```json ... ``` fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract the first [...] block
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    return []


# ---------------------------------------------------------------------------
# PDF page rendering
# ---------------------------------------------------------------------------

def _render_pages_as_b64(pdf_path: Path, page_nums: list[int]) -> list[str]:
    """Render given 1-based page numbers to base64-encoded PNG strings."""
    import fitz  # pymupdf

    doc = fitz.open(str(pdf_path))
    mat = fitz.Matrix(RENDER_SCALE, RENDER_SCALE)
    result: list[str] = []
    for pn in page_nums:
        idx = pn - 1  # 0-based
        if idx < 0 or idx >= doc.page_count:
            continue
        page = doc[idx]
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
        png_bytes = pix.tobytes("png")
        result.append(base64.b64encode(png_bytes).decode())
    doc.close()
    return result


# ---------------------------------------------------------------------------
# Section → page mapping
# ---------------------------------------------------------------------------

def _find_section_start_pages(pdf_path: Path, sections: "tuple[Section, ...]") -> dict[int, int]:
    """Return {order_idx: first_1based_page} by matching section start text."""
    import fitz

    doc = fitz.open(str(pdf_path))
    total = doc.page_count

    # Build per-page text index (normalised for fuzzy match)
    page_texts: list[str] = []
    for i in range(total):
        t = doc[i].get_text("text")
        page_texts.append(re.sub(r"\s+", " ", t).lower())
    doc.close()

    result: dict[int, int] = {}
    for sec in sections:
        # Use first 80 non-whitespace chars of plain_text as probe
        probe_raw = re.sub(r"\s+", " ", sec.plain_text[:200]).strip().lower()
        probe = probe_raw[:60]
        if len(probe) < 10:
            # Fallback: use section title subtitle
            title_sub = re.sub(r"^chapter\s+\d+[:\s]+", "", sec.title or "", flags=re.IGNORECASE)
            probe = re.sub(r"\s+", " ", title_sub).strip().lower()

        found = None
        for i, pt in enumerate(page_texts):
            if probe[:40] in pt:
                found = i + 1  # 1-based
                break

        if found is None:
            # Ratio estimate
            found = max(1, round((sec.order_idx + 0.5) / max(len(sections), 1) * total))

        result[sec.order_idx] = found

    return result


# ---------------------------------------------------------------------------
# Main public API
# ---------------------------------------------------------------------------

def extract_vision_math_for_sections(
    pdf_path: Path,
    sections: "tuple[Section, ...]",
    max_pages_per_section: int = MAX_PAGES_PER_SECTION,
    verbose: bool = True,
) -> "tuple[Section, ...]":
    """
    For each section, render its PDF pages and ask a vision LLM to extract math.
    Returns a new tuple of sections with math_blocks populated.

    Args:
        pdf_path:              Path to the downloaded PDF file.
        sections:              Tuple of Section objects (plain_text, no math_blocks).
        max_pages_per_section: How many pages to render per section.
        verbose:               Print progress to stdout.

    Returns:
        New tuple of Section objects with math_blocks filled in.
    """
    from lib.models import MathBlock

    if not sections:
        return sections

    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        if verbose:
            print("[vision_math] OPENROUTER_API_KEY not set — skipping")
        return sections

    if verbose:
        print(f"[vision_math] Finding section start pages in PDF…")
    start_pages = _find_section_start_pages(pdf_path, sections)

    import fitz
    doc = fitz.open(str(pdf_path))
    total_pages = doc.page_count
    doc.close()

    new_sections = list(sections)

    for i, sec in enumerate(sections):
        first = start_pages.get(sec.order_idx, 1)
        last = min(first + max_pages_per_section - 1, total_pages)
        page_nums = list(range(first, last + 1))

        if verbose:
            print(f"[vision_math] Section {i+1}/{len(sections)}: "
                  f"'{sec.title}' → pages {first}–{last}")

        try:
            images_b64 = _render_pages_as_b64(pdf_path, page_nums)
            if not images_b64:
                continue

            raw = _call_vision(images_b64)
            items = _parse_math_response(raw)

            blocks: list[MathBlock] = []
            seen: set[str] = set()
            for item in items:
                latex = str(item.get("latex", "")).strip()
                if not latex or latex in seen or len(latex) < 2:
                    continue
                seen.add(latex)
                env = item.get("env_type", "inline")
                if env not in ("inline", "display", "equation", "align"):
                    env = "inline"
                blocks.append(MathBlock(
                    order_idx=len(blocks),
                    env_type=env,
                    latex_expr=latex,
                    context_before=str(item.get("context_before", ""))[:300],
                    context_after=str(item.get("context_after", ""))[:300],
                    paper_type="textbook",
                ))

            if verbose:
                print(f"  → {len(blocks)} math block(s) extracted")

            new_sections[i] = dataclasses.replace(sec, math_blocks=tuple(blocks))

        except Exception as e:
            if verbose:
                print(f"  [WARN] vision extraction failed for section {i}: {e}")

        # Respect free-tier rate limit
        if i < len(sections) - 1:
            time.sleep(SLEEP_BETWEEN_SECTIONS)

    return tuple(new_sections)

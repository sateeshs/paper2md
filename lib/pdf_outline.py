"""PDF page mapping: read a paper's hyperref outline and align it to headings.

Knows only about PDFs and heading titles. No LaTeX parsing, no database.

Most arXiv papers built with ``hyperref`` ship a complete PDF outline — level,
section number, title and page for every heading.  That is an independent
derivation of the document structure, so aligning it against the LaTeX heading
tree both yields page numbers and cross-validates the parse.

Alignment uses ``difflib.SequenceMatcher`` over normalised titles, which
tolerates insertions and deletions on either side (starred headings, draft
content, front matter).  Headings that fail to align inherit a page by monotone
interpolation from their matched neighbours.

Every failure mode degrades to "no pages" rather than raising — page numbers are
an enhancement and must never block processing a paper.
"""

from __future__ import annotations

import difflib
import logging
import re
from dataclasses import dataclass
from typing import Sequence

log = logging.getLogger(__name__)

_PDF_URL = "https://arxiv.org/pdf/{arxiv_id}"
_TIMEOUT = 120.0

# Below this fraction of aligned headings the mapping is considered unreliable
# (wrong PDF, stale outline, heavily rewritten source) and is discarded whole.
MIN_MATCH_RATIO = 0.5


@dataclass(frozen=True)
class PageSpan:
    """Page range for one heading."""
    start: int
    end: int
    source: str      # 'pdf_outline' (aligned) | 'inferred' (interpolated)


@dataclass(frozen=True)
class OutlineEntry:
    """One entry of a PDF's hyperref outline."""
    level: int
    number: str      # "2.5.3"; "" when the bookmark carries no number
    title: str
    page: int        # 1-based


_NUMBER_PREFIX_RE = re.compile(r"^((?:\d+|[A-Z])(?:\.\d+)*)\s+(.*)$", re.DOTALL)


def _split_number(bookmark_title: str) -> tuple[str, str]:
    """Split "2.5.3 Maximization bias" into ("2.5.3", "Maximization bias")."""
    m = _NUMBER_PREFIX_RE.match(bookmark_title.strip())
    return (m.group(1), m.group(2).strip()) if m else ("", bookmark_title.strip())


def normalize_title(title: str) -> str:
    """Reduce a heading title to a comparison key.

    Inline math, control sequences and punctuation are dropped because they
    survive very differently in LaTeX source vs. a PDF bookmark:
    ``Sarsa($\\lambda$)`` becomes ``Sarsa()`` in the bookmark.
    """
    s = re.sub(r"\$[^$]*\$", " ", title)      # inline math
    s = re.sub(r"\\[a-zA-Z]+\s*", " ", s)     # control sequences
    s = re.sub(r"[^a-z0-9]+", " ", s.lower())  # punctuation, case
    return " ".join(s.split())


def parse_outline(pdf_bytes: bytes) -> tuple[OutlineEntry, ...]:
    """Extract the outline from PDF bytes. Returns () when absent or unreadable."""
    try:
        import pymupdf
    except ImportError:  # pragma: no cover - pymupdf is a declared dependency
        log.warning("pymupdf not installed — skipping PDF page mapping")
        return ()

    try:
        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
            toc = doc.get_toc()
    except Exception as exc:
        log.warning("could not read PDF outline: %s", exc)
        return ()

    entries: list[OutlineEntry] = []
    for level, raw_title, page in toc:
        number, title = _split_number(raw_title)
        entries.append(OutlineEntry(level=level, number=number, title=title, page=page))
    return tuple(entries)


def page_count(pdf_bytes: bytes) -> int | None:
    """Total pages in the PDF, or None if unreadable."""
    try:
        import pymupdf
        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
            return doc.page_count
    except Exception:
        return None


_REFERENCES_HEADINGS = frozenset({"references", "bibliography", "works cited"})


def find_references_page(pdf_bytes: bytes, after_page: int = 1) -> int | None:
    """First page whose heading is "References"/"Bibliography", or None.

    Many papers have no bookmark for the bibliography, so the outline alone
    cannot say where body content ends. Without this the final section absorbs
    the entire reference list — 54 pages of it for a 253-page book.
    """
    try:
        import pymupdf
    except ImportError:  # pragma: no cover - declared dependency
        return None

    try:
        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
            for pno in range(max(0, after_page - 1), doc.page_count):
                lines = [ln.strip() for ln in doc[pno].get_text().splitlines() if ln.strip()]
                if lines and lines[0].strip(" .0123456789").lower() in _REFERENCES_HEADINGS:
                    return pno + 1
    except Exception as exc:
        log.warning("could not scan for references page: %s", exc)
    return None


def fetch_pdf(arxiv_id: str) -> bytes | None:
    """Download a paper's PDF from arXiv. Returns None on any failure."""
    try:
        import httpx
        resp = httpx.get(
            _PDF_URL.format(arxiv_id=arxiv_id),
            follow_redirects=True,
            timeout=_TIMEOUT,
            headers={"User-Agent": "paper2md/1.0 (https://github.com/paper2md)"},
        )
        resp.raise_for_status()
        return resp.content
    except Exception as exc:
        log.warning("could not download PDF for %s: %s", arxiv_id, exc)
        return None


def map_pages(
    headings: Sequence["HeadingLike"],
    outline: Sequence[OutlineEntry],
    total_pages: int | None = None,
    references_page: int | None = None,
) -> dict[int, PageSpan]:
    """Align *headings* to *outline* and return heading index → PageSpan.

    Returns {} when the outline is empty or the alignment is too weak to trust.
    """
    if not headings or not outline:
        return {}

    heading_keys = [normalize_title(h.title) for h in headings]
    outline_keys = [normalize_title(e.title) for e in outline]

    matcher = difflib.SequenceMatcher(None, heading_keys, outline_keys, autojunk=False)
    matched: dict[int, int] = {}
    for h_start, o_start, size in matcher.get_matching_blocks():
        for k in range(size):
            matched[h_start + k] = o_start + k

    if len(matched) / len(headings) < MIN_MATCH_RATIO:
        log.warning(
            "PDF outline alignment too weak (%d/%d) — dropping page mapping",
            len(matched), len(headings),
        )
        return {}

    starts = _resolve_starts(headings, outline, matched)
    return _build_spans(starts, matched, outline, total_pages, references_page)


def _resolve_starts(
    headings: Sequence["HeadingLike"],
    outline: Sequence[OutlineEntry],
    matched: dict[int, int],
) -> list[int]:
    """Page for every heading — exact when aligned, interpolated otherwise.

    Interpolation carries the previous known page forward, which keeps the
    sequence monotone: an unaligned heading sits on (or after) the page of the
    last heading that was placed.
    """
    starts: list[int] = []
    carried = outline[matched[min(matched)]].page if matched else 1

    for i in range(len(headings)):
        if i in matched:
            carried = outline[matched[i]].page
        starts.append(carried)

    return starts


def _bibliography_page(
    outline: Sequence[OutlineEntry],
    total_pages: int | None,
    references_page: int | None = None,
) -> int | None:
    """Page where the references begin, used to cap the final heading's range.

    Preference order: an explicit page found by scanning the PDF text, then a
    bookmark in the outline, then the total page count.
    """
    if references_page:
        return references_page
    for entry in outline:
        if normalize_title(entry.title) in _REFERENCES_HEADINGS:
            return entry.page
    return total_pages


def _build_spans(
    starts: Sequence[int],
    matched: dict[int, int],
    outline: Sequence[OutlineEntry],
    total_pages: int | None,
    references_page: int | None = None,
) -> dict[int, PageSpan]:
    """Pair each start page with the next heading's start to form a range."""
    last_page = _bibliography_page(outline, total_pages, references_page)
    spans: dict[int, PageSpan] = {}

    for i, start in enumerate(starts):
        if i + 1 < len(starts):
            end = max(start, starts[i + 1])
        else:
            end = max(start, last_page) if last_page else start

        spans[i] = PageSpan(
            start=start,
            end=end,
            source="pdf_outline" if i in matched else "inferred",
        )

    return spans


def pages_for_arxiv(
    arxiv_id: str,
    headings: Sequence["HeadingLike"],
) -> dict[int, PageSpan]:
    """Convenience: download the PDF and map pages. {} on any failure."""
    pdf = fetch_pdf(arxiv_id)
    if pdf is None:
        return {}
    outline = parse_outline(pdf)
    if not outline:
        log.info("no PDF outline for %s — sections will have no page numbers", arxiv_id)
        return {}
    last_body_page = outline[-1].page if outline else 1
    return map_pages(
        headings,
        outline,
        total_pages=page_count(pdf),
        references_page=find_references_page(pdf, after_page=last_body_page),
    )


class HeadingLike:  # pragma: no cover - typing only
    title: str

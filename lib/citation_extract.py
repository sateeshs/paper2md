"""Extract bibliography entries from merged LaTeX source.

Handles two common formats:
  - \\bibitem style (natbib / manual bibliographies)
  - BibTeX @article/@inproceedings/@misc style (when .bib file is inlined)

For each entry, attempts to extract:
  - cite_key
  - arxiv_id  (from URLs, arXiv: labels, or eprint fields — version stripped)
  - title     (from BibTeX title= field or first sentence of \\bibitem)
  - url       (first https?:// URL in the entry)
"""

from __future__ import annotations

import re

from lib.models import Citation


# ---------------------------------------------------------------------------
# ArXiv ID extraction patterns (applied in priority order)
# ---------------------------------------------------------------------------

_ARXIV_PATTERNS: list[re.Pattern[str]] = [
    # arxiv.org/abs/XXXX.XXXXX or old-style arxiv.org/abs/cat/XXXXXXX
    re.compile(r"arxiv\.org/(?:abs|pdf)/([a-z\-]+/\d{7}|\d{4}\.\d{4,5})(?:v\d+)?", re.IGNORECASE),
    # arXiv:XXXX.XXXXX or arXiv: XXXX.XXXXX
    re.compile(r"arXiv[:\s]+(\d{4}\.\d{4,5})(?:v\d+)?", re.IGNORECASE),
    # eprint = {XXXX.XXXXX} (BibTeX)
    re.compile(r"eprint\s*=\s*[{\"](\d{4}\.\d{4,5})(?:v\d+)?[}\"]", re.IGNORECASE),
    # old-style category/NNNNNNN
    re.compile(r"arXiv[:\s]+([a-z\-]+/\d{7})(?:v\d+)?", re.IGNORECASE),
]

_VERSION_RE = re.compile(r"v\d+$")

# BibTeX title field
_BIBTEX_TITLE_RE = re.compile(
    r"title\s*=\s*[{\"](.+?)[}\"](?:\s*,|\s*\n)", re.IGNORECASE | re.DOTALL
)

# First URL in entry
_URL_RE = re.compile(r"https?://[^\s\}\]>,\"\\]+")

# BibTeX entry type line: @article{key, or @inproceedings{key,
_BIBTEX_ENTRY_RE = re.compile(
    r"@(article|inproceedings|proceedings|misc|book|techreport|phdthesis|mastersthesis|unpublished|online|software)\s*\{([^,\n]+)",
    re.IGNORECASE,
)

# \bibitem[optional]{key}
_BIBITEM_RE = re.compile(r"\\bibitem\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_arxiv_id(text: str) -> str | None:
    """Return canonical ArXiv ID (no version suffix) from entry text, or None."""
    for pat in _ARXIV_PATTERNS:
        m = pat.search(text)
        if m:
            return _VERSION_RE.sub("", m.group(1))
    return None


def _extract_title(text: str) -> str | None:
    """Best-effort title extraction from a bib entry."""
    # BibTeX title= field
    m = _BIBTEX_TITLE_RE.search(text)
    if m:
        raw = m.group(1)
        # Strip nested LaTeX braces used for case preservation: {Deep} → Deep
        raw = re.sub(r"\{([^{}]*)\}", r"\1", raw)
        raw = re.sub(r"\s+", " ", raw).strip()
        return raw[:200] if raw else None

    # For \bibitem style: take the first sentence after the key block
    # Strip the \bibitem{key} prefix and get the first meaningful sentence
    cleaned = _BIBITEM_RE.sub("", text).strip()
    # Remove newblock, textit, textbf wrappers
    cleaned = re.sub(r"\\(?:newblock|bibinfo\{[^}]*\}|textit|textbf|emph)\s*\{?", "", cleaned)
    cleaned = re.sub(r"[{}]", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    # Take up to the first period followed by a capital or end-of-reasonable-length
    first_sent = re.split(r"\.\s+[A-Z]|\.$", cleaned)[0].strip()
    if len(first_sent) >= 10:
        return first_sent[:200]
    return None


def _extract_url(text: str) -> str | None:
    """Return the first http(s) URL found in entry text."""
    m = _URL_RE.search(text)
    return m.group(0).rstrip(".,)") if m else None


# ---------------------------------------------------------------------------
# Bibliography section locators
# ---------------------------------------------------------------------------

def _find_bibitem_section(source: str) -> str | None:
    r"""Return the \begin{thebibliography}...\end{thebibliography} block, or None."""
    m = re.search(
        r"\\begin\{thebibliography\}.*?\\end\{thebibliography\}",
        source,
        re.DOTALL,
    )
    return m.group(0) if m else None


def _has_bibtex(source: str) -> bool:
    """Return True if source contains BibTeX @entry blocks."""
    return bool(_BIBTEX_ENTRY_RE.search(source))


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def _parse_bibitem(bib_section: str) -> list[Citation]:
    """Parse \\bibitem entries from a thebibliography block."""
    citations: list[Citation] = []

    # Split on \bibitem boundaries
    chunks = re.split(r"(?=\\bibitem)", bib_section)

    for chunk in chunks:
        m = _BIBITEM_RE.match(chunk.strip())
        if not m:
            continue
        cite_key = m.group(1).strip()
        raw = chunk.strip()[:1000]
        arxiv_id = _extract_arxiv_id(chunk)
        title = _extract_title(chunk)
        url = _extract_url(chunk)

        citations.append(Citation(
            order_idx=len(citations),
            cite_key=cite_key,
            raw_bib_entry=raw,
            arxiv_id=arxiv_id,
            title=title,
            url=url,
        ))

    return citations


def _parse_bibtex(source: str) -> list[Citation]:
    """Parse @article/@inproceedings/etc. BibTeX entries from source."""
    citations: list[Citation] = []

    # Split on @ boundaries (each entry starts with @type{)
    chunks = re.split(r"(?=@(?:article|inproceedings|proceedings|misc|book|techreport|phdthesis|mastersthesis|unpublished|online|software)\s*\{)", source, flags=re.IGNORECASE)

    for chunk in chunks:
        m = _BIBTEX_ENTRY_RE.match(chunk.strip())
        if not m:
            continue
        cite_key = m.group(2).strip()
        raw = chunk.strip()[:1000]
        arxiv_id = _extract_arxiv_id(chunk)
        title = _extract_title(chunk)
        url = _extract_url(chunk)

        citations.append(Citation(
            order_idx=len(citations),
            cite_key=cite_key,
            raw_bib_entry=raw,
            arxiv_id=arxiv_id,
            title=title,
            url=url,
        ))

    return citations


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_citations(full_source: str) -> tuple[Citation, ...]:
    """Extract bibliography entries from merged LaTeX source.

    Tries \\bibitem style first (most common for ArXiv papers), then falls
    back to BibTeX @entry style (when .bib files are inlined via \\input{}).

    Returns:
        Tuple of Citation objects ordered by bibliography position.
        Empty tuple if no bibliography is found.
    """
    if not full_source:
        return ()

    # Try \bibitem style first
    bib_section = _find_bibitem_section(full_source)
    if bib_section:
        citations = _parse_bibitem(bib_section)
        if citations:
            return tuple(citations)

    # Fall back to BibTeX @entry style
    if _has_bibtex(full_source):
        citations = _parse_bibtex(full_source)
        if citations:
            return tuple(citations)

    return ()

"""LaTeX heading tree: parse sectioning commands into a numbered outline.

Knows only about LaTeX. No PDF knowledge, no database knowledge.

The document's sectioning commands are walked in order, LaTeX's own section
counters are simulated to produce numbers like "2.5.3", and each heading owns
the span of source text running up to the next heading.

Unlike the heuristic splitter in ``latex_parse``, every heading becomes a unit —
including container headings whose own body is near-empty because their content
lives in child headings.  Dropping those is what loses chapter titles.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

# 1=chapter 2=section 3=subsection 4=subsubsection
_LEVEL_OF: dict[str, int] = {
    "chapter": 1,
    "section": 2,
    "subsection": 3,
    "subsubsection": 4,
}

_MAX_LEVEL = 4

# Sectioning command with optional star, optional [short title], and a braced
# title tolerating two levels of nesting: \subsection{Combining TD($\lambda$)}
_HEADING_RE = re.compile(
    r"\\(chapter|section|subsection|subsubsection)(\*?)\s*"
    r"(?:\[(?:[^\[\]]|\[[^\[\]]*\])*\])?\s*"
    r"\{((?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*)\}"
)

# A "%" starts a comment unless escaped. Mirrors _TEX_COMMENT_RE in latex_macros.
_TEX_COMMENT_RE = re.compile(r"(?<!\\)((?:\\\\)*)%[^\n]*")

# Environments whose bodies must survive comment stripping verbatim — a "%" or
# "#" inside minted/lstlisting is code, not a LaTeX comment.
_VERBATIM_RE = re.compile(
    r"\\begin\{(verbatim\*?|minted|lstlisting|Verbatim|alltt)\}.*?\\end\{\1\}",
    re.DOTALL,
)


@dataclass(frozen=True)
class Heading:
    """One sectioning command and the span of source text it owns."""
    level: int        # 1=chapter … 4=subsubsection
    number: str       # "2.5.3"; "" when starred/unnumbered
    title: str        # raw LaTeX title (not yet converted to text)
    body_start: int   # char offset of body start in the source
    body_end: int     # char offset of body end (next heading, or EOF)


def strip_comments(latex: str) -> str:
    """Remove LaTeX line comments, preserving verbatim-like environments.

    A bare ``re.sub`` would corrupt minted/lstlisting bodies, where ``%`` and
    ``#`` are source code.  Those regions are masked out, the rest is stripped,
    and the regions are restored.
    """
    kept: list[str] = []

    def mask(m: "re.Match[str]") -> str:
        kept.append(m.group(0))
        return f"\x00VERB{len(kept) - 1}\x00"

    masked = _VERBATIM_RE.sub(mask, latex)
    stripped = _TEX_COMMENT_RE.sub(r"\1", masked)

    def restore(m: "re.Match[str]") -> str:
        return kept[int(m.group(1))]

    return re.sub(r"\x00VERB(\d+)\x00", restore, stripped)


def parse_headings(latex_doc: str) -> tuple[Heading, ...]:
    """Parse *latex_doc* into a flat, document-ordered tuple of Headings.

    Section numbers are produced by simulating LaTeX's counters.  Starred
    headings are unnumbered and do not advance any counter, matching how
    ``hyperref`` omits them from the PDF outline.

    Numbering is relative to the shallowest level the document actually uses, so
    an article whose top level is ``\\section`` numbers 1, 1.1, 1.2 rather than
    0.1, 0.1.1 — matching what LaTeX itself typesets for that document class.
    """
    matches = list(_HEADING_RE.finditer(latex_doc))
    if not matches:
        return ()

    root = min(_LEVEL_OF[m.group(1)] for m in matches)
    counters = [0] * _MAX_LEVEL
    headings: list[Heading] = []

    for i, m in enumerate(matches):
        level = _LEVEL_OF[m.group(1)]
        starred = m.group(2) == "*"
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(latex_doc)

        if starred:
            number = ""
        else:
            counters[level - 1] += 1
            for deeper in range(level, _MAX_LEVEL):
                counters[deeper] = 0
            number = ".".join(str(c) for c in counters[root - 1:level])

        headings.append(Heading(
            level=level,
            number=number,
            title=m.group(3).strip(),
            body_start=m.end(),
            body_end=body_end,
        ))

    return tuple(headings)


def build_sections(
    headings: tuple[Heading, ...],
    latex_doc: str,
    pages: Mapping[int, "PageSpanLike"] | None = None,
) -> tuple["Section", ...]:
    """Turn Headings into Section objects, one per heading.

    ``order_idx`` is a running counter, so it is contiguous from 0 by
    construction — no gaps.  Nothing is dropped: a container heading with an
    empty body is still a navigation node with a valid page anchor.

    *pages* maps heading index → an object with ``start``/``end``/``source``.
    """
    # Imported here to keep this module's import graph shallow.
    from lib.latex_parse import _build_algorithm_blocks, _build_math_blocks, _latex_to_text
    from lib.models import Section

    sections: list[Section] = []

    for idx, h in enumerate(headings):
        body = latex_doc[h.body_start:h.body_end].strip()
        title = _latex_to_text(h.title).strip().lstrip(":–—,; ") or h.title
        span = pages.get(idx) if pages else None

        sections.append(Section(
            order_idx=idx,
            title=title,
            plain_text=_latex_to_text(body),
            raw_latex=body,
            math_blocks=_build_math_blocks(body),
            algorithm_blocks=_build_algorithm_blocks(body),
            level=h.level,
            number=h.number or None,
            page_start=span.start if span else None,
            page_end=span.end if span else None,
            page_source=span.source if span else None,
        ))

    return tuple(sections)


# Structural typing shim — avoids importing pdf_outline (which pulls in pymupdf)
# just for a type annotation.
class PageSpanLike:  # pragma: no cover - typing only
    start: int
    end: int
    source: str

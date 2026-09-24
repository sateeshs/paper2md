"""Heuristic document-type classification from section titles + text."""
from __future__ import annotations

import re

# Anchored patterns use MULTILINE so each section title is matched independently
# when titles are joined with newlines.
_TEXTBOOK_SIGNALS = (
    re.compile(r"^chapter\b", re.IGNORECASE | re.MULTILINE),
    re.compile(r"\bexercise", re.IGNORECASE),
    re.compile(r"\bproblem set\b", re.IGNORECASE),
    re.compile(r"^part\s+[ivx]+\b", re.IGNORECASE | re.MULTILINE),
)
# lib.latex_outline numbers chapters as level 1; only book-class documents
# use \chapter at all.
CHAPTER_LEVEL = 1

_NOTES_SIGNALS = (
    re.compile(r"^lecture\s*\d+", re.IGNORECASE | re.MULTILINE),
    re.compile(r"\bseminar\b", re.IGNORECASE),
)


def infer_paper_type(
    section_titles: list[str],
    sample_text: str = "",
    section_levels: "set[int] | None" = None,
) -> str:
    """Infer 'textbook' | 'lecture_notes' | 'research_paper'.

    Any textbook signal (chapter/exercise/problem set/part) classifies as
    textbook; otherwise any lecture-notes signal (or "lecture notes" appearing
    in sample_text) classifies as lecture_notes; otherwise research_paper.

    *section_levels* is the set of outline levels present in the document. A
    paper using LaTeX \\chapter is structurally a book even when no section is
    literally titled "Chapter N" — which is the common case, since the chapter
    heading text is the topic, not the word "Chapter".
    """
    if section_levels and CHAPTER_LEVEL in section_levels:
        return "textbook"

    joined = "\n".join(section_titles)
    if any(p.search(joined) for p in _TEXTBOOK_SIGNALS):
        return "textbook"
    if any(p.search(joined) for p in _NOTES_SIGNALS) or "lecture notes" in sample_text.lower():
        return "lecture_notes"
    return "research_paper"

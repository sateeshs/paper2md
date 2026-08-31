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
_NOTES_SIGNALS = (
    re.compile(r"^lecture\s*\d+", re.IGNORECASE | re.MULTILINE),
    re.compile(r"\bseminar\b", re.IGNORECASE),
)


def infer_paper_type(section_titles: list[str], sample_text: str = "") -> str:
    """Infer 'textbook' | 'lecture_notes' | 'research_paper' from section titles.

    Any textbook signal (chapter/exercise/problem set/part) classifies as
    textbook; otherwise any lecture-notes signal (or "lecture notes" appearing
    in sample_text) classifies as lecture_notes; otherwise research_paper.
    """
    joined = "\n".join(section_titles)
    if any(p.search(joined) for p in _TEXTBOOK_SIGNALS):
        return "textbook"
    if any(p.search(joined) for p in _NOTES_SIGNALS) or "lecture notes" in sample_text.lower():
        return "lecture_notes"
    return "research_paper"

"""Post-parse sanity checks.

`summarize_papers` reported "Processed 1/1 (errors=0)" while pushing a document
that had collapsed from 68 sections to a single 177k-char blob beginning
"\\@makefnmark to 0pt". A zero exit code only means nothing raised; it says
nothing about whether the parse produced a sane document. These checks close
that gap by inspecting the parsed result against its own source before anything
reaches the database.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from lib.models import Section

# Sectioning commands in the source, used as the expected-structure baseline.
_SOURCE_SECTION_RE = re.compile(r"\\(?:chapter|section|subsection)\*?\s*(?:\[[^\]]*\])?\s*\{")

# Internal LaTeX control sequences. A well-formed body never shows these to a
# reader — their presence means class or package internals leaked into the prose.
_INTERNAL_CS_RE = re.compile(r"\\@[a-zA-Z]+")

# A parse is considered collapsed when it recovers this fraction or less of the
# sectioning commands present in the source.
_COLLAPSE_RATIO = 0.25
_MIN_SOURCE_SECTIONS = 4

# Largest plausible single section. The corrupted 2608.27370 parse produced one
# section of 177k chars; the largest legitimate section seen is roughly 36k.
_HUGE_SECTION_CHARS = 120_000

# Fraction of sections carrying class internals above which the leak is
# document-wide rather than a stray macro in one block.
_INTERNALS_ERROR_RATIO = 0.25


@dataclass(frozen=True)
class ParseProblem:
    code: str
    severity: str          # "error" blocks the push, "warning" is advisory
    detail: str

    def __str__(self) -> str:
        return f"[{self.severity.upper()}] {self.code}: {self.detail}"


def _count_source_sections(latex_body: str) -> int:
    return len(_SOURCE_SECTION_RE.findall(latex_body))


def check_parse_health(
    sections: tuple[Section, ...], latex_body: str
) -> tuple[ParseProblem, ...]:
    """Compare a parsed document against its source and report what looks wrong."""
    problems: list[ParseProblem] = []

    if not sections:
        problems.append(ParseProblem(
            "no_sections", "error",
            "parser produced no sections at all",
        ))
        return tuple(problems)

    expected = _count_source_sections(latex_body)
    if expected >= _MIN_SOURCE_SECTIONS and len(sections) <= expected * _COLLAPSE_RATIO:
        problems.append(ParseProblem(
            "section_collapse", "error",
            f"source has {expected} sectioning commands but only "
            f"{len(sections)} section(s) were parsed — section markers were "
            f"probably consumed by macro expansion",
        ))

    # A few internals leak into normal parses — \@mainmatterfalse in a preamble
    # section, \@setsize in an acknowledgements block — so their mere presence
    # is not evidence of corruption. What distinguishes the 2608.27370 failure
    # is that they were *pervasive*: every section, and a section far too large.
    affected = [
        (s, _INTERNAL_CS_RE.findall(s.plain_text or ""))
        for s in sections
    ]
    affected = [(s, hits) for s, hits in affected if hits]
    if affected:
        ratio = len(affected) / len(sections)
        in_huge = any(len(s.plain_text or "") > _HUGE_SECTION_CHARS for s, _ in affected)
        severity = "error" if ratio >= _INTERNALS_ERROR_RATIO or in_huge else "warning"
        names = sorted({h for _, hits in affected for h in hits})[:4]
        problems.append(ParseProblem(
            "class_internals", severity,
            f"{len(affected)} of {len(sections)} section(s) contain internal "
            f"control sequences in their text: {', '.join(names)}",
        ))

    for section in sections:
        size = len(section.plain_text or "")
        if size > _HUGE_SECTION_CHARS:
            problems.append(ParseProblem(
                "huge_section", "warning",
                f"section {section.order_idx} ({section.title!r}) is {size:,} chars — "
                f"splitting may have failed",
            ))

    return tuple(problems)


def blocking(problems: tuple[ParseProblem, ...]) -> tuple[ParseProblem, ...]:
    """The subset that should prevent a push."""
    return tuple(p for p in problems if p.severity == "error")

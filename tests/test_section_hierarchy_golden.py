"""Golden test: arXiv 2412.05265 (Murphy, *Reinforcement Learning: An Overview*).

A 253-page, book-structured paper that exercised every extraction bug at once:
duplicated content, dropped chapter titles, order_idx gaps and no page numbers.

Fixtures are the real pipeline's output — LaTeX headings produced by
``lib.latex_outline.parse_headings`` over the merged tarball, and the PDF
hyperref outline read by ``lib.pdf_outline.parse_outline``. No network access.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from lib.pdf_outline import OutlineEntry, map_pages, normalize_title

FIXTURES = Path(__file__).parent / "fixtures" / "2412.05265"


@dataclass(frozen=True)
class FixtureHeading:
    level: int
    number: str
    title: str


@pytest.fixture(scope="module")
def headings() -> list[FixtureHeading]:
    return [FixtureHeading(**h) for h in json.loads((FIXTURES / "latex_headings.json").read_text())]


@pytest.fixture(scope="module")
def outline() -> list[OutlineEntry]:
    return [OutlineEntry(**e) for e in json.loads((FIXTURES / "pdf_outline.json").read_text())]


@pytest.fixture(scope="module")
def meta() -> dict:
    return json.loads((FIXTURES / "meta.json").read_text())


@pytest.fixture(scope="module")
def spans(headings, outline, meta):
    return map_pages(
        headings, outline,
        total_pages=meta["page_count"],
        references_page=meta["references_page"],
    )


# ── structure ──────────────────────────────────────────────────────────────

def test_latex_and_pdf_agree_on_heading_count(headings, outline):
    assert len(headings) == len(outline) == 388


def test_all_eight_chapters_are_present(headings):
    chapters = [h for h in headings if h.level == 1]
    assert [h.number for h in chapters] == [str(i) for i in range(1, 9)]
    assert chapters[0].title == "Introduction"
    assert chapters[1].title == "Value-based RL"


def test_chapter_titles_are_not_dropped(headings):
    """These four were silently deleted by the old < 50 char filter."""
    titles = {h.title for h in headings}
    assert {"Introduction", "Value-based RL", "Model-based RL", "LLMs and RL"} <= titles


def test_no_phantom_preamble_section(headings):
    assert not any(h.title == "Preamble" for h in headings)


def test_implementation_details_appears_exactly_once(headings):
    """The `%\\input{code}` bug inlined code.tex twice, once at the document top."""
    matches = [h for h in headings if h.title == "Implementation details"]
    assert len(matches) == 1
    assert matches[0].number == "6.4"


def test_eat_draft_content_is_excluded(headings):
    """\\eat{...} blocks are the author's deleted drafts and must not appear."""
    titles = {h.title for h in headings}
    assert "Bound optimization methods" not in titles


# ── numbering ──────────────────────────────────────────────────────────────

def test_latex_counter_simulation_matches_the_pdf_exactly(headings, outline):
    mismatches = [
        (h.number, e.number, h.title)
        for h, e in zip(headings, outline)
        if h.number != e.number
    ]
    assert mismatches == []


def test_level_distribution_matches_the_pdf(headings, outline):
    def by_level(items):
        counts: dict[int, int] = {}
        for i in items:
            counts[i.level] = counts.get(i.level, 0) + 1
        return counts

    assert by_level(headings) == by_level(outline) == {1: 8, 2: 34, 3: 145, 4: 201}


# ── page mapping ───────────────────────────────────────────────────────────

def test_every_heading_gets_a_page(spans, headings):
    assert len(spans) == len(headings)


def test_alignment_is_essentially_perfect(spans, headings):
    exact = sum(1 for s in spans.values() if s.source == "pdf_outline")
    assert exact / len(headings) >= 0.95, f"only {exact}/{len(headings)} exact"


def test_pages_never_go_backwards(spans, headings):
    """The PDF-order invariant: units are ordered as they appear in the PDF."""
    starts = [spans[i].start for i in range(len(headings))]
    violations = [
        (i, headings[i].number, starts[i - 1], starts[i])
        for i in range(1, len(starts))
        if starts[i] < starts[i - 1]
    ]
    assert violations == []


def test_page_ranges_are_well_formed(spans):
    assert all(s.end >= s.start >= 1 for s in spans.values())


def test_known_landmark_pages(spans, headings):
    by_number = {h.number: spans[i] for i, h in enumerate(headings)}
    assert by_number["1"].start == 13       # ch.1 Introduction
    assert by_number["2"].start == 31       # ch.2 Value-based RL
    assert by_number["6.4"].start == 165    # the formerly-duplicated section
    assert by_number["8"].start == 199      # ch.8 Acknowledgements


def test_final_section_stops_at_the_bibliography(spans, headings, meta):
    """Without capping, ch.8 runs to p.253 and swallows 54 pages of references."""
    last = spans[len(headings) - 1]
    assert last.end == meta["references_page"] == 201
    assert last.end < meta["page_count"]


def test_titles_are_normalised_consistently(headings, outline):
    mismatches = [
        (h.title, e.title)
        for h, e in zip(headings, outline)
        if normalize_title(h.title) != normalize_title(e.title)
    ]
    assert mismatches == []

"""Tests for lib/pdf_outline.py — outline parsing and heading→page alignment."""

from __future__ import annotations

from dataclasses import dataclass

from lib.pdf_outline import (
    MIN_MATCH_RATIO,
    OutlineEntry,
    _split_number,
    map_pages,
    normalize_title,
    parse_outline,
)


@dataclass(frozen=True)
class H:
    """Minimal stand-in for latex_outline.Heading (map_pages only reads .title)."""
    title: str


def entry(number: str, title: str, page: int, level: int = 2) -> OutlineEntry:
    return OutlineEntry(level=level, number=number, title=title, page=page)


# ── bookmark number splitting ──────────────────────────────────────────────

def test_splits_a_numeric_prefix():
    assert _split_number("2.5.3 Maximization bias") == ("2.5.3", "Maximization bias")


def test_splits_a_single_level_number():
    assert _split_number("8 Acknowledgements") == ("8", "Acknowledgements")


def test_leaves_an_unnumbered_bookmark_alone():
    assert _split_number("References") == ("", "References")


def test_does_not_treat_a_leading_year_word_as_a_number():
    assert _split_number("References") == ("", "References")


# ── title normalisation ────────────────────────────────────────────────────

def test_strips_inline_math_so_latex_and_bookmark_agree():
    assert normalize_title(r"Sarsa($\lambda$)") == normalize_title("Sarsa()")


def test_strips_control_sequences():
    assert normalize_title(r"\emph{Deep} Q-learning") == "deep q learning"


def test_is_case_and_punctuation_insensitive():
    assert normalize_title("Q-Learning: Off-Policy!") == normalize_title("q learning off policy")


# ── alignment ──────────────────────────────────────────────────────────────

def test_exact_alignment_gives_exact_pages():
    headings = [H("Intro"), H("Methods"), H("Results")]
    outline = [entry("1", "Intro", 1), entry("2", "Methods", 5), entry("3", "Results", 9)]
    spans = map_pages(headings, outline, total_pages=12)
    assert [spans[i].start for i in range(3)] == [1, 5, 9]
    assert all(spans[i].source == "pdf_outline" for i in range(3))


def test_page_end_is_the_next_headings_start():
    headings = [H("A"), H("B")]
    outline = [entry("1", "A", 3), entry("2", "B", 7)]
    spans = map_pages(headings, outline, total_pages=10)
    assert (spans[0].start, spans[0].end) == (3, 7)


def test_heading_missing_from_the_outline_is_interpolated():
    # "Extra" exists in LaTeX but has no bookmark (e.g. starred heading)
    headings = [H("A"), H("Extra"), H("B")]
    outline = [entry("1", "A", 3), entry("2", "B", 8)]
    spans = map_pages(headings, outline, total_pages=10)
    assert spans[1].source == "inferred"
    assert spans[0].start <= spans[1].start <= spans[2].start


def test_outline_entry_missing_from_latex_does_not_shift_pages():
    # Front matter bookmark with no corresponding LaTeX heading
    headings = [H("A"), H("B")]
    outline = [entry("", "Contents", 2), entry("1", "A", 5), entry("2", "B", 9)]
    spans = map_pages(headings, outline, total_pages=12)
    assert [spans[i].start for i in range(2)] == [5, 9]


def test_pages_are_monotone_with_interpolation_everywhere():
    headings = [H(f"H{i}") for i in range(10)]
    # 6/10 aligned — above MIN_MATCH_RATIO, so gaps get interpolated
    outline = [
        entry("1", "H0", 1), entry("2", "H1", 5), entry("3", "H3", 12),
        entry("4", "H5", 20), entry("5", "H7", 33), entry("6", "H9", 50),
    ]
    spans = map_pages(headings, outline, total_pages=60)
    starts = [spans[i].start for i in range(10)]
    assert starts == sorted(starts), starts


# ── degradation ────────────────────────────────────────────────────────────

def test_empty_outline_yields_no_pages():
    assert map_pages([H("A")], []) == {}


def test_no_headings_yields_no_pages():
    assert map_pages([], [entry("1", "A", 1)]) == {}


def test_weak_alignment_is_discarded_entirely():
    headings = [H(f"unrelated {i}") for i in range(10)]
    outline = [entry("1", "completely different", 1)]
    assert map_pages(headings, outline, total_pages=5) == {}


def test_alignment_at_the_threshold_is_kept():
    headings = [H("A"), H("B"), H("zzz"), H("yyy")]
    outline = [entry("1", "A", 1), entry("2", "B", 4)]
    spans = map_pages(headings, outline, total_pages=8)
    assert len(spans) == 4                      # 2/4 == MIN_MATCH_RATIO
    assert MIN_MATCH_RATIO == 0.5


def test_unreadable_pdf_bytes_yield_no_outline():
    assert parse_outline(b"not a pdf at all") == ()


# ── bibliography capping ───────────────────────────────────────────────────

def test_final_section_stops_at_the_bibliography():
    headings = [H("A"), H("Acknowledgements")]
    outline = [
        entry("1", "A", 10),
        entry("2", "Acknowledgements", 20),
        entry("", "References", 25, level=1),
    ]
    spans = map_pages(headings, outline, total_pages=200)
    assert spans[1].end == 25, "must not absorb 175 pages of references"


def test_final_section_falls_back_to_total_pages_without_a_bibliography():
    headings = [H("A")]
    outline = [entry("1", "A", 10)]
    assert map_pages(headings, outline, total_pages=30)[0].end == 30

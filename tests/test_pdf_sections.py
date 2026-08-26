"""Test PDF section splitting and roman numeral page number detection."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is in sys.path for lib imports
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from lib.pdf_sections import split_pdf_into_sections, is_roman_page_number


def test_inline_chapter_headings_split():
    text = (
        "Intro paragraph.\n\n"
        "Chapter 1 Nash Equilibrium\n\n" + "word " * 150 +
        "\n\nChapter 2 Bayesian Games\n\n" + "word " * 150
    )
    sections = split_pdf_into_sections(text)
    assert len(sections) >= 2
    assert any("Chapter 1" in s.title for s in sections)


def test_short_documents_fall_back_to_single_section():
    sections = split_pdf_into_sections("Just a little text.")
    assert len(sections) == 1


def test_common_words_not_treated_as_page_numbers():
    assert not is_roman_page_number("mix")
    assert not is_roman_page_number("civil")
    assert not is_roman_page_number("did")


def test_actual_roman_numerals_still_filtered():
    assert is_roman_page_number("iv")
    assert is_roman_page_number("XII")
    assert is_roman_page_number("xlv")


def test_long_roman_tokens_are_preserved_not_filtered():
    """Tokens ≥7 chars are kept because they're implausible as page numbers."""
    # "mcmxciv" is valid roman numeral (1999) but >6 chars
    # implausible as a page number; likely real content (e.g., years in prose)
    assert not is_roman_page_number("mcmxciv")


def _body(words: int = 110) -> str:
    return "word " * words  # ~550+ chars, above MIN_BODY so bodies are not merged


def test_numbered_headings_with_trailing_dot_split():
    """'N. Title' headings (common in PDF extraction) must split into sections."""
    text = (
        "Abstract paragraph.\n\n"
        "1. Introduction\n\n" + _body() +
        "\n\n2. Related Works\n\n" + _body() +
        "\n\n3. Proposed Model\n\n" + _body()
    )
    sections = split_pdf_into_sections(text)
    assert len(sections) >= 3
    titles = [s.title for s in sections]
    assert any("Introduction" in t for t in titles)
    assert any("Related Works" in t for t in titles)


def test_bare_page_number_lines_do_not_anchor_sections():
    """Standalone page-number lines ('1', '4', '6') followed by unpunctuated
    prose must not become section anchors that swallow body text.
    Mirrors the real failure on arXiv 2512.21804."""
    text = (
        "1. Introduction\n\n" + _body() +
        "\n\n4\n\nFinancial institutions banks and dealers trade large volumes of\n" + _body() +
        "\n\n5\n\nThe training procedure uses Adam optimizer with learning rate\n" + _body() +
        "\n\n6\n\nHYPERPARAMETERS TUNING:\nFollowing are the tuned values\n" + _body()
    )
    sections = split_pdf_into_sections(text)
    # The real heading is "1. Introduction"; a bare '4'/'6' line must not
    # start a section whose first line is just the page number.
    for s in sections:
        first_line = s.title.strip().splitlines()[0]
        assert not first_line.isdigit(), f"page number became title: {s.title!r}"


def test_running_headers_not_treated_as_sections():
    """A textbook running header (chapter title repeated on every page) must
    not spawn one section per page. Mirrors arXiv 2403.02467 where the header
    '1 Predictive Inference ...' repeated ~40 times produced hundreds of junk
    sections."""
    header = "1 Predictive Inference with Linear Regression in Moderately High Dimensions"
    text = ""
    for _ in range(8):
        text += f"\n\n{header}\n\n" + _body()
    # Distinct subsection headings appear once each — these are real anchors.
    text = (
        "1.1 Foundation of Linear Regression\n\n" + _body() +
        "\n\n" + header + "\n\n" + _body() +
        "\n\n" + header + "\n\n" + _body() +
        "\n\n1.2 Statistical Properties of Least Squares\n\n" + _body() +
        "\n\n" + header + "\n\n" + _body()
    )
    sections = split_pdf_into_sections(text)
    titles = [s.title for s in sections]
    assert sum(1 for t in titles if "Predictive Inference" in t) == 0, titles
    assert any("Foundation of Linear Regression" in t for t in titles)
    assert any("Statistical Properties of Least Squares" in t for t in titles)


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

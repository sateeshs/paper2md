"""Tests for heuristic paper-type inference."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.paper_type import infer_paper_type


def test_chapter_titles_signal_textbook():
    assert infer_paper_type(["Chapter 1: Limits", "Chapter 2: Derivatives"]) == "textbook"


def test_exercise_titles_signal_textbook():
    assert infer_paper_type(["Introduction", "Exercise Set 3"]) == "textbook"


def test_plain_titles_default_to_research_paper():
    assert infer_paper_type(["Abstract", "Related Work", "Experiments"]) == "research_paper"


def test_lecture_in_title_signals_notes():
    assert infer_paper_type(["Lecture 5: Convexity"], sample_text="course notes") == "lecture_notes"

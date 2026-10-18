"""Tests for title extraction in summarize_papers._title_from_latex.

`\title{%` is a standard LaTeX line-continuation idiom. Without stripping
comments the % survives into the stored title and renders on the site — as it
did for arXiv 2511.14427: "% Self-Supervised Multisensory Pretraining … %".
"""

from __future__ import annotations

from summarize_papers import _title_from_latex

FALLBACK = "fallback-title"


def test_plain_title():
    assert _title_from_latex(r"\title{Attention Is All You Need}", FALLBACK) == \
        "Attention Is All You Need"


def test_title_with_percent_continuation():
    src = "\\title{%\n  Self-Supervised Multisensory Pretraining %\n}"
    assert _title_from_latex(src, FALLBACK) == "Self-Supervised Multisensory Pretraining"


def test_trailing_percent_is_not_kept():
    src = "\\title{Deep Learning for Robots %\n}"
    assert "%" not in _title_from_latex(src, FALLBACK)


def test_a_commented_out_title_is_ignored():
    src = "%\\title{Draft Title We Abandoned}\n\\title{The Real Title}"
    assert _title_from_latex(src, FALLBACK) == "The Real Title"


def test_escaped_percent_survives():
    src = r"\title{Achieving 95\% Accuracy}"
    assert "95" in _title_from_latex(src, FALLBACK)


def test_nested_braces_still_work():
    src = r"\title{\textbf{Bold Title} and More}"
    assert _title_from_latex(src, FALLBACK) == "Bold Title and More"


def test_icmltitle_variant():
    assert _title_from_latex(r"\icmltitle{An ICML Paper}", FALLBACK) == "An ICML Paper"


def test_falls_back_when_absent():
    assert _title_from_latex("no title command here", FALLBACK) == FALLBACK

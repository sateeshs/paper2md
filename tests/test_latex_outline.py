"""Tests for lib/latex_outline.py — heading tree and LaTeX counter simulation."""

from __future__ import annotations

from lib.latex_outline import build_sections, parse_headings, strip_comments


# ── strip_comments ─────────────────────────────────────────────────────────

def test_removes_a_line_comment():
    assert strip_comments("keep me % drop me\nnext") == "keep me \nnext"


def test_keeps_escaped_percent():
    assert strip_comments(r"100\% done") == r"100\% done"


def test_escaped_backslash_before_percent_still_starts_a_comment():
    # `\\` ends a line; the % after it is a real comment
    assert strip_comments("line\\\\% note\nnext") == "line\\\\\nnext"


def test_preserves_percent_inside_minted():
    src = "before % gone\n\\begin{minted}{python}\nx = 5 % 2  # keep\n\\end{minted}\nafter % gone"
    out = strip_comments(src)
    assert "x = 5 % 2  # keep" in out
    assert "gone" not in out


def test_preserves_percent_inside_verbatim():
    src = "\\begin{verbatim}\n50% off\n\\end{verbatim}"
    assert "50% off" in strip_comments(src)


# ── counter simulation ─────────────────────────────────────────────────────

def test_numbers_all_four_levels():
    doc = (
        r"\chapter{One}" r"\section{A}" r"\subsection{a}" r"\subsubsection{i}"
        r"\subsubsection{ii}" r"\subsection{b}" r"\section{B}" r"\chapter{Two}"
    )
    assert [(h.number, h.title) for h in parse_headings(doc)] == [
        ("1", "One"), ("1.1", "A"), ("1.1.1", "a"), ("1.1.1.1", "i"),
        ("1.1.1.2", "ii"), ("1.1.2", "b"), ("1.2", "B"), ("2", "Two"),
    ]


def test_deeper_counters_reset_on_a_coarser_heading():
    doc = r"\section{A}\subsection{a}\subsubsection{i}\section{B}\subsection{b}"
    assert [h.number for h in parse_headings(doc)] == ["1", "1.1", "1.1.1", "2", "2.1"]


def test_starred_headings_are_unnumbered_and_do_not_advance_counters():
    doc = r"\section{A}\section*{Unnumbered}\section{B}"
    headings = parse_headings(doc)
    assert [h.number for h in headings] == ["1", "", "2"]
    assert headings[1].title == "Unnumbered"


def test_level_skip_keeps_zero_placeholders_like_latex():
    # \chapter straight to \subsubsection: LaTeX itself typesets 1.0.0.1
    assert [h.number for h in parse_headings(r"\chapter{C}\subsubsection{deep}")] == ["1", "1.0.0.1"]


def test_numbering_is_relative_to_the_documents_top_level():
    # An article with no \chapter must number from \section, not 0.1
    assert [h.number for h in parse_headings(r"\section{A}\subsection{a}")] == ["1", "1.1"]


def test_numbering_is_absolute_when_chapters_are_present():
    doc = r"\chapter{C}\section{A}\subsection{a}"
    assert [h.number for h in parse_headings(doc)] == ["1", "1.1", "1.1.1"]


# ── title parsing ──────────────────────────────────────────────────────────

def test_title_with_nested_braces_and_math():
    doc = r"\subsection{Combining TD and MC using TD($\lambda$)}"
    assert parse_headings(doc)[0].title == r"Combining TD and MC using TD($\lambda$)"


def test_optional_short_title_is_ignored():
    doc = r"\section[Short]{The Actual Long Title}"
    assert parse_headings(doc)[0].title == "The Actual Long Title"


def test_commented_headings_are_not_parsed():
    doc = strip_comments("%\\section{Ghost}\n\\section{Real}")
    assert [h.title for h in parse_headings(doc)] == ["Real"]


def test_no_headings_returns_empty():
    assert parse_headings("just prose, no sectioning at all") == ()


# ── body spans ─────────────────────────────────────────────────────────────

def test_body_runs_up_to_the_next_heading():
    doc = r"\section{A}" "\nbody of A\n" r"\section{B}" "\nbody of B"
    headings = parse_headings(doc)
    assert doc[headings[0].body_start:headings[0].body_end].strip() == "body of A"
    assert doc[headings[1].body_start:headings[1].body_end].strip() == "body of B"


# ── build_sections ─────────────────────────────────────────────────────────

def test_order_idx_is_contiguous_from_zero():
    doc = r"\chapter{C}" + "".join(rf"\section{{S{i}}} text {i}" for i in range(5))
    sections = build_sections(parse_headings(doc), doc)
    assert [s.order_idx for s in sections] == list(range(6))


def test_container_headings_with_empty_bodies_are_kept():
    # \chapter{Introduction} has no body of its own — it must survive as a node.
    doc = r"\chapter{Introduction}" + "\n" + r"\section{First}" + "\nreal content here"
    sections = build_sections(parse_headings(doc), doc)
    assert [s.title for s in sections] == ["Introduction", "First"]
    assert sections[0].level == 1 and sections[0].number == "1"


def test_level_and_number_are_carried_onto_sections():
    doc = r"\chapter{C}\section{S}\subsection{Sub} body"
    sections = build_sections(parse_headings(doc), doc)
    assert [(s.level, s.number) for s in sections] == [(1, "1"), (2, "1.1"), (3, "1.1.1")]


def test_page_fields_are_none_without_a_mapping():
    doc = r"\section{A} body"
    s = build_sections(parse_headings(doc), doc)[0]
    assert (s.page_start, s.page_end, s.page_source) == (None, None, None)


def test_page_fields_are_applied_from_the_mapping():
    from lib.pdf_outline import PageSpan

    doc = r"\section{A} body" r"\section{B} body"
    sections = build_sections(
        parse_headings(doc), doc,
        {0: PageSpan(3, 5, "pdf_outline"), 1: PageSpan(5, 9, "inferred")},
    )
    assert [(s.page_start, s.page_end, s.page_source) for s in sections] == [
        (3, 5, "pdf_outline"), (5, 9, "inferred"),
    ]


def test_starred_heading_gets_none_number_not_empty_string():
    doc = r"\section*{Acknowledgements} thanks"
    assert build_sections(parse_headings(doc), doc)[0].number is None

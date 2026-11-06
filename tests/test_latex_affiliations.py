"""Affiliations are read from the LaTeX source so search can match an
organisation ("google deepmind") as well as a title. Snippets are taken from
the papers they are named after."""
from __future__ import annotations

from lib.latex_affiliations import extract_affiliations


def test_icml_affiliation_uses_the_name_not_the_key():  # 2502.16238
    src = r"""
\icmlaffiliation{yyy}{Flatiron Institute, New York, USA}
\icmlaffiliation{cmu}{Carnegie Mellon University, Pittsburgh, USA}
"""
    assert extract_affiliations(src) == (
        "Flatiron Institute, New York, USA",
        "Carnegie Mellon University, Pittsburgh, USA",
    )


def test_affil_with_optional_marker():  # 2603.04735, 2610.22236
    src = r"""
\affil[1]{Google Research}
\affiliation[2]{Tsinghua University}
\affiliation{IBM Quantum, IBM Research}
"""
    assert extract_affiliations(src) == (
        "Google Research", "Tsinghua University", "IBM Quantum, IBM Research",
    )


def test_springer_keeps_department_org_and_place_but_not_street():  # 2512.17034
    src = (r"\affil[1]{\orgdiv{Department of EECS}, \orgname{Florida Atlantic University}, "
           r"\orgaddress{\street{777 Glades Rd}, \city{Boca Raton}, \postcode{33434}, "
           r"\state{FL}, \country{USA}}}")
    assert extract_affiliations(src) == (
        "Department of EECS, Florida Atlantic University, Boca Raton, FL, USA",
    )


def test_acmart_institution_parts_are_all_kept():
    src = (r"\affiliation{\institution{Google DeepMind}\department{Gemini Team}"
           r"\city{London}\country{United Kingdom}}")
    assert extract_affiliations(src) == ("Google DeepMind, Gemini Team, London, United Kingdom",)


def test_continuation_lines_are_kept_and_emails_dropped():  # 2610.41903, 2609.02084
    src = r"""
\affil[1]{University of Pennsylvania; yuxinc@wharton.upenn.edu}
\affil[2]{Graduate School of Mathematics, Nagoya University.\\ Nagoya, Japan \\ \texttt{x@nagoya-u.jp}}
"""
    assert extract_affiliations(src) == (
        "University of Pennsylvania",
        "Graduate School of Mathematics, Nagoya University, Nagoya, Japan",
    )


def test_merge_keeps_order_and_drops_case_insensitive_duplicates():
    from lib.latex_affiliations import merge_affiliations

    assert merge_affiliations(("Google DeepMind", "MIT"), ("google deepmind", "Mila")) == (
        "Google DeepMind", "MIT", "Mila",
    )


def test_institute_is_split_on_and():
    src = r"\institute{Google DeepMind, London \and University of Oxford}"
    assert extract_affiliations(src) == ("Google DeepMind, London", "University of Oxford")


def test_definitions_comments_and_duplicates_are_ignored():
    src = r"""
\newcommand{\icmlaffiliation}[2]{\gdef\@affil{#2}}
% \affil{Commented Out Lab}
\affiliation{IBM Quantum, IBM Research}
\affiliation{IBM Quantum,  IBM Research}
"""
    assert extract_affiliations(src) == ("IBM Quantum, IBM Research",)


def test_no_affiliation_commands_gives_empty_tuple():  # 2610.21691 uses \author superscripts
    assert extract_affiliations(r"\author{Tianyi Li$^{1}$ and A. Bertrand$^{1}$}") == ()

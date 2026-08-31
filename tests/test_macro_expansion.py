"""Regression tests for LaTeX macro expansion.

Every case here reproduces a way paper-specific macros used to leak into the
database unexpanded, which then surfaced as broken KaTeX rendering in the UI.
"""
import re

import pytest

from lib.arxiv_source import split_preamble
from lib.latex_macros import expand_custom_macros
from lib.latex_parse import parse_latex_sections


# ---------------------------------------------------------------------------
# The original defect: definitions live in the preamble, which is stripped
# before parsing, so the body was expanded against an empty macro table.
# ---------------------------------------------------------------------------

def test_preamble_macros_expand_into_the_body():
    preamble = r"\newcommand{\altpoint}{\theta}"
    body = r"Let $\altpoint_1 \in \R^d$ be given."
    assert expand_custom_macros(body, preamble) == r"Let $\theta_1 \in \R^d$ be given."


def test_body_without_preamble_leaves_macro_unexpanded():
    body = r"Let $\altpoint_1$ be given."
    assert r"\altpoint" in expand_custom_macros(body)


def test_parse_latex_sections_threads_the_preamble_through():
    preamble = r"\newcommand{\Ff}{\mathcal{F}}"
    body = (
        r"\section{Intro}" + "\n"
        + r"We study $\Ff(x) = 0$ closely, and it matters a great deal here."
    )
    sections = parse_latex_sections(body, preamble)
    exprs = [b.latex_expr for s in sections for b in s.math_blocks]
    assert exprs and all(r"\Ff" not in e for e in exprs)
    assert any(r"\mathcal{F}" in e for e in exprs)


def test_split_preamble_returns_everything_before_begin_document():
    src = "\\newcommand{\\a}{b}\n\\begin{document}\nbody\n\\end{document}"
    assert split_preamble(src).strip() == r"\newcommand{\a}{b}"


def test_split_preamble_of_a_bodyless_source_is_empty():
    assert split_preamble("no document marker here") == ""


# ---------------------------------------------------------------------------
# Brace nesting: the previous regex captured only one level, so any macro whose
# body nested deeper was never registered at all.
# ---------------------------------------------------------------------------

def test_macro_body_with_two_levels_of_nesting_expands():
    preamble = r"""
    \newcommand{\deflink}[2]{#2}
    \newcommand{\Aff}{\deflink{def:affine}{\mathcal{A}}}
    """
    assert expand_custom_macros(r"$\Aff_{m,n}$", preamble) == r"$\mathcal{A}_{m,n}$"


def test_macro_body_with_three_levels_of_nesting_expands():
    preamble = r"\newcommand{\deep}{\alpha{\beta{\gamma{\delta}}}}"
    assert expand_custom_macros(r"$\deep$", preamble) == r"$\alpha{\beta{\gamma{\delta}}}$"


# ---------------------------------------------------------------------------
# Scoping: papers redefine the same shorthand per chapter, sometimes with a
# different arity. A single global meaning corrupts every chapter but one.
# ---------------------------------------------------------------------------

def test_redefinition_applies_only_after_its_position():
    doc = (
        r"\newcommand{\x}{\mathscr{x}}"
        r"first $\x_m$ "
        r"\renewcommand{\x}[1]{x_{#1}}"
        r"second $\x{m}$"
    )
    out = expand_custom_macros(doc)
    assert r"\mathscr{x}_m" in out
    assert "x_{m}" in out


def test_providecommand_does_not_override_an_existing_definition():
    doc = r"\newcommand{\g}{\gamma}\providecommand{\g}{}$\g$"
    assert expand_custom_macros(doc) == r"$\gamma$"


def test_providecommand_defines_when_the_name_is_free():
    assert expand_custom_macros(r"\providecommand{\g}{\gamma}$\g$") == r"$\gamma$"


def test_guard_idiom_resolves_to_the_real_body():
    # \providecommandordefault{\f}{\cE} expands to a provide+renew pair; the
    # empty \providecommand must not win.
    doc = (
        r"\newcommand{\providecommandordefault}[2]{\providecommand{#1}{}\renewcommand{#1}{#2}}"
        r"\providecommandordefault{\f}{\mathcal{E}}"
        r"$\f(x)$"
    )
    assert expand_custom_macros(doc) == r"$\mathcal{E}(x)$"


def test_definitions_are_consumed_not_emitted():
    assert expand_custom_macros(r"\newcommand{\q}{Q}before $\q$") == "before $Q$"


# ---------------------------------------------------------------------------
# Definition families beyond \newcommand
# ---------------------------------------------------------------------------

def test_declare_math_operator():
    doc = r"\DeclareMathOperator{\tr}{tr}$\tr(A)$"
    assert expand_custom_macros(doc) == r"$\operatorname{tr}(A)$"


def test_def_with_parameters():
    doc = r"\def\pair#1#2{(#1,#2)}$\pair{a}{b}$"
    assert expand_custom_macros(doc) == "$(a,b)$"


def test_new_document_command_mandatory_arg():
    doc = r"\NewDocumentCommand{\sq}{m}{#1^2}$\sq{x}$"
    assert expand_custom_macros(doc) == "$x^2$"


def test_new_document_command_star_and_optional_args():
    doc = r"\NewDocumentCommand{\w}{s o m}{[#3]}$\w*[big]{y}$"
    assert expand_custom_macros(doc) == "$[y]$"


def test_new_document_command_with_unsupported_spec_is_left_alone():
    doc = r"\NewDocumentCommand{\weird}{r() m}{#2}$\weird(a){b}$"
    assert r"\weird" in expand_custom_macros(doc)


def test_declare_paired_delimiter():
    doc = r"\DeclarePairedDelimiter{\abs}{\lvert}{\rvert}$\abs{x}$"
    assert expand_custom_macros(doc) == r"$\left\lvert x \right\rvert$"


def test_declare_paired_delimiter_ignores_the_star_variant():
    doc = r"\DeclarePairedDelimiter{\abs}{\lvert}{\rvert}$\abs*{x}$"
    assert expand_custom_macros(doc) == r"$\left\lvert x \right\rvert$"


def test_paired_delimiter_xpp_renumbers_its_arguments():
    doc = (
        r"\DeclarePairedDelimiterXPP\Pnorm[2]{}\lVert\rVert{_{#1}}{#2}"
        r"$\Pnorm{p}{x}$"
    )
    assert expand_custom_macros(doc) == r"$\left\lVert x \right\rVert_{p}$"


def test_expl3_body_expands_to_nothing_but_still_eats_its_argument():
    # \cfadd is a cross-reference registry: no typeset output. Leaking it would
    # print the raw label ("def:affine") inside the formula.
    doc = (
        r"\NewDocumentCommand{\cfadd}{m}{\seq_if_in:NnF \g_list {#1} {}}"
        r"$\cfadd{def:affine}\mathcal{A}$"
    )
    assert expand_custom_macros(doc) == r"$\mathcal{A}$"


def test_optional_argument_with_a_default():
    doc = r"\newcommand{\pow}[2][2]{#2^{#1}}$\pow{x}$ and $\pow[3]{y}$"
    assert expand_custom_macros(doc) == "$x^{2}$ and $y^{3}$"


# ---------------------------------------------------------------------------
# Argument reading
# ---------------------------------------------------------------------------

def test_single_token_argument_that_is_a_control_sequence():
    doc = r"\newcommand{\dup}[1]{#1#1}$\dup\alpha$"
    assert expand_custom_macros(doc) == r"$\alpha\alpha$"


def test_macro_use_with_too_few_arguments_is_left_alone():
    # A single-token argument must never swallow a delimiter such as the
    # closing "$" — that would silently destroy the surrounding math.
    doc = r"\newcommand{\two}[2]{#1#2}$\two{a}$"
    assert expand_custom_macros(doc) == r"$\two{a}$"


def test_longer_macro_name_wins_over_its_prefix():
    preamble = r"\newcommand{\alt}{A}\newcommand{\altTwo}{B}"
    assert expand_custom_macros(r"$\altTwo$", preamble) == "$B$"


def test_macro_name_is_not_matched_inside_a_longer_name():
    preamble = r"\newcommand{\alt}{A}"
    assert expand_custom_macros(r"$\altitude$", preamble) == r"$\altitude$"


# ---------------------------------------------------------------------------
# Recursion is bounded
# ---------------------------------------------------------------------------

def test_self_referential_macro_terminates():
    doc = r"\newcommand{\loop}{\loop}$\loop$"
    assert isinstance(expand_custom_macros(doc), str)


def test_mutually_recursive_macros_terminate():
    doc = r"\newcommand{\aa}{\bb}\newcommand{\bb}{\aa}$\aa$"
    assert isinstance(expand_custom_macros(doc), str)


# ---------------------------------------------------------------------------
# The three mathtools paired-delimiter forms have *different* signatures.
# Conflating them makes the parser over-read and silently swallow whatever
# definition follows — which is how \br went missing from 2310.20360 even
# though it is defined in the preamble.
# ---------------------------------------------------------------------------

def test_paired_delimiter_x_does_not_swallow_the_next_definition():
    doc = (
        r"\DeclarePairedDelimiterX\expbr[1]{[}{]}{#1}"
        "\n"
        r"\DeclarePairedDelimiter{\br}{[}{]}"
        "\n"
        r"$\br[\big]{ x }$"
    )
    # \br must still be defined — before the fix the \expbr parse consumed it.
    assert r"\left[  x  \right]" in expand_custom_macros(doc)


def test_paired_delimiter_x_expands_its_own_uses():
    doc = r"\DeclarePairedDelimiterX\expbr[1]{[}{]}{#1}$\expbr{y}$"
    assert expand_custom_macros(doc) == r"$\left[ y \right]$"


def test_paired_delimiter_xpp_still_takes_five_groups():
    doc = (
        r"\DeclarePairedDelimiterXPP\Pnorm[2]{}\lVert\rVert{_{#1}}{#2}"
        r"\newcommand{\after}{OK}"
        r"$\Pnorm{p}{x}\after$"
    )
    out = expand_custom_macros(doc)
    assert r"\left\lVert x \right\rVert_{p}" in out
    assert "OK" in out          # the following definition survived


# ---------------------------------------------------------------------------
# TeX comments must be stripped before scanning: a commented-out brace breaks
# brace counting, and comment text otherwise leaks into macro bodies.
# ---------------------------------------------------------------------------

def test_comment_inside_a_macro_body_is_removed():
    doc = "\\newcommand{\\f}{%\n\\alpha\n}$\\f$"
    out = expand_custom_macros(doc)
    # Newlines are preserved so line positions (and section splitting) are
    # unaffected; only the comment text is removed.
    assert "%" not in out
    assert out.split("$")[1].strip() == r"\alpha"


def test_commented_out_brace_does_not_break_brace_counting():
    doc = "\\newcommand{\\g}{a% }\n b}\\newcommand{\\h}{H}$\\g\\h$"
    out = expand_custom_macros(doc)
    assert "H" in out           # \h was still registered


def test_escaped_percent_is_not_treated_as_a_comment():
    doc = r"\newcommand{\pct}{50\%}$\pct$"
    assert expand_custom_macros(doc) == r"$50\%$"


def test_comment_after_a_line_break_is_stripped():
    doc = "\\newcommand{\\k}{a \\\\% trailing\nb}$\\k$"
    assert "trailing" not in expand_custom_macros(doc)


# ---------------------------------------------------------------------------
# Inlining a local .sty is required to pick up a paper's math macros, but
# conference styles also redefine LaTeX's own structural commands. Expanding
# those rewrites every \section{...} as \@startsection class internals and the
# splitter then sees no sections at all — 2608.27370 collapsed 68 -> 1.
# ---------------------------------------------------------------------------

CONFERENCE_STY = r"""
\newcommand{\section}{\@startsection {section}{1}{\z@}{-2.0ex}{1.0ex}{\bf}}
\newcommand{\subsection}{\@startsection{subsection}{2}{\z@}{-1.8ex}{0.8ex}{\bf}}
\newcommand{\maketitle}{\par\begingroup\def\@makefnmark{\hbox to 0pt{}}\endgroup}
\newcommand{\vect}[1]{\mathbf{#1}}
"""


def test_structural_commands_are_never_expanded():
    body = r"\section{Intro}text $\vect{x}$ here"
    out = expand_custom_macros(body, CONFERENCE_STY)
    assert r"\section{Intro}" in out
    assert "@startsection" not in out


def test_a_papers_own_macros_still_expand_from_the_same_sty():
    body = r"value $\vect{x}$"
    assert expand_custom_macros(body, CONFERENCE_STY) == r"value $\mathbf{x}$"


def test_maketitle_body_is_not_injected_into_the_prose():
    out = expand_custom_macros(r"\maketitle Some prose.", CONFERENCE_STY)
    assert "@makefnmark" not in out
    assert "Some prose." in out


def test_section_splitting_survives_a_conference_style():
    doc = (
        r"\section{Alpha}" + "\n" + "Alpha body long enough to clear the fifty character minimum.\n"
        + r"\section{Beta}" + "\n" + "Beta body long enough to clear the fifty character minimum.\n"
    )
    sections = parse_latex_sections(doc, CONFERENCE_STY)
    assert [s.title for s in sections] == ["Alpha", "Beta"]


def test_reserved_names_are_matched_without_the_backslash():
    # \cite must survive so citation handling downstream still sees it.
    sty = r"\newcommand{\cite}[1]{[#1]}"
    assert r"\cite{key}" in expand_custom_macros(r"see \cite{key}", sty)

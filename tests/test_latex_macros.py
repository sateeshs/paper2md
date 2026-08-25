"""Tests for argument-taking custom macro expansion in lib.latex_parse."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.latex_parse import _expand_custom_macros


def test_zero_arg_macro_expansion_unchanged():
    src = r"\newcommand{\R}{\mathbb{R}} \R is the reals."
    assert "\\mathbb{R}" in _expand_custom_macros(src)


def test_one_arg_macro_expands():
    src = r"\newcommand{\norm}[1]{\left\|#1\right\|} $\norm{x}$"
    out = _expand_custom_macros(src)
    assert "\\left\\|x\\right\\|" in out
    assert "\\norm" not in out.replace("\\newcommand", "")


def test_two_arg_macro_expands():
    src = r"\newcommand{\set}[2]{\{#1,#2\}} $\set{a}{b}$"
    out = _expand_custom_macros(src)
    assert "\\{a,b\\}" in out


def test_macro_used_inside_another_macro_body():
    src = (
        r"\newcommand{\bR}{\mathbf{R}}"
        r"\newcommand{\matR}[1]{\bR^{#1}}"
        r" $\matR{n}$"
    )
    out = _expand_custom_macros(src)
    assert "\\mathbf{R}^{n}" in out


def test_macro_as_argument_not_duplicated():
    src = (
        r"\newcommand{\al}{\alpha}"
        r"\newcommand{\norm}[1]{\left\|#1\right\|}"
        r" $\norm{\al}$"
    )
    out = _expand_custom_macros(src)
    # The argument \al is consumed by \norm and expanded inside its body
    # exactly once at the use site — never re-emitted at its original position.
    # (Definition-line text may still contain \alpha; only the use region counts.)
    usage_region = out[out.index("$"):]
    assert usage_region.count("\\alpha") == 1
    assert "\\left\\|\\alpha\\right\\|" in out

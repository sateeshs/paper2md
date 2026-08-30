"""Guard against catastrophic regex backtracking in LaTeX → text conversion.

A single 800-char context window containing an unbalanced `$` used to take
300+ seconds, because `(?:[^$\n]|\\.)` gave the regex engine two ways to consume
every escape sequence. One such window stalled the whole batch job.
"""
import time

from lib.latex_parse import _latex_to_text, _preprocess_for_text

# Unbalanced "$" followed by a run of backslash escapes — the pathological shape.
PATHOLOGICAL = "Combining this with $" + r"\mathbb{N} \gamma \in \mathfrak{d} " * 30

BUDGET_SECONDS = 2.0


def _elapsed(fn, *args):
    start = time.perf_counter()
    fn(*args)
    return time.perf_counter() - start


def test_latex_to_text_does_not_backtrack_on_unbalanced_dollar():
    assert _elapsed(_latex_to_text, PATHOLOGICAL) < BUDGET_SECONDS


def test_preprocess_does_not_backtrack_on_unbalanced_dollar():
    assert _elapsed(_preprocess_for_text, PATHOLOGICAL) < BUDGET_SECONDS


def test_cost_stays_linear_as_the_escape_run_grows():
    short = "$" + r"\mathbb{N} \gamma " * 20
    long = "$" + r"\mathbb{N} \gamma " * 40
    assert _elapsed(_latex_to_text, long) < BUDGET_SECONDS
    assert _elapsed(_latex_to_text, short) < BUDGET_SECONDS


def test_balanced_inline_math_is_still_preserved_verbatim():
    # \_ must stay escaped inside math (plain _ would become a subscript).
    out = _preprocess_for_text(r"text with $a \_ b$ inside and \_ outside")
    assert r"$a \_ b$" in out
    assert "and _ outside" in out

r"""Explanations quote the paper's macros too.

repair_macros.py expanded latex_expr but left the explanation JSON alone, so
a block whose equation correctly read "\mathcal{L}({\bm{\theta}})" still had
an explanation saying "$\loss(\vtheta)$" — an undefined control sequence that
KaTeX renders as a raw code span mid-sentence.
"""
import json

from repair_macros import expand_explanation_json

PREAMBLE = r"""
\newcommand{\vtheta}{{\bm{\theta}}}
\newcommand{\loss}{\mathcal{L}}
\newcommand{\vs}{{\bm{s}}}
\newcommand{\va}{{\bm{a}}}
"""


def test_expands_macros_inside_each_string_value():
    original = json.dumps({
        "what_it_computes": r"The left-hand side, $\loss(\vtheta)$, is the loss.",
        "symbol_meanings": r"$A(\vs^n,\va^n)$: the advantage.",
    })
    out = expand_explanation_json(original, PREAMBLE)
    assert out is not None
    parsed = json.loads(out)
    assert r"\mathcal{L}" in parsed["what_it_computes"]
    assert r"\loss" not in parsed["what_it_computes"]
    assert r"{\bm{s}}" in parsed["symbol_meanings"]
    assert r"\vs" not in parsed["symbol_meanings"]


def test_result_is_still_valid_json():
    original = json.dumps({"derivation": r"Substituting $\vtheta$ gives $\loss$."})
    out = expand_explanation_json(original, PREAMBLE)
    json.loads(out)  # must not raise


def test_returns_none_when_nothing_changes():
    """No macro to expand means no UPDATE should be issued."""
    original = json.dumps({"intuition": "Plain prose with no math at all."})
    assert expand_explanation_json(original, PREAMBLE) is None


def test_non_json_explanation_is_left_alone():
    """Older rows stored bare prose, not JSON — never corrupt them."""
    assert expand_explanation_json("just a sentence", PREAMBLE) is None


def test_nested_lists_and_dicts_are_handled():
    original = json.dumps({"prerequisites": [r"$\vtheta$ basics", r"$\loss$ theory"]})
    out = expand_explanation_json(original, PREAMBLE)
    assert out is not None
    assert json.loads(out)["prerequisites"][0].startswith("${\\bm{\\theta}}$")

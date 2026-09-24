"""Tests for lib/explanation_quality.py — rejecting degenerate LLM output.

These failures all parse as valid JSON, so without an explicit check they are
stored as real explanations and shown on the site. A block written with garbage
also looks "explained" and is never retried, so accepting one is worse than
recording a failure.
"""

from __future__ import annotations

import json

import pytest

from lib.explanation_quality import find_defect, is_usable


def good(**overrides) -> str:
    payload = {
        "what_it_computes": "The expected discounted return under policy pi.",
        "symbol_meanings": "V is the value function; gamma is the discount factor.",
        "intuition": "It sums future rewards, weighting later ones less.",
    }
    payload.update(overrides)
    return json.dumps(payload)


# ── accepting ──────────────────────────────────────────────────────────────

def test_a_real_explanation_is_usable():
    assert is_usable(good())
    assert find_defect(good()) is None


def test_extra_fields_are_fine():
    assert is_usable(good(proof_role="lemma", prerequisites="MDPs"))


def test_ordinary_repeated_words_are_not_a_repetition_loop():
    prose = "The value function is the expected return. " * 12
    assert is_usable(good(intuition=prose)), find_defect(good(intuition=prose))


# ── rejecting ──────────────────────────────────────────────────────────────

def test_empty_input_is_rejected():
    assert find_defect("") == "empty explanation"
    assert find_defect(None) == "empty explanation"


def test_unparseable_json_is_rejected():
    assert find_defect("{not json at all") == "unparseable JSON"


def test_non_object_json_is_rejected():
    assert "expected a JSON object" in find_defect('["a", "b"]')


def test_missing_required_field_is_rejected():
    payload = json.dumps({"intuition": "something"})
    assert "what_it_computes" in find_defect(payload)


def test_blank_required_field_is_rejected():
    assert "what_it_computes" in find_defect(good(what_it_computes="   "))


@pytest.mark.parametrize("placeholder", [
    "{what_it_computes text}",
    "{symbol_meanings}",
    "{intuition text}",
    "  {derivation text}  ",
])
def test_echoed_field_templates_are_rejected(placeholder):
    """The exact failure seen on 2412.05265: the model echoed the template."""
    defect = find_defect(good(symbol_meanings=placeholder))
    assert defect and "placeholder" in defect


def test_placeholder_in_the_required_field_is_rejected():
    assert find_defect(good(what_it_computes="{what_it_computes text}"))


def test_repetition_loop_is_rejected():
    """The failure behind the max_tokens=8000 truncation warnings."""
    loop = "for " * 300
    defect = find_defect(good(intuition=loop))
    assert defect and "repetition loop" in defect


def test_low_diversity_text_is_rejected():
    loop = ("in for the of " * 150)
    defect = find_defect(good(derivation=loop))
    assert defect and "repetition loop" in defect


def test_short_repetitive_text_is_not_flagged():
    """Below the length threshold, repetition is not evidence of a loop."""
    assert is_usable(good(intuition="very very very good"))

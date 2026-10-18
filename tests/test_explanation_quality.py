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


# ── candidate fetch pagination ─────────────────────────────────────────────

def test_fetch_all_pages_past_the_postgrest_row_cap():
    """PostgREST caps a response at 1000 rows; --force has no filter to shrink
    the set, so without paging it refetches the same rows forever."""
    from explain_math_only import _PAGE_SIZE, _fetch_all

    class FakeQuery:
        def __init__(self, total): self.total, self.calls = total, []
        def range(self, lo, hi):
            self.calls.append((lo, hi)); self._lo, self._hi = lo, hi; return self
        def execute(self):
            rows = [{"id": i} for i in range(self._lo, min(self._hi + 1, self.total))]
            return type("R", (), {"data": rows})()

    q = FakeQuery(2060)
    rows = _fetch_all(q)
    assert len(rows) == 2060
    assert q.calls[0] == (0, _PAGE_SIZE - 1)
    assert len(q.calls) == 3, "should page until a short page is returned"


def test_fetch_all_stops_on_a_single_short_page():
    from explain_math_only import _fetch_all

    class FakeQuery:
        def range(self, lo, hi): self._lo, self._hi = lo, hi; return self
        def execute(self):
            return type("R", (), {"data": [{"id": i} for i in range(5)]})()

    assert len(_fetch_all(FakeQuery())) == 5

"""MathExplainer must fall back when ChainOfThought overruns max_tokens.

Large display equations make the CoT response exceed max_tokens=8000; the
provider then returns an empty response and the block is stored with no
explanation. Retrying the same predictor is useless — DSPy caches the truncated
result and replays it instantly — so the retry must use a different predictor.
"""
from types import SimpleNamespace

import pytest

from lib.models import MathBlock


FIELDS = {
    "what_it_computes": "computes a thing",
    "symbol_meanings": "x: a symbol",
    "intuition": "the intuition",
    "derivation": "the derivation",
    "proof_role": "a lemma step",
    "prerequisites": "linear algebra",
    "mathematical_significance": "it matters",
}


def _block(expr: str = r"\begin{equation}x = 1\end{equation}", env: str = "equation") -> MathBlock:
    return MathBlock(order_idx=0, env_type=env, latex_expr=expr,
                     context_before="", context_after="")


@pytest.fixture
def explainer():
    from lib.dspy_modules import MathExplainer
    return MathExplainer()


def test_falls_back_to_terse_when_chain_of_thought_returns_empty(explainer, monkeypatch):
    calls: list[str] = []

    def fake_call(module, **kwargs):
        if module is explainer.explain:
            calls.append("cot")
            raise RuntimeError("The LM returned an empty or null response.")
        calls.append("terse")
        return SimpleNamespace(**FIELDS)

    monkeypatch.setattr("lib.dspy_modules._call_with_tracking", fake_call)
    out = explainer.explain_block(_block(), "Paper", "Section")

    assert calls == ["cot", "terse"]
    assert out.explanation and "computes a thing" in out.explanation


def test_terse_predictor_is_a_distinct_module(explainer):
    # Same module would hit the same DSPy cache entry and replay the failure.
    assert explainer.explain_terse is not explainer.explain


def test_no_fallback_when_chain_of_thought_succeeds(explainer, monkeypatch):
    calls: list[str] = []

    def fake_call(module, **kwargs):
        calls.append("cot" if module is explainer.explain else "terse")
        return SimpleNamespace(**FIELDS)

    monkeypatch.setattr("lib.dspy_modules._call_with_tracking", fake_call)
    out = explainer.explain_block(_block(), "Paper", "Section")

    assert calls == ["cot"]
    assert out.explanation


def test_block_returned_unchanged_when_both_predictors_fail(explainer, monkeypatch):
    def fake_call(module, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("lib.dspy_modules._call_with_tracking", fake_call)
    block = _block()
    out = explainer.explain_block(block, "Paper", "Section")

    assert out.explanation is None


def test_trivial_inline_block_calls_no_predictor(explainer, monkeypatch):
    def fake_call(module, **kwargs):
        raise AssertionError("should not be called for a trivial block")

    monkeypatch.setattr("lib.dspy_modules._call_with_tracking", fake_call)
    out = explainer.explain_block(_block("$n$", "inline"), "Paper", "Section")

    assert out.explanation is None

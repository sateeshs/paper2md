"""Tests for theorem-environment context tagging on math blocks."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.latex_parse import _build_math_blocks


BODY = (
    r"We now state the key bound."
    r"\begin{lemma}\label{lem:main}"
    r"Let $f$ be continuous. Then "
    r"\begin{equation} \int_0^1 f(x)\,dx \leq 1 \end{equation}"
    r"\end{lemma}"
    r"This completes the section with filler text to pass the length checks. " * 3
)


def test_equation_inside_lemma_gets_tagged_context():
    blocks = _build_math_blocks(BODY)
    eq = next(b for b in blocks if b.env_type == "equation")
    assert "[Inside lemma:" in eq.context_before
    assert "continuous" in eq.context_before


def test_equation_outside_theorem_env_untagged():
    body = r"Standalone discussion. " * 20 + r"\begin{equation} a+b=c \end{equation}"
    blocks = _build_math_blocks(body)
    eq = next(b for b in blocks if b.env_type == "equation")
    assert "[Inside" not in eq.context_before

"""DSPy modules: MathExplainer and PaperSummarizer.

Both use ChainOfThought — CoT is important for math reasoning quality
because the model needs to show its working before committing to an answer.

Usage:
    from lib.dspy_config import configure_dspy
    from lib.dspy_modules import MathExplainer, PaperSummarizer

    configure_dspy()
    explainer = MathExplainer()
    summarizer = PaperSummarizer()
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
import time

import dspy
from tqdm import tqdm

from lib.content_analysis import chunk_text_for_llm
from lib.dspy_config import (
    PROVIDER_CONFIG,
    increment_provider_count,
    is_provider_exhausted,
    rate_limit_sleep,
)
from lib.dspy_signatures import (
    ExplainAlgorithmBlock,
    ExplainMathBlock,

    ReduceToFinalSummary,
    SATTutor,
    SummarizeChunk,
)
from lib.models import AlgorithmBlock, MathBlock, Paper, Section


# ---------------------------------------------------------------------------
# Explanation post-processing — sanitise LLM output before storing
# ---------------------------------------------------------------------------

# Unicode Greek → LaTeX mapping (outside $...$ these break KaTeX)
_GREEK_MAP: dict[str, str] = {
    "α": r"\alpha", "β": r"\beta", "γ": r"\gamma", "δ": r"\delta",
    "ε": r"\varepsilon", "ζ": r"\zeta", "η": r"\eta", "θ": r"\theta",
    "ι": r"\iota", "κ": r"\kappa", "λ": r"\lambda", "μ": r"\mu",
    "ν": r"\nu", "ξ": r"\xi", "π": r"\pi", "ρ": r"\rho",
    "σ": r"\sigma", "τ": r"\tau", "υ": r"\upsilon", "φ": r"\varphi",
    "χ": r"\chi", "ψ": r"\psi", "ω": r"\omega",
    "Γ": r"\Gamma", "Δ": r"\Delta", "Θ": r"\Theta", "Λ": r"\Lambda",
    "Ξ": r"\Xi", "Π": r"\Pi", "Σ": r"\Sigma", "Φ": r"\Phi",
    "Ψ": r"\Psi", "Ω": r"\Omega",
    "∑": r"\sum", "∏": r"\prod", "∫": r"\int", "∞": r"\infty",
    "∈": r"\in", "∉": r"\notin", "⊂": r"\subset", "⊃": r"\supset",
    "≤": r"\leq", "≥": r"\geq", "≠": r"\neq", "≈": r"\approx",
    "→": r"\to", "←": r"\leftarrow", "↔": r"\leftrightarrow",
    "⊤": r"\top", "⊥": r"\bot", "∀": r"\forall", "∃": r"\exists",
    "∇": r"\nabla", "∂": r"\partial", "×": r"\times", "⊗": r"\otimes",
    "⊕": r"\oplus", "·": r"\cdot",
}

# Build a single regex that matches any bare Unicode math symbol NOT already inside $...$
_GREEK_CHARS_RE = re.compile(
    "|".join(re.escape(ch) for ch in _GREEK_MAP)
)

# Patterns that signal the LLM echoed a DSPy field description instead of generating content
_FIELD_DESC_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\s*:?\s*\d[\d-]*\s*sentences?\s*(max|min)?\.?\s*", re.I),
    re.compile(r"^\s*list\s+the\s+\d+\s+most\s+important", re.I),
    re.compile(r"^\s*comma[- ]separated\s+list\s+of", re.I),
    re.compile(r"^\s*1-\d+\s+sentences?\.\s*", re.I),
    re.compile(r"^\s*what\s+does\s+this\s+expression\s+compute", re.I),
    re.compile(r"^\s*briefly\s+walk\s+through", re.I),
    re.compile(r"^\s*explain\s+the\s+intuition\s+in\s+plain", re.I),
    re.compile(r"^\s*what\s+logical\s+role", re.I),
    re.compile(r"^\s*why\s+does\s+this\s+expression\s+matter", re.I),
)

# Quadruple-escaped backslashes (\\\\) that appear in LLM output
_QUAD_BACKSLASH_RE = re.compile(r"\\\\\\\\")
# Double-escaped that should be single (but not in \\n, \\t, etc.)
_DOUBLE_BACKSLASH_RE = re.compile(r"\\\\(?=[a-zA-Z{])")


def _wrap_bare_greek(text: str) -> str:
    """Replace Unicode Greek/math symbols outside $...$ with $\\symbol$."""
    # Split text on $...$ spans to avoid touching content already in math mode
    parts = re.split(r"(\$[^$]+\$)", text)
    result: list[str] = []
    for i, part in enumerate(parts):
        if i % 2 == 1:
            # Inside $...$ — leave as-is
            result.append(part)
        else:
            # Outside math delimiters — wrap bare Greek
            result.append(
                _GREEK_CHARS_RE.sub(
                    lambda m: f"${_GREEK_MAP[m.group()]}$",
                    part,
                )
            )
    return "".join(result)


def _fix_escaped_backslashes(text: str) -> str:
    """Fix over-escaped LaTeX backslashes from LLM output."""
    text = _QUAD_BACKSLASH_RE.sub(r"\\\\", text)
    return text


def _is_echoed_description(text: str) -> bool:
    """Return True if text looks like a parroted DSPy field description."""
    return any(p.search(text) for p in _FIELD_DESC_PATTERNS)


def _sanitize_explanation_field(value: str) -> str:
    """Clean a single explanation field value from LLM output."""
    if not value or not value.strip():
        return value

    # Strip echoed field descriptions
    if _is_echoed_description(value):
        # Try to salvage: the LLM sometimes prefixes the description then adds real content
        # e.g. ": 2 sentences max. This formula defines..."
        cleaned = re.sub(
            r"^\s*:?\s*\d[\d-]*\s*sentences?\s*(max|min)?\.?\s*",
            "",
            value,
            flags=re.I,
        ).strip()
        if cleaned and not _is_echoed_description(cleaned):
            value = cleaned
        else:
            return ""

    value = _wrap_bare_greek(value)
    value = _fix_escaped_backslashes(value)
    return value


def _sanitize_explanation(fields: dict[str, str]) -> dict[str, str]:
    """Post-process all explanation fields from LLM output."""
    return {k: _sanitize_explanation_field(v) for k, v in fields.items()}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _active_provider() -> str:
    """Return the name of the currently configured primary DSPy provider."""
    lm = dspy.settings.lm
    if lm is None:
        return "unknown"
    model: str = getattr(lm, "model", "") or ""
    for name in PROVIDER_CONFIG:
        if name in model.lower():
            return name
    return "unknown"


def _call_with_tracking(module: dspy.Module, **kwargs) -> dspy.Prediction:
    """Call a DSPy module, track usage count, and sleep for rate limiting.
    Retries up to 4 times on rate limit errors with exponential backoff.
    """
    provider = _active_provider()
    max_retries = 4
    for attempt in range(max_retries):
        try:
            result = module(**kwargs)
            increment_provider_count(provider)
            rate_limit_sleep(provider)
            return result
        except Exception as e:
            msg = str(e).lower()
            is_rate_limit = "ratelimit" in msg or "rate_limit" in msg or "429" in msg or "rate limit" in msg
            if is_rate_limit and attempt < max_retries - 1:
                # Use retry_after from response if available, else exponential backoff
                import re
                match = re.search(r'"retry_after_seconds"\s*:\s*(\d+)', str(e))
                wait = int(match.group(1)) + 2 if match else 15 * (2 ** attempt)
                tqdm.write(f"[WARN] Rate limited (attempt {attempt+1}/{max_retries}), waiting {wait}s…")
                time.sleep(wait)
            else:
                raise


# ---------------------------------------------------------------------------
# MathExplainer
# ---------------------------------------------------------------------------

class MathExplainer(dspy.Module):
    """Explain every math block in a paper section using ExplainMathBlock signature.

    Applies per-call rate limiting and records which model generated each explanation.
    Skips inline blocks that are too trivial (single variable, ≤ 5 chars).
    """

    # Minimum LaTeX expression length to bother explaining
    _MIN_EXPR_LEN = 6

    def __init__(self) -> None:
        super().__init__()
        self.explain = dspy.ChainOfThought(ExplainMathBlock)

    def _should_skip(self, block: MathBlock) -> bool:
        """Skip trivially short inline expressions like $n$, $x$, $i$."""
        if block.env_type == "inline" and len(block.latex_expr.strip()) < self._MIN_EXPR_LEN:
            return True
        return False

    def explain_block(
        self,
        block: MathBlock,
        paper_title: str,
        section_title: str,
    ) -> MathBlock:
        """Return a new MathBlock with explanation filled in."""
        if self._should_skip(block):
            return block

        try:
            pred = _call_with_tracking(
                self.explain,
                paper_title=paper_title,
                section_title=section_title or "Unknown Section",
                context_before=block.context_before or "",
                latex_expr=block.latex_expr,
                context_after=block.context_after or "",
                paper_type=block.paper_type,
            )
            raw_fields = {
                "what_it_computes":        pred.what_it_computes,
                "symbol_meanings":         pred.symbol_meanings,
                "intuition":               pred.intuition,
                "derivation":              pred.derivation,
                "proof_role":              pred.proof_role,
                "prerequisites":           pred.prerequisites,
                "mathematical_significance": pred.mathematical_significance,
            }
            explanation = json.dumps(
                _sanitize_explanation(raw_fields),
                ensure_ascii=False,
            )
            return dataclasses.replace(
                block,
                explanation=explanation,
                explanation_model=_active_provider(),
            )
        except Exception as e:
            # Non-fatal: log and continue without explanation
            tqdm.write(f"[WARN] MathExplainer failed for block {block.order_idx}: {e}")
            return block

    def forward(
        self,
        paper: Paper,
        max_blocks: int | None = None,
        max_blocks_per_section: int | None = None,
    ) -> Paper:
        """Return Paper with explanations filled into all math blocks across all sections.

        Args:
            paper:                  Paper object with sections + math_blocks already populated.
            max_blocks:             Global cap on total blocks to explain (cost control).
                                    Prioritises named environments (equation/align) over inline.
            max_blocks_per_section: If set, take at most this many named-env blocks + this many
                                    inline blocks per section before applying the global cap.
                                    Ensures every section gets some coverage on large papers.
        """
        limit = max_blocks or int(os.environ.get("PAPER2MD_MAX_MATH_BLOCKS", 50))
        per_section = max_blocks_per_section or (
            int(os.environ.get("PAPER2MD_MAX_MATH_BLOCKS_PER_SECTION", 0)) or None
        )

        # Collect (section_idx, block) pairs sorted by priority
        # Named envs first, then inline
        prioritised: list[tuple[int, MathBlock]] = []
        inline_queue: list[tuple[int, MathBlock]] = []

        for s_idx, section in enumerate(paper.sections):
            if per_section is not None:
                # Section-aware: take up to per_section named-env + per_section inline
                named = [b for b in section.math_blocks if b.env_type != "inline"][:per_section]
                inline = [b for b in section.math_blocks if b.env_type == "inline"][:per_section]
                prioritised.extend((s_idx, b) for b in named)
                inline_queue.extend((s_idx, b) for b in inline)
            else:
                for block in section.math_blocks:
                    if block.env_type == "inline":
                        inline_queue.append((s_idx, block))
                    else:
                        prioritised.append((s_idx, block))

        candidates = (prioritised + inline_queue)[:limit]
        total = len(candidates)

        if total == 0:
            return paper

        # Map: section_idx → list of explained blocks (preserve order)
        explained_map: dict[int, dict[int, MathBlock]] = {}

        with tqdm(total=total, desc="Explaining math", unit="block") as pbar:
            for s_idx, block in candidates:
                section = paper.sections[s_idx]
                explained = self.explain_block(block, paper.title, section.title)
                explained_map.setdefault(s_idx, {})[block.order_idx] = explained
                pbar.update(1)

        # Rebuild sections with explained blocks substituted in
        new_sections: list[Section] = []
        for s_idx, section in enumerate(paper.sections):
            if s_idx not in explained_map:
                new_sections.append(section)
                continue
            overrides = explained_map[s_idx]
            new_blocks = tuple(
                overrides.get(b.order_idx, b) for b in section.math_blocks
            )
            new_sections.append(dataclasses.replace(section, math_blocks=new_blocks))

        return dataclasses.replace(paper, sections=tuple(new_sections))


# ---------------------------------------------------------------------------
# AlgorithmExplainer
# ---------------------------------------------------------------------------

class AlgorithmExplainer(dspy.Module):
    """Explain every algorithm block in a paper using ExplainAlgorithmBlock signature.

    Capped at PAPER2MD_MAX_ALGORITHM_BLOCKS (default 10) since pseudocode
    explanations are LLM-expensive and most papers have 1-3 algorithms.
    """

    def __init__(self) -> None:
        super().__init__()
        self.explain = dspy.ChainOfThought(ExplainAlgorithmBlock)

    def explain_block(
        self,
        block: AlgorithmBlock,
        paper_title: str,
        section_title: str,
    ) -> AlgorithmBlock:
        """Return a new AlgorithmBlock with explanation filled in."""
        try:
            pred = _call_with_tracking(
                self.explain,
                paper_title=paper_title,
                section_title=section_title or "Unknown Section",
                algorithm_caption=block.caption or "Unnamed Algorithm",
                pseudocode_text=block.pseudocode_text or block.raw_pseudocode[:1000],
                context_before=block.context_before or "",
                context_after=block.context_after or "",
            )
            explanation = json.dumps({
                "purpose":        pred.purpose,
                "inputs_outputs": pred.inputs_outputs,
                "step_by_step":   pred.step_by_step,
                "complexity":     pred.complexity,
                "key_insight":    pred.key_insight,
                "prerequisites":  pred.prerequisites,
            }, ensure_ascii=False)
            return dataclasses.replace(
                block,
                explanation=explanation,
                explanation_model=_active_provider(),
            )
        except Exception as e:
            tqdm.write(f"[WARN] AlgorithmExplainer failed for block {block.order_idx}: {e}")
            return block

    def forward(self, paper: Paper, max_blocks: int | None = None) -> Paper:
        """Return Paper with explanations filled into all algorithm blocks across sections."""
        limit = max_blocks or int(os.environ.get("PAPER2MD_MAX_ALGORITHM_BLOCKS", 10))

        # Collect (section_idx, block) pairs
        candidates: list[tuple[int, AlgorithmBlock]] = []
        for s_idx, section in enumerate(paper.sections):
            for block in section.algorithm_blocks:
                candidates.append((s_idx, block))
                if len(candidates) >= limit:
                    break
            if len(candidates) >= limit:
                break

        total = len(candidates)
        if total == 0:
            return paper

        explained_map: dict[int, dict[int, AlgorithmBlock]] = {}

        with tqdm(total=total, desc="Explaining algorithms", unit="block") as pbar:
            for s_idx, block in candidates:
                section = paper.sections[s_idx]
                explained = self.explain_block(block, paper.title, section.title)
                explained_map.setdefault(s_idx, {})[block.order_idx] = explained
                pbar.update(1)

        new_sections: list[Section] = []
        for s_idx, section in enumerate(paper.sections):
            if s_idx not in explained_map:
                new_sections.append(section)
                continue
            overrides = explained_map[s_idx]
            new_blocks = tuple(
                overrides.get(b.order_idx, b) for b in section.algorithm_blocks
            )
            new_sections.append(dataclasses.replace(section, algorithm_blocks=new_blocks))

        return dataclasses.replace(paper, sections=tuple(new_sections))


# ---------------------------------------------------------------------------
# PaperSummarizer
# ---------------------------------------------------------------------------

class PaperSummarizer(dspy.Module):
    """Map-reduce paper summarization using DSPy ChainOfThought.

    Replaces lib/summarization.py. Uses the same chunk_text_for_llm()
    utility so chunking behaviour is unchanged.
    """

    def __init__(self) -> None:
        super().__init__()
        self.summarize_chunk = dspy.ChainOfThought(SummarizeChunk)
        self.reduce = dspy.ChainOfThought(ReduceToFinalSummary)

    def forward(
        self,
        paper: Paper,
        max_chars: int = 12_000,
        max_chunks: int = 8,
    ) -> Paper:
        """Return Paper with summary_md populated.

        Args:
            paper:      Paper with text extracted (pdf or arxiv).
            max_chars:  Max chars per chunk passed to chunk_text_for_llm.
            max_chunks: Max chunks to process.
        """
        if not paper.text:
            return paper

        chunks = chunk_text_for_llm(paper.text, max_chars=max_chars)[:max_chunks]
        chunk_summaries: list[str] = []

        for idx, chunk in enumerate(
            tqdm(chunks, desc=f"  Summarising {paper.title[:40]}", leave=False),
            start=1,
        ):
            try:
                pred = _call_with_tracking(
                    self.summarize_chunk,
                    paper_title=paper.title,
                    chunk_index=f"{idx}/{len(chunks)}",
                    chunk_text=chunk,
                )
                chunk_summaries.append(pred.summary_bullets)
            except Exception as e:
                tqdm.write(f"[WARN] Chunk {idx} summarisation failed: {e}")

        if not chunk_summaries:
            return paper

        try:
            final = _call_with_tracking(
                self.reduce,
                paper_title=paper.title,
                chunk_summaries="\n\n".join(chunk_summaries),
            )
        except Exception as e:
            tqdm.write(f"[WARN] Reduce step failed for {paper.title[:40]}: {e}")
            return paper

        summary_md = _format_summary(final)
        return dataclasses.replace(paper, summary_md=summary_md)


# ---------------------------------------------------------------------------
# SATTutorModule
# ---------------------------------------------------------------------------

class SATTutorModule(dspy.Module):
    """Run the SATTutor signature for a single SAT question session.

    Returns a dict with all 7 response fields ready to write to sat_sessions.
    """

    def __init__(self) -> None:
        super().__init__()
        self.tutor = dspy.ChainOfThought(SATTutor)

    def forward(self, question: str, subject: str, user_context: str = "") -> dict:
        """Return dict with sat_sessions response fields.

        Raises on unrecoverable LLM error so sat_tutor.py can mark session as error.
        """
        pred = _call_with_tracking(
            self.tutor,
            question=question,
            subject=subject,
            user_context=user_context or "",
        )
        return {
            "explanation":      pred.explanation,
            "step_by_step":     pred.step_by_step,
            "key_concepts":     pred.key_concepts,
            "hints":            pred.hints,
            "common_mistakes":  pred.common_mistakes,
            "sat_strategy":     pred.sat_strategy,
            "answer":           pred.answer,
            "agent_model":      _active_provider(),
        }


def _format_summary(pred: dspy.Prediction) -> str:
    """Render a ReduceToFinalSummary prediction as the existing markdown format."""
    parts = [
        f"### TL;DR\n{pred.tldr}",
        f"### Problem\n{pred.problem}",
        f"### Approach\n{pred.approach}",
        f"### Results\n{pred.results}",
        f"### Practical Takeaways\n{pred.takeaways}",
        f"### Limitations / Open Questions\n{pred.limitations}",
    ]
    return "\n\n".join(parts)

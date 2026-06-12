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
from lib.dspy_signatures import ExplainMathBlock, ReduceToFinalSummary, SATTutor, SummarizeChunk
from lib.models import MathBlock, Paper, Section


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
            explanation = json.dumps({
                "what_it_computes":        pred.what_it_computes,
                "symbol_meanings":         pred.symbol_meanings,
                "intuition":               pred.intuition,
                "derivation":              pred.derivation,
                "proof_role":              pred.proof_role,
                "prerequisites":           pred.prerequisites,
                "mathematical_significance": pred.mathematical_significance,
            }, ensure_ascii=False)
            return dataclasses.replace(
                block,
                explanation=explanation,
                explanation_model=_active_provider(),
            )
        except Exception as e:
            # Non-fatal: log and continue without explanation
            tqdm.write(f"[WARN] MathExplainer failed for block {block.order_idx}: {e}")
            return block

    def forward(self, paper: Paper, max_blocks: int | None = None) -> Paper:
        """Return Paper with explanations filled into all math blocks across all sections.

        Args:
            paper:      Paper object with sections + math_blocks already populated.
            max_blocks: Cap on total blocks to explain (cost control).
                        Prioritises named environments (equation/align) over inline.
        """
        limit = max_blocks or int(os.environ.get("PAPER2MD_MAX_MATH_BLOCKS", 50))

        # Collect (section_idx, block) pairs sorted by priority
        # Named envs first, then inline
        prioritised: list[tuple[int, MathBlock]] = []
        inline_queue: list[tuple[int, MathBlock]] = []

        for s_idx, section in enumerate(paper.sections):
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

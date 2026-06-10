"""DSPy typed signatures for all LLM calls in paper2md.

Three signatures cover the full pipeline:
  ExplainMathBlock      — per math block: structured 4-field explanation
  SummarizeChunk        — map step: summarise one text chunk of a paper
  ReduceToFinalSummary  — reduce step: combine chunk bullets into final markdown
"""

from __future__ import annotations

import dspy


class ExplainMathBlock(dspy.Signature):
    """Explain a mathematical expression from a research paper in thorough, plain English.

    The audience is a software engineer with ML knowledge who wants to deeply understand
    each formula — not just what it says but what it *means* and how it *works*.

    Write each field as clear, flowing prose. No bullet points. No LaTeX-only answers —
    always translate notation into words.

    CRITICAL — math formatting rules (violating these breaks rendering):
    - ALWAYS wrap every math symbol, variable, subscript, or expression in $...$
    - NEVER use Unicode Greek letters (α β γ σ θ μ φ ψ etc.) outside of $...$
    - NEVER write LaTeX subscripts like _theta or _{i} outside of $...$
    - Correct: "$\\sigma_\\theta(q, u_{<i})$" — Wrong: "σ_θ(q, u_{<i})"
    - Correct: "$u_{<i}$" — Wrong: "u_{<i}"
    - Correct: "$F_\\theta$" — Wrong: "F_θ"
    - Correct: "$\\theta$ (theta) are the model weights" — Wrong: "θ are the model weights"
    """

    paper_title: str = dspy.InputField(
        desc="Full title of the research paper"
    )
    section_title: str = dspy.InputField(
        desc="Title of the section containing this expression"
    )
    context_before: str = dspy.InputField(
        desc="Plain text immediately before the formula"
    )
    latex_expr: str = dspy.InputField(
        desc="The LaTeX math expression to explain"
    )
    context_after: str = dspy.InputField(
        desc="Plain text immediately after the formula"
    )

    what_it_computes: str = dspy.OutputField(
        desc="In 2-4 plain-English sentences, describe what this expression computes or defines. "
             "State clearly what the left-hand side (LHS) represents and what the right-hand side "
             "(RHS) says about it. Avoid saying 'this equation' — be specific about the quantity."
    )
    symbol_meanings: str = dspy.OutputField(
        desc="List every symbol, variable, subscript, superscript, and operator in this expression. "
             "For each one give: (1) its full name or acronym expansion in plain English, "
             "(2) what it represents in this paper specifically. "
             "Examples of the level of detail expected: "
             "'$\\mathcal{L}_{\\text{flow}}$ (script L subscript flow) is the normalizing flow loss — "
             "it measures how well the flow model can reconstruct the original CoT trace'; "
             "'subscript $1:K$ means a sequence spanning positions 1 through K, i.e. the entire sequence'; "
             "'$\\theta$ (theta) are the trainable parameters of the neural network (both NF head and LM head)'. "
             "Do not skip any symbol, even single-letter ones or subscripts."
    )
    derivation: str = dspy.OutputField(
        desc="Walk through what happens when you substitute the definitions into both sides of the equation. "
             "Show explicitly: LHS = [what LHS means in words] = RHS = [what each RHS term expands to]. "
             "For example: 'The left side, $u_{1:K}$ (the continuous thought sequence), equals $F_\\theta(e_{1:K}; q)$, "
             "which means: apply the normalizing flow $F$ (parameterised by $\\theta$) to the discrete CoT trace "
             "$e_{1:K}$, conditioned on the prompt $q$. So concretely: take the token-level reasoning trace, "
             "feed it through a stack of causal affine flows, and out comes a continuous latent sequence in "
             "embedding space.' Be this concrete for every formula."
    )
    intuition: str = dspy.OutputField(
        desc="In 3-5 sentences, explain the intuition behind this expression in plain English — "
             "no math jargon. Imagine explaining it to a curious senior engineer who has never seen "
             "this paper. Use analogies if helpful. Focus on *why* the formula is structured this way, "
             "not just what it says."
    )
    paper_relevance: str = dspy.OutputField(
        desc="In 2-3 sentences, explain why this specific expression is central to this paper's contribution. "
             "Connect it to the paper's main idea and explain what breaks if you remove or change it."
    )


class SummarizeChunk(dspy.Signature):
    """Summarise one chunk of an ML/RecSys research paper for an engineering audience.

    Focus on: problem being solved, key methods or algorithms introduced,
    concrete claims or results, and any stated assumptions or limitations.
    Return 6-10 tightly written bullet points. Each bullet must be self-contained.
    """

    paper_title: str = dspy.InputField(
        desc="Full title of the research paper"
    )
    chunk_index: str = dspy.InputField(
        desc="Position of this chunk, e.g. '2/5'"
    )
    chunk_text: str = dspy.InputField(
        desc="Raw text of this chunk of the paper"
    )

    summary_bullets: str = dspy.OutputField(
        desc="6-10 bullet points (each starting with '- ') summarising this chunk. "
             "Include numbers/metrics where stated."
    )


class ReduceToFinalSummary(dspy.Signature):
    """Combine per-chunk bullet summaries into a final structured paper summary
    for engineers who want to quickly assess if a paper is relevant to their work.

    Output exactly the six fields below. Use plain prose (no nested bullets).
    Prefer concrete numbers from the chunks wherever available.
    If something cannot be determined from the summaries, write 'Unclear from text'.
    """

    paper_title: str = dspy.InputField(
        desc="Full title of the research paper"
    )
    chunk_summaries: str = dspy.InputField(
        desc="All per-chunk bullet summaries joined with double newlines"
    )

    tldr: str = dspy.OutputField(
        desc="Exactly 3 bullet points (each starting with '- ') giving the highest-signal takeaways"
    )
    problem: str = dspy.OutputField(
        desc="The core problem or gap this paper addresses. 2-3 sentences."
    )
    approach: str = dspy.OutputField(
        desc="The method or architecture proposed. Include key design choices."
    )
    results: str = dspy.OutputField(
        desc="Key results with concrete metrics and benchmark names where available."
    )
    takeaways: str = dspy.OutputField(
        desc="Practical engineering takeaways: what you could borrow or implement."
    )
    limitations: str = dspy.OutputField(
        desc="Stated or apparent limitations and open questions."
    )

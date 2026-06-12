"""DSPy typed signatures for all LLM calls in paper2md.

Four signatures cover the full pipeline:
  ExplainMathBlock      — per math block: structured explanation
  SummarizeChunk        — map step: summarise one text chunk of a paper
  ReduceToFinalSummary  — reduce step: combine chunk bullets into final markdown
  SATTutor              — SAT question analysis with step-by-step tutoring
"""

from __future__ import annotations

import dspy


class ExplainMathBlock(dspy.Signature):
    """Explain a mathematical expression found in an academic document in thorough, plain English.

    Adapt your explanation style to the document type provided in `paper_type`:
    - research_paper: audience is an engineer or researcher; stress what is novel,
      what the expression contributes, and how it connects to the paper's main idea.
    - textbook / lecture_notes: audience is a student; stress pedagogical clarity,
      prerequisite scaffolding, and how this expression fits the learning arc.

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
    paper_type: str = dspy.InputField(
        desc="Type of document: 'research_paper', 'textbook', or 'lecture_notes'. "
             "Adjust explanation depth and framing accordingly."
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
             "no math jargon. Imagine explaining it to a curious person who has never seen this material. "
             "Use analogies if helpful. Focus on *why* the formula is structured this way, not just what it says. "
             "Where the expression has a geometric or visual interpretation (e.g. it describes a distance, "
             "a projection, a rotation, an area, or a boundary), explicitly describe that geometric picture."
    )
    proof_role: str = dspy.OutputField(
        desc="In 1-3 sentences, describe the logical role this expression plays within its proof or derivation. "
             "Is it an intermediate lemma, a key substitution, a boundary condition, a definition being introduced, "
             "or the conclusion of the argument? "
             "If the expression is not part of a proof, write: "
             "'Not part of a proof — this is a [definition / model equation / stated result]'."
    )
    prerequisites: str = dspy.OutputField(
        desc="In 2-4 sentences, list the mathematical concepts and definitions a reader must already know "
             "to understand this expression. Be specific: name the concepts "
             "(e.g. 'the Radon–Nikodym theorem', 'basic measure theory', 'the chain rule for matrix calculus') "
             "rather than vague categories. "
             "For research_paper documents, also note any paper-specific notation introduced earlier "
             "that this expression builds on."
    )
    mathematical_significance: str = dspy.OutputField(
        desc="In 2-3 sentences, explain the mathematical or conceptual significance of this expression. "
             "For research papers: connect it to the paper's core contribution and explain what breaks "
             "if you remove or change it. "
             "For textbooks/lecture notes: explain what mathematical insight this expression crystallises "
             "and why it is a milestone in the exposition."
    )


class SATTutor(dspy.Signature):
    """You are an expert SAT tutor with deep knowledge of College Board test design.

    A student has pasted an SAT question and optional extra context. Your job is to:
    1. Identify the exact SAT concept or skill being tested.
    2. Solve the problem step-by-step with full working shown.
    3. Give three progressive hints (from gentle to nearly giving it away).
    4. Flag the most common mistake students make on this type of question.
    5. Share a concise SAT strategy (pacing, elimination tricks, key formulas).
    6. State the correct answer with a clear justification.

    Subject-specific guidance:
    - math: Show all algebraic steps. Wrap every math expression in $...$. Never use
      Unicode math symbols outside of $...$. Name the formula/rule used at each step.
    - english: Quote the specific line or phrase from the passage that justifies the answer.
      Explain why each wrong answer choice fails.
    - reading: Identify the evidence in the text. Explain what makes the best answer
      "most supported" and why alternatives are too extreme or off-topic.

    Tone: encouraging, clear, student-friendly. Assume the student is working hard but
    may have gaps. Never just state the answer — always teach.
    """

    question: str = dspy.InputField(
        desc="The full SAT question text, including any answer choices (A/B/C/D)"
    )
    subject: str = dspy.InputField(
        desc="SAT section: 'math', 'english' (Writing and Language), or 'reading'"
    )
    user_context: str = dspy.InputField(
        desc="Optional extra context from the student — passage text, what they tried, "
             "which answer they chose, or what's confusing them. May be empty."
    )

    explanation: str = dspy.OutputField(
        desc="2-4 sentences explaining the core SAT concept or skill this question tests. "
             "Name the specific concept (e.g. 'linear systems of equations', "
             "'subject-verb agreement', 'identifying the author's claim'). "
             "Explain why College Board includes this skill on the SAT."
    )
    step_by_step: str = dspy.OutputField(
        desc="A numbered, step-by-step solution. Each step must state: "
             "(1) what you are doing and why, (2) the calculation or reasoning, "
             "(3) the result. For math: show all algebra. "
             "For reading/english: quote the key passage evidence at each step. "
             "End with a clear statement of the final answer."
    )
    key_concepts: str = dspy.OutputField(
        desc="Comma-separated list of 3-6 SAT concepts or skills this question tests. "
             "Be specific: e.g. 'linear equations, substitution method, systems with no solution' "
             "rather than just 'algebra'. These help the student know what to review."
    )
    hints: str = dspy.OutputField(
        desc="A JSON array of exactly 3 strings: progressive hints from subtle to near-answer. "
             "Hint 1: a gentle nudge toward the right approach (no spoilers). "
             "Hint 2: the key insight that unlocks the problem. "
             "Hint 3: almost the full solution — one step away from the answer. "
             'Format: ["Hint 1 text", "Hint 2 text", "Hint 3 text"]. '
             "Valid JSON only — no trailing commas."
    )
    common_mistakes: str = dspy.OutputField(
        desc="2-3 sentences describing the most frequent errors students make on this "
             "specific question or question type. Include why the wrong answer choices "
             "are tempting (the 'trap' answers). This helps the student learn from others' errors."
    )
    sat_strategy: str = dspy.OutputField(
        desc="1-3 sentences of concrete SAT test strategy for this question type: "
             "time management, process of elimination tips, when to plug in numbers, "
             "key formulas to memorise, or how to quickly identify the question type. "
             "Be actionable — the student should be able to apply this immediately."
    )
    answer: str = dspy.OutputField(
        desc="State the correct answer choice (e.g. 'Answer: C') followed by 2-3 sentences "
             "explaining exactly why it is correct and why each incorrect choice is wrong. "
             "For math: verify numerically if possible."
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

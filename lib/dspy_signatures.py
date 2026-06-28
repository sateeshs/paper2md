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
        desc="2 sentences max. What does this expression compute or define? "
             "Name the quantity on the LHS and summarise what the RHS says about it."
    )
    symbol_meanings: str = dspy.OutputField(
        desc="List the 5 most important symbols/operators (skip trivial ones like $i$, $n$). "
             "For each: symbol in $...$, plain-English name, role in this paper. One line per symbol."
    )
    derivation: str = dspy.OutputField(
        desc="2-3 sentences. Briefly walk through what each side of the expression expands to "
             "when you substitute the definitions. Be concrete but concise."
    )
    intuition: str = dspy.OutputField(
        desc="2-3 sentences. Explain the intuition in plain English with no jargon. "
             "Use an analogy or geometric picture if helpful."
    )
    proof_role: str = dspy.OutputField(
        desc="1-2 sentences. What logical role does this play in its proof/derivation? "
             "If not part of a proof, write: 'Not part of a proof — this is a [definition/result]'."
    )
    prerequisites: str = dspy.OutputField(
        desc="Comma-separated list of specific prerequisite concepts. "
             "Example: 'measure theory, Radon-Nikodym theorem, matrix calculus'. "
             "Write 'none' if no specific prerequisites beyond standard undergrad math."
    )
    mathematical_significance: str = dspy.OutputField(
        desc="1-2 sentences. Why does this expression matter? "
             "For research papers: link to the core contribution. "
             "For textbooks: what insight does it crystallise?"
    )


class ExplainAlgorithmBlock(dspy.Signature):
    """Explain a pseudocode algorithm found in an academic paper in clear, plain English.

    The pseudocode may use LaTeX algorithmic commands (\\State, \\If, \\For, \\While,
    \\Procedure, \\Return, etc.) or algorithm2e commands (\\KwIn, \\KwOut, \\ForEach).
    Treat these as structured control flow — not as LaTeX artifacts.

    Write each field as clear, flowing prose. No bullet points inside fields.
    When referencing variable names or expressions from the pseudocode, wrap them
    in backticks (e.g. `x`, `best_score`).

    CRITICAL — math formatting rules:
    - Wrap every math expression in $...$
    - NEVER use Unicode Greek letters outside of $...$
    """

    paper_title: str = dspy.InputField(desc="Full title of the research paper")
    section_title: str = dspy.InputField(desc="Title of the section containing this algorithm")
    algorithm_caption: str = dspy.InputField(
        desc="The \\caption{} text of the algorithm float, or 'Unnamed Algorithm' if absent"
    )
    pseudocode_text: str = dspy.InputField(
        desc="Plain-text pseudocode with LaTeX command prefixes stripped"
    )
    context_before: str = dspy.InputField(desc="Prose immediately before the algorithm block")
    context_after: str = dspy.InputField(desc="Prose immediately after the algorithm block")

    purpose: str = dspy.OutputField(
        desc="2-3 sentences describing what problem this algorithm solves in the context of the paper. "
             "Be specific about what it computes and why it is needed."
    )
    inputs_outputs: str = dspy.OutputField(
        desc="Describe what the algorithm takes as input and what it produces as output. "
             "Name the key variables. If complexity is stated or obvious, include it here."
    )
    step_by_step: str = dspy.OutputField(
        desc="A plain-English walkthrough of each major step, loop, or branch in the algorithm. "
             "Describe what each major block does and why. Keep it concrete and sequential."
    )
    complexity: str = dspy.OutputField(
        desc="Time and/or space complexity if stated in the paper or directly derivable from the pseudocode. "
             "Write 'Not stated' if neither is available."
    )
    key_insight: str = dspy.OutputField(
        desc="In 1-3 sentences, describe the core algorithmic idea or design choice that makes this "
             "algorithm work. For example: 'This is a greedy sweep because...', "
             "'The key trick is that by sorting first, each lookup becomes O(1)...'"
    )
    prerequisites: str = dspy.OutputField(
        desc="List the algorithmic concepts, data structures, or prior paper-specific notation "
             "a reader must already understand to follow this algorithm."
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

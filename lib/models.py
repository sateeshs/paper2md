"""Data models for paper2md."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class MathBlock:
    """A single mathematical expression extracted from a paper section."""
    order_idx: int
    env_type: str          # equation | align | gather | multline | cases | display | inline
    latex_expr: str
    context_before: str    # up to 800 chars for named envs, 300 for display/inline
    context_after: str     # up to 800 chars for named envs, 300 for display/inline
    explanation: str | None = None
    explanation_model: str | None = None  # e.g. "gemini-2.0-flash"
    paper_type: str = "research_paper"    # "research_paper" | "textbook" | "lecture_notes"


@dataclass(frozen=True)
class AlgorithmBlock:
    """A single algorithm/pseudocode block extracted from a paper section."""
    order_idx: int
    caption: str | None          # text from \caption{} inside the algorithm float
    raw_pseudocode: str          # full \begin{algorithm}...\end{algorithm} source
    pseudocode_text: str         # plain-text version (LaTeX commands stripped)
    context_before: str          # 300 chars of surrounding prose
    context_after: str
    explanation: str | None = None        # JSON: {purpose, inputs_outputs, step_by_step, complexity, key_insight, prerequisites}
    explanation_model: str | None = None


@dataclass(frozen=True)
class Section:
    """A section of a paper with its text and extracted math blocks."""
    order_idx: int
    title: str
    plain_text: str
    raw_latex: str | None = None
    math_blocks: tuple[MathBlock, ...] = field(default_factory=tuple)
    algorithm_blocks: tuple[AlgorithmBlock, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Citation:
    """A single bibliography entry extracted from a paper's LaTeX source."""
    order_idx: int
    cite_key: str           # e.g. "vaswani2017attention"
    raw_bib_entry: str      # full \bibitem{...} or @article{...} block (up to 1000 chars)
    arxiv_id: str | None    # canonical ArXiv ID (no version suffix), or None
    title: str | None       # best-effort extracted title
    url: str | None         # first URL found in the entry


@dataclass(frozen=True)
class Paper:
    """Represents a research paper with extracted metadata and content."""
    title: str
    text: str
    pdf_path: Path | None = None
    arxiv_id: str | None = None
    source_type: str = "pdf"              # "arxiv_latex" | "pdf"
    summary_md: str | None = None
    sections: tuple[Section, ...] = field(default_factory=tuple)
    citations: tuple[Citation, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ExtractedContent:
    """Structured content extracted from paper text."""
    abstract: str | None
    doi: str | None
    contributions: list[str]

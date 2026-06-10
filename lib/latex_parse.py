"""LaTeX parsing: split into sections and extract math environments.

Handles:
  Named display environments:  equation, equation*, align, align*,
                               gather, gather*, multline, multline*,
                               cases, eqnarray, eqnarray*
  Display math delimiters:     $$...$$ and \\[...\\]
  Inline math:                 $...$  (only if expression length > MIN_INLINE_LEN)

Uses pylatexenc for plain-text conversion of section bodies.
Falls back gracefully if pylatexenc is not installed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterator

from lib.models import MathBlock, Section


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Inline math expressions shorter than this are skipped (e.g. $n$, $x$)
MIN_INLINE_LEN = 6

# Characters of surrounding plain text to capture as context
CONTEXT_WINDOW = 300

# Math environment names to extract (with and without *)
_NAMED_ENVS = (
    "equation", "align", "gather", "multline",
    "eqnarray", "cases", "split", "subequations",
    "flalign", "alignat",
)

# Section-level commands (ordered from coarsest to finest)
_SECTION_CMDS = (
    r"\chapter",
    r"\section",
    r"\subsection",
    r"\subsubsection",
)


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

def _named_env_pattern() -> re.Pattern[str]:
    """Match \\begin{env}...\\end{env} for all known math environments."""
    names = "|".join(re.escape(e) + r"\*?" for e in _NAMED_ENVS)
    return re.compile(
        r"\\begin\{(" + names + r")\}(.*?)\\end\{\1\}",
        re.DOTALL,
    )


def _display_dollar_pattern() -> re.Pattern[str]:
    """Match $$...$$ (non-greedy)."""
    return re.compile(r"\$\$(.+?)\$\$", re.DOTALL)


def _display_bracket_pattern() -> re.Pattern[str]:
    """Match \\[...\\]."""
    return re.compile(r"\\\[(.*?)\\\]", re.DOTALL)


def _inline_dollar_pattern() -> re.Pattern[str]:
    r"""Match $...$ (single dollar, non-greedy). Avoids matching $$."""
    # Negative lookbehind/lookahead for $ to avoid matching $$
    return re.compile(r"(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)", re.DOTALL)


def _section_pattern() -> re.Pattern[str]:
    """Match any section-level command and capture its title argument."""
    cmds = "|".join(re.escape(c) for c in _SECTION_CMDS)
    return re.compile(
        r"(" + cmds + r")\*?\s*\{([^}]*)\}",
        re.MULTILINE,
    )


_NAMED_ENV_RE = _named_env_pattern()
_DISPLAY_DOLLAR_RE = _display_dollar_pattern()
_DISPLAY_BRACKET_RE = _display_bracket_pattern()
_INLINE_DOLLAR_RE = _inline_dollar_pattern()
_SECTION_RE = _section_pattern()


# ---------------------------------------------------------------------------
# Pre-processing before plain-text conversion
# ---------------------------------------------------------------------------

# Environments whose content does not contribute readable prose
_NON_TEXT_ENVS = (
    "tabular", "tabular*", "longtable", "longtable*",
    "table", "table*",
    "figure", "figure*",
    "tikzpicture", "pgfpicture", "forest",
    "algorithm", "algorithm*", "algorithmic",
    "lstlisting", "verbatim", "Verbatim",
    "minipage",
    "wrapfigure", "subfigure",
)

# Compile once
_NON_TEXT_ENV_RE = re.compile(
    r"\\begin\{(" + "|".join(re.escape(e) for e in _NON_TEXT_ENVS) + r")\}.*?\\end\{\1\}",
    re.DOTALL,
)


def _preprocess_for_text(latex: str) -> str:
    """Strip constructs that produce garbage when converted to plain text."""
    # 1. Remove % comments (everything from % to end of line, not inside math)
    latex = re.sub(r"%[^\n]*", "", latex)
    # 2. Remove non-prose environments (tables, figures, algorithms, …)
    latex = _NON_TEXT_ENV_RE.sub(" ", latex)
    # 3. Remove display math environments — these are rendered as MathBlock by the
    #    frontend; leaving them in causes pylatexenc to garble them into prose.
    latex = _NAMED_ENV_RE.sub(" ", latex)
    latex = _DISPLAY_DOLLAR_RE.sub(" ", latex)
    latex = _DISPLAY_BRACKET_RE.sub(" ", latex)
    # 4. Remove \hline / \toprule / \midrule / \bottomrule / \cline
    latex = re.sub(r"\\(hline|toprule|midrule|bottomrule|cline\{[^}]*\})", " ", latex)
    # 5. Collapse leftover table separators
    latex = re.sub(r"\s*&\s*", " ", latex)
    latex = re.sub(r"\\\\", "\n", latex)
    return latex


# ---------------------------------------------------------------------------
# Plain-text conversion
# ---------------------------------------------------------------------------

def _latex_to_text(latex: str) -> str:
    """Convert LaTeX to plain text using pylatexenc, with regex fallback.

    Inline math expressions ($...$) are preserved verbatim with their
    delimiters so the frontend can render them with KaTeX.
    """
    latex = _preprocess_for_text(latex)

    # Protect inline $...$ from pylatexenc — replace with unique placeholders
    # so pylatexenc never sees the raw LaTeX inside the math delimiters.
    placeholders: list[str] = []

    def _protect(m: re.Match) -> str:  # type: ignore[type-arg]
        idx = len(placeholders)
        placeholders.append(m.group(0))   # keep original $...$
        return f"\x00MATH{idx}\x00"

    protected = _INLINE_DOLLAR_RE.sub(_protect, latex)

    try:
        from pylatexenc.latex2text import LatexNodes2Text  # type: ignore
        text = LatexNodes2Text().latex_to_text(protected)
    except Exception:
        # Fallback: strip LaTeX commands with a simple regex
        text = re.sub(r"\\[a-zA-Z]+\*?\s*(\{[^}]*\})*", " ", protected)
        text = re.sub(r"[{}]", " ", text)
        text = re.sub(r"\s+", " ", text)
        text = text.strip()

    # Restore original inline math expressions
    for i, expr in enumerate(placeholders):
        text = text.replace(f"\x00MATH{i}\x00", expr)

    return text


# ---------------------------------------------------------------------------
# Context extraction
# ---------------------------------------------------------------------------

def _extract_context(full_text: str, match_start: int, match_end: int) -> tuple[str, str]:
    """Return (context_before, context_after) plain-text windows around a match."""
    before_raw = full_text[max(0, match_start - CONTEXT_WINDOW): match_start]
    after_raw = full_text[match_end: match_end + CONTEXT_WINDOW]
    return (
        _latex_to_text(before_raw).strip(),
        _latex_to_text(after_raw).strip(),
    )


# ---------------------------------------------------------------------------
# Math block extraction
# ---------------------------------------------------------------------------

@dataclass
class _RawMatch:
    start: int
    end: int
    env_type: str
    latex_expr: str


def _extract_math_matches(latex_body: str) -> list[_RawMatch]:
    """Find all math expressions in a LaTeX section body, sorted by position."""
    matches: list[_RawMatch] = []
    seen_spans: list[tuple[int, int]] = []

    def _overlaps(start: int, end: int) -> bool:
        return any(s < end and start < e for s, e in seen_spans)

    def _add(start: int, end: int, env_type: str, expr: str) -> None:
        if not _overlaps(start, end):
            matches.append(_RawMatch(start, end, env_type, expr.strip()))
            seen_spans.append((start, end))

    # 1. Named environments (highest priority — most precise)
    for m in _NAMED_ENV_RE.finditer(latex_body):
        env_name = m.group(1).rstrip("*")
        _add(m.start(), m.end(), env_name, m.group(0))

    # 2. Display math $$...$$
    for m in _DISPLAY_DOLLAR_RE.finditer(latex_body):
        _add(m.start(), m.end(), "display", m.group(0))

    # 3. Display math \[...\]
    for m in _DISPLAY_BRACKET_RE.finditer(latex_body):
        _add(m.start(), m.end(), "display", m.group(0))

    # 4. Inline math $...$ (only if long enough)
    for m in _INLINE_DOLLAR_RE.finditer(latex_body):
        inner = m.group(1).strip()
        if len(inner) >= MIN_INLINE_LEN:
            _add(m.start(), m.end(), "inline", m.group(0))

    matches.sort(key=lambda r: r.start)
    return matches


def _build_math_blocks(latex_body: str) -> tuple[MathBlock, ...]:
    """Extract all math blocks from a section body.

    Strips non-text environments (tables, figures) *before* scanning so that
    table-cell symbols like $\\downarrow$ are not captured as math blocks.
    """
    # Use the same clean body for both scanning and context extraction so
    # character positions stay consistent.
    clean = _NON_TEXT_ENV_RE.sub(" ", latex_body)
    clean = re.sub(r"%[^\n]*", "", clean)   # strip % comments

    raw_matches = _extract_math_matches(clean)
    blocks: list[MathBlock] = []

    for idx, raw in enumerate(raw_matches):
        ctx_before, ctx_after = _extract_context(clean, raw.start, raw.end)
        blocks.append(MathBlock(
            order_idx=idx,
            env_type=raw.env_type,
            latex_expr=raw.latex_expr,
            context_before=ctx_before,
            context_after=ctx_after,
        ))

    return tuple(blocks)


# ---------------------------------------------------------------------------
# Section splitting
# ---------------------------------------------------------------------------

def _split_sections(latex_doc: str) -> list[tuple[str, str]]:
    """Split a LaTeX document body into (title, body) pairs.

    Returns a list of (section_title, raw_latex_body) where the first
    entry may be ('', preamble_text) for content before the first section.
    """
    section_matches = list(_SECTION_RE.finditer(latex_doc))

    if not section_matches:
        # No sections found — treat entire document as one unnamed section
        return [("", latex_doc)]

    result: list[tuple[str, str]] = []

    # Content before first section
    pre = latex_doc[: section_matches[0].start()].strip()
    if pre:
        result.append(("", pre))

    for i, m in enumerate(section_matches):
        title = m.group(2).strip()
        body_start = m.end()
        body_end = (
            section_matches[i + 1].start()
            if i + 1 < len(section_matches)
            else len(latex_doc)
        )
        body = latex_doc[body_start:body_end].strip()
        result.append((title, body))

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_latex_sections(latex_doc: str) -> tuple[Section, ...]:
    """
    Parse a merged LaTeX document into Section objects with math blocks.

    Args:
        latex_doc: Full LaTeX source (preamble already stripped).

    Returns:
        Tuple of Section objects, each containing zero or more MathBlock objects.
    """
    raw_sections = _split_sections(latex_doc)
    sections: list[Section] = []

    for idx, (title, body) in enumerate(raw_sections):
        if not body.strip():
            continue

        plain_text = _latex_to_text(body)
        if len(plain_text.strip()) < 50:
            continue   # skip near-empty sections

        math_blocks = _build_math_blocks(body)

        sections.append(Section(
            order_idx=idx,
            title=title or _infer_section_title(idx, plain_text),
            plain_text=plain_text,
            raw_latex=body,
            math_blocks=math_blocks,
        ))

    return tuple(sections)


def _infer_section_title(idx: int, plain_text: str) -> str:
    """Heuristic title for an unnamed pre-section block (abstract, intro preamble)."""
    first_line = plain_text.strip().splitlines()[0][:60] if plain_text.strip() else ""
    lower = first_line.lower()
    if "abstract" in lower:
        return "Abstract"
    if idx == 0:
        return "Preamble"
    return f"Section {idx}"

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
# Named display environments get a wider window to capture the full theorem/proof context
CONTEXT_WINDOW_NAMED = 800    # equation, align, gather, etc.
CONTEXT_WINDOW_DEFAULT = 300  # display $$, inline $

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

# Commands used for *splitting* the document — subsections stay inside their parent
_SPLIT_CMDS = (
    r"\chapter",
    r"\section",
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
    r"""Match $...$ (single dollar, non-greedy). Avoids matching $$.

    Intentionally no re.DOTALL — inline math must not span blank lines.
    A single \n is allowed (soft wrap), but two or more consecutive
    newlines signal a paragraph break and end the match.
    """
    return re.compile(r"(?<!\$)\$(?!\$)([^\n$]{1,200})(?<!\$)\$(?!\$)")


def _section_pattern(cmds: tuple[str, ...] = _SPLIT_CMDS) -> re.Pattern[str]:
    """Match section-level commands and capture their title argument.

    Handles one level of nested braces inside the title, e.g.:
        \\section{\\macro{}: Some title}  →  title = "\\macro{}: Some title"
    """
    cmd_pat = "|".join(re.escape(c) for c in cmds)
    # Title group: any mix of non-brace chars and single-level {…} pairs
    title_group = r"((?:[^{}]|\{[^{}]*\})*)"
    return re.compile(
        r"(" + cmd_pat + r")\*?\s*\{" + title_group + r"\}",
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
    """Strip constructs that produce garbage when converted to plain text.

    Also converts structural LaTeX (subsections, lists, inline formatting) to
    markdown syntax so the frontend can render them with proper visual hierarchy.
    """
    # 1. Remove % comments (everything from % to end of line, not inside math)
    latex = re.sub(r"%[^\n]*", "", latex)
    # 2. Remove non-prose environments (tables, figures, algorithms, …)
    latex = _NON_TEXT_ENV_RE.sub(" ", latex)
    # 3. Remove display math environments — rendered as MathBlock by the frontend
    latex = _NAMED_ENV_RE.sub(" ", latex)
    latex = _DISPLAY_DOLLAR_RE.sub(" ", latex)
    latex = _DISPLAY_BRACKET_RE.sub(" ", latex)

    # 4. Convert inline formatting to markdown BEFORE pylatexenc sees them.
    #    One level of brace nesting is sufficient for all common cases.
    _grp = r"((?:[^{}]|\{[^{}]*\})*)"
    # \texttt, \code, \func, \file, \textsc → `code`
    latex = re.sub(r"\\(?:texttt|code|func|file|textsc)\s*\{" + _grp + r"\}", r"`\1`", latex)
    # \textbf → **bold**
    latex = re.sub(r"\\textbf\s*\{" + _grp + r"\}", r"**\1**", latex)
    # \emph, \textit → *italic*
    latex = re.sub(r"\\(?:emph|textit)\s*\{" + _grp + r"\}", r"*\1*", latex)

    # 5. Convert subsections/subsubsections to placeholder tokens.
    #    We use \x02 control chars because pylatexenc passes them through
    #    unchanged — using \n here would get collapsed by pylatexenc.
    #    _latex_to_text() restores these to proper \n\n markdown after conversion.
    def _to_h3(m: re.Match) -> str:  # type: ignore[type-arg]
        return f"\x02H3\x02{m.group(1).strip()}\x02/H3\x02"

    def _to_h4(m: re.Match) -> str:  # type: ignore[type-arg]
        return f"\x02H4\x02{m.group(1).strip()}\x02/H4\x02"

    latex = re.sub(r"\\subsection\*?\s*\{" + _grp + r"\}", _to_h3, latex)
    latex = re.sub(r"\\subsubsection\*?\s*\{" + _grp + r"\}", _to_h4, latex)

    # 6. Convert list environments to placeholder tokens (same reason as above).
    def _convert_enumerate(m: re.Match) -> str:  # type: ignore[type-arg]
        raw_items = re.split(r"\\item\b(?:\[[^\]]*\])?", m.group(1))
        filtered = [it.strip() for it in raw_items if it.strip()]
        return ("\x02OL\x02" + "\x02LI\x02".join(filtered) + "\x02/OL\x02") if filtered else " "

    def _convert_itemize(m: re.Match) -> str:  # type: ignore[type-arg]
        raw_items = re.split(r"\\item\b(?:\[[^\]]*\])?", m.group(1))
        filtered = [it.strip() for it in raw_items if it.strip()]
        return ("\x02UL\x02" + "\x02LI\x02".join(filtered) + "\x02/UL\x02") if filtered else " "

    for _ in range(3):
        latex = re.sub(
            r"\\begin\{itemize\}(?:\[[^\]]*\])?\s*(.*?)\s*\\end\{itemize\}",
            _convert_itemize, latex, flags=re.DOTALL,
        )
        latex = re.sub(
            r"\\begin\{enumerate\}(?:\[[^\]]*\])?\s*(.*?)\s*\\end\{enumerate\}",
            _convert_enumerate, latex, flags=re.DOTALL,
        )

    # 7. Strip cross-reference and citation commands (avoids empty parens)
    latex = re.sub(r"\\(?:Cref|cref|ref|eqref|autoref|pageref)\s*\{[^}]*\}", "", latex)
    latex = re.sub(r"\\(?:citep|citet|cite[a-zA-Z]*)\s*(?:\[[^\]]*\])?\s*\{[^}]*\}", "", latex)
    # Remove empty parentheses left behind after stripping refs/citations
    latex = re.sub(r"\(\s*\)", "", latex)
    # Remove empty brackets left behind similarly
    latex = re.sub(r"\[\s*\]", "", latex)

    # 8. Convert LaTeX special characters that pylatexenc fallback misses.
    # \_ must NOT be converted inside inline $...$ math — KaTeX needs \_ to
    # render a literal underscore (plain _ is a subscript operator in math mode).
    _INLINE_MATH_RE = re.compile(r'\$\$[\s\S]*?\$\$|\$(?:[^$\n]|\\.)+?\$')

    def _sub_outside_math(text: str, pat: str, repl: str) -> str:
        parts: list[str] = []
        last = 0
        for m in _INLINE_MATH_RE.finditer(text):
            parts.append(re.sub(pat, repl, text[last:m.start()]))
            parts.append(m.group(0))  # preserve inline math verbatim
            last = m.end()
        parts.append(re.sub(pat, repl, text[last:]))
        return "".join(parts)

    latex = re.sub(r"\\%", "%", latex)                      # \% → %
    latex = _sub_outside_math(latex, r"\\_", "_")           # \_ → _ (plain text only)
    latex = re.sub(r"\\&", "and", latex)                    # \& → and
    latex = re.sub(r"\\#", "#", latex)                      # \# → #
    latex = re.sub(r"(?<!\\)~", " ", latex)                 # ~ (non-breaking space) → space
    latex = re.sub(r"\\[,;:! ]", " ", latex)    # thin/medium/thick/forced spaces → space
    latex = re.sub(r"---", "—", latex)          # em dash
    latex = re.sub(r"--", "–", latex)           # en dash
    latex = re.sub(r"``", "\u201c", latex)       # opening double quote
    latex = re.sub(r"''", "\u201d", latex)       # closing double quote

    # 9. Remove spacing/layout commands that turn into bracketed artifacts
    latex = re.sub(r"\\(vskip|hskip|vspace\*?|hspace\*?)\s*[{\[]?[\d.]+\s*(?:pt|mm|cm|in|em|ex|bp|pc|dd|cc|sp)?[}\]]?", " ", latex)
    # 10. Remove \hline / \toprule / \midrule / \bottomrule / \cline
    latex = re.sub(r"\\(hline|toprule|midrule|bottomrule|cline\{[^}]*\})", " ", latex)
    # 11. Collapse leftover table separators
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

    # Restore structural placeholders to proper markdown with paragraph breaks.
    # These were inserted as \x02 tokens to survive pylatexenc's whitespace collapsing.

    # Headings
    text = re.sub(r"\x02H3\x02(.*?)\x02/H3\x02", lambda m: f"\n\n### {m.group(1).strip()}\n\n", text)
    text = re.sub(r"\x02H4\x02(.*?)\x02/H4\x02", lambda m: f"\n\n#### {m.group(1).strip()}\n\n", text)

    # Ordered list: \x02OL\x02item1\x02LI\x02item2\x02/OL\x02
    def _restore_ol(m: re.Match) -> str:  # type: ignore[type-arg]
        items = [it.strip() for it in m.group(1).split("\x02LI\x02") if it.strip()]
        lines = "\n".join(f"{i}. {it}" for i, it in enumerate(items, 1))
        return f"\n\n{lines}\n\n"

    text = re.sub(r"\x02OL\x02(.*?)\x02/OL\x02", _restore_ol, text, flags=re.DOTALL)

    # Unordered list: \x02UL\x02item1\x02LI\x02item2\x02/UL\x02
    def _restore_ul(m: re.Match) -> str:  # type: ignore[type-arg]
        items = [it.strip() for it in m.group(1).split("\x02LI\x02") if it.strip()]
        lines = "\n".join(f"- {it}" for it in items)
        return f"\n\n{lines}\n\n"

    text = re.sub(r"\x02UL\x02(.*?)\x02/UL\x02", _restore_ul, text, flags=re.DOTALL)

    # Clean up any stray \x02 bytes that escaped the above patterns
    text = text.replace("\x02", " ")

    return text


# ---------------------------------------------------------------------------
# Context extraction
# ---------------------------------------------------------------------------

def _extract_context(full_text: str, match_start: int, match_end: int, env_type: str = "inline") -> tuple[str, str]:
    """Return (context_before, context_after) plain-text windows around a match."""
    window = CONTEXT_WINDOW_NAMED if env_type not in ("display", "inline") else CONTEXT_WINDOW_DEFAULT
    before_raw = full_text[max(0, match_start - window): match_start]
    after_raw = full_text[match_end: match_end + window]
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
        ctx_before, ctx_after = _extract_context(clean, raw.start, raw.end, raw.env_type)
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
        # group(2) is the title; clean up residual LaTeX macros
        raw_title = m.group(2).strip()
        title = _latex_to_text(raw_title).strip().lstrip(":–—,; ")
        if not title:
            # Unknown macro (e.g. \planbench{}) — extract macro name as fallback
            mac = re.match(r"\\([A-Za-z]+)", raw_title)
            title = mac.group(1).capitalize() if mac else raw_title
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
        # Strip leading bracket artifacts left by \twocolumn[...] optional args
        plain_text = re.sub(r"^\s*\[\s*\]\s*", "", plain_text)
        if len(plain_text.strip()) < 50:
            continue   # skip near-empty sections

        math_blocks = _build_math_blocks(body)

        sections.append(Section(
            order_idx=idx,
            title=title or _infer_section_title(idx, plain_text, raw_latex=body),
            plain_text=plain_text,
            raw_latex=body,
            math_blocks=math_blocks,
        ))

    return tuple(sections)


def _infer_section_title(idx: int, plain_text: str, raw_latex: str = "") -> str:
    """Heuristic title for an unnamed pre-section block (abstract, intro preamble)."""
    # Check raw LaTeX first — most reliable signal for abstract detection
    if r"\begin{abstract}" in raw_latex or "abstract" in plain_text[:800].lower():
        return "Abstract"
    if idx == 0:
        return "Preamble"
    return f"Section {idx}"

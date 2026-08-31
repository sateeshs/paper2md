"""Extract and split PDF sections from plain text."""

from __future__ import annotations

import collections
import dataclasses
import re

from lib.models import Section

# Identical heading text appearing ≥ this many times is treated as a running
# page header (textbook chapter title on every page), not section starts.
RUNNING_HEADER_MIN_REPEATS = 3

_ENGLISH_WORDS_OF_ROMAN_LETTERS = frozenset({
    "did", "dim", "mix", "civil", "mil", "lid", "vim", "mid", "ill", "id",
    "mi", "di", "xi", "im", "icu", "midi", "dvd", "lcd",
})


def is_roman_page_number(token: str) -> bool:
    """True if a standalone line is plausibly a roman-numeral page number.

    Filters out common English words that happen to be spelled with roman letters.
    Tokens longer than 6 chars are preserved (not filtered) as they are implausible
    page numbers and may be real prose content (e.g., years, indices).
    """
    t = token.strip()
    if not t or len(t) > 6 or not re.fullmatch(r"[ivxlcdm]+", t, re.IGNORECASE):
        return False
    return t.lower() not in _ENGLISH_WORDS_OF_ROMAN_LETTERS


def split_pdf_into_sections(text: str) -> tuple[Section, ...]:
    """Heuristically split plain PDF text into Section objects.

    Tries three strategies in order, returning as soon as one yields ≥ 2 sections:

    1. Multi-line chapter marker (pdfminer artefact for stylised chapter headings):
          \\nChapter\\n\\n<N>\\n\\n<Title>
       Reliable when the PDF was typeset with a prominent chapter title design.

    2. Inline chapter keyword heading (single line):
          "Chapter 3 Nash Equilibrium"  or  "CHAPTER 3"
       Common in textbooks with simpler layouts.

    3. Paragraph chunking — no heading detection at all.
       Splits on double newlines into chunks of ~CHUNK_CHARS chars.
       Used as a guaranteed fallback; section title = first 80 chars of chunk.

    Sections shorter than MIN_BODY chars are merged into the previous one.
    """
    from lib.content_analysis import chunk_text_for_llm

    MIN_BODY = 500   # chars — merge stubs into previous section
    CHUNK_CHARS = 20_000  # target chars per chunk in fallback mode

    # Pattern: pdfminer often inserts 2–3 extra spaces inside justified-text words
    _MULTI_SPACE = re.compile(r"  +")
    # Orphaned math symbol lines: ≤20 chars containing mostly symbols/brackets/operators
    _MATH_ORPHAN = re.compile(
        r"^[\s\d\W\\{}\[\]().,;:!?=<>≤≥≠±∓∈∉⊂⊃⊆⊇∪∩∅→←↔↑↓⇒⇔∀∃∑∏∫∂∇∞√·×÷αβγδεζηθιλμνξπρστυφχψωΑΒΓΔΕΖΗΘΙΛΜΝΞΠΡΣΤΥΦΧΨΩ]+$"
    )

    def _clean_pdf_body(body: str) -> str:
        """Strip common pdfminer artefacts from a PDF section body.

        Removes:
        - Standalone page numbers (digit-only lines)
        - Standalone roman numeral page numbers (≤ 6 chars)
        - Running headers/footers: short lines (< 80 chars) that appear 4+ times
        - Orphaned math-symbol lines (≤ 20 chars, only operators/Greek/brackets)
        Fixes justified-text double-spacing.
        Collapses runs of 3+ blank lines to two.
        """
        raw_lines = body.split("\n")

        # Count frequency of short lines to detect running headers
        freq: dict[str, int] = {}
        for ln in raw_lines:
            t = ln.strip()
            if t and len(t) < 80:
                freq[t] = freq.get(t, 0) + 1
        repeated = {t for t, cnt in freq.items() if cnt >= 4}

        kept: list[str] = []
        for ln in raw_lines:
            t = ln.strip()
            if re.match(r"^\d+$", t):           # standalone page number
                continue
            if is_roman_page_number(t):
                continue                         # roman numeral page number
            if t in repeated:                    # running header / footer
                continue
            if t and len(t) <= 20 and _MATH_ORPHAN.match(t):
                continue                         # orphaned math-symbol fragment
            # Fix justified-text multiple spaces between words
            ln = _MULTI_SPACE.sub(" ", ln)
            kept.append(ln)

        result = "\n".join(kept)
        result = re.sub(r"\n{3,}", "\n\n", result)
        return result.strip()

    def _build_from_positions(
        full_text: str, positions: list[tuple[int, int, str]]
    ) -> list[Section]:
        """Given (body_start, heading_end, title) triples, slice full_text into sections.

        body_start: character offset where the body content begins (after the heading).
        heading_end: same as body_start — kept for clarity; the next section's
                     heading_start determines where this section ends.
        """
        result: list[Section] = []
        for i, (body_start, _heading_end, title) in enumerate(positions):
            next_heading_start = positions[i + 1][0] if i + 1 < len(positions) else len(full_text)
            content = full_text[body_start:next_heading_start].strip()
            content = _clean_pdf_body(content)
            if len(content) < MIN_BODY:
                if result:
                    result[-1] = dataclasses.replace(
                        result[-1],
                        plain_text=result[-1].plain_text + "\n\n" + content,
                    )
                continue
            result.append(Section(order_idx=len(result), title=title, plain_text=content))
        return result

    # ── Strategy 1: multi-line "Chapter\n\nN\n\nTitle" (pdfminer artefact) ──
    # Use m.end() as body_start so the heading itself is excluded from the body.
    _MULTILINE_CH = re.compile(r"\nChapter\n\n(\d+)\n\n([^\n]+)")
    matches = list(_MULTILINE_CH.finditer(text))
    if len(matches) >= 2:
        positions = [
            (m.end(), m.end(), f"Chapter {m.group(1)}: {m.group(2).strip()}")
            for m in matches
        ]
        sections = _build_from_positions(text, positions)
        if len(sections) >= 2:
            return tuple(sections)

    # ── Strategy 2: inline chapter keyword heading ────────────────────────────
    _INLINE_CH = re.compile(
        r"^(?:Chapter|CHAPTER)\s+\d+(?:\s+[A-Z][^\n]{0,80})?$", re.MULTILINE
    )
    inline_matches = list(_INLINE_CH.finditer(text))
    if len(inline_matches) >= 2:
        # body starts after the heading line (m.end()) not at m.start()
        positions = [
            (m.end(), m.end(), m.group(0).strip())
            for m in inline_matches
        ]
        sections = _build_from_positions(text, positions)
        if len(sections) >= 2:
            return tuple(sections)

    # ── Strategy 3: numbered section headings ──────────────────────────────────
    # Handles both well-spaced PDFs ("1 Introduction\n") and no-space PDFs where
    # headings are glued to body text ("2Background:PolicyOptimization...").

    # 3a: standalone-line headings (well-formatted PDFs).
    # Number may carry a trailing dot ("1. Introduction") or nested dots ("2.3 Model").
    # Separator is [ \t]+ (NOT \s) so a bare page-number line followed by body text
    # on later lines cannot anchor a section; the title class excludes newlines for
    # the same reason.
    _NUMBERED_SEC_LINE = re.compile(
        r"^(\d+(?:\.\d+)*\.?|[A-Z])[ \t]+([A-Z][A-Za-z ,:&\-–—]{2,78})$", re.MULTILINE
    )
    line_matches = list(_NUMBERED_SEC_LINE.finditer(text))
    # Drop running headers: a textbook repeats the chapter title at the top of
    # every page; the identical heading line appearing ≥3 times is a page
    # header, not N section starts (real headings repeat ≤2×: TOC entry + body).
    title_counts = collections.Counter(
        m.group(0).strip().lower() for m in line_matches
    )
    line_matches = [
        m for m in line_matches
        if title_counts[m.group(0).strip().lower()] < RUNNING_HEADER_MIN_REPEATS
    ]
    if len(line_matches) >= 2:
        positions = [
            (m.end(), m.end(), m.group(0).strip())
            for m in line_matches
            if len(m.group(0).strip()) <= 100
        ]
        sections = _build_from_positions(text, positions)
        if len(sections) >= 2:
            return tuple(sections)

    # 3b: no-space PDFs — find top-level section markers using known heading keywords.
    # In poorly-extracted PDFs, text runs together without whitespace. We look for
    # digit + known academic section keywords (Introduction, Background, Conclusion, etc.)
    _KNOWN_SECTIONS = (
        "Introduction", "Background", "Related", "Method", "Approach",
        "Algorithm", "Experiment", "Result", "Discussion", "Conclusion",
        "Evaluation", "Implementation", "Analysis", "Preliminaries",
        "Problem", "Model", "Framework", "Architecture", "Training",
        "Setup", "Appendix", "Overview", "Motivation", "Objective",
        "Formulation", "Surrogate", "Adaptive", "Clipped",
    )
    _SEC_KW_PATTERN = re.compile(
        r"(\d)(" + "|".join(_KNOWN_SECTIONS) + r")"
    )
    all_kw_matches = list(_SEC_KW_PATTERN.finditer(text))
    # Filter to strictly sequential section numbers (1, 2, 3, ...).
    # This avoids false positives from figure/table data containing digit + keyword.
    kw_matches: list[re.Match[str]] = []
    expected_sec = 1
    for m in all_kw_matches:
        num = int(m.group(1))
        if num == expected_sec:
            kw_matches.append(m)
            expected_sec = num + 1

    if len(kw_matches) >= 3:
        parts = [text[:kw_matches[0].start()]]
        for i, m in enumerate(kw_matches):
            end = kw_matches[i + 1].start() if i + 1 < len(kw_matches) else len(text)
            parts.append(text[m.start():end])
    else:
        parts = []

    if len(parts) >= 4:  # first part is preamble + at least 3 sections
        def _nospace_title(chunk: str, keyword: str) -> str:
            """Build a readable section title from the matched keyword.

            For no-space PDFs, we rely on the keyword matched by the regex
            since word boundaries are unreliable in concatenated text.
            For well-spaced text, we also grab words after the keyword.
            """
            m = re.match(r"(\d+)", chunk)
            num = m.group(1) if m else ""
            title = re.sub(r"([a-z])([A-Z])", r"\1 \2", keyword)
            # If text has spaces (well-formatted PDF), grab extra title words
            after_kw = chunk[len(num) + len(keyword):]
            if " " in after_kw[:30]:
                # Well-spaced: take up to 3 additional capitalized words
                words = after_kw.strip().split()
                for w in words[:3]:
                    if w[0:1].isupper() and len(w) <= 15:
                        title += " " + w
                    else:
                        break
            return f"{num} {title}"

        built_sections: list[Section] = []
        # Skip first part (preamble/abstract before section 1)
        for i, part in enumerate(parts[1:]):
            body = _clean_pdf_body(part)
            if len(body) < MIN_BODY:
                if built_sections:
                    built_sections[-1] = dataclasses.replace(
                        built_sections[-1],
                        plain_text=built_sections[-1].plain_text + "\n\n" + body,
                    )
                continue
            keyword = kw_matches[i].group(2) if i < len(kw_matches) else ""
            title = _nospace_title(part, keyword)
            built_sections.append(
                Section(order_idx=len(built_sections), title=title, plain_text=body)
            )
        if len(built_sections) >= 3:
            return tuple(built_sections)

    # ── Strategy 4: paragraph-aware chunking (guaranteed fallback) ────────────
    chunks = chunk_text_for_llm(text, max_chars=CHUNK_CHARS)
    result: list[Section] = []
    for chunk in chunks:
        if len(chunk.strip()) < MIN_BODY:
            if result:
                result[-1] = dataclasses.replace(
                    result[-1], plain_text=result[-1].plain_text + "\n\n" + chunk
                )
            continue
        # Title = first meaningful non-whitespace line, truncated
        first_line = next(
            (ln.strip() for ln in chunk.splitlines() if ln.strip()), "Section"
        )
        title = first_line[:80] + ("…" if len(first_line) > 80 else "")
        result.append(Section(order_idx=len(result), title=title, plain_text=chunk.strip()))
    return tuple(result) if result else (Section(order_idx=0, title="Content", plain_text=text.strip()),)

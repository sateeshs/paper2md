# Section Hierarchy & PDF Page Numbers — Design

**Date:** 2026-09-24
**Status:** Approved (pending spec review)
**Driving case:** arXiv 2412.05265 — Kevin P. Murphy, *Reinforcement Learning: An Overview* (253 pages, book-structured)

---

## Problem

Book-length papers extract badly. For 2412.05265 the current pipeline produces 86 flat
sections with no hierarchy, gaps in `order_idx`, duplicated content, dropped chapter
titles, and no page numbers — making it unusable for reading a paper end to end.

### Root causes

| # | Bug | Location | Effect |
|---|-----|----------|--------|
| 1 | `\input`/`\include` resolution is not comment-aware | `lib/arxiv_source.py:36` (`_INPUT_RE`) | `%\input{code}` is inlined anyway. `code.tex` (~730 lines) appears **twice** — once at the top of the document. The leftover `%` glues onto the file's first line, yielding `%\section{Implementation details}`. |
| 2 | Section splitting is not comment-aware | `lib/latex_parse.py:110` (`_SECTION_RE`) | Commented-out headings become real sections. |
| 3 | `order_idx` is the enumerate index over *raw* sections, including skipped ones | `lib/latex_parse.py` `parse_latex_sections` | Gaps: 0, 2, 3, 4, 6, 7, 8… |
| 4 | Sections with `plain_text < 50` chars are dropped | `lib/latex_parse.py` `parse_latex_sections` | Container headings are deleted. For this paper that silently removes the chapters `Introduction`, `Value-based RL`, `Model-based RL`, `LLMs and RL`. |
| 5 | `_SPLIT_CMDS` = `\chapter` + `\section` only; `\subsection` re-split fires only when a body exceeds 30 000 chars | `lib/latex_parse.py:52,669` | Flat output with wildly inconsistent granularity (52 → 24 451 chars) and no hierarchy. |
| 6 | No page data anywhere | schema + pipeline + web | Cannot follow along in the PDF. |

Note: `\eat{...}` draft content is **already** correctly discarded by `expand_custom_macros`.
The stale Supabase row (built 2026-08-13) still contains it; reprocessing fixes that.

---

## Goals

1. Sections mirror the document's real structure, in the same order as the PDF.
2. Every section carries its section number (`2.5.3`) and PDF page range.
3. Nothing is silently dropped or duplicated.
4. Generic — works for any paper; degrades cleanly when the inputs are weaker.

## Non-goals

- Compiling LaTeX locally.
- Re-extracting math or algorithm blocks (unchanged logic; they simply attach to finer sections).
- Backfilling every existing paper. Only 2412.05265 is reprocessed here.

---

## Key insight

The arXiv PDF ships a complete `hyperref` outline. For 2412.05265 that is 388 entries,
each with level, section number, title, and page. Measured against the LaTeX source after
fixes 1–2:

```
LaTeX headings: 388   PDF toc: 388
title-matched:  388/388 = 100.0%
number agrees:  388/388 = 100.0%   (LaTeX counter simulation == PDF numbering)
ORDER VIOLATIONS: 0                (page_start never decreases)
```

Two fully independent derivations of the structure agree exactly, so the result is
cross-validated rather than assumed.

---

## Design

### Granularity

**All four outline levels become reading units** — 388 units for this paper, ~1 PDF page
each. Measured body sizes: median 1 204 chars, mean 1 614, max 8 343.

1:1 with the PDF outline is the invariant. **No heading is ever dropped.** The 5 units
under 50 chars are container headings whose content lives in their children; they are kept
as navigation nodes with a valid page anchor.

`PAPER2MD_SECTION_MAX_LEVEL` is **not** introduced — the cut-off is fixed at 4 (YAGNI).

### New module: `lib/latex_outline.py`

Owns "what is the heading tree of this document". No PDF knowledge, no DB knowledge.

```python
@dataclass(frozen=True)
class Heading:
    level: int      # 1=chapter 2=section 3=subsection 4=subsubsection
    number: str     # "2.5.3"; "" for starred/unnumbered
    title: str
    body_start: int # char offset into the merged doc
    body_end: int

def parse_headings(latex_doc: str) -> tuple[Heading, ...]
def build_sections(
    headings: tuple[Heading, ...],
    latex_doc: str,
    pages: Mapping[int, PageSpan] | None = None,
) -> tuple[Section, ...]
```

- Walks all four heading commands in document order, comment-aware.
- Simulates LaTeX counters. Starred headings get `number=""` and do not advance counters.
- Title regex tolerates two levels of nested braces (`\subsection{TD($\lambda$)}`).
- `build_sections` assigns `order_idx` from a running counter — contiguous by construction.

### New module: `lib/pdf_outline.py`

Owns "which page is each heading on". No LaTeX knowledge.

```python
@dataclass(frozen=True)
class PageSpan:
    start: int
    end: int
    source: str      # 'pdf_outline' | 'inferred'


@dataclass(frozen=True)
class OutlineEntry:
    level: int
    number: str
    title: str
    page: int

def fetch_outline(arxiv_id: str) -> tuple[OutlineEntry, ...]
def map_pages(headings, outline) -> dict[int, PageSpan]   # keyed by heading index
```

- Downloads `arxiv.org/pdf/{id}`, reads bookmarks via `pymupdf.get_toc()`. PDF cached on
  disk through the existing `PaperCache` (this one is 11 MB).
- Aligns with `difflib.SequenceMatcher` over normalised titles (strip `$…$`, strip control
  sequences, casefold, collapse non-alphanumerics). Alignment absorbs insertions and
  deletions on either side.
- Matched → exact page, `page_source='pdf_outline'`.
- Unmatched → monotone interpolation from matched neighbours, `page_source='inferred'`.
- `page_end` = next unit's `page_start`.
- **Final unit** `page_end` is capped at the start of the bibliography, not the last PDF
  page — otherwise `8 Acknowledgements` absorbs 54 pages of references.

#### Degradation

| Condition | Behaviour |
|---|---|
| PDF unreachable / download fails | pages `NULL`, structure still correct, processing continues |
| PDF has no bookmarks | pages `NULL` |
| Title match rate < 50 % | discard the mapping entirely, pages `NULL` |

Page mapping never blocks or fails processing.

### Changes to existing modules

**`lib/arxiv_source.py`**
- Strip LaTeX comments before `_INPUT_RE.sub` in `_resolve_includes`, reusing the correct
  `_TEX_COMMENT_RE` from `lib/latex_macros.py:400` (handles `\%` and `\\`).
- Guard: do not strip inside `verbatim` / `minted` / `lstlisting`, so `%` and `#` inside
  code listings survive. `code.tex` in this paper contains minted Python.

**`lib/latex_parse.py`**
- `parse_latex_sections` delegates to `latex_outline` when the document has any
  `\chapter`/`\section`. The existing `_split_sections` heuristics remain as the fallback
  for papers with no sectioning commands at all.
- `order_idx` becomes a running counter over kept sections.
- The `< 50 chars` drop is removed on the structured path.

**`lib/models.py`** — extend `Section`:

```python
level: int | None = None
number: str | None = None
page_start: int | None = None
page_end: int | None = None
page_source: str | None = None
```

All default `None`, so PDF-sourced papers and the fallback path are unaffected.

**`lib/supabase_push.py`** — persist the five new columns.

### Schema — `supabase/migrations/008_section_hierarchy.sql`

```sql
ALTER TABLE sections
  ADD COLUMN level       INTEGER,
  ADD COLUMN number      TEXT,
  ADD COLUMN page_start  INTEGER,
  ADD COLUMN page_end    INTEGER,
  ADD COLUMN page_source TEXT;
```

All nullable; existing rows are valid. No new index — the existing
`UNIQUE (paper_id, order_idx)` constraint already provides one. Followed by `npm run gen:types` in `web/`.

### Web

- `web/lib/supabase/queries.ts` — select the new columns.
- `SectionCard` — indent by `level`, render `number` prefix and a `p. 42–43` badge.
- Paper page — render the flat ordered list as a hierarchical tree using `level`.
- Section detail page — header shows `§2.5.3 · pages 42–43`.
- `PaperSplitView` / `PdfViewer` — open the PDF at `page_start` rather than page 1.

---

## Data flow

```
arxiv_source.fetch_arxiv_latex_full   →  merged body (comment-aware includes)
latex_macros.expand_custom_macros     →  macros expanded, \eat{} discarded
latex_outline.parse_headings          →  388 Headings, numbered, document order
pdf_outline.fetch_outline             →  388 OutlineEntries with pages
pdf_outline.map_pages                 →  heading index → PageSpan
latex_outline.build_sections          →  388 Sections (order_idx 0..387)
supabase_push.push_paper              →  DELETE + INSERT sections
```

---

## Testing

**`tests/test_latex_outline.py`**
- counter simulation across all four levels, including level skips
- starred headings: no number, counters unchanged
- nested-brace titles: `\subsection{TD($\lambda$)}`
- commented headings ignored
- `order_idx` contiguous from 0
- container headings with empty bodies are retained

**`tests/test_arxiv_source.py`**
- `%\input{x}` is not inlined; `\input{x}` is
- `\%` escaped percent does not start a comment
- `%` inside a `minted` block survives

**`tests/test_pdf_outline.py`**
- alignment with insertions and deletions on both sides
- interpolation is monotone
- empty outline → all pages `NULL`
- match rate < 50 % → mapping discarded

**`tests/test_section_hierarchy_golden.py`** — fixture-backed, no network:
- 388 headings, 388 units, `order_idx` 0..387 with no gaps
- 8 chapters, numbered `1`…`8`
- section numbers agree with the PDF outline for 100 % of matched units
- ≥ 95 % of units have `page_source='pdf_outline'`
- `page_start` is non-decreasing across `order_idx` (**PDF order invariant**)
- exactly one unit titled "Implementation details", at `§6.4`, `page_start == 165`
- no unit titled "Preamble"

Fixtures: trimmed LaTeX sources plus the extracted outline as JSON, committed under
`tests/fixtures/2412.05265/`. The 11 MB PDF is not committed.

---

## Rollout

1. Apply migration 008, regenerate `web/lib/supabase/types.ts`.
2. `python summarize_papers.py --arxiv-id 2412.05265 --push-supabase --force`
3. Verify at `/paper/2412.05265`: 388 units, chapter tree, page badges ascending 13 → 199.
4. Deploy `web/` to Vercel (`vercel --prod` from `web/`, Node 22).

Other papers are reprocessed lazily; their rows keep `NULL` in the new columns until then,
and the UI falls back to the current flat rendering when `level IS NULL`.

---

## Risks

| Risk | Mitigation |
|---|---|
| Comment stripping corrupts verbatim/minted code | Explicit guard + dedicated test; `code.tex` in this paper is the live case |
| A paper's PDF has no bookmarks | Pages `NULL`; structure unaffected |
| Title alignment misfires on a different paper | < 50 % match discards the mapping; interpolation keeps pages monotone |
| 388 rows per paper increases DB writes | Bounded; sections are already DELETE + INSERT per paper |
| Reprocessing regenerates math explanations (LLM cost) | Math blocks attach to finer sections; run with existing per-paper caps |

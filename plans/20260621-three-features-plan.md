# Three-Feature Implementation Plan
Date: 2026-06-21

---

## Feature 1: Algorithm Block Extraction and Explanation

### Architecture Overview

Algorithm blocks live alongside math blocks as a parallel extracted artifact.
The pipeline is: detect in `latex_parse.py` → new dataclass in `models.py` → new
DSPy signature in `dspy_signatures.py` → new DSPy module in `dspy_modules.py` →
new DB table + push in `supabase_push.py` → section page renders them via a new
`AlgorithmBlock` component.

Algorithm blocks are deliberately NOT merged into `math_blocks`. Their content is
pseudocode, not mathematical notation, so they need a separate explanation schema
and different rendering (monospace, line-numbered, not KaTeX).

### Files to Create

| Path | Purpose |
|------|---------|
| `supabase/migrations/003_algorithm_blocks.sql` | New table DDL + RLS |
| `web/components/AlgorithmBlock.tsx` | Client component: renders pseudocode + collapsible explanation |

### Files to Modify

| Path | What changes |
|------|-------------|
| `lib/models.py` | Add `AlgorithmBlock` frozen dataclass; add `algorithm_blocks` field to `Section` |
| `lib/latex_parse.py` | Add `_build_algorithm_blocks()` + call it in `parse_latex_sections()` |
| `lib/dspy_signatures.py` | Add `ExplainAlgorithmBlock` DSPy Signature |
| `lib/dspy_modules.py` | Add `AlgorithmExplainer` module; wire it into the export |
| `lib/supabase_push.py` | Add step 4.5: delete+insert `algorithm_blocks` after `math_blocks` |
| `summarize_papers.py` | Call `AlgorithmExplainer.forward(paper)` after `MathExplainer.forward()` |
| `web/lib/supabase/types.ts` | Add `AlgorithmBlock` row type (regenerate via `npm run gen:types`) |
| `web/lib/supabase/queries.ts` | Extend `getSectionWithMath` to also join `algorithm_blocks` |
| `web/app/paper/[arxiv_id]/[section_id]/page.tsx` | Render `AlgorithmBlock` cards after `SectionBody` |

### Detailed Change Specifications

#### `lib/models.py`

Add a new frozen dataclass after `MathBlock`:

```python
@dataclass(frozen=True)
class AlgorithmBlock:
    order_idx: int
    caption: str | None          # text from \caption{} inside the algorithm float
    raw_pseudocode: str          # the full \begin{algorithm}...\end{algorithm} source
    pseudocode_text: str         # plain-text version (strip LaTeX commands)
    context_before: str          # 300 chars of surrounding prose
    context_after: str
    explanation: str | None = None        # JSON from DSPy
    explanation_model: str | None = None
```

Extend `Section` by adding:
```python
algorithm_blocks: tuple[AlgorithmBlock, ...] = field(default_factory=tuple)
```

`Section` is frozen, so all existing `dataclasses.replace(section, ...)` calls must
also forward `algorithm_blocks=section.algorithm_blocks` when they do not intend to
change it. Check every `dataclasses.replace(section,` call in `dspy_modules.py` —
there are two in `MathExplainer.forward()`. Both use `dataclasses.replace(section,
math_blocks=new_blocks)`, which will auto-carry `algorithm_blocks` through because
Python's `dataclasses.replace` copies all unspecified fields.

#### `lib/latex_parse.py`

The environments `algorithm`, `algorithm*`, and `algorithmic` are already in
`_NON_TEXT_ENVS` (line 123-126 of the current file) and are stripped from prose.
This is correct — they should not appear in `plain_text`. They need to be extracted
separately before they are stripped.

Add a module-level regex:
```python
_ALGORITHM_ENV_NAMES = ("algorithm", "algorithm*", "algorithmic", "algorithm2e")
_ALGORITHM_ENV_RE = re.compile(
    r"\\begin\{(algorithm\*?|algorithmic|algorithm2e)\}(.*?)\\end\{\1\}",
    re.DOTALL,
)
```

Add function `_extract_algorithm_caption(block_src: str) -> str | None`:
  - Look for `\caption{...}` inside `block_src` using a brace-aware regex.
  - Return the stripped text content, or `None` if absent.

Add function `_pseudocode_to_text(src: str) -> str`:
  - Strip known algorithmic commands: `\State`, `\If`, `\ElsIf`, `\Else`,
    `\EndIf`, `\For`, `\EndFor`, `\While`, `\EndWhile`, `\Procedure`,
    `\EndProcedure`, `\Function`, `\EndFunction`, `\Return`, `\Require`,
    `\Ensure`, `\Comment`, `\algorithmicindent`.
  - Convert `\COMMENT{...}` → `// ...`.
  - Strip remaining LaTeX commands via the existing fallback regex.
  - Preserve indentation structure by keeping leading whitespace.

Add function `_build_algorithm_blocks(latex_body: str) -> tuple[AlgorithmBlock, ...]`:
  - Scan the raw body (before `_NON_TEXT_ENV_RE` strips it) for `_ALGORITHM_ENV_RE`.
  - For each match, extract caption, plain text, and context window (300 chars,
    same as `CONTEXT_WINDOW_DEFAULT`).
  - Return a tuple of `AlgorithmBlock` ordered by position.

In `parse_latex_sections()`, call `_build_algorithm_blocks(body)` alongside the
existing `_build_math_blocks(body)` call and pass the result into `Section(...)`.

Critical: `_build_algorithm_blocks` must be called on the **raw** `body` before any
stripping, because `_NON_TEXT_ENV_RE` (used inside `_build_math_blocks`) will have
already erased the algorithm environments from the clean copy.

#### `lib/dspy_signatures.py`

Add a new signature class `ExplainAlgorithmBlock`:

Input fields:
- `paper_title: str`
- `section_title: str`
- `algorithm_caption: str` — the `\caption{}` text, or "Unnamed Algorithm"
- `pseudocode_text: str` — the plain-text pseudocode (stripped LaTeX)
- `context_before: str`
- `context_after: str`

Output fields:
- `purpose: str` — 2-3 sentences: what problem this algorithm solves in the paper
- `inputs_outputs: str` — what the algorithm takes as input and produces as output
- `step_by_step: str` — plain English walkthrough of each major step or loop
- `complexity: str` — time/space complexity if stated or derivable; "Not stated" otherwise
- `key_insight: str` — the core algorithmic idea (e.g. "This is a greedy sweep because...")
- `prerequisites: str` — concepts a reader needs to understand the algorithm

The docstring of the signature should instruct the model to treat pseudocode
commands like `\State`, `\For`, `\If` as structured control flow, not LaTeX artifacts.

#### `lib/dspy_modules.py`

Add `AlgorithmExplainer(dspy.Module)` modeled after `MathExplainer`:

- `__init__`: `self.explain = dspy.ChainOfThought(ExplainAlgorithmBlock)`
- `explain_block(block, paper_title, section_title) -> AlgorithmBlock`
  - Calls `_call_with_tracking(self.explain, ...)` with all six inputs.
  - Serialises output to JSON with keys matching the six output fields.
  - Returns `dataclasses.replace(block, explanation=json_str, explanation_model=...)`.
  - Non-fatal: on exception, returns the original block unchanged.
- `forward(paper, max_blocks=10) -> Paper`
  - Cap at 10 by default (algorithms are expensive to explain; most papers have 1-3).
  - Iterate sections, collect algorithm blocks, explain up to the cap.
  - Rebuild sections via `dataclasses.replace(section, algorithm_blocks=new_blocks)`.
  - The env var `PAPER2MD_MAX_ALGORITHM_BLOCKS` should override the default.

Import `ExplainAlgorithmBlock` from `dspy_signatures` and `AlgorithmBlock` from `models`.

#### `lib/supabase_push.py`

After the existing step 4 (insert `math_blocks`), add step 4.5:

```
# Delete existing algorithm_blocks (cascade from section deletes handles this,
# but make it explicit for clarity if section IDs are stable across reruns)
# Because sections are deleted and re-inserted (step 2), algorithm_blocks
# are already cascade-deleted. Just insert fresh rows.
```

Build `algorithm_rows` list by iterating `paper.sections` and their
`algorithm_blocks`, mapping `section.order_idx` → `section_db_id` from
`section_id_map`. Each row:
```python
{
    "section_id":        section_db_id,
    "order_idx":         block.order_idx,
    "caption":           _s(block.caption),
    "raw_pseudocode":    _s(block.raw_pseudocode),
    "pseudocode_text":   _s(block.pseudocode_text),
    "context_before":    _s(block.context_before),
    "context_after":     _s(block.context_after),
    "explanation":       _s(block.explanation),
    "explanation_model": _s(block.explanation_model),
}
```

Batch insert with the existing `_batches(algorithm_rows, 100)` utility.

#### `summarize_papers.py`

In `process_arxiv_id()`, after the existing `MathExplainer.forward(paper)` call,
add a lazy-loaded `AlgorithmExplainer` call:

```python
def _get_algorithm_explainer():
    from lib.dspy_modules import AlgorithmExplainer
    return AlgorithmExplainer()
```

Call it conditionally, the same way `--no-math-explain` is handled. Add a
`--no-algo-explain` flag using the same argparse pattern.

#### `supabase/migrations/003_algorithm_blocks.sql`

```sql
CREATE TABLE algorithm_blocks (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    section_id        UUID NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
    order_idx         INTEGER NOT NULL,
    caption           TEXT,
    raw_pseudocode    TEXT NOT NULL,
    pseudocode_text   TEXT,
    context_before    TEXT,
    context_after     TEXT,
    explanation       TEXT,          -- JSON: {purpose, inputs_outputs, step_by_step, ...}
    explanation_model TEXT,
    created_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ON algorithm_blocks (section_id);

-- RLS: same policy as math_blocks
ALTER TABLE algorithm_blocks ENABLE ROW LEVEL SECURITY;
CREATE POLICY "anon select" ON algorithm_blocks FOR SELECT USING (true);
-- Inserts handled by service_role key (bypasses RLS)
```

Apply in Supabase SQL editor. Then run `npm run gen:types` to regenerate
`web/lib/supabase/types.ts`.

#### `web/lib/supabase/queries.ts`

Extend `getSectionWithMath` to join `algorithm_blocks`:

```typescript
.select(`
  *,
  math_blocks (*),
  algorithm_blocks (*)
`)
.order("order_idx", { referencedTable: "algorithm_blocks" })
```

Update the `SectionWithMath` type in `web/lib/supabase/types.ts` (post-codegen)
to include `algorithm_blocks: AlgorithmBlock[]`.

#### `web/components/AlgorithmBlock.tsx`

New `'use client'` component. Props interface:

```typescript
interface AlgorithmBlockProps {
  block: AlgorithmBlockType;  // from @/lib/supabase/types
}
```

Render structure:
- Outer card: `border border-zinc-200 dark:border-zinc-700 rounded-lg overflow-hidden my-4`
- Header bar: shows caption (or "Algorithm") + optional `explanation_model` badge
- Pseudocode body: `<pre>` with `font-mono text-sm` class, `whitespace-pre-wrap`,
  renders `block.pseudocode_text`
- Toggle button: "Explanation" collapsible, identical pattern to `MathBlock.tsx`
- `ExplanationPanel`: renders the six JSON fields from `explanation` using
  `ProseWithMath` for each value. Fields: Purpose, Inputs / Outputs, Step-by-step,
  Complexity, Key insight, Prerequisites.

Do NOT use KaTeX here — pseudocode does not contain math delimiters.

#### `web/app/paper/[arxiv_id]/[section_id]/page.tsx`

After the `<SectionBody>` rendering, add an `AlgorithmSection` block:

```typescript
const algorithmBlocks = (section as SectionWithMath & { algorithm_blocks?: AlgorithmBlockType[] }).algorithm_blocks ?? [];

{algorithmBlocks.length > 0 && (
  <div className="mt-8">
    <h2 className="text-lg font-semibold mb-4">Algorithms</h2>
    <div className="space-y-4">
      {algorithmBlocks.map((block) => (
        <AlgorithmBlock key={block.id} block={block} />
      ))}
    </div>
  </div>
)}
```

Import `AlgorithmBlock` from `@/components/AlgorithmBlock`.

### Implementation Order

1. DB migration (`003_algorithm_blocks.sql`) — apply in Supabase, regenerate types
2. `lib/models.py` — add `AlgorithmBlock` dataclass + extend `Section`
3. `lib/latex_parse.py` — add detection and extraction functions
4. `lib/dspy_signatures.py` — add `ExplainAlgorithmBlock`
5. `lib/dspy_modules.py` — add `AlgorithmExplainer`
6. `lib/supabase_push.py` — add algorithm_blocks insert step
7. `summarize_papers.py` — wire in `AlgorithmExplainer` call
8. `web/lib/supabase/queries.ts` — extend join
9. `web/components/AlgorithmBlock.tsx` — new component
10. `web/app/paper/[arxiv_id]/[section_id]/page.tsx` — render panel

### Gotchas and Design Decisions

**Detection before stripping:** `_NON_TEXT_ENVS` already includes `algorithm`,
`algorithm*`, and `algorithmic`, meaning `_build_math_blocks` already works on a
body where those are blanked out. `_build_algorithm_blocks` must run on the
**original** body before it is cleaned. In `parse_latex_sections`, the call order
must be `_build_algorithm_blocks(body)` first, then `_build_math_blocks(body)`.

**`algorithm2e` package:** Some papers use `algorithm2e` which has different
command names (`\KwIn`, `\KwOut`, `\KwRet`, `\ForEach`). The `_pseudocode_to_text`
stripper should handle both sets of commands.

**`algorithmic` vs `algorithm`:** The `algorithm` float wraps the `algorithmic`
environment. A paper may have `\begin{algorithm}...\begin{algorithmic}...\end{algorithmic}...\end{algorithm}`.
The outer `algorithm` match already captures the full block including the inner
`algorithmic`. Do not double-extract — only match the outermost `algorithm`/`algorithm*`
float; the standalone `algorithmic` case (without an outer float) should be matched
only if no enclosing `algorithm` was found.

**Cap at 10:** Algorithm explanations are LLM-expensive (pseudocode can be long).
`PAPER2MD_MAX_ALGORITHM_BLOCKS=10` is a safe default. The env var should follow the
same `os.environ.get` pattern as `PAPER2MD_MAX_MATH_BLOCKS`.

**Section cascade delete:** Because sections are deleted and re-inserted in
`push_paper`, all `algorithm_blocks` referencing those section IDs are already
cascade-deleted via `ON DELETE CASCADE`. No explicit delete step is needed before
insert, unlike a true upsert scenario.

---

## Feature 2: Prerequisites Dependency Graph (Frontend Only)

### Architecture Overview

No backend changes. The `prerequisites` field already exists inside every
`math_blocks.explanation` JSON blob (stored as a `TEXT` column). The plan is to:
1. Parse the `prerequisites` string out of each block's explanation on the server.
2. Aggregate them into a deduplicated, sorted list at the section level.
3. Render a sticky "Prerequisites" panel in the section page sidebar or above the
   math content, showing each concept as a badge with a tooltip.

Because this is purely frontend and the data is already in the DB rows returned by
`getSectionWithMath`, no query changes or migrations are needed.

### Files to Create

| Path | Purpose |
|------|---------|
| `web/components/PrerequisitesPanel.tsx` | Client component: badge grid of prerequisites |
| `web/lib/prerequisites.ts` | Pure utility: parse + aggregate + deduplicate prerequisites |

### Files to Modify

| Path | What changes |
|------|-------------|
| `web/app/paper/[arxiv_id]/[section_id]/page.tsx` | Extract prerequisites on server side; pass to `PrerequisitesPanel` |

### Detailed Change Specifications

#### `web/lib/prerequisites.ts`

Export two pure functions:

```typescript
// Parse a single prerequisites string from a math block explanation.
// Returns an array of individual concept strings.
export function parsePrerequisiteString(raw: string): string[]

// Aggregate prerequisites across all math blocks in a section.
// Returns a deduplicated, sorted array.
export function aggregatePrerequisites(
  mathBlocks: Array<{ explanation: string | null }>
): string[]
```

`parsePrerequisiteString` implementation strategy:
- The `prerequisites` field is prose, not a structured list. Example value:
  "The reader needs basic measure theory, the Radon–Nikodym theorem, and
  familiarity with normalizing flows as introduced in Section 2."
- Split on `, ` and `; ` and ` and ` to tokenise. Filter tokens shorter than 4
  characters. Trim whitespace and trailing periods from each token.
- Additionally, detect comma-separated sequences preceded by phrases like
  "needs", "requires", "must know", "familiarity with", "knowledge of".
- This is heuristic — precision matters more than recall. A concept that is split
  incorrectly into two halves is worse than a concept that is not split at all.
  Use conservative splitting: prefer whole-sentence extraction if no separator is found.

`aggregatePrerequisites` implementation:
- For each math block: parse `JSON.parse(block.explanation)?.prerequisites ?? ""`.
- Collect all tokens from `parsePrerequisiteString`.
- Deduplicate by lowercased value.
- Sort alphabetically.
- Cap at 30 entries to avoid visual overflow.

#### `web/components/PrerequisitesPanel.tsx`

This is a Server Component (no `'use client'` needed — no state, no events).

Props:
```typescript
interface PrerequisitesPanelProps {
  prerequisites: string[];  // from aggregatePrerequisites()
}
```

Render structure:
- Collapsible `<details>` element (native HTML, no JS needed, accessible).
- `<summary>` label: "Prerequisites for this section" + count badge.
- Badge grid: each prerequisite rendered as a `<span>` with
  `bg-blue-50 dark:bg-blue-950 text-blue-700 dark:text-blue-300 text-xs px-2 py-0.5 rounded-full border border-blue-200 dark:border-blue-800`.
- Empty state: if `prerequisites.length === 0`, render nothing (return `null`).
- Place the panel between the breadcrumb and the `<h1>` section title in the layout.

Do not use any external graph library. The original prompt says "visual prerequisites
panel" but given the data format (a prose field, not a structured graph of named
nodes), a badge-cloud is the correct interpretation. A proper graph would require
structured prerequisite data (named nodes with edges) that does not exist.

If the team later wants a true graph, the `prerequisites` field in the DSPy signature
would need to be changed to output structured JSON (array of concept strings), and a
library like `d3-force` or `react-flow` could be introduced. That is out of scope here.

#### `web/app/paper/[arxiv_id]/[section_id]/page.tsx`

In `SectionPage`, after fetching `section` and `paper`:

```typescript
import { aggregatePrerequisites } from "@/lib/prerequisites";
import { PrerequisitesPanel } from "@/components/PrerequisitesPanel";

const mathBlocks = section.math_blocks ?? [];
const prerequisites = aggregatePrerequisites(mathBlocks);
```

Insert `<PrerequisitesPanel prerequisites={prerequisites} />` between the breadcrumb
nav and the `<h1>` heading in the JSX. This keeps it above the fold before the user
scrolls into the math content.

### Implementation Order

1. `web/lib/prerequisites.ts` — pure utility (no deps, testable in isolation)
2. `web/components/PrerequisitesPanel.tsx` — Server Component, depends on #1's type
3. `web/app/paper/[arxiv_id]/[section_id]/page.tsx` — wire in the panel

### Gotchas and Design Decisions

**Data quality is variable.** The `prerequisites` field is LLM-generated prose.
Some blocks will say "Not part of a proof" (copy-pasted from `proof_role` field) or
"No special prerequisites are needed." The parsing function must filter these
noise phrases. Add a blocklist: if the cleaned string matches phrases like
"no special", "none required", "standard undergraduate", it should be excluded.

**Older rows lack the field.** Math blocks processed before the `prerequisites`
output field was added (pre-Phase 3) will have `explanation` JSON without the key.
`aggregatePrerequisites` must guard with `?.prerequisites ?? ""` and return `[]`
gracefully — the panel simply will not render.

**`<details>` is the right primitive.** Using a `<details>/<summary>` element
means zero client JS for the toggle. The section page already has a client
component (`MathBlock`), but the prerequisites panel itself does not need to be
one. This avoids adding another client bundle entry.

**No graph structure in current data.** The plan avoids `react-flow` or `d3`.
If the team later wants to show "Theorem A requires Lemma B which requires Definition C",
that requires changing the DSPy signature to output a proper adjacency list —
a separate feature.

---

## Feature 3: Citation Extraction and Auto-Queue

### Architecture Overview

The LaTeX source already lives in memory during `fetch_arxiv_latex_full`. The plan
adds a citation extraction step that parses `\bibitem` / `.bib` entries from the
full merged LaTeX source, identifies ArXiv IDs in URLs, and stores them as a
`paper_citations` junction table. The web UI adds a "Referenced Papers" section
on the paper detail page with a per-citation queue button (reusing `QueueForm`
logic).

Two separate concerns:
1. **Python pipeline:** extract citations during processing and push to DB.
2. **Web UI:** display citations on the paper page with queue-or-visit buttons.

The auto-queue aspect is deliberate: clicking "Queue" on a citation fires the same
`POST /api/queue` endpoint used by `QueueForm`, so no new API route is needed.

### Files to Create

| Path | Purpose |
|------|---------|
| `lib/citation_extract.py` | Parse `\bibitem` / `.bib` entries and extract ArXiv IDs |
| `supabase/migrations/004_citations.sql` | `paper_citations` table + RLS |
| `web/components/CitationsPanel.tsx` | Client component: citation list with queue buttons |

### Files to Modify

| Path | What changes |
|------|-------------|
| `lib/models.py` | Add `Citation` frozen dataclass; add `citations` field to `Paper` |
| `lib/supabase_push.py` | Add step 4.7: delete+insert `paper_citations` |
| `summarize_papers.py` | Call `extract_citations()` and attach to paper after LaTeX fetch |
| `web/lib/supabase/types.ts` | Add `PaperCitation` row type (regenerate) |
| `web/lib/supabase/queries.ts` | Add `getCitationsForPaper(client, paperId)` |
| `web/app/paper/[arxiv_id]/page.tsx` | Fetch citations; pass to `PaperSplitView` or render directly |
| `web/components/PaperSplitView.tsx` | Accept and forward citations to the detail panel |

### Detailed Change Specifications

#### `lib/models.py`

Add a new frozen dataclass:

```python
@dataclass(frozen=True)
class Citation:
    order_idx: int
    cite_key: str           # the \bibitem key, e.g. "vaswani2017attention"
    raw_bib_entry: str      # full \bibitem{...} ... block, up to 1000 chars
    arxiv_id: str | None    # extracted ArXiv ID, or None if not an ArXiv paper
    title: str | None       # extracted title from bibentry, best-effort
    url: str | None         # any URL found in the entry
```

Extend `Paper`:
```python
citations: tuple[Citation, ...] = field(default_factory=tuple)
```

`Paper` is frozen; all `dataclasses.replace(paper, ...)` calls throughout
`dspy_modules.py` and `summarize_papers.py` do not need to be changed because
unspecified fields are preserved.

#### `lib/citation_extract.py`

This is a new module. It works on the `full_source` string (the merged LaTeX
**including** the preamble and bibliography section) returned by `fetch_arxiv_latex_full`.

**`extract_citations(full_source: str) -> tuple[Citation, ...]`** — public API.

Internal steps:

1. **Locate bibliography:** Look for `\begin{thebibliography}...\end{thebibliography}`
   or a `.bib` file reference. The full merged source already inlines `\input{refs.bib}`
   style includes, so if the `.bib` content was included it will be present as-is.

2. **Split bibitem blocks:** Use regex:
   ```python
   re.split(r"(?=\\bibitem)", bib_section)
   ```
   Each chunk starts with `\bibitem[...]{}` or `\bibitem{}`.

3. **Extract cite key:** Pattern `r"\\bibitem\s*(?:\[.*?\])?\s*\{([^}]+)\}"`.

4. **Extract ArXiv ID from each chunk:** Apply these patterns in order (first match wins):
   - Direct URL: `arxiv\.org/abs/([\d]{4}\.\d{4,5}(?:v\d+)?)`
   - Direct URL old format: `arxiv\.org/abs/([a-z-]+/\d{7}(?:v\d+)?)`
   - arXiv label: `arXiv[:\s]+([\d]{4}\.\d{4,5}(?:v\d+)?)`
   - eprint field in BibTeX: `eprint\s*=\s*\{([\d]{4}\.\d{4,5})\}`

   If found, strip version suffix (`v1`, `v2`, etc.) to get the canonical ID.

5. **Extract title:** Pattern `title\s*=\s*[\{"](.*?)[\}"](?:,|\n)` (BibTeX style).
   For `\bibitem` style, use the first sentence of the block after the cite key block.
   Limit to 200 chars.

6. **Extract URL:** First URL matching `https?://[^\s\}]+` in the chunk.

7. Build `Citation(order_idx=idx, cite_key=..., raw_bib_entry=chunk[:1000], ...)`.

8. Return tuple ordered by position.

**Handle the case where no bibliography section exists:** Return `()` immediately.

**Handle `.bib` file format:** Some papers include raw BibTeX blocks (not `\bibitem`).
Detect by presence of `@article{`, `@inproceedings{`, `@misc{` etc. In that case,
split on `^@` and use the BibTeX field extraction patterns for title, eprint/url.

#### `supabase/migrations/004_citations.sql`

```sql
CREATE TABLE paper_citations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    paper_id        UUID NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    order_idx       INTEGER NOT NULL,
    cite_key        TEXT NOT NULL,
    raw_bib_entry   TEXT,
    arxiv_id        TEXT,           -- NULL if not an ArXiv paper
    title           TEXT,
    url             TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (paper_id, cite_key)
);

CREATE INDEX ON paper_citations (paper_id);
CREATE INDEX ON paper_citations (arxiv_id) WHERE arxiv_id IS NOT NULL;

ALTER TABLE paper_citations ENABLE ROW LEVEL SECURITY;
CREATE POLICY "anon select" ON paper_citations FOR SELECT USING (true);
```

Apply in Supabase SQL editor. Run `npm run gen:types`.

#### `lib/supabase_push.py`

After math_blocks insert (step 4), add step 4.7:

```python
# ── 4.7. Insert paper_citations ─────────────────────────────────────────────
# First delete existing (safe because paper_id is stable across reruns,
# and we ON CONFLICT DO NOTHING isn't available without a compositekey upsert)
client.table("paper_citations").delete().eq("paper_id", paper_id).execute()

citation_rows = [
    {
        "paper_id":      paper_id,
        "order_idx":     c.order_idx,
        "cite_key":      _s(c.cite_key),
        "raw_bib_entry": _s(c.raw_bib_entry),
        "arxiv_id":      _s(c.arxiv_id),
        "title":         _s(c.title),
        "url":           _s(c.url),
    }
    for c in paper.citations
]

for batch in _batches(citation_rows, 100):
    client.table("paper_citations").insert(batch).execute()
```

Note: unlike `algorithm_blocks`, citations belong to `paper_id` not `section_id`,
so they are NOT cascade-deleted when sections are deleted. An explicit delete
before re-insert is required.

#### `summarize_papers.py`

In `process_arxiv_id()`, after the call to `fetch_arxiv_latex_full` that returns
`(body, full_source)`, add:

```python
from lib.citation_extract import extract_citations
citations = extract_citations(full_source)
paper = dataclasses.replace(paper, citations=citations)
tqdm.write(f"[INFO] Extracted {len(citations)} citations "
           f"({sum(1 for c in citations if c.arxiv_id)} with ArXiv IDs)")
```

This must happen before `push_paper(paper)` is called.

No new CLI flag needed — citation extraction is cheap (pure regex, no LLM) and
should always run for ArXiv papers.

#### `web/lib/supabase/queries.ts`

Add a new query function:

```typescript
export type PaperCitation = Database["public"]["Tables"]["paper_citations"]["Row"];

export async function getCitationsForPaper(
  client: Client,
  paperId: string
): Promise<PaperCitation[]> {
  const { data, error } = await client
    .from("paper_citations")
    .select("*")
    .eq("paper_id", paperId)
    .order("order_idx", { ascending: true });

  if (error) throw new Error(`getCitationsForPaper: ${error.message}`);
  return data ?? [];
}
```

Note: query by `paper_id` (UUID), not `arxiv_id`. The paper page already has the
paper object from `getPaperWithSections`, which includes the `id` field.

#### `web/app/paper/[arxiv_id]/page.tsx`

The page currently passes everything to `<PaperSplitView paper={paper} arxivId={arxiv_id} />`.

Add parallel citation fetch:

```typescript
const [paper, citations] = await Promise.all([
  getPaperWithSections(client, arxiv_id),
  // Citations need paper.id; fetch after paper is known.
]);
```

Because citations require `paper.id`, they cannot be fetched in parallel with the
paper itself. The simplest approach: fetch `paper` first, then citations:

```typescript
const paper = await getPaperWithSections(client, arxiv_id);
if (!paper) notFound();
const citations = await getCitationsForPaper(client, paper.id);
```

Pass `citations` to `PaperSplitView` as a new prop.

#### `web/components/PaperSplitView.tsx`

Read the file before modifying. The component receives the paper and renders the
section list + PDF viewer. Add a `citations` prop to its interface and render
`<CitationsPanel citations={citations} />` at the bottom of the left (content) pane,
below the section list.

#### `web/components/CitationsPanel.tsx`

This is a `'use client'` component because the queue button fires a `fetch` POST.

Props:
```typescript
interface CitationsPanelProps {
  citations: PaperCitation[];
}
```

Internal state per citation: `queued: boolean`, `loading: boolean`.

Render structure:
- Section heading: "References" with count badge.
- For ArXiv citations: show title (or `cite_key` if no title), ArXiv badge linking to
  `https://arxiv.org/abs/{arxiv_id}`, and a "Queue" button.
  - "Queue" button calls `POST /api/queue` with `{ arxiv_id }`.
  - On success: show a checkmark "Queued" label. On error: show "Failed".
  - If the `arxiv_id` already exists in the DB (the API returns `{ existing: true }`),
    show a "View" link to `/paper/{arxiv_id}` instead of the Queue button.
- For non-ArXiv citations: show title (or `cite_key`), URL as a link if present,
  no queue button.
- Limit initial display to 20 citations with a "Show all N references" button for
  the remainder, using local state.
- Empty state: if `citations.length === 0`, render nothing.

**Queue button design decision:** Do not call `triggerProcessing()` (GitHub dispatch)
directly from the client. Call `POST /api/queue` and let the existing route handler
trigger the dispatch. This keeps the GitHub token server-side only.

### Implementation Order

1. DB migration (`004_citations.sql`) — apply, regenerate types
2. `lib/models.py` — add `Citation` dataclass + extend `Paper`
3. `lib/citation_extract.py` — new extraction module
4. `lib/supabase_push.py` — add citation insert step
5. `summarize_papers.py` — wire in citation extraction after LaTeX fetch
6. `web/lib/supabase/queries.ts` — add `getCitationsForPaper`
7. `web/components/CitationsPanel.tsx` — new client component
8. `web/components/PaperSplitView.tsx` — add citations prop + render panel
9. `web/app/paper/[arxiv_id]/page.tsx` — fetch citations and pass down

### Gotchas and Design Decisions

**`full_source` vs `body`:** `fetch_arxiv_latex_full` returns `(body, full_source)`.
The bibliography is almost always outside `\begin{document}...\end{document}` in
the original file but gets inlined during `_resolve_includes`. Check: `full_source`
is the merged file **before** `_strip_preamble`, so bibliographies at the end of
the document body will be present. The `body` returned by the public API has the
preamble stripped but the bibliography at the end of `\end{document}` is typically
inside the document body, so `body` should work too. Using `full_source` is safer
because some papers put the bibliography in `\bibliography{}` files inlined by
`\input{refs.bib}`.

In `process_arxiv_id()` in `summarize_papers.py`, the current code unpacks only
the body:
```python
latex_source = fetch_arxiv_latex(arxiv_id)  # public wrapper returning body only
```
The `full_source` is available via `fetch_arxiv_latex_full`. The implementer must
switch to `fetch_arxiv_latex_full` and keep both return values.

**Deduplication of cited ArXiv IDs vs the paper itself:** If a paper cites itself
(self-citation), skip it. Add a guard: `if c.arxiv_id == arxiv_id: continue`.

**ArXiv ID versions:** Strip `v1`/`v2` suffixes before storing so that
`paper_citations.arxiv_id` always matches the canonical ID stored in `papers.arxiv_id`.

**`UNIQUE (paper_id, cite_key)` constraint:** If the pipeline is re-run, the
explicit `DELETE + INSERT` pattern handles this cleanly. Do not use `ON CONFLICT DO UPDATE`
because the goal is a clean re-run, not an incremental update.

**Volume:** Major ML papers may have 80-200 references. Store all of them, but the UI
caps the initial visible list at 20. The `order_idx` column preserves bibliography order.

**Non-ArXiv citations are still useful:** Show them as plain reference entries. This
is important for papers that cite books, IEEE/ACM conference papers, etc. The queue
button simply does not appear.

**`getPaperWithSections` already returns `paper.id`:** The sequential fetch
(paper first, then citations by `paper.id`) is only one extra DB round-trip and is
acceptable. Do not embed citations in `getPaperWithSections` as a nested join —
citations are not needed on all pages that call that query.

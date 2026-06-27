# How References and Prerequisites Are Captured

## Prerequisites

**Source**: The LLM, not the LaTeX parser.

The `ExplainMathBlock` DSPy signature (`lib/dspy_signatures.py`) asks the LLM to produce a `prerequisites` field for every math block it explains:

> *"List the mathematical concepts and definitions a reader must already know to understand this expression"* — e.g. "the Radon–Nikodym theorem", "chain rule for matrix calculus"

The LLM returns this as a prose string stored inside the `explanation` JSON column in the `math_blocks` table:

```json
{
  "what_it_computes": "...",
  "prerequisites": "the chain rule, linear projections, softmax function...",
  "..."
}
```

At render time, `web/lib/prerequisites.ts` (`aggregatePrerequisites`) parses those prose strings across **all math blocks in a section**, splits on commas/semicolons/conjunctions, deduplicates, and passes the resulting list to `PrerequisitesPanel`, which displays them as badge pills.

**There is no separate DB column** — prerequisites are re-parsed from the explanation JSON on every page load.

### Pipeline

```
LaTeX source
  └─► latex_parse.py      — extracts math blocks (env_type, latex_expr, context)
        └─► dspy_modules.py  — MathExplainer calls LLM with ExplainMathBlock signature
              └─► supabase_push.py  — stores explanation JSON in math_blocks.explanation
                    └─► prerequisites.ts  — parses prerequisites field at read time
                          └─► PrerequisitesPanel.tsx  — renders badges with ProseWithMath
```

---

## References (Citations)

**Source**: Regex parsing of the LaTeX source — no LLM involved.

`lib/citation_extract.py` (`extract_citations`) scans the merged LaTeX source for the bibliography section and handles two formats:

| Format | Trigger |
|--------|---------|
| `\bibitem{key}` style | `\begin{thebibliography}` block present |
| BibTeX `@article{key,` style | `.bib` file inlined via `\input{}` |

For each entry it extracts:

| Field | Method |
|-------|--------|
| `cite_key` | From `\bibitem{key}` or `@article{key,` |
| `arxiv_id` | Regex on URLs, `arXiv:` labels, `eprint=` BibTeX field (version suffix stripped) |
| `title` | BibTeX `title=` field, or first sentence of `\bibitem` text |
| `url` | First `https://` URL in the entry |
| `raw_bib_entry` | First 1000 chars of the raw entry text |

These are stored in the `paper_citations` table (one row per reference) and displayed in `CitationsPanel` on the paper overview page (`/paper/[arxiv_id]`).

### Pipeline

```
LaTeX source (merged with \input{} resolved)
  └─► citation_extract.py   — regex parses \bibitem / BibTeX @entry blocks
        └─► supabase_push.py   — DELETE + INSERT into paper_citations table
              └─► queries.ts (getCitationsForPaper)  — fetched by paper page
                    └─► CitationsPanel.tsx  — renders collapsible reference list
```

---

## Key Differences

| | Prerequisites | Citations |
|---|---|---|
| **Source** | LLM-generated prose | Regex on LaTeX source |
| **Storage** | Inside `math_blocks.explanation` JSON | Dedicated `paper_citations` table |
| **Granularity** | Per math block → aggregated per section | Per paper (bibliography) |
| **Parsed at** | Read time (frontend) | Write time (Python pipeline) |
| **Accuracy** | Depends on LLM output quality | Depends on bibliography format |

# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

---

## Repository Layout

```
paper2md/
├── lib/                        # Python processing core
├── web/                        # Next.js web app (deployed to Vercel)
├── supabase/migrations/        # SQL schema + RLS
├── .github/workflows/          # GitHub Actions pipeline
├── scripts/                    # One-time setup scripts
├── papers/                     # Sample PDFs
├── summarize_papers.py         # Main CLI entry point
├── explain_math_only.py        # Run math-explanation step only
├── repair_plain_text.py        # Repair plain_text for existing DB rows
├── prompts.json                # DSPy prompt config (runtime-editable)
└── requirements.txt
```

---

## Python Backend

### Setup

```bash
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt
cp .env.local .env   # fill in keys (see Environment Variables below)
```

### Running the CLI

```bash
# Process a single ArXiv paper and push to Supabase
python summarize_papers.py --arxiv-id 2301.07984 --push-supabase

# Process all pending papers in Supabase queue
python summarize_papers.py --process-pending --push-supabase

# Batch from a file of IDs
python summarize_papers.py --arxiv-list ids.txt --push-supabase

# PDF directory mode (legacy — reads papers/, writes output/PAPERS_SUMMARY.md)
python summarize_papers.py --papers-dir papers --out output/PAPERS_SUMMARY.md

# Force re-process already-complete papers
python summarize_papers.py --arxiv-id 2301.07984 --push-supabase --force

# Skip math explanation step
python summarize_papers.py --arxiv-id 2301.07984 --no-math-explain

# Cache control
python summarize_papers.py --no-cache      # skip cache, re-extract
python summarize_papers.py --clear-cache   # wipe cache then run
```

Set `PAPER2MD_DEBUG_TRACE=1` for full tracebacks on failures.

### Pipeline (per paper)

```
arxiv_source.py        Download tar.gz → find main .tex → merge \input{}
latex_parse.py         Split sections, extract math blocks + context windows
dspy_modules.py        PaperSummarizer: chunk → map SummarizeChunk → reduce
dspy_modules.py        MathExplainer: ExplainMathBlock per block (cap: 50)
supabase_push.py       UPSERT papers, DELETE+INSERT sections+math_blocks
```

### `lib/` Modules

| File | Responsibility | Key public API |
|------|---------------|----------------|
| `models.py` | Frozen dataclasses | `Paper`, `Section`, `MathBlock`, `ExtractedContent` |
| `pdf_extract.py` | PDF text + title | `extract_paper_from_pdf(pdf_path, max_pages)` |
| `text_clean.py` | Pure normalization | `clean_pdf_text()`, `normalize_for_sentences()` |
| `content_analysis.py` | Metadata from text | `extract_structured_content()`, `chunk_text_for_llm()` |
| `cache.py` | SHA-256 hash cache | `PaperCache` — `.get_cached()`, `.store()`, `.clear()` |
| `arxiv_source.py` | ArXiv LaTeX download | `fetch_arxiv_latex_full(arxiv_id) → (body, full_src)` |
| `latex_parse.py` | Section + math extraction | `parse_latex_sections(latex_source) → tuple[Section]` |
| `dspy_config.py` | Provider setup + fallback | `configure_dspy() → str` |
| `dspy_signatures.py` | Typed LLM contracts | `ExplainMathBlock`, `SummarizeChunk`, `ReduceToFinalSummary` |
| `dspy_modules.py` | DSPy CoT modules | `MathExplainer.forward(paper)`, `PaperSummarizer.forward(paper)` |
| `supabase_push.py` | DB writes | `push_paper(paper)`, `fetch_pending_arxiv_ids()`, `mark_processing()` |
| `summarization.py` | *Legacy* OpenAI summarizer | Replaced by `dspy_modules.py` — do not use for new work |

### Data Models

```python
Paper(title, text, pdf_path, arxiv_id, source_type, summary_md, sections)
Section(order_idx, title, plain_text, raw_latex, math_blocks)
MathBlock(order_idx, env_type, latex_expr, context_before, context_after,
          explanation, explanation_model)
# explanation is JSON: {what_it_computes, symbol_meanings, derivation,
#                        intuition, paper_relevance}
# summary_md is JSON: {tldr, problem, approach, results, takeaways, limitations}
```

`Paper` and `Section` are frozen — mutate via `dataclasses.replace()`.

### LLM Provider Priority

```
1. Gemini 2.0 Flash      GEMINI_API_KEY         1,500 req/day free
2. Groq llama-3.3-70b    GROQ_API_KEY           1,000 req/day free
3. OpenRouter (free)     OPENROUTER_API_KEY       ~200 req/day free
4. OpenAI gpt-4o-mini    OPENAI_API_KEY           paid fallback
```

Force a provider: `PAPER2MD_LLM_PROVIDER=gemini` (or `groq`, `openrouter`, `openai`).

### Key Design Decisions (Python)

- **Cache stores extracted text, never summaries** — text is deterministic; summaries go stale with prompt/model changes.
- **prompts.json is runtime-editable** — change `chunk_prompt`, `reduce_prompt`, `chunk_max_chars`, `max_chunks` without code changes.
- **supabase_push uses NullPool** — correct for short-lived CLI/Actions runs; do not switch to a pooling mode.
- **MathExplainer prioritises named envs** (equation/align/gather) over inline `$...$`; capped at `PAPER2MD_MAX_MATH_BLOCKS` (default 50).
- **ArXiv rate-limit respect** — `arxiv_source.py` sleeps 30s between downloads; exponential backoff on 429.

### Adding a PDF with broken title metadata

```python
# lib/pdf_extract.py
TITLE_OVERRIDES: dict[str, str] = {
    "filename.pdf": "Actual Paper Title",
}
```

---

## Web App (`web/`)

### Setup

```bash
cd web
npm install
cp .env.local.example .env.local   # fill in NEXT_PUBLIC_SUPABASE_* + GITHUB_* tokens
npm run dev                         # http://localhost:3000
```

### Stack

- **Next.js 15** App Router, React 19, TypeScript strict
- **Tailwind v4** — uses `@import "tailwindcss"` in globals.css + `@tailwindcss/postcss`
- **Supabase SSR v0.10.3** (`@supabase/ssr`) — server + browser clients
- **KaTeX** — loaded via CDN in `layout.tsx <head>`, rendered client-side in `MathBlock`
- **PDF.js** (`pdfjs-dist`) — PDF side-by-side viewer in `PaperSplitView`

### Pages

| Route | File | Purpose |
|-------|------|---------|
| `/` | `app/page.tsx` | Hero + SearchBar + QueueForm + 20 recent papers |
| `/paper/[arxiv_id]` | `app/paper/[arxiv_id]/page.tsx` | Paper overview + section list + PDF split view |
| `/paper/[arxiv_id]/[section_id]` | `app/paper/[arxiv_id]/[section_id]/page.tsx` | Section detail + math blocks |

### API Routes

| Method | Route | Purpose |
|--------|-------|---------|
| GET | `/api/search?q=` | Autocomplete — searches `title` + `arxiv_id` in Supabase |
| GET | `/api/arxiv?q=` | Proxy ArXiv Atom API title search |
| POST | `/api/queue` | Enqueue paper (`status=pending`) + trigger `workflow_dispatch` |
| POST | `/api/like` | Like paper → generate MD → commit to GitHub kb → update DB |
| GET | `/api/pdf/[arxiv_id]` | Proxy arxiv.org PDF (strips `X-Frame-Options` for embedding) |

### Key Components

| Component | Type | Purpose |
|-----------|------|---------|
| `QueueForm` | `'use client'` | Two-tab form: ArXiv search + paste ID/URL |
| `SearchBar` | `'use client'` | Debounced autocomplete (250ms), keyboard nav |
| `MathBlock` | `'use client'` | KaTeX render + expandable explanation panel |
| `PaperSplitView` | `'use client'` | Side-by-side: section list + live PDF |
| `PdfViewer` | `'use client'` | PDF.js document manager |
| `LikeButton` | `'use client'` | Optimistic star → POST /api/like → show GitHub link |
| `ProcessButton` | `'use client'` | Manual trigger via `triggerProcessing()` |
| `PaperHeader` | Server | Title, authors, abstract |
| `SectionCard` | Server | Section summary card |
| `ProseWithMath` | `'use client'` | Rich text with inline KaTeX rendering |

### Key Utilities (`web/lib/`)

```typescript
// arxiv-id.ts
extractArxivId(input: string): string | null
// Accepts: "2301.07984", "2301.07984v2", arxiv.org URLs, alphaxiv.org URLs

// github-dispatch.ts
triggerProcessing(arxiv_id: string): Promise<DispatchResult>
// Calls GitHub Actions workflow_dispatch REST API

// github-publish.ts
generatePaperMarkdown(paper, sections): string
commitMarkdownToGitHub(arxiv_id, markdown): Promise<CommitResult>
// PUT to GitHub Contents API — creates or updates papers/{arxiv_id}.md

// supabase/queries.ts  (all accept a Supabase client as first arg)
getRecentPapers(), getPaperByArxivId(), getPaperWithSections(),
getSectionWithMath(), searchPapers(), getAllCompletePaperIds(), queuePaper()

// supabase/server.ts
createClient()        // anon key — server components + route handlers
createServiceClient() // service_role key — like route, write operations
```

### Supabase Auth Pattern

```typescript
// Server components & route handlers
import { createClient } from '@/lib/supabase/server'  // relative to web/
const supabase = await createClient()  // MUST await — Next.js 15 async cookies

// Client components only
import { createClient } from '@/lib/supabase/client'
const supabase = createClient()  // no await
```

No user auth in v1 — all actions are anonymous. Service role key is used server-side only (in `/api/like`) to bypass RLS for write operations.

### Next.js 15 Params

```typescript
// params and searchParams are Promises in Next.js 15
export default async function Page({
  params,
}: {
  params: Promise<{ arxiv_id: string }>
}) {
  const { arxiv_id } = await params
}
```

### Useful Scripts

```bash
npm run type-check          # tsc --noEmit
npm run gen:types           # regenerate lib/supabase/types.ts from live DB schema
```

---

## Database Schema

Three tables in Supabase PostgreSQL:

**`papers`** — one row per paper
```
arxiv_id TEXT UNIQUE, title, abstract, authors TEXT[], source_type,
status (pending|processing|complete|error), error_msg, summary_md (JSON),
liked BOOLEAN, liked_at TIMESTAMPTZ, github_md_url TEXT, created_at, updated_at
```

**`sections`** — ordered sections per paper
```
paper_id → papers.id, order_idx, title, plain_text, raw_latex, has_math
UNIQUE (paper_id, order_idx)
```

**`math_blocks`** — math blocks per section
```
section_id → sections.id, order_idx, env_type, latex_expr,
context_before (300 chars), context_after (300 chars),
explanation (JSON), explanation_model
```

**RLS policies** (applied in `002_indexes_rls.sql`):
- Anon key: SELECT all, INSERT pending papers only
- Service role key: bypasses RLS — used by Python worker + `/api/like`

Migrations are in `supabase/migrations/` and are applied manually via the Supabase SQL editor or `scripts/setup_supabase.sh`.

---

## GitHub Actions

File: `.github/workflows/process_pending.yml`

Triggers:
- **Cron**: `0 */6 * * *` (every 6 hours)
- **workflow_dispatch**: manual or via REST API from `/api/queue`
  - Optional input: `arxiv_id` — if set, processes only that paper

Required GitHub Secrets:
```
GEMINI_API_KEY, GROQ_API_KEY, OPENROUTER_API_KEY, OPENAI_API_KEY
SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
PAPER2MD_LLM_PROVIDER=gemini
PAPER2MD_MAX_MATH_BLOCKS=50
```

The repo must be **public** for unlimited free Actions minutes.

---

## Environment Variables

### Python (`.env`)
```bash
PAPER2MD_LLM_PROVIDER=gemini       # primary provider
GEMINI_API_KEY=
GROQ_API_KEY=
OPENROUTER_API_KEY=
OPENAI_API_KEY=                     # paid fallback
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=          # service_role key (NOT anon key)
PAPER2MD_MAX_MATH_BLOCKS=50
PAPER2MD_DEBUG_TRACE=0              # set to 1 for full tracebacks
```

### Next.js (`web/.env.local`)
```bash
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=   # anon key — safe to expose
GITHUB_DISPATCH_TOKEN=                  # PAT: Actions read/write (triggers pipeline)
GITHUB_KB_TOKEN=                        # PAT: Contents write (commits .md files)
GITHUB_KB_OWNER=                        # GitHub username/org
GITHUB_KB_REPO=                         # e.g. "paper2md-kb"
```

> **Note**: `SUPABASE_SERVICE_ROLE_KEY` in `.env.local` must be the real service_role key, not the anon key. Get it from Supabase dashboard → Project Settings → API → service_role.

---

## Pending Work (Phase 4 & 5)

### Phase 4 — Automation
- [ ] Create GitHub PAT (Actions: read/write), add as `GITHUB_DISPATCH_TOKEN` to Vercel
- [ ] Deploy to Vercel — Root Directory: `web/`, add env vars
- [ ] Make repo public (enables unlimited free Actions minutes)

### Phase 5 — Like / Publish to GitHub
- [ ] Create `paper2md-kb` public GitHub repo
- [ ] DB migration — add `liked`, `liked_at`, `github_md_url` columns (already in `001_schema.sql` in plans, but verify they are applied)
- [ ] Create GitHub PAT for kb repo (Contents: read/write), add `GITHUB_KB_*` env vars

### Misc
- [ ] Replace placeholder titles in DB for 3 papers that have `arxiv_id` stored as title
- [ ] Add `GEMINI_API_KEY` to `.env` and GitHub Secrets

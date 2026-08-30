# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

---

## Architecture

paper2md is an **AI-agent-native app** where a Claude LLM calls structured MCP tools to
process papers, read sections, explain math, surface prerequisites, and recommend references.

```
User → /chat → POST /api/chat → Claude Sonnet 4.6
                                   ↕ MCP tools (maxSteps: 20)
                   paper-processor-mcp  (Python / Modal)          — process, parse, explain
                   paper-reader-mcp     (TypeScript / CF Workers)  — sections, math, prereqs
                   arxiv-search-mcp     (TypeScript / CF Workers)  — discover papers
                   math-to-code-mcp     (TypeScript / CF Workers)  — formula → Python code
```

**Batch processing** — Modal `process_pending_batch()` cron (every 6h) replaced GitHub Actions.
**Queue fallback** — `/api/queue` fires MCP when `PAPER_PROCESSOR_MCP_URL` is set; falls back
to GitHub Actions `workflow_dispatch` otherwise.
**Health** — `GET /api/health` pings all configured MCP server `/health` endpoints.

---

## Repository Layout

```
paper2md/
├── lib/                        # Python processing core
├── mcp-servers/                # MCP server implementations
│   ├── paper-processor-mcp/   # Python (Modal) — 5 tools: process, sections, math, algos, status
│   └── paper-reader-mcp/      # TypeScript (CF Workers) — 5 tools: sections, math, prereqs, refs
│   └── arxiv-search-mcp/      # TypeScript (CF Workers) — 3 tools: search, metadata, find-prereqs
├── web/                        # Next.js web app (deployed to Vercel)
│   ├── app/chat/              # Chat interface + tool result cards
│   ├── app/api/chat/          # POST streaming handler (Claude + MCP)
│   ├── app/api/health/        # GET /api/health — pings all MCP servers
│   └── lib/                   # mcp-clients.ts, mcp-dispatch.ts, feature-flags.ts
├── supabase/migrations/        # SQL schema + RLS
├── .github/workflows/          # workflow_dispatch fallback (cron retired → Modal)
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

### Filling missing math explanations

`explain_math_only.py` generates explanations for math blocks already in Supabase
without re-processing the paper. It UPDATEs rows in-place — no sections are deleted.

```bash
# All unexplained blocks across all papers
python explain_math_only.py

# Single paper
python explain_math_only.py --arxiv-id 2407.18384 --max-blocks 300

# Single section (page) — pass the Supabase section UUID
python explain_math_only.py --section-id 479197f5-140e-4c8e-8b08-d79ee62ecd75

# Re-explain blocks that already have explanations
python explain_math_only.py --arxiv-id 2407.18384 --force

# Cap blocks per section (ensures coverage across all sections)
python explain_math_only.py --arxiv-id 2407.18384 --max-blocks-per-section 5

# Textbook framing (changes explanation style)
python explain_math_only.py --arxiv-id 2409.02668 --paper-type textbook
```

Key options: `--min-expr-len` (skip trivial inline exprs, default 6),
`--paper-type` (`research_paper` | `textbook` | `lecture_notes`).

### Debugging section count issues

If a paper shows fewer sections than expected, run the diagnostic script:

```bash
python debug_sections.py <arxiv_id>
```

This prints:
- Raw `\section` / `\subsection` counts in the LaTeX source
- Every match found by `_SECTION_RE`
- Raw `_split_sections()` output with body sizes
- Final `parse_latex_sections()` output with plain text lengths

### Macro expansion — always pass the preamble

`parse_latex_sections(body, preamble)` **requires** the preamble. Papers define
almost all of their macros there (`\newcommand`, `\def`, `\NewDocumentCommand`,
`\DeclarePairedDelimiter`), and `_strip_preamble()` removes it from the body.
Calling `parse_latex_sections(body)` alone leaves those macros unexpanded; they
reach the DB as raw control sequences and KaTeX cannot render them.

Get it via `split_preamble(full_src)` from the second element of
`fetch_arxiv_latex_full()`. `lib/latex_macros.py` handles:

- `\newcommand` / `\renewcommand` / `\providecommand`, including `[n]` and `[n][default]`
- `\def\name#1#2{...}` (undelimited parameters only)
- `\DeclareMathOperator`
- xparse `\NewDocumentCommand` and friends — specs `m`, `o`, `O{d}`, `s`
- mathtools `\DeclarePairedDelimiter` / `\DeclarePairedDelimiterXPP`
- macro-defining wrappers (a macro whose body contains `\newcommand`)

Definitions apply **from the point they appear**, so per-chapter redefinitions
with different arities resolve correctly. expl3-bodied definitions (`\seq_…:Nn`)
expand to nothing but still consume their arguments — they are bookkeeping
commands with no typeset output.

Not handled: delimited-parameter `\def`, and macros from packages that are not
shipped inside the tarball.

**Adaptive splitting**: `latex_parse.py` automatically re-splits any section
body > 30 000 chars on `\subsection` commands. This handles survey/textbook
papers that have few top-level `\section{}` blocks with enormous bodies.

### Pipeline (per paper)

```
arxiv_source.py        Download tar.gz → find main .tex → merge \input{} + local .sty
latex_macros.py        Expand the paper's own macros (preamble + body)
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
| `arxiv_source.py` | ArXiv LaTeX download | `fetch_arxiv_latex_full(arxiv_id) → (body, full_src)`, `split_preamble(full_src)` |
| `latex_macros.py` | Custom macro expansion | `expand_custom_macros(body, *extra_sources)` |
| `latex_parse.py` | Section + math extraction | `parse_latex_sections(body, preamble) → tuple[Section]` |
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
| `/chat` | `app/chat/page.tsx` | AI chat interface (Claude + MCP tools) |
| `/paper/[arxiv_id]` | `app/paper/[arxiv_id]/page.tsx` | Paper overview + section list + PDF split view |
| `/paper/[arxiv_id]/[section_id]` | `app/paper/[arxiv_id]/[section_id]/page.tsx` | Section detail + math blocks |

### API Routes

| Method | Route | Purpose |
|--------|-------|---------|
| GET | `/api/health` | Ping all configured MCP server `/health` endpoints |
| POST | `/api/chat` | Streaming chat handler — Claude Sonnet 4.6 + MCP tools, `maxSteps:20` |
| GET | `/api/search?q=` | Autocomplete — searches `title` + `arxiv_id` in Supabase |
| GET | `/api/arxiv?q=` | Proxy ArXiv Atom API title search |
| POST | `/api/queue` | Enqueue paper (`status=pending`) + trigger MCP or `workflow_dispatch` |
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

// mcp-clients.ts
USE_MCP: boolean                                 // true when all 3 core MCP URLs are set
createAllMCPClients(): Promise<MCPClient[]>      // paper-processor + paper-reader + arxiv-search
createMathToCodeClient(): Promise<MCPClient>     // math-to-code-mcp (optional)

// mcp-dispatch.ts
triggerMCPProcessing(arxivId: string): Promise<void>
// Fire-and-forget: calls process_paper tool on paper-processor-mcp

// feature-flags.ts
flags.USE_PAPER_PROCESSOR_MCP   // true when PAPER_PROCESSOR_MCP_URL is set
flags.USE_PAPER_READER_MCP      // true when PAPER_READER_MCP_URL is set
flags.USE_ARXIV_SEARCH_MCP      // true when ARXIV_SEARCH_MCP_URL is set
flags.SHOW_CHAT_INTERFACE       // true when NEXT_PUBLIC_SHOW_CHAT=true
flags.SHOW_CODE_TOGGLE          // default true; false when NEXT_PUBLIC_SHOW_CODE_TOGGLE=false

// paper-agent-prompt.ts
PAPER_AGENT_SYSTEM_PROMPT: string  // system prompt for /api/chat (tool ordering + style)

// github-dispatch.ts  (fallback when MCP not configured)
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
npm test                    # vitest run — KaTeX helpers, ProseWithMath, render fixture
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

The scheduled cron has been **retired** — batch processing is now handled by Modal's
`process_pending_batch()` function (every 6h). The workflow remains as `workflow_dispatch`-only
for manual triggers and emergency fallback.

Triggers:
- **workflow_dispatch**: manual or via REST API from `/api/queue` (fallback when MCP not set)
  - Optional input: `arxiv_id` — if set, processes only that paper

Required GitHub Secrets (still needed for fallback path):
```
GEMINI_API_KEY, GROQ_API_KEY, OPENROUTER_API_KEY, OPENAI_API_KEY
SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
PAPER2MD_LLM_PROVIDER=gemini
PAPER2MD_MAX_MATH_BLOCKS=50
```

---

## Modal Deployment

```bash
# One-time secrets setup
modal secret create paper2md-secrets \
  SUPABASE_URL="https://..." \
  SUPABASE_SERVICE_ROLE_KEY="sb_secret_..." \
  GEMINI_API_KEY="..." \
  GROQ_API_KEY="..." \
  OPENROUTER_API_KEY="..." \
  PAPER2MD_LLM_PROVIDER="gemini" \
  PAPER2MD_MAX_MATH_BLOCKS="50"

# Deploy MCP server + batch cron
modal deploy mcp-servers/paper-processor-mcp/modal_app.py

# Local dev (live reload)
modal serve mcp-servers/paper-processor-mcp/modal_app.py
```

The deploy registers two Modal functions:
- `serve` — ASGI web endpoint for the FastMCP server (MCP tools over HTTP)
- `process_pending_batch` — Cron job running every 6h (replaces GitHub Actions)

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

# MCP server URLs (set to enable MCP path; leave unset for GitHub Actions fallback)
PAPER_PROCESSOR_MCP_URL=            # Modal serve URL for paper-processor-mcp
PAPER_READER_MCP_URL=               # Cloudflare Workers URL for paper-reader-mcp
ARXIV_SEARCH_MCP_URL=               # Cloudflare Workers URL for arxiv-search-mcp
MATH_TO_CODE_MCP_URL=               # Cloudflare Workers URL for math-to-code-mcp (optional)

# UI feature flags (client-readable)
NEXT_PUBLIC_SHOW_CHAT=true          # show /chat page (default false until MCP live)
NEXT_PUBLIC_SHOW_CODE_TOGGLE=true   # show Code toggle on MathBlock (default true)
NEXT_PUBLIC_SHOW_REVIEW_UI=true     # show Save-to-DB button in CodePanel (default true)

# GitHub fallback (only needed when PAPER_PROCESSOR_MCP_URL is unset)
GITHUB_DISPATCH_TOKEN=              # PAT: Actions read/write
GITHUB_KB_TOKEN=                    # PAT: Contents write (commits .md files)
GITHUB_KB_OWNER=                    # GitHub username/org
GITHUB_KB_REPO=                     # e.g. "paper2md-kb"
```

> **Note**: `SUPABASE_SERVICE_ROLE_KEY` in `.env.local` must be the real service_role key, not the anon key. Get it from Supabase dashboard → Project Settings → API → service_role.

---

## Pending Work

### MCP Deployment
- [ ] Deploy `paper-processor-mcp` to Modal (`modal deploy mcp-servers/paper-processor-mcp/modal_app.py`)
- [ ] Deploy `paper-reader-mcp` to Cloudflare Workers (`wrangler deploy` in `mcp-servers/paper-reader-mcp/`)
- [ ] Deploy `arxiv-search-mcp` to Cloudflare Workers (`wrangler deploy` in `mcp-servers/arxiv-search-mcp/`)
- [ ] Add MCP URLs to Vercel env vars + set `NEXT_PUBLIC_SHOW_CHAT=true`
- [ ] Verify `GET /api/health` returns `{ status: 'ok' }` for all 3 servers

### Like / Publish to GitHub
- [ ] Create `paper2md-kb` public GitHub repo
- [ ] DB migration — verify `liked`, `liked_at`, `github_md_url` columns are applied
- [ ] Create GitHub PAT for kb repo (Contents: read/write), add `GITHUB_KB_*` env vars

### math-to-code-mcp (TypeScript / CF Workers — ready to deploy)
- [ ] `wrangler secret put SUPABASE_URL` in `mcp-servers/math-to-code-mcp/`
- [ ] `wrangler secret put SUPABASE_SERVICE_ROLE_KEY`
- [ ] `wrangler secret put ANTHROPIC_API_KEY`
- [ ] `wrangler deploy` → add URL to Vercel + `.env.local` as `MATH_TO_CODE_MCP_URL`
- [ ] Apply `supabase/migrations/005_math_code_artifacts.sql` and run `npm run gen:types`

### Misc
- [ ] Replace placeholder titles in DB for 3 papers that have `arxiv_id` stored as title
- [ ] Add `GEMINI_API_KEY` to `.env` and GitHub Secrets

# paper2md — Full Implementation Plan

_Created: 2026-06-08 | Last updated: 2026-06-09_

---

## What This Is

A full-stack pipeline + public web app that explains the mathematics inside ArXiv papers.
Users queue a paper → GitHub Actions fetches its LaTeX, extracts math blocks, uses DSPy
to explain each equation in plain English, then stores everything in Supabase. The Next.js
web app on Vercel reads from Supabase and renders math with KaTeX.

---

## Technology Decisions (Final)

| Concern | Choice | Reason |
|---|---|---|
| LLM interaction | **DSPy 2.5+** | Structured outputs, multi-model, built-in fallback |
| LLM providers | **Gemini → Groq → OpenRouter** | Free tiers, priority order |
| OpenRouter model | **google/gemma-3-27b-it:free** | Qwen3-235b removed from free tier |
| LaTeX parsing | **pylatexenc** | Best Python lib for math env extraction |
| ArXiv source | **Direct HTTP tarball** | Free, no rate limits at our scale |
| Database | **Supabase PostgreSQL** | Free 500MB, RLS, type generation |
| Frontend | **Next.js 15 App Router** | Vercel-native, Server Components |
| Math rendering | **KaTeX** (Client Component) | DOM required, fastest renderer |
| Hosting | **Vercel free** | Next.js optimized, 100GB bandwidth/month |
| Processing trigger | **GitHub Actions** | Free unlimited minutes on public repo |
| Repo visibility | **Public** | Required for unlimited free Actions minutes |
| Knowledge base repo | **paper2md-kb (public GitHub)** | Stores liked papers as .md files via Contents API |
| Like / publish | **GitHub Contents API** | No git CLI — commit .md files server-side from Next.js |
| Guardrails | **Skipped** | Public academic content, no PII/safety risk |

---

## Repository Structure (Current State)

```
paper2md/
│
├── lib/                               # Python processing core
│   ├── models.py                      # Paper, Section, MathBlock dataclasses
│   ├── pdf_extract.py                 # PDF text extraction (pdfminer.six)
│   ├── text_clean.py                  # Pure text normalization
│   ├── content_analysis.py            # DOI, abstract, chunk_text_for_llm
│   ├── cache.py                       # SHA-256 keyed cache (.paper2md/cache.json)
│   ├── summarization.py               # Legacy (replaced by dspy_modules.py)
│   ├── dspy_config.py                 # Provider setup + fallback chain
│   ├── dspy_signatures.py             # Typed I/O contracts for all LLM calls
│   ├── dspy_modules.py                # MathExplainer, PaperSummarizer
│   ├── arxiv_source.py                # Download + unpack ArXiv tarball
│   ├── latex_parse.py                 # Section split + math extraction
│   └── supabase_push.py               # Upsert pipeline (NullPool)
│
├── supabase/
│   └── migrations/
│       ├── 001_schema.sql
│       └── 002_indexes_rls.sql
│
├── .github/
│   └── workflows/
│       └── process_pending.yml        # Cron every 6h + workflow_dispatch trigger
│
├── summarize_papers.py                # CLI entry point
├── requirements.txt
├── .env                               # Python env vars (never committed)
├── .gitignore
├── CLAUDE.md
└── Plans/
    └── math-explanation-architecture.md   # this file
│
└── web/                               # Next.js app (deployed to Vercel)
    ├── app/
    │   ├── layout.tsx                 # Sticky header, KaTeX CDN, footer
    │   ├── page.tsx                   # Hero, SearchBar, QueueForm, recent papers
    │   ├── not-found.tsx
    │   ├── paper/
    │   │   └── [arxiv_id]/
    │   │       ├── page.tsx           # Paper overview + section list
    │   │       └── [section_id]/
    │   │           └── page.tsx       # Section detail + math blocks
    │   └── api/
    │       ├── queue/route.ts         # POST: enqueue arxiv_id (+ title)
    │       ├── search/route.ts        # GET: autocomplete from Supabase
    │       └── arxiv/route.ts         # GET: proxy ArXiv Atom API search
    ├── components/
    │   ├── MathBlock.tsx              # 'use client' — KaTeX + explanation toggle
    │   ├── SectionCard.tsx            # Server Component
    │   ├── PaperHeader.tsx            # Server Component
    │   ├── SearchBar.tsx              # 'use client' — debounced autocomplete
    │   └── QueueForm.tsx              # 'use client' — two-tab: ArXiv search + paste ID
    ├── lib/
    │   ├── supabase/
    │   │   ├── client.ts              # Browser client (anon/publishable key)
    │   │   ├── server.ts              # SSR server client (async cookies)
    │   │   ├── queries.ts             # Typed query helpers
    │   │   └── types.ts               # Generated: supabase gen types typescript
    │   └── arxiv-id.ts                # extractArxivId() — parses URLs + bare IDs
    ├── postcss.config.mjs             # Required for Tailwind v4
    ├── package.json
    ├── next.config.ts                 # CSP headers, KaTeX CDN allowed
    └── tsconfig.json
```

---

## Data Models

### Python `lib/models.py`

```
Paper (frozen dataclass)
├── pdf_path:         Path | None
├── arxiv_id:         str | None
├── title:            str
├── text:             str
├── summary_md:       str | None
├── source_type:      str              "arxiv_latex" | "pdf"
└── sections:         tuple[Section, ...]

Section (frozen dataclass)
├── order_idx:        int
├── title:            str
├── plain_text:       str
├── raw_latex:        str | None
└── math_blocks:      tuple[MathBlock, ...]

MathBlock (frozen dataclass)
├── order_idx:        int
├── env_type:         str              "equation"|"align"|"gather"|"multline"|"cases"|"display"|"inline"
├── latex_expr:       str
├── context_before:   str              300 chars before block
├── context_after:    str              300 chars after block
├── explanation:      str | None       DSPy-generated markdown
└── explanation_model: str | None      provider name that generated explanation
```

### Supabase Schema

```sql
-- 001_schema.sql

CREATE TABLE papers (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    arxiv_id      TEXT UNIQUE,
    title         TEXT NOT NULL,
    abstract      TEXT,
    authors       TEXT[],
    source_type   TEXT NOT NULL CHECK (source_type IN ('arxiv_latex','pdf')),
    pdf_filename  TEXT,
    status        TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending','processing','complete','error')),
    error_msg     TEXT,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE sections (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    paper_id      UUID NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    order_idx     INTEGER NOT NULL,
    title         TEXT,
    plain_text    TEXT,
    raw_latex     TEXT,
    has_math      BOOLEAN DEFAULT FALSE,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (paper_id, order_idx)
);

CREATE TABLE math_blocks (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    section_id        UUID NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
    order_idx         INTEGER NOT NULL,
    env_type          TEXT NOT NULL,
    latex_expr        TEXT NOT NULL,
    context_before    TEXT,
    context_after     TEXT,
    explanation       TEXT,
    explanation_model TEXT,
    created_at        TIMESTAMPTZ DEFAULT NOW()
);

-- 002_indexes_rls.sql

CREATE INDEX idx_papers_arxiv_id        ON papers(arxiv_id);
CREATE INDEX idx_papers_status          ON papers(status);
CREATE INDEX idx_sections_paper_id      ON sections(paper_id);
CREATE INDEX idx_math_blocks_section_id ON math_blocks(section_id);

ALTER TABLE papers      ENABLE ROW LEVEL SECURITY;
ALTER TABLE sections    ENABLE ROW LEVEL SECURITY;
ALTER TABLE math_blocks ENABLE ROW LEVEL SECURITY;

-- Anon key: read all complete data
CREATE POLICY "anon_read" ON papers      FOR SELECT USING (true);
CREATE POLICY "anon_read" ON sections    FOR SELECT USING (true);
CREATE POLICY "anon_read" ON math_blocks FOR SELECT USING (true);

-- Anon key: queue new papers only (pending status enforced)
CREATE POLICY "anon_queue" ON papers
    FOR INSERT WITH CHECK (status = 'pending');

-- Service role key bypasses RLS — used by Python worker for UPDATE/DELETE
```

---

## Processing Pipeline

```
Web user queues paper
        │
        ▼
POST /api/queue  (Next.js route handler)
  - extractArxivId() parses bare ID or any URL:
      2301.07984
      https://arxiv.org/abs/2301.07984
      https://www.alphaxiv.org/abs/2301.07984
      https://arxiv.org/pdf/2301.07984
  - INSERT papers (status='pending', title=real title if from ArXiv search)
  - [PLANNED] trigger GitHub Actions workflow_dispatch via REST API
        │
        ▼
Supabase: papers row, status = 'pending'
        │
        ▼
GitHub Actions (workflow_dispatch or cron every 6h)
runs: python summarize_papers.py --process-pending --push-supabase
        │
        ├── fetch_pending_arxiv_ids() from Supabase
        │
        └── per paper:
              │
              ├── mark_processing()  → status = 'processing'
              │
              ├── arxiv_source.py
              │     GET https://arxiv.org/src/{arxiv_id}
              │     Unpack tar.gz → find main .tex (\documentclass)
              │     Resolve \input{} / \include{} directives recursively
              │     Strip preamble → body only
              │
              ├── latex_parse.py
              │     Split on \section / \subsection
              │     Extract math envs: equation, align, align*, gather,
              │       multline, cases, $$...$$, \[...\], $...$
              │     Extract 300-char context windows around each block
              │     pylatexenc → plain text per section
              │
              ├── dspy_modules.PaperSummarizer
              │     chunk_text_for_llm() → N chunks (max 12,000 chars each)
              │     SummarizeChunk × N  → chunk summaries
              │     ReduceToFinalSummary → tldr, problem, approach,
              │                            results, takeaways, limitations
              │
              ├── dspy_modules.MathExplainer
              │     Prioritise equation/align over inline
              │     Cap at PAPER2MD_MAX_MATH_BLOCKS (default 50)
              │     ExplainMathBlock per block:
              │       → what_it_computes, symbol_meanings,
              │         intuition, paper_relevance
              │     Retry on rate limit: exponential backoff,
              │       uses retry_after_seconds from response if available
              │
              └── supabase_push.py
                    UPSERT papers (on_conflict arxiv_id)
                    DELETE existing sections (idempotent re-run)
                    Bulk INSERT sections (100 rows/batch)
                    Bulk INSERT math_blocks (100 rows/batch)
                    UPDATE status = 'complete'
```

---

## DSPy Layer

### Provider priority and free limits

```
Priority  Provider      Model                        Free/day   RPM   Sleep/call
──────────────────────────────────────────────────────────────────────────────
1         Gemini        gemini-2.0-flash              1,500      15    4s
2         Groq          llama-3.3-70b-versatile       1,000      30    2s
3         OpenRouter    google/gemma-3-27b-it:free       50       8    8s
4         OpenAI        gpt-4o-mini (paid fallback)    none     500    0.1s
──────────────────────────────────────────────────────────────────────────────
Set PAPER2MD_LLM_PROVIDER=gemini to force primary.
Fallback chain is automatic via dspy.LM(fallback=[...]).
```

### DSPy Signatures (`lib/dspy_signatures.py`)

```
ExplainMathBlock
  IN:  paper_title, section_title, context_before, latex_expr, context_after
  OUT: what_it_computes, symbol_meanings, intuition, paper_relevance

SummarizeChunk
  IN:  paper_title, chunk_index, chunk_text
  OUT: summary_bullets

ReduceToFinalSummary
  IN:  paper_title, chunk_summaries
  OUT: tldr, problem, approach, results, takeaways, limitations
```

All three use `dspy.ChainOfThought` — CoT required for math reasoning quality.

### Retry logic (`lib/dspy_modules._call_with_tracking`)

```python
max_retries = 4
for attempt in range(max_retries):
    try:
        result = module(**kwargs)
        ...
    except Exception as e:
        if is_rate_limit and attempt < max_retries - 1:
            # Use server's retry_after_seconds if present, else exponential backoff
            wait = retry_after_seconds + 2  OR  15 * (2 ** attempt)
            time.sleep(wait)
        else:
            raise
```

---

## Web App

### Pages

```
/                               Landing: hero + SearchBar + QueueForm + 20 recent papers
/paper/[arxiv_id]               Paper overview + section list (ISR revalidate: 3600)
/paper/[arxiv_id]/[section_id]  Section detail + math blocks
/api/queue     POST             Enqueue paper → INSERT papers status=pending
/api/search    GET ?q=          Autocomplete from Supabase (title + arxiv_id search)
/api/arxiv     GET ?q=          Proxy ArXiv Atom API title search → ArxivResult[]
```

### QueueForm — URL input handling (`web/lib/arxiv-id.ts`)

```typescript
extractArxivId(input: string): string | null
// Accepts:
//   "2301.07984"                              bare ID
//   "2301.07984v2"                            with version (stripped)
//   "https://arxiv.org/abs/2301.07984"
//   "https://arxiv.org/pdf/2301.07984"
//   "https://www.alphaxiv.org/abs/2301.07984"
//   "https://alphaxiv.org/abs/2301.07984"
```

QueueForm has two tabs:
- **Search ArXiv** — debounced 400ms title search via `/api/arxiv`; if input is a URL/ID,
  shows "Detected ArXiv ID: XXXX" inline quick-queue row instead of searching
- **Paste ID** — accepts bare IDs or full URLs, extracts ID before submitting

### SearchBar autocomplete

- Debounced 250ms, queries `/api/search?q=`
- Dropdown: keyboard nav (arrows/enter/escape), click navigates to paper page
- Searches both `title` and `arxiv_id` columns (no status filter — shows pending too)

### Paper status badges

```
pending    → amber  "Processing…"   (not clickable — no page yet)
processing → blue   "Processing…"   (not clickable)
complete   → green  (clickable link to paper page)
error      → red    "Error"
```

### Component split

```
Server Components (default)        Client Components ('use client')
───────────────────────────        ────────────────────────────────
PaperHeader                        MathBlock  (KaTeX needs DOM)
SectionCard                        SearchBar  (controlled input, dropdown)
page.tsx (all pages)               QueueForm  (form state, fetch)
```

### Key config decisions

- **Tailwind v4** — uses `@import "tailwindcss"` in globals.css + `@tailwindcss/postcss`
  in postcss.config.mjs (NOT the v3 pattern)
- **Supabase SSR v0.10.3** — upgraded from 0.6.1 due to supabase-js v2.108.0 generic
  incompatibility
- **Env var name** — `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` (not the standard ANON_KEY name)
- **KaTeX** — loaded via CDN link tag in layout.tsx `<head>`, dynamic import in MathBlock
- **CSP** — `'unsafe-inline' 'unsafe-eval'` required for Next.js hydration scripts

---

## GitHub Actions Workflow

File: `.github/workflows/process_pending.yml`

```yaml
on:
  schedule:
    - cron: "0 */6 * * *"       # every 6 hours
  workflow_dispatch:              # manual trigger from Actions UI or REST API
    inputs:
      arxiv_id:
        description: "Optional: single ArXiv ID (e.g. 2301.07984)"
        required: false
        type: string
```

### On-demand trigger via GitHub REST API (PLANNED)

From `web/app/api/queue/route.ts` after successful INSERT:

```typescript
await fetch(
  `https://api.github.com/repos/{owner}/{repo}/actions/workflows/process_pending.yml/dispatches`,
  {
    method: "POST",
    headers: {
      Authorization: `Bearer ${process.env.GITHUB_DISPATCH_TOKEN}`,
      Accept: "application/vnd.github+json",
    },
    body: JSON.stringify({ ref: "main", inputs: { arxiv_id: arxivId } }),
  }
);
```

Required env var: `GITHUB_DISPATCH_TOKEN` — GitHub PAT with `Actions: Read/Write` scope.
Add to Vercel env vars (not GitHub Secrets — it's called from the web app).

### GitHub Secrets required

```
GEMINI_API_KEY              primary LLM (1500 req/day free)
GROQ_API_KEY                fallback LLM
OPENROUTER_API_KEY          emergency fallback
SUPABASE_URL                https://xxxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY   service_role key (bypasses RLS — write access)
```

---

## Environment Variables

### Python (`.env` — never committed)

```bash
PAPER2MD_LLM_PROVIDER=gemini
GEMINI_API_KEY=
GROQ_API_KEY=
OPENROUTER_API_KEY=
OPENAI_API_KEY=              # legacy / paid fallback
OPENAI_BASE_URL=
OPENAI_MODEL=
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=   # real service_role key, NOT the anon/publishable key
PAPER2MD_MAX_MATH_BLOCKS=50
PAPER2MD_DEBUG_TRACE=0       # set to 1 for full tracebacks
```

### Next.js (`web/.env.local` — never committed)

```bash
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=   # anon/publishable key (safe to expose)
GITHUB_DISPATCH_TOKEN=                  # PAT for triggering workflow_dispatch
```

---

## Deployment

### Vercel (web app)

1. Connect GitHub repo to Vercel
2. Set **Root Directory** → `web`
3. Framework: Next.js (auto-detected)
4. Add env vars: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`,
   `GITHUB_DISPATCH_TOKEN`
5. Deploy — automatic on every push to `main`

### GitHub Actions (Python worker)

1. Make repo **public** (required for unlimited free minutes)
2. Add secrets: `GEMINI_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY`,
   `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`
3. Push `.github/workflows/process_pending.yml` — cron activates automatically
4. Manual trigger: Actions tab → "Process Pending Papers" → Run workflow

### Supabase

1. Run SQL migrations in Supabase SQL Editor:
   - `supabase/migrations/001_schema.sql`
   - `supabase/migrations/002_indexes_rls.sql`
2. Verify RLS: anon key can SELECT + INSERT(pending); UPDATE blocked (service_role only)
3. Get the real `service_role` key: Project Settings → API → service_role (secret)

---

## Free Tier Budget

```
Service          Resource          Free Limit        At 10 papers/day
──────────────────────────────────────────────────────────────────────────
Gemini           Requests/day      1,500             ~200 (20 blocks × 10)
Groq             Requests/day      1,000             overflow only
OpenRouter       Requests/day      50 free           emergency only
Supabase DB      Storage           500 MB            ~1MB/paper → 500 papers
Vercel           Bandwidth         100 GB/month      negligible
GitHub Actions   Minutes/month     Unlimited (public repo)
──────────────────────────────────────────────────────────────────────────
```

---

## Error Handling

```
No LaTeX source (PDF-only paper)    Fall back to PDF download; math extraction skipped
Multiple \documentclass files       Prefer main.tex; else largest .tex file
Rate limit hit                      Exponential backoff; use retry_after_seconds if present
All LLM providers exhausted         status='error'; GitHub Actions retries in 6h
Math block count > cap              Prioritise equation/align over inline $...$
Supabase push fails                 Write ~/.paper2md/failed_push.json; mark error
KaTeX render error                  Catch in useEffect; fall back to <code>{raw}</code>
Duplicate arxiv_id queued           UPSERT ON CONFLICT is idempotent
RLS blocks UPDATE                   Only service_role key (never anon) can update status
Title stored as placeholder         Fixed: QueueForm passes real title from ArXiv search
```

---

## Known Issues / Pending Work

- [ ] **GitHub dispatch trigger** — wire `/api/queue` to call workflow_dispatch after INSERT
      so papers process immediately instead of waiting up to 6 hours
- [ ] **GITHUB_DISPATCH_TOKEN** — create PAT, add to Vercel env vars
- [ ] **SUPABASE_SERVICE_ROLE_KEY** — user needs real service_role key (current .env.local
      has anon key in that slot); get from Supabase dashboard → Project Settings → API
- [ ] **Fix existing placeholder titles** — 3 papers in DB have arxiv_id as title;
      run in Supabase SQL editor:
      ```sql
      UPDATE papers SET title = '2506.06447' WHERE arxiv_id = '2506.06447' AND title = '2506.06447';
      -- or bulk: re-queue and re-process via --arxiv-id
      ```
- [ ] **GEMINI_API_KEY** — add to .env and GitHub Secrets for best math explanation quality
- [ ] **Deploy to Vercel** — connect repo, set env vars, go live
- [ ] **Make repo public** — required for unlimited GitHub Actions minutes
- [ ] **Phase 5: Like feature** — see Plans/requirements.md for full spec
      - DB migration: add liked, liked_at, arxiv_url (generated), github_md_url columns
      - Create paper2md-kb GitHub repo (public)
      - web/lib/github-publish.ts — markdown generator + GitHub Contents API commit
      - web/app/api/like/route.ts — orchestrate fetch → generate → commit → update DB
      - web/components/LikeButton.tsx — star button with optimistic update + GitHub link

---

## Implementation Phases (Completed)

```
Phase 1 — Python backend                    ✅ DONE
  lib/models.py                             Section, MathBlock dataclasses added
  lib/dspy_config.py                        Provider setup + fallback chain
  lib/dspy_signatures.py                    ExplainMathBlock, SummarizeChunk, ReduceToFinalSummary
  lib/dspy_modules.py                       MathExplainer + PaperSummarizer + retry logic
  lib/arxiv_source.py                       Download + unpack + find main .tex
  lib/latex_parse.py                        Section split + math extraction
  lib/supabase_push.py                      Upsert pipeline
  summarize_papers.py                       --arxiv-id, --arxiv-list, --process-pending, --push-supabase

Phase 2 — Supabase                          ✅ DONE (migrations run manually in SQL editor)
  001_schema.sql + 002_indexes_rls.sql      Applied
  RLS policies                              anon read + anon insert-pending + service_role write

Phase 3 — Next.js web app                   ✅ DONE
  All pages, components, API routes         Built and running on localhost:3000
  Tailwind v4 + KaTeX CDN                   Configured
  ArXiv title search + autocomplete         Working
  alphaxiv.org + arxiv.org URL support      Working (lib/arxiv-id.ts)
  QueueForm two-tab UI                      Working

Phase 4 — Automation                        🔲 TODO
  .github/workflows/process_pending.yml     File exists, not yet triggered end-to-end
  workflow_dispatch from /api/queue         Not yet wired
  Vercel deploy                             Not yet done
```

# paper2md — Product Requirements Document

_Created: 2026-06-09_

---

## Vision

A public web app that makes ArXiv papers accessible by explaining every mathematical
equation in plain English. When a user finds a paper they want to keep, they can "like"
it — this publishes the full analysis as a Markdown file to a GitHub knowledge-base repo
and saves the GitHub file URL back to the database for permanent reference.

---

## Users

| User | Description |
|---|---|
| **Visitor** | Anyone — no login required. Can search, queue, and browse papers. |
| *(Future)* Registered user | Auth not in scope for v1 — all actions are anonymous |

---

## Core Features

### F1 — Queue a Paper

**Trigger**: User pastes an ArXiv ID, arxiv.org URL, or alphaxiv.org URL into the Queue form.

**Behaviour**:
- Extract the ArXiv ID from any supported URL format
- `INSERT` into `papers` table with `status = 'pending'`
- If paper already exists: show "Already in DB" — no duplicate insert
- [Phase 4] Trigger GitHub Actions `workflow_dispatch` immediately via REST API
  so processing begins within ~30 seconds instead of waiting up to 6 hours

**Supported input formats**:
```
2301.07984
https://arxiv.org/abs/2301.07984
https://arxiv.org/pdf/2301.07984
https://www.alphaxiv.org/abs/2301.07984
https://alphaxiv.org/abs/2301.07984
```

**Queue form tabs**:
- **Search ArXiv** — live title search (debounced 400ms), per-row Queue button, stores real title
- **Paste ID/URL** — accepts bare IDs or full URLs, extracts ID before queuing

---

### F2 — Search Papers

**Trigger**: User types in the SearchBar on the landing page.

**Behaviour**:
- Debounced 250ms, queries `/api/search?q=`
- Searches both `title` and `arxiv_id` columns
- Shows all statuses (pending, processing, complete, error) — no filter
- Dropdown with keyboard nav (arrows / enter / escape)
- Clicking a result navigates to the paper page (complete) or stays on landing (pending)

---

### F3 — Browse Papers

**Landing page** (`/`):
- Hero + SearchBar + QueueForm
- List of 20 most recently updated papers
- Status badges: pending=amber, processing=blue, complete=green (clickable), error=red

**Paper page** (`/paper/[arxiv_id]`):
- Title, authors, abstract
- Section list with math block count badges
- Summary: TL;DR, Problem, Approach, Results, Takeaways, Limitations

**Section page** (`/paper/[arxiv_id]/[section_id]`):
- Section plain text
- Each math block: rendered LaTeX (KaTeX) + expandable explanation panel
  showing: What it computes / Symbols / Intuition / Why it matters

---

### F4 — Like a Paper ⭐ *(NEW)*

**Trigger**: User clicks the "Like" / star button on a complete paper page.

**What it stores in Supabase** (`papers` table):
```
liked          BOOLEAN DEFAULT FALSE
liked_at       TIMESTAMPTZ
arxiv_url      TEXT    -- https://arxiv.org/abs/{arxiv_id}
github_md_url  TEXT    -- https://github.com/{owner}/{repo}/blob/main/papers/{arxiv_id}.md
```

**What it publishes to GitHub**:
- Generates full Markdown document from the paper's DB content
- Commits `papers/{arxiv_id}.md` to a dedicated GitHub knowledge-base repo
  via the GitHub Contents API (no git CLI needed)
- File URL format: `https://github.com/{owner}/{kb_repo}/blob/main/papers/{arxiv_id}.md`

**Markdown file format** (`papers/{arxiv_id}.md`):
```markdown
# {title}

**ArXiv**: https://arxiv.org/abs/{arxiv_id}
**Published**: {created_at date}

---

## Summary

### TL;DR
{tldr}

### Problem
{problem}

### Approach
{approach}

### Results
{results}

### Practical Takeaways
{takeaways}

### Limitations / Open Questions
{limitations}

---

## Sections

### {section_1_title}

{section_1_plain_text}

#### Math Blocks

**Block 1** — `{env_type}`
```latex
{latex_expr}
```
**What it computes**: {what_it_computes}
**Symbols**: {symbol_meanings}
**Intuition**: {intuition}
**Why it matters**: {paper_relevance}

...
```

**API flow**:
```
POST /api/like  { arxiv_id }
        │
        ├── 1. Fetch paper + sections + math_blocks from Supabase
        ├── 2. Generate markdown string
        ├── 3. Commit to GitHub via Contents API
        │       PUT https://api.github.com/repos/{owner}/{kb_repo}/contents/papers/{arxiv_id}.md
        │       body: { message, content: base64(markdown), sha (if updating) }
        ├── 4. UPDATE papers SET liked=true, liked_at=now(),
        │           arxiv_url='https://arxiv.org/abs/{arxiv_id}',
        │           github_md_url='{github_file_url}'
        └── 5. Return { github_md_url }
```

**UI feedback**:
- Star button turns yellow / filled on success
- Link appears: "View on GitHub →" pointing to the committed file
- If already liked: star stays filled, link stays visible

**Environment variable required**:
```
GITHUB_KB_TOKEN=      # PAT with Contents:Write on the knowledge-base repo
GITHUB_KB_OWNER=      # GitHub username or org
GITHUB_KB_REPO=       # repo name, e.g. "paper2md-kb"
```

---

## Processing Pipeline (Python)

### Trigger methods

| Method | Latency | How |
|---|---|---|
| GitHub Actions cron | Up to 6h | Scheduled `0 */6 * * *` |
| GitHub Actions manual | ~30s | Actions UI → Run workflow |
| workflow_dispatch via REST API | ~30s | Called from `/api/queue` after INSERT |

### Pipeline steps per paper

```
1. fetch_pending_arxiv_ids()       Supabase SELECT WHERE status='pending'
2. mark_processing()               UPDATE status='processing'
3. fetch_arxiv_latex()             GET arxiv.org/src/{id} → tar.gz → merged .tex
4. parse_latex_sections()          sections + math_blocks (pylatexenc)
5. PaperSummarizer.forward()       DSPy map-reduce → summary_md
6. MathExplainer.forward()         DSPy per-block → explanations (capped at 50)
7. push_paper()                    UPSERT papers, INSERT sections+math_blocks
8. UPDATE status='complete'
```

### LLM provider priority

```
1. Gemini 2.0 Flash      GEMINI_API_KEY       1,500 req/day free   4s/call
2. Groq llama-3.3-70b    GROQ_API_KEY         1,000 req/day free   2s/call
3. openrouter/free        OPENROUTER_API_KEY   ~200 req/day free    6s/call
                          (auto-routes to best available free model)
```

---

## Database Schema

### `papers` table (current + additions for F4)

```sql
CREATE TABLE papers (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    arxiv_id        TEXT UNIQUE,
    title           TEXT NOT NULL,
    abstract        TEXT,
    authors         TEXT[],
    source_type     TEXT NOT NULL CHECK (source_type IN ('arxiv_latex','pdf')),
    pdf_filename    TEXT,
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','processing','complete','error')),
    error_msg       TEXT,
    summary_md      TEXT,

    -- F4: Like / publish to GitHub
    liked           BOOLEAN NOT NULL DEFAULT FALSE,
    liked_at        TIMESTAMPTZ,
    arxiv_url       TEXT GENERATED ALWAYS AS (
                        CASE WHEN arxiv_id IS NOT NULL
                        THEN 'https://arxiv.org/abs/' || arxiv_id
                        END
                    ) STORED,
    github_md_url   TEXT,

    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
```

### `sections` table

```sql
CREATE TABLE sections (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    paper_id    UUID NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    order_idx   INTEGER NOT NULL,
    title       TEXT,
    plain_text  TEXT,
    raw_latex   TEXT,
    has_math    BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (paper_id, order_idx)
);
```

### `math_blocks` table

```sql
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
```

### RLS policies

```sql
-- Everyone can read
CREATE POLICY "anon_read" ON papers      FOR SELECT USING (true);
CREATE POLICY "anon_read" ON sections    FOR SELECT USING (true);
CREATE POLICY "anon_read" ON math_blocks FOR SELECT USING (true);

-- Anyone can queue (insert pending only)
CREATE POLICY "anon_queue" ON papers
    FOR INSERT WITH CHECK (status = 'pending');

-- Like update: only the liked + github_md_url columns via anon key
-- (or use service_role key called server-side — simpler)
CREATE POLICY "anon_like" ON papers
    FOR UPDATE USING (status = 'complete')
    WITH CHECK (status = 'complete');

-- All writes by Python worker use service_role key (bypasses RLS)
```

---

## API Routes (Next.js)

| Method | Route | Description |
|---|---|---|
| GET | `/api/search?q=` | Autocomplete — search title + arxiv_id in Supabase |
| GET | `/api/arxiv?q=` | Proxy ArXiv Atom API title search |
| POST | `/api/queue` | Enqueue paper — INSERT status=pending, trigger workflow_dispatch |
| POST | `/api/like` | Like paper — generate MD, commit to GitHub, update DB |

### `POST /api/like` request/response

```typescript
// Request
{ arxiv_id: string }

// Response 200
{ liked: true, github_md_url: string }

// Response 400
{ error: "Paper not complete yet" }

// Response 409
{ liked: true, github_md_url: string }   // already liked — return existing URL
```

---

## Environment Variables

### Next.js (`web/.env.local`)

```bash
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=    # anon key — safe to expose

GITHUB_DISPATCH_TOKEN=                   # PAT: Actions read/write — triggers processing
GITHUB_KB_TOKEN=                         # PAT: Contents write — commits MD files
GITHUB_KB_OWNER=                         # GitHub username/org owning kb repo
GITHUB_KB_REPO=                          # e.g. "paper2md-kb"
```

### Python (`.env`)

```bash
PAPER2MD_LLM_PROVIDER=gemini
GEMINI_API_KEY=
GROQ_API_KEY=
OPENROUTER_API_KEY=
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=               # real JWT service_role key — not anon key
PAPER2MD_MAX_MATH_BLOCKS=50
PAPER2MD_DEBUG_TRACE=0
```

### GitHub Secrets (for Actions workflow)

```
GEMINI_API_KEY
GROQ_API_KEY
OPENROUTER_API_KEY
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
```

---

## GitHub Repositories

| Repo | Purpose | Visibility |
|---|---|---|
| `paper2md` | Main app — Next.js + Python pipeline + workflows | Public (free Actions minutes) |
| `paper2md-kb` | Knowledge base — committed `.md` files from liked papers | Public (free, readable URLs) |

### `paper2md-kb` structure

```
paper2md-kb/
├── README.md              # auto-generated index of all liked papers
└── papers/
    ├── 1706.03762.md      # Attention Is All You Need
    ├── 2301.07984.md      # ...
    └── 2606.06447.md      # Latent Reasoning with Normalizing Flows
```

---

## UI Components

### LikeButton (`web/components/LikeButton.tsx`)

```
'use client'

Props:
  arxiv_id:     string
  initialLiked: boolean
  initialUrl:   string | null

States:
  idle       → star outline button
  loading    → spinner
  liked      → star filled (yellow) + "View on GitHub →" link
  error      → "Failed" text, retry available

Behaviour:
  - POST /api/like on click
  - Optimistic update (star fills immediately)
  - On success: store github_md_url, show link
  - On error: revert star
```

---

## Pages — Updated

```
/                               Landing: hero + search + queue + recent papers
                                  Each paper row shows ⭐ count (future)

/paper/[arxiv_id]               Paper overview + sections + LikeButton
                                  If liked: shows "View on GitHub →" link

/paper/[arxiv_id]/[section_id]  Section + math blocks

/api/queue     POST             Enqueue + trigger workflow_dispatch
/api/like      POST             Like paper + commit MD to GitHub kb repo
/api/search    GET              Autocomplete search
/api/arxiv     GET              ArXiv title search proxy
```

---

## Implementation Phases

### Phase 1 — Python backend ✅ DONE
### Phase 2 — Supabase schema ✅ DONE (migrations applied)
### Phase 3 — Next.js web app ✅ DONE

### Phase 4 — Automation & Deployment 🔲 TODO

```
4a. Wire workflow_dispatch trigger
    - Create GitHub PAT (Actions: read/write)
    - Add GITHUB_DISPATCH_TOKEN to Vercel env vars
    - Update /api/queue route.ts to call dispatch API after INSERT

4b. Deploy to Vercel
    - Connect GitHub repo (root dir: web/)
    - Add env vars: NEXT_PUBLIC_SUPABASE_*, GITHUB_DISPATCH_TOKEN
    - Verify build passes

4c. Make repo public
    - Ensure .env* files are gitignored (done)
    - Push to GitHub
    - Unlimited Actions minutes activated
```

### Phase 5 — Like / Publish to GitHub 🔲 TODO

```
5a. Create paper2md-kb repo on GitHub (public)

5b. DB migration — add columns to papers table
    ALTER TABLE papers
      ADD COLUMN liked         BOOLEAN NOT NULL DEFAULT FALSE,
      ADD COLUMN liked_at      TIMESTAMPTZ,
      ADD COLUMN arxiv_url     TEXT GENERATED ALWAYS AS (...) STORED,
      ADD COLUMN github_md_url TEXT;

5c. Create GitHub PAT for kb repo
    - Scope: Contents read/write on paper2md-kb
    - Add to Vercel: GITHUB_KB_TOKEN, GITHUB_KB_OWNER, GITHUB_KB_REPO

5d. web/lib/github-publish.ts
    - generatePaperMarkdown(paper, sections, mathBlocks): string
    - commitMarkdownToGitHub(arxiv_id, markdown): Promise<string>  // returns file URL

5e. web/app/api/like/route.ts
    - GET paper + sections + math_blocks from Supabase
    - Generate markdown
    - Commit to GitHub via Contents API
    - UPDATE papers SET liked=true, github_md_url=...
    - Return { liked: true, github_md_url }

5f. web/components/LikeButton.tsx
    - 'use client', star button, optimistic update
    - Shows "View on GitHub →" link on success

5g. Add LikeButton to /paper/[arxiv_id]/page.tsx
```

---

## Open Questions / Decisions

| Question | Decision |
|---|---|
| Auth on Like — anyone or logged in? | v1: anyone (no auth in scope) |
| Multiple likes from same user? | Idempotent — second like is a no-op, returns existing URL |
| Update MD on re-like if paper re-processed? | Yes — check sha before commit, update if changed |
| Index page in paper2md-kb? | Yes — auto-update README.md with table of all liked papers |
| Like count visible publicly? | Not in v1 — just the star state and GitHub link |
| RLS for like UPDATE — anon or server-side? | Server-side using service_role key (simpler, no RLS complexity) |

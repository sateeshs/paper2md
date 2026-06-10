-- paper2md schema
-- Run via: supabase db push  OR  paste into Supabase SQL editor

CREATE TABLE papers (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    arxiv_id      TEXT UNIQUE,
    title         TEXT NOT NULL,
    abstract      TEXT,
    authors       TEXT[],
    source_type   TEXT NOT NULL CHECK (source_type IN ('arxiv_latex', 'pdf')),
    pdf_filename  TEXT,
    status        TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'processing', 'complete', 'error')),
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

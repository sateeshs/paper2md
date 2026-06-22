-- Migration: paper_citations table
-- Apply in Supabase SQL editor, then run: cd web && npm run gen:types

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
-- Inserts handled by service_role key (bypasses RLS)

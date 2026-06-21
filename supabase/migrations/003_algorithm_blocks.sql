-- Migration: algorithm_blocks table
-- Apply in Supabase SQL editor, then run: cd web && npm run gen:types

CREATE TABLE algorithm_blocks (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    section_id        UUID NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
    order_idx         INTEGER NOT NULL,
    caption           TEXT,
    raw_pseudocode    TEXT NOT NULL,
    pseudocode_text   TEXT,
    context_before    TEXT,
    context_after     TEXT,
    explanation       TEXT,          -- JSON: {purpose, inputs_outputs, step_by_step, complexity, key_insight, prerequisites}
    explanation_model TEXT,
    created_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ON algorithm_blocks (section_id);

-- RLS: same policy as math_blocks
ALTER TABLE algorithm_blocks ENABLE ROW LEVEL SECURITY;
CREATE POLICY "anon select" ON algorithm_blocks FOR SELECT USING (true);
-- Inserts handled by service_role key (bypasses RLS)

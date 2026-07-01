-- Migration 005: math_code_artifacts table
-- Stores generated Python code for math blocks (math-to-code-mcp output).
-- block_id + library is effectively unique — we DELETE+INSERT on re-generation.

CREATE TABLE IF NOT EXISTS math_code_artifacts (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  block_id        UUID REFERENCES math_blocks(id) ON DELETE CASCADE,
  section_id      UUID REFERENCES sections(id) ON DELETE CASCADE,
  library         TEXT NOT NULL,           -- "numpy" | "pytorch" | "jax" | "scipy"
  function_name   TEXT NOT NULL,
  imports         TEXT NOT NULL,
  code            TEXT NOT NULL,
  example_usage   TEXT,
  test_code       TEXT,
  parameters      JSONB,
  notes           TEXT,
  generated_model TEXT,                    -- which LLM generated it
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_math_code_artifacts_block_id
  ON math_code_artifacts(block_id);

CREATE INDEX IF NOT EXISTS idx_math_code_artifacts_section_id
  ON math_code_artifacts(section_id);

CREATE INDEX IF NOT EXISTS idx_math_code_artifacts_block_library
  ON math_code_artifacts(block_id, library);

-- RLS: anon can read; only service role can write (same pattern as math_blocks)
ALTER TABLE math_code_artifacts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "anon_read_math_code_artifacts"
  ON math_code_artifacts FOR SELECT
  USING (true);

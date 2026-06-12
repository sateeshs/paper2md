-- Migration 004: SAT Tutor sessions table

CREATE TABLE IF NOT EXISTS sat_sessions (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  question         TEXT NOT NULL,
  subject          TEXT NOT NULL CHECK (subject IN ('math', 'english', 'reading')),
  user_context     TEXT,
  status           TEXT NOT NULL DEFAULT 'pending'
                   CHECK (status IN ('pending', 'processing', 'complete', 'error')),

  -- Response fields — populated by the DSPy agent
  explanation      TEXT,   -- prose: what concept this question tests
  step_by_step     TEXT,   -- numbered solution steps
  key_concepts     TEXT,   -- comma-separated SAT concepts
  hints            TEXT,   -- JSON array of 3 progressive hints
  common_mistakes  TEXT,   -- what students typically get wrong
  sat_strategy     TEXT,   -- timing / approach tip
  answer           TEXT,   -- correct answer with justification

  agent_model      TEXT,
  error_msg        TEXT,

  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION update_sat_sessions_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$;

CREATE TRIGGER sat_sessions_updated_at
  BEFORE UPDATE ON sat_sessions
  FOR EACH ROW EXECUTE FUNCTION update_sat_sessions_updated_at();

-- RLS
ALTER TABLE sat_sessions ENABLE ROW LEVEL SECURITY;

-- Anon: read all, insert pending only
CREATE POLICY "sat_anon_select" ON sat_sessions FOR SELECT USING (true);
CREATE POLICY "sat_anon_insert" ON sat_sessions FOR INSERT WITH CHECK (status = 'pending');
-- Service role bypasses all RLS automatically

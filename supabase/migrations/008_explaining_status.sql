-- "explaining": sections and math blocks are stored and the paper is readable,
-- but the math-explanation backfill is still filling in explanations.
-- explain_math_only.py flips it to 'complete' after a full pass over the paper.
ALTER TABLE papers DROP CONSTRAINT IF EXISTS papers_status_check;
ALTER TABLE papers ADD CONSTRAINT papers_status_check
    CHECK (status IN ('pending', 'processing', 'explaining', 'complete', 'error'));

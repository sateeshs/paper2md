-- Indexes
CREATE INDEX idx_papers_arxiv_id        ON papers(arxiv_id);
CREATE INDEX idx_papers_status          ON papers(status);
CREATE INDEX idx_sections_paper_id      ON sections(paper_id);
CREATE INDEX idx_math_blocks_section_id ON math_blocks(section_id);

-- Row Level Security
ALTER TABLE papers      ENABLE ROW LEVEL SECURITY;
ALTER TABLE sections    ENABLE ROW LEVEL SECURITY;
ALTER TABLE math_blocks ENABLE ROW LEVEL SECURITY;

-- Public read (anon key)
CREATE POLICY "anon_read_papers"      ON papers      FOR SELECT USING (true);
CREATE POLICY "anon_read_sections"    ON sections    FOR SELECT USING (true);
CREATE POLICY "anon_read_math_blocks" ON math_blocks FOR SELECT USING (true);

-- Allow web UI to queue a paper (INSERT pending only)
CREATE POLICY "anon_queue_paper" ON papers
    FOR INSERT WITH CHECK (status = 'pending');

-- service_role key bypasses RLS automatically — no extra write policies needed

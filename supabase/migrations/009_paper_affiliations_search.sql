-- Search papers by author and by organisation ("google deepmind"), not only by
-- title. affiliations is filled from the LaTeX source (lib/latex_affiliations.py),
-- authors from the arXiv API; scripts/backfill_paper_metadata.py fills both for
-- papers processed before this migration.
ALTER TABLE papers ADD COLUMN IF NOT EXISTS affiliations TEXT[] NOT NULL DEFAULT '{}';

-- PostgREST cannot substring-match inside array columns, so search is a
-- function. SECURITY INVOKER keeps the caller's RLS (anon may read all papers).
-- LIKE wildcards in the query are escaped so "%" or "_" match literally.
CREATE OR REPLACE FUNCTION search_papers(q TEXT, max_results INT DEFAULT 20)
RETURNS SETOF papers
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = public
AS $$
  WITH pattern AS (
    SELECT '%' || replace(replace(replace(q, '\', '\\'), '%', '\%'), '_', '\_') || '%' AS p
  )
  SELECT papers.*
  FROM papers, pattern
  WHERE papers.title ILIKE pattern.p
     OR papers.arxiv_id ILIKE pattern.p
     OR EXISTS (SELECT 1 FROM unnest(papers.authors) AS a WHERE a ILIKE pattern.p)
     OR EXISTS (SELECT 1 FROM unnest(papers.affiliations) AS a WHERE a ILIKE pattern.p)
  ORDER BY papers.updated_at DESC
  LIMIT LEAST(GREATEST(max_results, 1), 100);
$$;

GRANT EXECUTE ON FUNCTION search_papers(TEXT, INT) TO anon, authenticated;

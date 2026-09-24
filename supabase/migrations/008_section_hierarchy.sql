-- 008_section_hierarchy.sql
-- Outline metadata for sections: hierarchy level, section number, PDF page range.
--
-- Populated for LaTeX papers parsed via lib/latex_outline.py. All columns are
-- nullable: existing rows, PDF-sourced papers, and papers whose PDF has no
-- hyperref outline keep NULL and render with the previous flat layout.

ALTER TABLE sections
  ADD COLUMN IF NOT EXISTS level       INTEGER,
  ADD COLUMN IF NOT EXISTS number      TEXT,
  ADD COLUMN IF NOT EXISTS page_start  INTEGER,
  ADD COLUMN IF NOT EXISTS page_end    INTEGER,
  ADD COLUMN IF NOT EXISTS page_source TEXT;

COMMENT ON COLUMN sections.level       IS '1=chapter 2=section 3=subsection 4=subsubsection';
COMMENT ON COLUMN sections.number      IS 'LaTeX section number, e.g. "2.5.3"';
COMMENT ON COLUMN sections.page_start  IS '1-based first PDF page of this section';
COMMENT ON COLUMN sections.page_end    IS '1-based last PDF page of this section';
COMMENT ON COLUMN sections.page_source IS 'pdf_outline = aligned to PDF bookmark; inferred = interpolated';

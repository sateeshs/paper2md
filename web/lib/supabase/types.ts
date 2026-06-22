/**
 * Supabase database types for paper2md.
 *
 * Manually maintained to match supabase/migrations/*.sql
 * Regenerate via: supabase gen types typescript --project-id $SUPABASE_PROJECT_ID > lib/supabase/types.ts
 * (requires Supabase CLI + SUPABASE_PROJECT_ID env var)
 */

// ---------------------------------------------------------------------------
// Row types — one per table
// ---------------------------------------------------------------------------

export interface Paper {
  id: string;
  arxiv_id: string | null;
  title: string;
  abstract: string | null;
  authors: string[] | null;
  source_type: string;
  pdf_filename: string | null;
  status: "pending" | "processing" | "complete" | "error";
  error_msg: string | null;
  liked: boolean | null;
  liked_at: string | null;
  github_md_url: string | null;
  summary_md: string | null;
  created_at: string;
  updated_at: string;
}

export interface Section {
  id: string;
  paper_id: string;
  order_idx: number;
  title: string | null;
  plain_text: string | null;
  raw_latex: string | null;
  has_math: boolean | null;
  created_at: string;
}

export interface MathBlock {
  id: string;
  section_id: string;
  order_idx: number;
  env_type: string;
  latex_expr: string;
  context_before: string | null;
  context_after: string | null;
  explanation: string | null; // JSON: {what_it_computes, symbol_meanings, intuition, derivation, proof_role, prerequisites, mathematical_significance}
  explanation_model: string | null;
  created_at: string;
}

export interface AlgorithmBlock {
  id: string;
  section_id: string;
  order_idx: number;
  caption: string | null;
  raw_pseudocode: string;
  pseudocode_text: string | null;
  context_before: string | null;
  context_after: string | null;
  explanation: string | null; // JSON: {purpose, inputs_outputs, step_by_step, complexity, key_insight, prerequisites}
  explanation_model: string | null;
  created_at: string;
}

export interface PaperCitation {
  id: string;
  paper_id: string;
  order_idx: number;
  cite_key: string;
  raw_bib_entry: string | null;
  arxiv_id: string | null;
  title: string | null;
  url: string | null;
  created_at: string;
}

export interface SatSession {
  id: string;
  question: string;
  subject: "math" | "english" | "reading";
  user_context: string | null;
  status: "pending" | "processing" | "complete" | "error";
  explanation: string | null;
  step_by_step: string | null;
  key_concepts: string | null;
  hints: string | null; // JSON array of 3 strings
  common_mistakes: string | null;
  sat_strategy: string | null;
  answer: string | null;
  agent_model: string | null;
  error_msg: string | null;
  created_at: string;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// Composite types used by queries.ts
// ---------------------------------------------------------------------------

export interface SectionWithMath extends Section {
  math_blocks: MathBlock[];
  algorithm_blocks: AlgorithmBlock[];
}

export interface SectionWithMathCount extends Section {
  math_blocks: Pick<MathBlock, "id">[];
}

export interface PaperWithSections extends Paper {
  sections: SectionWithMathCount[];
}

// ---------------------------------------------------------------------------
// Database shape (used by Supabase client generics)
// ---------------------------------------------------------------------------

export type Database = {
  public: {
    Tables: {
      papers: {
        Row: Paper;
        Insert: Omit<Paper, "id" | "created_at" | "updated_at"> & {
          id?: string;
          created_at?: string;
          updated_at?: string;
        };
        Update: Partial<Omit<Paper, "id">>;
      };
      sections: {
        Row: Section;
        Insert: Omit<Section, "id" | "created_at"> & {
          id?: string;
          created_at?: string;
        };
        Update: Partial<Omit<Section, "id">>;
      };
      math_blocks: {
        Row: MathBlock;
        Insert: Omit<MathBlock, "id" | "created_at"> & {
          id?: string;
          created_at?: string;
        };
        Update: Partial<Omit<MathBlock, "id">>;
      };
      algorithm_blocks: {
        Row: AlgorithmBlock;
        Insert: Omit<AlgorithmBlock, "id" | "created_at"> & {
          id?: string;
          created_at?: string;
        };
        Update: Partial<Omit<AlgorithmBlock, "id">>;
      };
      paper_citations: {
        Row: PaperCitation;
        Insert: Omit<PaperCitation, "id" | "created_at"> & {
          id?: string;
          created_at?: string;
        };
        Update: Partial<Omit<PaperCitation, "id">>;
      };
      sat_sessions: {
        Row: SatSession;
        Insert: Omit<SatSession, "id" | "created_at" | "updated_at"> & {
          id?: string;
          created_at?: string;
          updated_at?: string;
        };
        Update: Partial<Omit<SatSession, "id">>;
      };
    };
    Views: Record<string, never>;
    Functions: Record<string, never>;
    Enums: Record<string, never>;
  };
};

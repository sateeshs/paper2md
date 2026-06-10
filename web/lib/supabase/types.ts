/**
 * Supabase database types — generated from schema.
 *
 * To regenerate after schema changes:
 *   npm run gen:types
 * (requires SUPABASE_PROJECT_ID env var and supabase CLI installed)
 */

export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[];

export type Database = {
  public: {
    Tables: {
      papers: {
        Row: {
          id: string;
          arxiv_id: string | null;
          title: string;
          abstract: string | null;
          authors: string[] | null;
          source_type: "arxiv_latex" | "pdf";
          pdf_filename: string | null;
          status: "pending" | "processing" | "complete" | "error";
          error_msg: string | null;
          summary_md: string | null;
          liked: boolean;
          liked_at: string | null;
          github_md_url: string | null;
          created_at: string;
          updated_at: string;
        };
        Insert: {
          id?: string;
          arxiv_id?: string | null;
          title: string;
          abstract?: string | null;
          authors?: string[] | null;
          source_type: "arxiv_latex" | "pdf";
          pdf_filename?: string | null;
          status?: "pending" | "processing" | "complete" | "error";
          error_msg?: string | null;
          summary_md?: string | null;
          liked?: boolean;
          liked_at?: string | null;
          github_md_url?: string | null;
          created_at?: string;
          updated_at?: string;
        };
        Update: {
          id?: string;
          arxiv_id?: string | null;
          title?: string;
          abstract?: string | null;
          authors?: string[] | null;
          source_type?: "arxiv_latex" | "pdf";
          pdf_filename?: string | null;
          status?: "pending" | "processing" | "complete" | "error";
          error_msg?: string | null;
          summary_md?: string | null;
          liked?: boolean;
          liked_at?: string | null;
          github_md_url?: string | null;
          created_at?: string;
          updated_at?: string;
        };
        Relationships: [];
      };

      sections: {
        Row: {
          id: string;
          paper_id: string;
          order_idx: number;
          title: string | null;
          plain_text: string | null;
          raw_latex: string | null;
          has_math: boolean;
          created_at: string;
        };
        Insert: {
          id?: string;
          paper_id: string;
          order_idx: number;
          title?: string | null;
          plain_text?: string | null;
          raw_latex?: string | null;
          has_math?: boolean;
          created_at?: string;
        };
        Update: {
          id?: string;
          paper_id?: string;
          order_idx?: number;
          title?: string | null;
          plain_text?: string | null;
          raw_latex?: string | null;
          has_math?: boolean;
          created_at?: string;
        };
        Relationships: [
          {
            foreignKeyName: "sections_paper_id_fkey";
            columns: ["paper_id"];
            referencedRelation: "papers";
            referencedColumns: ["id"];
          }
        ];
      };

      math_blocks: {
        Row: {
          id: string;
          section_id: string;
          order_idx: number;
          env_type: string;
          latex_expr: string;
          context_before: string | null;
          context_after: string | null;
          explanation: string | null;
          explanation_model: string | null;
          created_at: string;
        };
        Insert: {
          id?: string;
          section_id: string;
          order_idx: number;
          env_type: string;
          latex_expr: string;
          context_before?: string | null;
          context_after?: string | null;
          explanation?: string | null;
          explanation_model?: string | null;
          created_at?: string;
        };
        Update: {
          id?: string;
          section_id?: string;
          order_idx?: number;
          env_type?: string;
          latex_expr?: string;
          context_before?: string | null;
          context_after?: string | null;
          explanation?: string | null;
          explanation_model?: string | null;
          created_at?: string;
        };
        Relationships: [
          {
            foreignKeyName: "math_blocks_section_id_fkey";
            columns: ["section_id"];
            referencedRelation: "sections";
            referencedColumns: ["id"];
          }
        ];
      };
    };
    Views: Record<string, never>;
    Functions: Record<string, never>;
    Enums: {
      paper_source_type: "arxiv_latex" | "pdf";
      paper_status: "pending" | "processing" | "complete" | "error";
    };
  };
};

// ── Convenience aliases ───────────────────────────────────────────────────────

export type Tables<T extends keyof Database["public"]["Tables"]> =
  Database["public"]["Tables"][T]["Row"];

export type InsertTables<T extends keyof Database["public"]["Tables"]> =
  Database["public"]["Tables"][T]["Insert"];

export type UpdateTables<T extends keyof Database["public"]["Tables"]> =
  Database["public"]["Tables"][T]["Update"];

// Typed row aliases used throughout the app
export type Paper = Tables<"papers">;
export type Section = Tables<"sections">;
export type MathBlock = Tables<"math_blocks">;

// Paper with nested sections (joined query result shape)
export type PaperWithSections = Paper & {
  sections: SectionWithMath[];
};

// Section with nested math blocks
export type SectionWithMath = Section & {
  math_blocks: MathBlock[];
};

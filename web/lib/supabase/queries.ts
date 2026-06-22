/**
 * Typed Supabase query helpers used by Server Components.
 *
 * All functions accept a Supabase client so they can be tested
 * independently of Next.js request context.
 */

import type { SupabaseClient } from "@supabase/supabase-js";
import type {
  Database,
  Paper,
  PaperCitation,
  PaperWithSections,
  SectionWithMath,
} from "./types";

type Client = SupabaseClient<Database>;

// ── Papers ────────────────────────────────────────────────────────────────────

/** Return the 20 most recently completed papers for the landing page. */
export async function getRecentPapers(client: Client): Promise<Paper[]> {
  const { data, error } = await client
    .from("papers")
    .select("*")
    .order("updated_at", { ascending: false })
    .limit(20);

  if (error) throw new Error(`getRecentPapers: ${error.message}`);
  return data ?? [];
}

/** Return a single paper by ArXiv ID. */
export async function getPaperByArxivId(
  client: Client,
  arxivId: string
): Promise<Paper | null> {
  const { data, error } = await client
    .from("papers")
    .select("*")
    .eq("arxiv_id", arxivId)
    .maybeSingle();

  if (error) throw new Error(`getPaperByArxivId: ${error.message}`);
  return data;
}

/** Return paper + all sections (with math block counts) for the paper page. */
export async function getPaperWithSections(
  client: Client,
  arxivId: string
): Promise<PaperWithSections | null> {
  const { data, error } = await client
    .from("papers")
    .select(
      `
      *,
      sections (
        *,
        math_blocks ( id )
      )
    `
    )
    .eq("arxiv_id", arxivId)
    .eq("status", "complete")
    .order("order_idx", { referencedTable: "sections" })
    .maybeSingle();

  if (error) throw new Error(`getPaperWithSections: ${error.message}`);
  return data as PaperWithSections | null;
}

/** Return a single section with all its math and algorithm blocks for the section detail page. */
export async function getSectionWithMath(
  client: Client,
  sectionId: string
): Promise<SectionWithMath | null> {
  const { data, error } = await client
    .from("sections")
    .select(
      `
      *,
      math_blocks (*),
      algorithm_blocks (*)
    `
    )
    .eq("id", sectionId)
    .order("order_idx", { referencedTable: "math_blocks" })
    .order("order_idx", { referencedTable: "algorithm_blocks" })
    .maybeSingle();

  if (error) throw new Error(`getSectionWithMath: ${error.message}`);
  return data as SectionWithMath | null;
}

/** Search papers by title (case-insensitive prefix match). */
export async function searchPapers(
  client: Client,
  query: string
): Promise<Paper[]> {
  const { data, error } = await client
    .from("papers")
    .select("*")
    .or(`title.ilike.%${query}%,arxiv_id.ilike.%${query}%`)
    .order("updated_at", { ascending: false })
    .limit(20);

  if (error) throw new Error(`searchPapers: ${error.message}`);
  return data ?? [];
}

/** Return all complete paper ArXiv IDs for static generation. */
export async function getAllCompletePaperIds(
  client: Client
): Promise<string[]> {
  const { data, error } = await client
    .from("papers")
    .select("*")
    .eq("status", "complete")
    .not("arxiv_id", "is", null);

  if (error) throw new Error(`getAllCompletePaperIds: ${error.message}`);
  return (data ?? []).map((r) => r.arxiv_id!);
}

/** Return all citations for a paper, ordered by bibliography position. */
export async function getCitationsForPaper(
  client: Client,
  paperId: string
): Promise<PaperCitation[]> {
  const { data, error } = await client
    .from("paper_citations")
    .select("*")
    .eq("paper_id", paperId)
    .order("order_idx", { ascending: true });

  if (error) throw new Error(`getCitationsForPaper: ${error.message}`);
  return data ?? [];
}

/** Queue a new paper for processing (INSERT with status=pending). */
export async function queuePaper(
  client: Client,
  arxivId: string,
  title?: string
): Promise<{ queued: boolean; existing: boolean }> {
  // Check if already exists
  const existing = await getPaperByArxivId(client, arxivId);
  if (existing) {
    return { queued: false, existing: true };
  }

  const { error } = await client.from("papers").insert({
    arxiv_id: arxivId,
    title: title ?? arxivId,   // use real title when known, else placeholder
    source_type: "arxiv_latex",
    status: "pending",
  });

  if (error) throw new Error(`queuePaper: ${error.message}`);
  return { queued: true, existing: false };
}

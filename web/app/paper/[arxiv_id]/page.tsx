import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { createClient, createStaticClient } from "@/lib/supabase/server";
import {
  getPaperMeta,
  getSectionsPaged,
  getAllCompletePaperIds,
  getCitationsForPaper,
} from "@/lib/supabase/queries";
import { PaperSplitView } from "@/components/PaperSplitView";
import type { PaperWithSections } from "@/lib/supabase/types";

export const revalidate = 3600;

interface PageProps {
  params: Promise<{ arxiv_id: string }>;
}

export async function generateStaticParams(): Promise<{ arxiv_id: string }[]> {
  // Build-time: no request scope — use cookie-free static client
  const client = createStaticClient();
  const ids = await getAllCompletePaperIds(client);
  return ids.map((id) => ({ arxiv_id: id }));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { arxiv_id } = await params;
  const client = await createClient();
  const paper = await getPaperMeta(client, arxiv_id);
  return { title: paper?.title ?? arxiv_id };
}

export default async function PaperPage({ params }: PageProps) {
  const { arxiv_id } = await params;
  const client = await createClient();

  const paper = await getPaperMeta(client, arxiv_id);
  if (!paper) notFound();

  const [{ sections, total: totalSections }, citations] = await Promise.all([
    getSectionsPaged(client, paper.id, 1),
    getCitationsForPaper(client, paper.id),
  ]);

  const paperWithSections: PaperWithSections = { ...paper, sections };

  return (
    <PaperSplitView
      paper={paperWithSections}
      arxivId={arxiv_id}
      citations={citations}
      totalSections={totalSections}
    />
  );
}

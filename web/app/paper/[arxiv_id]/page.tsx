import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { createClient, createStaticClient } from "@/lib/supabase/server";
import {
  getPaperWithSections,
  getAllCompletePaperIds,
} from "@/lib/supabase/queries";
import { PaperSplitView } from "@/components/PaperSplitView";

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
  const paper = await getPaperWithSections(client, arxiv_id);
  return { title: paper?.title ?? arxiv_id };
}

export default async function PaperPage({ params }: PageProps) {
  const { arxiv_id } = await params;
  const client = await createClient();
  const paper = await getPaperWithSections(client, arxiv_id);

  if (!paper) notFound();

  return <PaperSplitView paper={paper} arxivId={arxiv_id} />;
}

import type { Metadata } from "next";
import { Suspense } from "react";
import { createClient } from "@/lib/supabase/server";
import { getRecentPapers, searchPapers } from "@/lib/supabase/queries";
import { SearchBar } from "@/components/SearchBar";
import { QueueForm } from "@/components/QueueForm";
import { PapersList } from "@/components/PapersList";

export const metadata: Metadata = { title: "paper2md" };
export const revalidate = 3600;

const PAGE_SIZE = 20;

interface PageProps {
  searchParams: Promise<{ q?: string; page?: string }>;
}

export default async function LandingPage({ searchParams }: PageProps) {
  const { q, page: pageParam } = await searchParams;
  const page = Math.max(1, parseInt(pageParam ?? "1", 10) || 1);
  const client = await createClient();

  let papers: import("@/lib/supabase/types").Paper[] = [];
  let total = 0;

  if (q) {
    papers = await searchPapers(client, q);
    total = papers.length;
  } else {
    const result = await getRecentPapers(client, page);
    papers = result.papers;
    total = result.total;
  }

  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <div className="h-full overflow-y-auto">
    <div className="max-w-5xl mx-auto px-6 py-10 space-y-12">
      {/* Hero */}
      <div className="text-center space-y-4 py-8">
        <h1 className="text-4xl font-bold tracking-tight text-zinc-900">
          Understand the math in<br className="hidden sm:block" /> ArXiv papers
        </h1>
        <p className="text-zinc-500 text-lg max-w-xl mx-auto">
          Every equation explained — what it computes, what the symbols mean,
          and why it matters.
        </p>
        <div className="max-w-xl mx-auto pt-2">
          <Suspense>
            <SearchBar />
          </Suspense>
        </div>
      </div>

      {/* Queue */}
      <div className="max-w-xl mx-auto">
        <QueueForm />
      </div>

      {/* Papers list with inline filter */}
      <PapersList
        papers={papers}
        total={total}
        isSearch={!!q}
        searchQuery={q}
      />

      {/* Pagination — only shown for non-search listing */}
      {!q && totalPages > 1 && (
        <div className="flex items-center justify-center gap-3 mt-6">
          {page > 1 ? (
            <a
              href={`/?page=${page - 1}`}
              className="px-4 py-2 text-sm font-medium rounded-lg border border-zinc-200 bg-white text-zinc-700 hover:bg-zinc-50 transition-colors"
            >
              ← Previous
            </a>
          ) : (
            <span className="px-4 py-2 text-sm font-medium rounded-lg border border-zinc-100 bg-zinc-50 text-zinc-300 cursor-not-allowed">
              ← Previous
            </span>
          )}

          <span className="text-sm text-zinc-500">
            Page {page} of {totalPages}
          </span>

          {page < totalPages ? (
            <a
              href={`/?page=${page + 1}`}
              className="px-4 py-2 text-sm font-medium rounded-lg border border-zinc-200 bg-white text-zinc-700 hover:bg-zinc-50 transition-colors"
            >
              Next →
            </a>
          ) : (
            <span className="px-4 py-2 text-sm font-medium rounded-lg border border-zinc-100 bg-zinc-50 text-zinc-300 cursor-not-allowed">
              Next →
            </span>
          )}
        </div>
      )}
    </div>
    </div>
  );
}

